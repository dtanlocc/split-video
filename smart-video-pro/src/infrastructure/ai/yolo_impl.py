"""
yolo_impl.py – The Ultimate Professional AI Cameraman
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from __future__ import annotations
import gc
import math
import subprocess
import threading
import queue
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
import torch
from tqdm import tqdm
from ultralytics import YOLO

from src.domain.schemas import CropConfig
from src.domain.interfaces import IYOLOCropper

_STOP = object()

# ─────────────────────────────────────────────────────────────────────────────
# 1. Kalman 2-D (Bộ ổn định hình ảnh chuyên nghiệp)
# ─────────────────────────────────────────────────────────────────────────────

class Kalman2D:
    __slots__ = ("initialized","x","P","F","H","Q","R","_I4")
    def __init__(self, q: float = 0.005, r: float = 7.0): # R cao giúp camera lướt đi mượt hơn
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

# ─────────────────────────────────────────────────────────────────────────────
# 2. UI & Graphics Helpers (Title & Dominant Color)
# ─────────────────────────────────────────────────────────────────────────────

def _make_vignette_lut(title_h, width):
    xs = np.arange(width, dtype=np.float32)
    edge = np.clip(np.minimum(xs, width - xs) / (width * 0.15), 0.6, 1.0)
    return np.tile(edge[np.newaxis, :, np.newaxis], (title_h, 1, 1))

def _build_title_area(title_h, width, dom_bgr, vignette, video_strip=None, bleed=32):
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

def _dominant_color(frame):
    small = cv2.resize(frame, (32, 18), interpolation=cv2.INTER_NEAREST)
    data = small.reshape(-1, 3).astype(np.float32)
    _, labels, centers = cv2.kmeans(data, 2, None, (cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER, 5, 1.0), 1, cv2.KMEANS_PP_CENTERS)
    return centers[np.argmax(np.bincount(labels.flatten()))].astype(np.uint8)

# ─────────────────────────────────────────────────────────────────────────────
# 3. YOLO Implementation (The Brain)
# ─────────────────────────────────────────────────────────────────────────────

class YOLOImpl(IYOLOCropper):
    OUT_W, OUT_H = 1080, 1920
    TITLE_RATIO, FACE_POS = 0.19, 0.40  # 40% headroom chuẩn
    YOLO_H = 384
    HOLD_FRAMES = 45   # 1.5s Hold máy
    DRIFT_SPEED = 0.02 # Tốc độ lia máy mượt (0.01 - 0.05)

    def __init__(self, model_path="yolov8n.pt"):
        self.model_path = model_path
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.half = (self.device == "cuda")
        self.model = None
        self.batch_size = 8 if self.device == "cuda" else 1

    def _load_model(self):
        if not self.model: self.model = YOLO(self.model_path)

    def process_video(self, video_path: Path, output_dir: Path, config: CropConfig = None):
        self._load_model()
        cap = cv2.VideoCapture(str(video_path))
        fps, total = cap.get(cv2.CAP_PROP_FPS) or 30.0, int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        orig_w, orig_h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # Bố cục Camera (No Zoom Policy)
        title_h = int(self.OUT_H * self.TITLE_RATIO)
        content_h = self.OUT_H - title_h
        content_w = int(orig_h * (self.OUT_W / content_h))
        yolo_w = int(orig_w * (self.YOLO_H / orig_h))
        scale_x, vignette = orig_w / yolo_w, _make_vignette_lut(title_h, self.OUT_W)

        # Queues & Threads
        raw_q, yolo_q, result_q, write_q = [queue.Queue(maxsize=m) for m in [128, 32, 64, 16]]

        def _reader():
            fid = 0
            while True:
                ret, frame = cap.read()
                if not ret: raw_q.put(_STOP); break
                raw_q.put((fid, frame)); fid += 1

        def _resizer():
            while True:
                item = raw_q.get()
                if item is _STOP: yolo_q.put(_STOP); break
                fid, frame = item
                small = cv2.resize(frame, (yolo_w, self.YOLO_H), interpolation=cv2.INTER_NEAREST)
                yolo_q.put((fid, frame, small))

        def _inference():
            target_bbox, pending = None, []
            
            def _run_batch(batch):
                nonlocal target_bbox
                imgs = [x[2] for x in batch]
                preds = self.model.predict(imgs, device=self.device, verbose=False, half=self.half, classes=[0])
                for i, (fid, frame, _) in enumerate(batch):
                    found = False
                    boxes = preds[i].boxes.xyxy.cpu().numpy() if preds[i].boxes else []
                    if len(boxes) > 0:
                        # Activity Score: Ưu tiên người to và cao (đang đứng/nói)
                        centers = [((b[0]+b[2])/2 * scale_x, (b[1]+b[3])/2) for b in boxes]
                        scores = [(b[3]-b[1]) * 1.5 + (b[2]-b[0]) for b in boxes]
                        
                        if target_bbox is None: target_bbox = centers[np.argmax(scores)]
                        else:
                            # Cân bằng giữa người cũ và người mới hoạt động mạnh
                            idx = np.argmin([math.hypot(c[0]-target_bbox[0], c[1]-target_bbox[1]) for c in centers])
                            target_bbox = centers[idx]
                        found = True
                    result_q.put((fid, frame, target_bbox, found))

            while True:
                item = yolo_q.get()
                if item is _STOP:
                    if pending: _run_batch(pending)
                    result_q.put(_STOP); break
                pending.append(item)
                if len(pending) >= self.batch_size: _run_batch(pending); pending = []

        def _composer():
            kalman = Kalman2D()
            lx, ly, lost_cnt = orig_w/2, orig_h/2, 0
            dom, out_buf = np.array([30,30,30], np.uint8), np.empty((self.OUT_H, self.OUT_W, 3), np.uint8)
            cached_title, last_key = None, None
            
            while True:
                item = result_q.get()
                if item is _STOP: write_q.put(_STOP); break
                fid, frame, bbox, found = item

                # Virtual Cameraman Brain (Hold & Drift)
                if found:
                    tx, ty, lost_cnt = bbox[0], bbox[1], 0
                    lx, ly = tx, ty
                else:
                    lost_cnt += 1
                    if lost_cnt < self.HOLD_FRAMES: tx, ty = lx, ly
                    else: # Drift về giữa chuyên nghiệp
                        tx = lx * (1-self.DRIFT_SPEED) + (orig_w/2) * self.DRIFT_SPEED
                        ty = ly * (1-self.DRIFT_SPEED) + (orig_h/2) * self.DRIFT_SPEED
                        lx, ly = tx, ty
                
                sx, sy = kalman.update(tx, ty)
                cx = int(np.clip(sx - content_w/2, 0, orig_w - content_w))
                cy = int(np.clip(sy - content_h*self.FACE_POS, 0, orig_h - content_h))
                
                # Render
                crop = np.ascontiguousarray(frame[cy:cy+content_h, cx:cx+content_w])
                v_crop = cv2.resize(crop, (self.OUT_W, content_h), interpolation=cv2.INTER_LINEAR)
                
                if fid % int(fps*3) == 0: dom = _dominant_color(frame)
                if cached_title is None or tuple(dom) != last_key:
                    cached_title = _build_title_area(title_h, self.OUT_W, dom, vignette, v_crop[:4])
                    last_key = tuple(dom)

                out_buf[:title_h], out_buf[title_h:] = cached_title, v_crop
                write_q.put(out_buf.tobytes())

        # Start Pipeline
        threads = [threading.Thread(target=f, daemon=True) for f in [_reader, _resizer, _inference, _composer]]
        for t in threads: t.start()

        # FFmpeg
        out_path = output_dir / f"{video_path.stem}_916.mp4"
        cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-vcodec", "rawvideo", "-s", "1080x1920", "-pix_fmt", "bgr24", 
               "-r", str(fps), "-i", "-", "-i", str(video_path), "-map", "0:v:0", "-map", "1:a:0?", 
               "-c:v", "h264_nvenc", "-preset", "p2", "-rc", "vbr", "-cq", "24", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out_path)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        
        for _ in tqdm(range(total), desc=f"🎬 {video_path.name}"):
            data = write_q.get()
            if data is _STOP: break
            proc.stdin.write(data)

        proc.stdin.close(); proc.wait(); cap.release()
        self.release_resources()

    def release_resources(self):
        if self.model: del self.model; self.model = None
        torch.cuda.empty_cache(); gc.collect()

    @staticmethod
    def horizontal_flip(frame): return np.fliplr(frame)