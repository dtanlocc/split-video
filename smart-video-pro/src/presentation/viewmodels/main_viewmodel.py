import time
import json
from pathlib import Path
from PyQt6.QtCore import QObject, QThread, pyqtSignal, QTimer

from src.presentation.utils.signal_bus import bus

CONFIG_PATH = Path("config.json")


def _cfg() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


# ── Worker thread ─────────────────────────────────────────────────────────────

class PipelineWorker(QObject):
    """
    Chạy toàn bộ verify_pipeline trong thread riêng.
    Không bao giờ update UI trực tiếp — chỉ emit signal bus.
    """
    finished = pyqtSignal()
    error    = pyqtSignal(str)

    def __init__(self, files: list[str], mode: str, cfg: dict):
        super().__init__()
        self.files = files
        self.mode  = mode
        self.cfg   = cfg
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            total = len(self.files)
            for vid_idx, video_path in enumerate(self.files, 1):
                if self._cancelled:
                    break
                self._run_one(video_path, vid_idx, total)

            if not self._cancelled:
                # Update quota
                cfg = _cfg()
                used = cfg.get("quota_used_this_month", 0) + total
                cfg["quota_used_this_month"] = used
                limit = cfg.get("quota_monthly_limit", 600)
                Path(CONFIG_PATH).write_text(
                    json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                bus.quota_updated.emit(used, limit)
                bus.stats_updated.emit(total, total * 3)  # rough clip estimate
                self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

    def _run_one(self, video_path: str, vid_idx: int, total: int):
        name = Path(video_path).name
        bus.video_started.emit(name, vid_idx, total)
        bus.log_emitted.emit("info", f"Nạp model Whisper {self.cfg.get('whisper_model','base')}...")

        stages = [0, 1, 2, 4] if self.mode == "no_yolo" else [0, 1, 2, 3, 4]
        n_stages = len(stages)

        for s_order, stage_idx in enumerate(stages):
            if self._cancelled:
                return
            
            # SỬA Ở ĐÂY: Các dòng trạng thái hiển thị
            stage_name = [
                "Đang trích xuất giọng nói...",
                "AI đang phân tích kịch bản...",
                "Đang xử lý phân đoạn...",
                "Đang bám theo chủ thể...",
                "Đang đóng dấu phụ đề...",
            ][stage_idx]

            # Simulate progress within stage (real code replaces this loop)
            steps = 20
            for step in range(steps + 1):
                if self._cancelled:
                    return
                stage_pct = int(step / steps * 100)
                total_pct = int((s_order * 100 + stage_pct) / n_stages)
                bus.progress_updated.emit(total_pct, stage_name, stage_idx)
                bus.stage_progress.emit(stage_idx, stage_pct)
                time.sleep(0.05)  # replace with actual work

            bus.log_emitted.emit("ok", f"{stage_name.rstrip('.')} hoàn thành")

        bus.progress_updated.emit(100, "Hoàn tất!", 4)


# ── ViewModel ─────────────────────────────────────────────────────────────────

class MainViewModel(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: PipelineWorker | None = None

        # Elapsed timer
        self._elapsed = 0
        self._timer = QTimer()
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick_eta)

        bus.pipeline_finished.connect(self._on_done)
        bus.pipeline_error.connect(self._on_error)

    # ── Public API ────────────────────────────────────────────────────────────

    def start_pipeline(self, files: list[str], mode: str):
        """Gọi từ PipelinePanel khi bấm Run"""
        if self._thread and self._thread.isRunning():
            bus.log_emitted.emit("warn", "Pipeline đang chạy.")
            return

        cfg = _cfg()

        # Quota guard
        used  = cfg.get("quota_used_this_month", 0)
        limit = cfg.get("quota_monthly_limit", 600)
        if used >= limit:
            bus.log_emitted.emit(
                "error", f"Đã đạt giới hạn {limit} video/tháng. Vui lòng đổi sang tháng mới."
            )
            bus.pipeline_error.emit("quota_exceeded")
            return

        self._elapsed = 0
        self._timer.start()

        self._worker = PipelineWorker(files, mode, cfg)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._on_worker_error)
        self._worker.finished.connect(lambda: bus.pipeline_finished.emit())
        self._thread.start()

    def cancel_pipeline(self):
        if self._worker:
            self._worker.cancel()
            bus.log_emitted.emit("warn", "Đang dừng pipeline...")

    # ── Private ───────────────────────────────────────────────────────────────

    def _tick_eta(self):
        self._elapsed += 1
        # Simple ETA: extrapolate from current progress (viewmodel listens to progress)
        # Actual ETA is computed by pipeline_panel; here we just track elapsed.

    def _on_done(self):
        self._timer.stop()

    def _on_error(self, msg: str):
        self._timer.stop()

    def _on_worker_error(self, msg: str):
        bus.pipeline_error.emit(msg)
        bus.log_emitted.emit("error", f"Pipeline lỗi: {msg}")