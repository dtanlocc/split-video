# src/presentation/widgets/pipeline_panel.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QButtonGroup, QFrame, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from pathlib import Path
from src.presentation.utils.signal_bus import bus

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv"}

class FileItem(QListWidgetItem):
    def __init__(self, file_path: str):
        super().__init__()
        p = Path(file_path)
        size_mb = p.stat().st_size / (1024 * 1024) if p.exists() else 0
        size_str = f"{size_mb/1024:.1f} GB" if size_mb > 1024 else f"{size_mb:.1f} MB"
        
        self.file_path = file_path
        self.setText(f" {p.name}\n   {size_str}")
        self.setToolTip(file_path)
        self.setSizeHint(QSize(0, 52))


class DropZone(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropzone")
        self.setMinimumHeight(140)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(8)

        icon = QLabel("⬇️")
        icon.setStyleSheet("font-size:42px; color:#4a5068;")
        title = QLabel("Kéo thư mục hoặc video vào đây")
        title.setStyleSheet("font-size:13px; font-weight:500; color:#dde1f0;")
        sub = QLabel("hoặc click để chọn")
        sub.setStyleSheet("color:#8890aa; font-size:11px;")

        btn = QPushButton("Chọn thư mục...")
        btn.clicked.connect(self._browse_folder)

        lay.addWidget(icon)
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addWidget(btn)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục chứa video")
        if folder:
            self._load_files_from_folder(folder)

    def _load_files_from_folder(self, folder: str):
        paths = []
        for f in Path(folder).iterdir():
            if f.is_file() and f.suffix.lower() in VIDEO_EXTS:
                paths.append(str(f))
        if paths:
            bus.files_added.emit(paths)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.setStyleSheet("background:#6c63ff22; border:1.5px dashed #6c63ff;")

    def dragLeaveEvent(self, e):
        self.setStyleSheet("")

    def dropEvent(self, e: QDropEvent):
        self.setStyleSheet("")
        paths = []
        for url in e.mimeData().urls():
            path = url.toLocalFile()
            p = Path(path)
            if p.is_dir():
                for f in p.iterdir():
                    if f.is_file() and f.suffix.lower() in VIDEO_EXTS:
                        paths.append(str(f))
            elif p.is_file() and p.suffix.lower() in VIDEO_EXTS:
                paths.append(str(p))
        if paths:
            bus.files_added.emit(paths)


class ModeButton(QPushButton):
    def __init__(self, title, desc, is_selected=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setMinimumHeight(78)
        
        if is_selected:
            self.setProperty("mode", "selected")
        else:
            self.setProperty("mode", "normal")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        
        t = QLabel(title)
        t.setStyleSheet("font-size:14px; font-weight:600;")
        d = QLabel(desc)
        d.setStyleSheet("font-size:11px; color:#94a3b8;")
        
        lay.addWidget(t)
        lay.addWidget(d)

    def setChecked(self, checked: bool):
        super().setChecked(checked)
        if checked:
            self.setStyleSheet("background:#6c63ff22; border:1px solid #6c63ff; border-radius:8px;")
        else:
            self.setStyleSheet("background:#181b24; border:1px solid rgba(255,255,255,0.08); border-radius:8px;")


class PipelinePanel(QWidget):
    files_added = pyqtSignal(list)  # internal

    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: list[str] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        # Dropzone
        self.dropzone = DropZone()
        lay.addWidget(self.dropzone)

        # File List
        list_header = QLabel("Hàng đợi xử lý")
        list_header.setStyleSheet("color:#8890aa; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;")
        lay.addWidget(list_header)

        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(180)
        self.file_list.itemDoubleClicked.connect(self._preview_file)
        lay.addWidget(self.file_list)

        # Pipeline Mode
        mode_lbl = QLabel("Chế độ Pipeline")
        mode_lbl.setStyleSheet("color:#8890aa; font-size:11px; text-transform:uppercase; letter-spacing:0.6px; margin-top:8px;")
        lay.addWidget(mode_lbl)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)

        # mode_row = QHBoxLayout()
        self.mode_full = ModeButton("Full Pipeline", "(Có YOLO crop)", True)
        self.mode_noyolo = ModeButton("Bỏ Crop", "(Nhanh hơn)", False)

        self.mode_full.setChecked(True)

        group = QButtonGroup(self)
        group.addButton(self.mode_full)
        group.addButton(self.mode_noyolo)

        mode_row.addWidget(self.mode_full)
        mode_row.addWidget(self.mode_noyolo)
        lay.addLayout(mode_row)

        # Stats Row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(8)
        self.stat_done = self._create_stat("Video xong", "#1fc98a")
        self.stat_clips = self._create_stat("Clips tạo ra", "#8880ff")
        self.stat_quota = self._create_stat("Quota còn", "#18d4be")

        for s in (self.stat_done, self.stat_clips, self.stat_quota):
            stats_row.addWidget(s)
        lay.addLayout(stats_row)

        lay.addStretch()

        # Run Button
        self.run_btn = QPushButton("🚀 BẮT ĐẦU XỬ LÝ")
        self.run_btn.setObjectName("btn_run")
        self.run_btn.setMinimumHeight(52)
        self.run_btn.clicked.connect(self._on_run_clicked)
        lay.addWidget(self.run_btn)

        # Connect signals
        bus.files_added.connect(self._add_files)
        bus.stats_updated.connect(self._update_stats)
        bus.quota_updated.connect(self._update_quota)

    def _create_stat(self, title: str, color: str):
        card = QFrame()
        card.setObjectName("card")
        v = QVBoxLayout(card)
        v.setContentsMargins(12, 10, 12, 10)
        lbl = QLabel(title)
        lbl.setStyleSheet("color:#94a3b8; font-size:10.5px;")
        val = QLabel("0")
        val.setStyleSheet(f"font-size:26px; font-weight:700; color:{color};")
        v.addWidget(lbl)
        v.addWidget(val)
        card.value_label = val
        return card

    def _add_files(self, paths: list[str]):
        existing = {self.file_list.item(i).file_path for i in range(self.file_list.count()) 
                   if hasattr(self.file_list.item(i), 'file_path')}
        
        for p in paths:
            if p not in existing:
                item = FileItem(p)
                self.file_list.addItem(item)
                self._files.append(p)

    def _preview_file(self, item: QListWidgetItem):
        if hasattr(item, "file_path"):
            bus.file_preview_requested.emit(item.file_path)

    def _on_run_clicked(self):
        files = self.get_files()
        if not files:
            bus.log_emitted.emit("warn", "Chưa có video nào trong danh sách!")
            return
        bus.log_emitted.emit("info", f"Bắt đầu pipeline với {len(files)} video...")
        # ViewModel sẽ xử lý tiếp

    def get_files(self) -> list[str]:
        return [self.file_list.item(i).file_path 
                for i in range(self.file_list.count()) 
                if hasattr(self.file_list.item(i), "file_path")]

    def get_mode(self) -> str:
        return "noyolo" if self.mode_noyolo.isChecked() else "full"

    def _update_stats(self, done: int, clips: int):
        self.stat_done.value_label.setText(str(done))
        self.stat_clips.value_label.setText(str(clips))

    def _update_quota(self, used: int, limit: int):
        remain = limit - used
        self.stat_quota.value_label.setText(str(remain))