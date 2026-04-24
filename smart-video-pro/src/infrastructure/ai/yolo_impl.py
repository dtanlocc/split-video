"""
yolo_impl.py – Professional AI Cameraman · TikTok 3-Zone Layout
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Giữ NGUYÊN 100% camera logic từ bản gốc:
  ✅ 4-thread pipeline: _reader → _resizer → _inference → _composer
  ✅ write_q: tách composer khỏi FFmpeg I/O (không block nhau)
  ✅ Hold & Drift: HOLD_FRAMES giữ vị trí, sau đó drift về center
  ✅ Activity Score: ưu tiên người to + cao (đứng/nói)
  ✅ target_bbox tracking: bám người cũ, không nhảy sang người khác
  ✅ Kalman2D: làm mượt cả X lẫn Y
  ✅ FACE_POS = 0.40: 40% headroom chuẩn nghề
  ✅ horizontal_flip() static method

Thay đổi DUY NHẤT so với bản gốc:
  ✅ Layout 3 vùng thay vì 2 vùng:
       CŨ: title_h (TITLE_RATIO%) | content_h (phần còn lại)  
       MỚI: TITLE_H=420px | CROP_S=1080px 1:1 | SUB_H=420px
  ✅ Hằng số tuyệt đối khớp renderer_impl.py (không dùng ratio 0.19)
  ✅ Crop 1:1 (vuông) thay vì crop 9:16 full-height
  ✅ scale_y fix (bản gốc thiếu scale Y khi map tọa độ YOLO về gốc)
  ✅ GPU opts: torch.inference_mode(), half=, OOM fallback, warm-up
  ✅ Thread join() tránh data race
  ✅ write_q dùng bytes() để tránh buffer overwrite race

Layout output 1080×1920:
┌─────────────────────────┐  0px
│   TITLE AREA            │  420px  ← gradient dominant + renderer chèn title
├─────────────────────────┤  420px
│                         │
│   1:1 VIDEO  (1080²)    │  1080px ← YOLO-tracked, Kalman-smoothed
│                         │
├─────────────────────────┤  1500px
│   SUBTEXT AREA          │  420px  ← gradient + renderer chèn ASS subtitle
└─────────────────────────┘  1920px
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

try:
    from src.domain.schemas import CropConfig
    from src.domain.interfaces import IYOLOCropper
except ImportError:
    class CropConfig:
        ffmpeg_codec  = "libx264"
        ffmpeg_preset = "fast"
        output_size   = (1080, 1920)
    class IYOLOCropper:
        pass

_STOP = object()   # Sentinel để dừng pipeline


# ─────────────────────────────────────────────────────────────────────────────
# Layout constants – PHẢI khớp chính xác với renderer_impl.py
# ─────────────────────────────────────────────────────────────────────────────
OUT_W    = 1080
OUT_H    = 1920
CROP_S   = 1080                        # Cạnh vuông video 1:1
TITLE_H  = (OUT_H - CROP_S) // 2      # = 420px
SUB_H    = OUT_H - CROP_S - TITLE_H   # = 420px
VIDEO_Y0 = TITLE_H                    # = 420px  ← top of video zone
VIDEO_Y1 = TITLE_H + CROP_S          # = 1500px ← bottom of video zone


# ─────────────────────────────────────────────────────────────────────────────
# 1. Kalman 2-D  (giữ nguyên bản gốc)
# ─────────────────────────────────────────────────────────────────────────────

class Kalman2D:
    """
    Bộ ổn định hình ảnh chuyên nghiệp.
    R cao → camera lướt mượt, không giật theo detection.
    State: [x, y, vx, vy]
    """
    __slots__ = ("initialized", "x", "P", "F", "H", "Q", "R", "_I4")

    def __init__(self, q: float = 0.005, r: float = 7.0):
        self.initialized = False
        self.x   = np.zeros(4, dtype=np.float64)
        self.P   = np.eye(4, dtype=np.float64) * 500.0
        self.F   = np.array(
            [[1, 0, 1, 0],
             [0, 1, 0, 1],
             [0, 0, 1, 0],
             [0, 0, 0, 1]], dtype=np.float64
        )
        self.H   = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=np.float64)
        self.Q   = np.diag([q, q, q * 4, q * 4]).astype(np.float64)
        self.R   = np.diag([r, r]).astype(np.float64)
        self._I4 = np.eye(4, dtype=np.float64)

    def update(self, mx: float, my: float) -> Tuple[float, float]:
        if not self.initialized:
            self.x[:2]       = [mx, my]
            self.initialized = True
            return mx, my
        # Predict
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        # Update
        z = np.array([mx, my], dtype=np.float64)
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x += K @ y
        self.P  = (self._I4 - K @ self.H) @ self.P
        return float(self.x[0]), float(self.x[1])


# ─────────────────────────────────────────────────────────────────────────────
# 2. UI & Graphics Helpers  (giữ nguyên bản gốc + thêm subtext)
# ─────────────────────────────────────────────────────────────────────────────

def _make_vignette_lut(height: int, width: int) -> np.ndarray:
    """Vignette mask: hai bên tối hơn, giữa sáng."""
    xs   = np.arange(width, dtype=np.float32)
    edge = np.clip(np.minimum(xs, width - xs) / (width * 0.15), 0.6, 1.0)
    return np.tile(edge[np.newaxis, :, np.newaxis], (height, 1, 1))


def _build_title_area(
    title_h: int,
    width: int,
    dom_bgr: np.ndarray,
    vignette: np.ndarray,
    video_strip: Optional[np.ndarray] = None,
    bleed: int = 32,
) -> np.ndarray:
    """
    Gradient title area (giữ nguyên logic bản gốc).
    video_strip: hàng đầu của crop làm bleed source.
    """
    tile = np.zeros((title_h, width, 3), np.float32)
    d    = dom_bgr.astype(np.float32)

    solid    = int(title_h * 0.35)
    grad_end = (title_h - bleed) if video_strip is not None else title_h

    if grad_end > solid:
        t     = np.linspace(0.0, 1.0, grad_end - solid, dtype=np.float32)
        color = d[np.newaxis, :] * (t[:, np.newaxis] * 0.55)
        tile[solid:grad_end] = color[:, np.newaxis, :]

    if video_strip is not None and bleed > 0:
        blurred = cv2.GaussianBlur(video_strip.astype(np.float32), (0, 0), 8)
        strip   = cv2.resize(blurred, (width, bleed), interpolation=cv2.INTER_LINEAR)
        alphas  = np.linspace(0.0, 1.0, bleed, dtype=np.float32)[:, np.newaxis, np.newaxis]
        tile[grad_end:grad_end + bleed] = (
            tile[grad_end:grad_end + bleed] * (1 - alphas) + strip * alphas
        )

    tile *= vignette
    return np.clip(tile, 0, 255).astype(np.uint8)


def _build_subtext_area(
    sub_h: int,
    width: int,
    dom_bgr: np.ndarray,
    vignette: np.ndarray,
    video_strip: Optional[np.ndarray] = None,
    bleed: int = 32,
) -> np.ndarray:
    """
    Gradient subtext area: đen ở trên → dominant ở dưới.
    Đối xứng với title area.
    video_strip: hàng cuối của crop làm bleed source.
    """
    tile = np.zeros((sub_h, width, 3), np.float32)
    d    = dom_bgr.astype(np.float32)

    solid      = int(sub_h * 0.65)
    grad_start = bleed if video_strip is not None else 0

    if solid > grad_start:
        t     = np.linspace(0.0, 1.0, solid - grad_start, dtype=np.float32)
        color = d[np.newaxis, :] * (t[:, np.newaxis] * 0.50)
        tile[grad_start:solid] = color[:, np.newaxis, :]

    if solid < sub_h:
        tile[solid:] = (d * 0.50)[np.newaxis, :]

    # Bleed từ đáy video xuống subtext
    if video_strip is not None and bleed > 0:
        blurred = cv2.GaussianBlur(video_strip.astype(np.float32), (0, 0), 8)
        strip   = cv2.resize(blurred, (width, bleed), interpolation=cv2.INTER_LINEAR)
        alphas  = np.linspace(1.0, 0.0, bleed, dtype=np.float32)[:, np.newaxis, np.newaxis]
        tile[:bleed] = strip * alphas + tile[:bleed] * (1 - alphas)

    tile *= vignette
    return np.clip(tile, 0, 255).astype(np.uint8)


def _dominant_color(frame: np.ndarray) -> np.ndarray:
    """KMeans k=2 trên thumbnail 32×18 → màu chủ đạo BGR."""
    small = cv2.resize(frame, (32, 18), interpolation=cv2.INTER_NEAREST)
    data  = small.reshape(-1, 3).astype(np.float32)
    _, labels, centers = cv2.kmeans(
        data, 2, None,
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 5, 1.0),
        1, cv2.KMEANS_PP_CENTERS,
    )
    return centers[np.argmax(np.bincount(labels.flatten()))].astype(np.uint8)


# ─────────────────────────────────────────────────────────────────────────────
# 3. YOLOImpl
# ─────────────────────────────────────────────────────────────────────────────

class YOLOImpl(IYOLOCropper):
    """
    Professional AI Cameraman – 4-thread pipeline:
      Thread-1 _reader   : đọc frame thô từ video
      Thread-2 _resizer  : resize → input YOLO (INTER_NEAREST, nhanh)
      Thread-3 _inference: batch YOLO detect → tọa độ mục tiêu
      Thread-4 _composer : Kalman + crop 1:1 + compose 3-zone frame
      Main thread        : write_q → FFmpeg stdin
    """

    # Camera params (giữ nguyên bản gốc)
    YOLO_H      = 384    # Input height YOLO
    FACE_POS    = 0.40   # 40% headroom chuẩn nghề
    HOLD_FRAMES = 45     # 1.5s hold máy khi mất track
    DRIFT_SPEED = 0.02   # Tốc độ lia máy về center

    def __init__(
        self,
        model_path:   str  = "yolov8n.pt",
        device:       str  = "auto",
        batch_size:   int  = None,
        use_half:     bool = True,
        queue_raw:    int  = 128,
        queue_result: int  = 64,
    ):
        # Device TRƯỚC (các method khác phụ thuộc)
        if device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        self.model_path         = model_path
        self.use_half           = use_half and (self.device == "cuda")
        self.queue_raw_size     = queue_raw
        self.queue_result_size  = queue_result
        self.model              = None
        self._oom_fallback_done = False

        # batch_size SAU khi device đã set
        self.batch_size = batch_size if batch_size is not None else self._get_optimal_batch_size()

        if self.device == "cuda" and torch.cuda.is_available():
            major, _ = torch.cuda.get_device_capability(0)
            self.use_half = self.use_half and (major >= 7)
            props = torch.cuda.get_device_properties(0)
            vram  = props.total_memory / 1024 ** 3
            print(f"🎮 GPU: {props.name} | VRAM: {vram:.1f}GB", flush=True)
            print(
                f"⚙️  batch={self.batch_size} | fp16={self.use_half} | "
                f"queue_raw={self.queue_raw_size}",
                flush=True,
            )
        else:
            print(f"⚙️  CPU mode | batch={self.batch_size}", flush=True)

        print(
            f"📐 Layout: {TITLE_H}px title | {CROP_S}px 1:1 video | {SUB_H}px subtext",
            flush=True,
        )

    # ──────────────────────────────────────────────────────────────────────────

    def _get_optimal_batch_size(self, reserved_mb: int = 512) -> int:
        if self.device != "cuda" or not torch.cuda.is_available():
            return 1
        try:
            total   = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
            alloc   = torch.cuda.memory_allocated(0) / 1024 ** 3
            reserve = torch.cuda.memory_reserved(0)  / 1024 ** 3
            free    = total - alloc - reserve - (reserved_mb / 1024)
            factor  = 0.3 if self.use_half else 0.6
            return max(1, int(free / factor))
        except Exception:
            return 1
        
    def _get_available_encoder(self):
        for enc in ["h264_nvenc", "h264_amf", "h264_qsv", "libx264"]:
            try:
                subprocess.run(
                    ["ffmpeg", "-encoders"], 
                    capture_output=True, text=True, check=True
                )
                if enc in subprocess.run(["ffmpeg", "-encoders"], 
                                    capture_output=True, text=True).stdout:
                    return enc
            except: continue
        return "libx264"  # Fallback cuối

    def _load_model(self):
        if self.model:
            return
        try:
            print(f"📦 Loading YOLO: {self.model_path} → {self.device}", flush=True)
            self.model = YOLO(self.model_path)
            self.model.overrides["batch"] = self.batch_size

            if self.device == "cuda":
                dummy = [np.zeros((self.YOLO_H, 640, 3), dtype=np.uint8)]
                with torch.inference_mode():
                    self.model.predict(
                        dummy, verbose=False,
                        device=self.device, half=self.use_half,
                    )
                torch.cuda.synchronize()
                print(f"🔥 GPU warm-up done (fp16={self.use_half})", flush=True)

        except Exception as e:
            if "CUDA out of memory" in str(e) and not self._oom_fallback_done:
                print("⚠️ VRAM OOM → Fallback CPU", flush=True)
                self.device             = "cpu"
                self.use_half           = False
                self.batch_size         = 1
                self._oom_fallback_done = True
                self.model              = YOLO(self.model_path)
                self.model.overrides["batch"] = 1
            else:
                raise

    # ──────────────────────────────────────────────────────────────────────────
    # process_video
    # ──────────────────────────────────────────────────────────────────────────

    def process_video(self, video_path: Path, output_dir: Path, config: CropConfig = None):
        self._load_model()

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {video_path}")

        fps          = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        orig_w       = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_h       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Kích thước crop 1:1 trên frame gốc
        crop_s_src  = min(orig_w, orig_h)

        # YOLO scale factors
        yolo_w  = int(orig_w * (self.YOLO_H / orig_h))
        scale_x = orig_w / yolo_w
        scale_y = orig_h / self.YOLO_H   # ← fix: bản gốc thiếu scale_y

        # Vignette LUT (pre-compute 1 lần)
        vignette_title = _make_vignette_lut(TITLE_H, OUT_W)
        vignette_sub   = _make_vignette_lut(SUB_H,   OUT_W)

        # ── 4 queues (giữ nguyên kiến trúc bản gốc)
        stop_event = threading.Event()
        raw_q    = queue.Queue(maxsize=self.queue_raw_size)
        yolo_q   = queue.Queue(maxsize=32)
        result_q = queue.Queue(maxsize=self.queue_result_size)
        write_q  = queue.Queue(maxsize=16)

        # ── Thread 1: Reader ──────────────────────────────────────────────────
        def _reader():
            fid = 0
            while not stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    break
                raw_q.put((fid, frame))
                fid += 1
            raw_q.put(_STOP)

        # ── Thread 2: Resizer (giữ nguyên bản gốc) ───────────────────────────
        def _resizer():
            while True:
                item = raw_q.get()
                if item is _STOP:
                    yolo_q.put(_STOP)
                    break
                fid, frame = item
                small = cv2.resize(
                    frame, (yolo_w, self.YOLO_H),
                    interpolation=cv2.INTER_NEAREST,   # Nhanh hơn LINEAR cho resize nhỏ
                )
                yolo_q.put((fid, frame, small))

        # ── Thread 3: Inference (giữ nguyên camera logic bản gốc) ────────────
        def _inference():
            target_bbox = None   # Bám người cũ, không nhảy lung tung
            pending     = []

            def _run_batch(batch):
                nonlocal target_bbox
                imgs = [x[2] for x in batch]

                try:
                    with torch.inference_mode():
                        preds = self.model.predict(
                            imgs,
                            device  = self.device,
                            verbose = False,
                            half    = self.use_half,
                            classes = [0],           # person only
                            imgsz   = self.YOLO_H,
                        )
                except Exception as e:
                    print(f"❌ Inference lỗi: {e}", flush=True)
                    result_q.put(_STOP)
                    stop_event.set()
                    return

                for i, (fid, frame, _) in enumerate(batch):
                    boxes     = preds[i].boxes
                    raw_boxes = (
                        boxes.xyxy.cpu().numpy()
                        if (boxes is not None and len(boxes) > 0)
                        else []
                    )

                    if len(raw_boxes) > 0:
                        # Scale tọa độ về frame gốc (cả X lẫn Y)
                        centers = [
                            (
                                (b[0] + b[2]) / 2 * scale_x,
                                (b[1] + b[3]) / 2 * scale_y,
                            )
                            for b in raw_boxes
                        ]
                        # Activity Score: ưu tiên người to + cao (đứng/nói)
                        scores = [
                            (b[3] - b[1]) * scale_y * 1.5 + (b[2] - b[0]) * scale_x
                            for b in raw_boxes
                        ]

                        if target_bbox is None:
                            # Khởi tạo: chọn người có score cao nhất
                            target_bbox = centers[int(np.argmax(scores))]
                        else:
                            # Bám người GẦN target nhất (không nhảy sang người khác)
                            idx = int(np.argmin([
                                math.hypot(c[0] - target_bbox[0], c[1] - target_bbox[1])
                                for c in centers
                            ]))
                            target_bbox = centers[idx]

                        result_q.put((fid, frame, target_bbox, True))
                    else:
                        result_q.put((fid, frame, target_bbox, False))

            while True:
                item = yolo_q.get()
                if item is _STOP:
                    if pending:
                        _run_batch(pending)
                    result_q.put(_STOP)
                    break
                pending.append(item)
                if len(pending) >= self.batch_size:
                    _run_batch(pending)
                    pending = []

        # ── Thread 4: Composer (Hold+Drift logic + 3-zone layout) ────────────
        def _composer():
            kalman           = Kalman2D()
            lx               = float(orig_w / 2)
            ly               = float(orig_h / 2)
            lost_cnt         = 0
            dom              = np.array([30, 30, 30], np.uint8)
            out_buf          = np.empty((OUT_H, OUT_W, 3), np.uint8)
            cached_title     = None
            cached_sub       = None
            last_dom_key     = None

            while True:
                item = result_q.get()
                if item is _STOP:
                    write_q.put(_STOP)
                    break

                fid, frame, bbox, found = item

                # ── Hold & Drift (giữ nguyên bản gốc)
                if found:
                    tx, ty   = bbox[0], bbox[1]
                    lx, ly   = tx, ty
                    lost_cnt = 0
                else:
                    lost_cnt += 1
                    if lost_cnt < self.HOLD_FRAMES:
                        tx, ty = lx, ly   # Hold vị trí cũ
                    else:
                        # Drift chuyên nghiệp về center
                        tx = lx * (1 - self.DRIFT_SPEED) + (orig_w / 2) * self.DRIFT_SPEED
                        ty = ly * (1 - self.DRIFT_SPEED) + (orig_h / 2) * self.DRIFT_SPEED
                        lx, ly = tx, ty

                # Kalman smooth cả 2 trục (giữ nguyên bản gốc)
                sx, sy = kalman.update(tx, ty)

                # ── Crop 1:1: cx theo Kalman X, cy đặt mặt ở FACE_POS
                cx_ideal = int(sx - crop_s_src / 2)
                cx = int(np.clip(cx_ideal, 0, max(0, orig_w - crop_s_src)))

                cy_ideal = int(sy - crop_s_src * self.FACE_POS)
                cy = int(np.clip(cy_ideal, 0, max(0, orig_h - crop_s_src)))

                # Crop và scale lên CROP_S × CROP_S
                crop_sq = np.ascontiguousarray(frame[cy: cy + crop_s_src, cx: cx + crop_s_src])
                if crop_sq.shape[0] != CROP_S or crop_sq.shape[1] != CROP_S:
                    crop_sq = cv2.resize(crop_sq, (CROP_S, CROP_S), interpolation=cv2.INTER_LINEAR)

                # ── Dominant color mỗi 3 giây
                if fid % max(1, int(fps * 3)) == 0:
                    dom = _dominant_color(frame)

                dom_key = (int(dom[0]), int(dom[1]), int(dom[2]))
                if dom_key != last_dom_key:
                    # Dùng 64px đầu/cuối của crop làm bleed source
                    bleed_top = crop_sq[:64]  if crop_sq.shape[0] >= 64 else crop_sq[:1]
                    bleed_bot = crop_sq[-64:] if crop_sq.shape[0] >= 64 else crop_sq[-1:]
                    cached_title = _build_title_area(
                        TITLE_H, OUT_W, dom, vignette_title, bleed_top, bleed=32
                    )
                    cached_sub = _build_subtext_area(
                        SUB_H, OUT_W, dom, vignette_sub, bleed_bot, bleed=32
                    )
                    last_dom_key = dom_key

                # ── Compose 3-zone frame
                out_buf[:VIDEO_Y0]         = cached_title   # 0–420px
                out_buf[VIDEO_Y0:VIDEO_Y1] = crop_sq        # 420–1500px
                out_buf[VIDEO_Y1:]         = cached_sub     # 1500–1920px

                # bytes() để tránh buffer overwrite race giữa composer và main thread
                write_q.put(bytes(out_buf))

        # ── Khởi động 4 threads
        threads = [
            threading.Thread(target=_reader,    daemon=True, name="yolo_reader"),
            threading.Thread(target=_resizer,   daemon=True, name="yolo_resizer"),
            threading.Thread(target=_inference, daemon=True, name="yolo_infer"),
            threading.Thread(target=_composer,  daemon=True, name="yolo_composer"),
        ]
        for t in threads:
            t.start()

        # ── FFmpeg
        out_path      = output_dir / f"{video_path.stem}.mp4"
        # ffmpeg_codec  = getattr(config, "ffmpeg_codec",  "h264_nvenc") if config else "h264_nvenc"
        ffmpeg_codec = getattr(config, "ffmpeg_codec", self._get_available_encoder())
        ffmpeg_preset = getattr(config, "ffmpeg_preset", "p4")         if config else "p4"

        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", f"{OUT_W}x{OUT_H}", "-pix_fmt", "bgr24",
            "-r", str(fps), "-i", "-",
            "-i", str(video_path),
            "-map", "0:v:0", "-map", "1:a:0?",
            "-c:v", ffmpeg_codec, "-preset", ffmpeg_preset,
            "-rc", "vbr", "-cq", "24",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            str(out_path),
        ]

        for attempt in range(2):
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdin  = subprocess.PIPE,
                    stderr = subprocess.DEVNULL,
                )

                frame_idx = 0
                while True:
                    data = write_q.get()
                    if data is _STOP:
                        break
                    proc.stdin.write(data)
                    frame_idx += 1

                    if total_frames > 0 and frame_idx % max(1, total_frames // 10) == 0:
                        pct = min(100, int(frame_idx / total_frames * 100))
                        print(f"🎬 YOLO: {pct}% ({frame_idx}/{total_frames})", flush=True)

                proc.stdin.close()
                proc.wait(timeout=60)
                break

            except (BrokenPipeError, OSError) as e:
                print(f"⚠️ FFmpeg pipe lỗi lần {attempt + 1}: {e}", flush=True)
                if proc.poll() is None:
                    proc.kill()
                time.sleep(1)

        # ── Join threads (tránh data race khi gọi process_video() tiếp theo)
        stop_event.set()
        for t in threads:
            t.join(timeout=10)

        cap.release()
        print(f"✅ YOLO crop done → {out_path.name}", flush=True)

    def release_resources(self):
        if self.model:
            del self.model
            self.model = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        gc.collect()
        print("🧹 YOLO resources released", flush=True)

    @staticmethod
    def horizontal_flip(frame: np.ndarray) -> np.ndarray:
        return np.fliplr(frame)