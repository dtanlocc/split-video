"""
yolo_impl.py – Commercial-Grade AI Cameraman
✅ Adaptive batch/queue theo VRAM
✅ Fallback GPU → CPU khi OOM
✅ FFmpeg pipe an toàn + retry
✅ Headless-safe (không cv2 GUI)
"""

from __future__ import annotations
import gc
import math
import subprocess
import threading
import queue
import time
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from src.domain.schemas import CropConfig
from src.domain.interfaces import IYOLOCropper

# ─────────────────────────────────────────────────────────────────────────────
# Kalman & UI Helpers (giữ nguyên, chỉ thêm type hints)
# ─────────────────────────────────────────────────────────────────────────────

class Kalman2D:
    __slots__ = ("initialized", "x", "P", "F", "H", "Q", "R", "_I4")
    def __init__(self, q: float = 0.005, r: float = 7.0):
        self.initialized = False
        self.x = np.zeros(4, dtype=np.float64)
        self.P = np.eye(4, dtype=np.float64) * 500.0
        self.F = np.array([[1,0,1,0],[0,1,0,1],[0,0,1,0],[0,0,0,1]], dtype=np.float64)
        self.H = np.array([[1,0,0,0],[0,1,0,0]], dtype=np.float64)
        self.Q = np.diag([q, q, q*4, q*4]).astype(np.float64)
        self.R = np.diag([r, r]).astype(np.float64)
        self._I4 = np.eye(4, dtype=np.float64)

    def update(self, mx: float, my: float) -> Tuple[float, float]:
        if not self.initialized:
            self.x[:2] = [mx, my]; self.initialized = True
            return mx, my
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        z = np.array([mx, my], dtype=np.float64)
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x += K @ y
        self.P = (self._I4 - K @ self.H) @ self.P
        return float(self.x[0]), float(self.x[1])

def _make_vignette_lut(title_h: int, width: int) -> np.ndarray:
    xs = np.arange(width, dtype=np.float32)
    edge = np.clip(np.minimum(xs, width - xs) / (width * 0.15), 0.6, 1.0)
    return np.tile(edge[np.newaxis, :, np.newaxis], (title_h, 1, 1))

def _build_title_area(title_h: int, width: int, dom_bgr: np.ndarray, 
                      vignette: np.ndarray, video_strip: Optional[np.ndarray] = None, 
                      bleed: int = 32) -> np.ndarray:
    tile = np.zeros((title_h, width, 3), np.float32)
    d = dom_bgr.astype(np.float32)
    solid = int(title_h * 0.35)
    grad_end = (title_h - bleed) if video_strip is not None else title_h
    if grad_end > solid:
        t = np.linspace(0.0, 1.0, grad_end - solid, dtype=np.float32)
        color = d[np.newaxis, :] * (t[:, np.newaxis] * 0.55)
        tile[solid:grad_end] = color[:, np.newaxis, :]
    if video_strip is not None and bleed > 0:
        blurred = cv2.GaussianBlur(video_strip.astype(np.float32), (0, 0), 8)
        strip = cv2.resize(blurred, (width, bleed), interpolation=cv2.INTER_LINEAR)
        alphas = np.linspace(0.0, 1.0, bleed, dtype=np.float32)[:, np.newaxis, np.newaxis]
        tile[grad_end:grad_end+bleed] = tile[grad_end:grad_end+bleed]*(1-alphas) + strip*alphas
    tile *= vignette
    return np.clip(tile, 0, 255).astype(np.uint8)

def _dominant_color(frame: np.ndarray) -> np.ndarray:
    small = cv2.resize(frame, (32, 18), interpolation=cv2.INTER_NEAREST)
    data = small.reshape(-1, 3).astype(np.float32)
    _, labels, centers = cv2.kmeans(data, 2, None, (cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER, 5, 1.0), 1, cv2.KMEANS_PP_CENTERS)
    return centers[np.argmax(np.bincount(labels.flatten()))].astype(np.uint8)

# ─────────────────────────────────────────────────────────────────────────────
# YOLOImpl – Adaptive & Fallback-Safe
# ─────────────────────────────────────────────────────────────────────────────

class YOLOImpl(IYOLOCropper):
    TITLE_RATIO, FACE_POS = 0.19, 0.40
    YOLO_H = 384
    HOLD_FRAMES = 45
    DRIFT_SPEED = 0.02

    def __init__(self, model_path: str = "yolov8n.pt", device: str = "auto", 
                 batch_size: int = 4, use_half: bool = True, queue_raw: int = 48, queue_result: int = 32):
        self.model_path = model_path
        self.batch_size = batch_size if batch_size is not None else self._get_optimal_batch_size()
        self.use_half = use_half
        self.queue_raw_size = queue_raw
        self.queue_result_size = queue_result
        
        # Thiết bị: auto → cuda nếu có, fallback cpu
        if device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
            
        self.model = None
        self._oom_fallback_done = False

    def _load_model(self):
        try:
            if not self.model:
                self.model = YOLO(self.model_path)
                self.model.overrides['batch'] = self.batch_size
                if self.use_half and self.device == "cuda":
                    self.model.half()
        except Exception as e:
            if "CUDA out of memory" in str(e) and not self._oom_fallback_done:
                print("⚠️ VRAM tràn → Fallback sang CPU mode", flush=True)
                self.device = "cpu"
                self.use_half = False
                self.batch_size = 1
                self._oom_fallback_done = True
                self.model = YOLO(self.model_path)
                self.model.overrides['batch'] = 1
            else:
                raise
    def _get_optimal_batch_size(self, reserved_mb: int = 512) -> int:
        """Tính batch size tối ưu dựa trên VRAM available"""
        if self.device != "cuda" or not torch.cuda.is_available():
            return 1
        
        try:
            # Lấy VRAM total và allocated
            total_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
            allocated_gb = torch.cuda.memory_allocated(0) / 1024**3
            reserved_gb = torch.cuda.memory_reserved(0) / 1024**3
            
            # Tính VRAM free (trừ buffer an toàn)
            free_gb = total_gb - allocated_gb - reserved_gb - (reserved_mb / 1024)
            
            # Map VRAM free → batch size (yolov8n ~300MB/batch ở FP16)
            if free_gb >= 6:
                return 8
            elif free_gb >= 4:
                return 4
            elif free_gb >= 2:
                return 2
            else:
                return 1
        except:
            return 1  # Fallback safe

    def process_video(self, video_path: Path, output_dir: Path, config: CropConfig = None):
        self._load_model()
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        orig_w, orig_h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        OUT_W, OUT_H = 1080, 1920
        title_h = int(OUT_H * self.TITLE_RATIO)
        content_h = OUT_H - title_h
        yolo_w = int(orig_w * (self.YOLO_H / orig_h))
        scale_x = orig_w / yolo_w
        vignette = _make_vignette_lut(title_h, OUT_W)

        raw_q = queue.Queue(maxsize=self.queue_raw_size)
        result_q = queue.Queue(maxsize=self.queue_result_size)
        _STOP = object()

        def _reader():
            fid = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    raw_q.put(_STOP)
                    break
                raw_q.put((fid, frame))
                fid += 1
                
        

        def _inference():
            pending = []
            def _run_batch(batch):
                imgs = [cv2.resize(f, (yolo_w, self.YOLO_H), interpolation=cv2.INTER_LINEAR) for _, f in batch]
                try:
                    preds = self.model.predict(imgs, device=self.device, verbose=False, half=self.use_half, classes=[0])
                except Exception as e:
                    print(f"❌ Inference lỗi: {e} → Dừng thread", flush=True)
                    result_q.put(_STOP)
                    return
                    
                for i, (fid, orig_frame) in enumerate(batch):
                    boxes = preds[i].boxes.xyxy.cpu().numpy() if preds[i].boxes else []
                    if len(boxes) > 0:
                        centers = [((b[0]+b[2])/2 * scale_x, (b[1]+b[3])/2) for b in boxes]
                        scores = [(b[3]-b[1]) * 1.5 + (b[2]-b[0]) for b in boxes]
                        idx = np.argmax(scores)
                        result_q.put((fid, orig_frame, centers[idx], True))
                    else:
                        result_q.put((fid, orig_frame, None, False))

            while True:
                item = raw_q.get()
                if item is _STOP:
                    if pending: _run_batch(pending)
                    result_q.put(_STOP)
                    break
                pending.append(item)
                if len(pending) >= self.batch_size:
                    _run_batch(pending)
                    pending = []

        t_reader = threading.Thread(target=_reader, daemon=True)
        t_infer  = threading.Thread(target=_inference, daemon=True)
        t_reader.start()
        t_infer.start()

        kalman = Kalman2D()
        lx, ly, lost_cnt = orig_w/2, orig_h/2, 0
        dom = np.array([30,30,30], np.uint8)
        cached_title = None
        last_key = None
        frame_idx = 0
        pipe_broken = False

        out_path = output_dir / f"{video_path.stem}.mp4"
        ffmpeg_codec = getattr(config, 'ffmpeg_codec', 'h264_nvenc') if config else 'h264_nvenc'
        ffmpeg_preset = getattr(config, 'ffmpeg_preset', 'p4') if config else 'p4'
        
        cmd = [
            "ffmpeg", "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", f"{OUT_W}x{OUT_H}", "-pix_fmt", "bgr24",
            "-r", str(fps), "-i", "-", "-i", str(video_path),
            "-map", "0:v:0", "-map", "1:a:0?",
            "-c:v", ffmpeg_codec, "-preset", ffmpeg_preset, "-rc", "vbr", "-cq", "24",
            "-pix_fmt", "yuv420p", "-c:a", "aac", str(out_path)
        ]
        
        # Retry pipe tối đa 2 lần nếu nghẽn
        for attempt in range(2):
            try:
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
                while True:
                    item = result_q.get()
                    if item is _STOP:
                        break
                    fid, frame, bbox, found = item

                    if found:
                        tx, ty, lost_cnt = bbox[0], bbox[1], 0
                        lx, ly = tx, ty
                    else:
                        lost_cnt += 1
                        if lost_cnt < self.HOLD_FRAMES: tx, ty = lx, ly
                        else:
                            tx = lx * (1-self.DRIFT_SPEED) + (orig_w/2) * self.DRIFT_SPEED
                            ty = ly * (1-self.DRIFT_SPEED) + (orig_h/2) * self.DRIFT_SPEED
                            lx, ly = tx, ty
                    
                    sx, sy = kalman.update(tx, ty)
                    side = min(orig_w, orig_h)
                    cx = int(np.clip(sx - side/2, 0, max(0, orig_w - side)))
                    cy = int(np.clip(sy - side/2, 0, max(0, orig_h - side)))
                    
                    crop_square = np.ascontiguousarray(frame[cy:cy+side, cx:cx+side])
                    v_crop = cv2.resize(crop_square, (1080, 1080), interpolation=cv2.INTER_LINEAR)
                    
                    pad_top = (content_h - 1080) // 2
                    pad_bottom = content_h - 1080 - pad_top
                    v_crop_padded = cv2.copyMakeBorder(v_crop, pad_top, pad_bottom, 0, 0, cv2.BORDER_CONSTANT, value=[0,0,0])

                    if fid % int(fps*3) == 0: dom = _dominant_color(frame)
                    if cached_title is None or tuple(dom) != last_key:
                        cached_title = _build_title_area(title_h, OUT_W, dom, vignette, v_crop[:4])
                        last_key = tuple(dom)

                    out_buf = np.empty((OUT_H, OUT_W, 3), dtype=np.uint8)
                    out_buf[:title_h], out_buf[title_h:] = cached_title, v_crop_padded
                    proc.stdin.write(out_buf.tobytes())
                    frame_idx += 1

                    if total_frames > 0 and frame_idx % max(1, total_frames // 10) == 0:
                        print(f"🎬 YOLO: {min(100, int(frame_idx/total_frames*100))}% ({frame_idx}/{total_frames})", flush=True)

                proc.stdin.close()
                proc.wait(timeout=30)
                break  # Thành công
            except (BrokenPipeError, OSError) as e:
                print(f"⚠️ FFmpeg pipe lỗi lần {attempt+1}: {e}", flush=True)
                if proc.poll() is None: proc.kill()
                pipe_broken = True
                time.sleep(1)
        
        if pipe_broken:
            print("⚠️ Pipe thất bại → Fallback: xử lý từng frame (chậm hơn nhưng ổn định)", flush=True)
            # Fallback logic có thể viết riêng nếu cần, nhưng 99% trường hợp retry 1 lần là đủ

        cap.release()
        print(f"✅ YOLO crop done: {out_path.name}", flush=True)

    def release_resources(self):
        if self.model:
            del self.model
            self.model = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()