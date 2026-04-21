# src/presentation/utils/signal_bus.py
from PyQt6.QtCore import QObject, pyqtSignal

class _SignalBus(QObject):
    """Signal Bus trung tâm"""
    
    # Pipeline & Progress
    progress_updated = pyqtSignal(int, str, int)   # pct, stage_name, stage_idx
    stage_progress = pyqtSignal(int, int)
    stats_updated = pyqtSignal(int, int)           # done, clips
    quota_updated = pyqtSignal(int, int)
    video_started = pyqtSignal(str, int, int)      # name, idx, total
    pipeline_finished = pyqtSignal()
    pipeline_error = pyqtSignal(str)

    # File management
    files_added = pyqtSignal(list)                 # ← THÊM DÒNG NÀY
    
    # Log
    log_emitted = pyqtSignal(str, str)             # level, message
    
    # Preview
    file_preview_requested = pyqtSignal(str)

    # Settings
    settings_saved = pyqtSignal()


# Global instance
bus = _SignalBus()