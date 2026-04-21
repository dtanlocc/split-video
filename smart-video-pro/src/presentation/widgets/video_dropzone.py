import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QFileDialog, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QMimeData, QSize
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QColor

from src.presentation.utils.signal_bus import bus

VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv"}


class FileItem(QListWidgetItem):
    def __init__(self, path: str):
        super().__init__()
        p = Path(path)
        size_mb = p.stat().st_size / (1024 * 1024) if p.exists() else 0
        size_str = f"{size_mb/1024:.1f} GB" if size_mb > 1024 else f"{size_mb:.0f} MB"
        self.file_path = path
        self.setText(f"  {p.name}  ·  {size_str}")
        self.setToolTip(path)
        self.setSizeHint(QSize(0, 36))


class DropZone(QFrame):
    """Dashed border frame — nhận drag từ Explorer"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropzone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(90)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(4)

        icon = QLabel("⬇")
        icon.setStyleSheet("font-size:20px; color:#4a5068; background:transparent;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title = QLabel("Kéo thư mục video vào đây")
        self.title.setStyleSheet("font-size:12px; font-weight:500; color:#8890aa; background:transparent;")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub = QLabel("hoặc")
        sub.setObjectName("lbl_muted")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn = QPushButton("Chọn thư mục...")
        btn.setFixedWidth(130)
        btn.clicked.connect(self._browse)

        lay.addWidget(icon)
        lay.addWidget(self.title)
        lay.addWidget(sub)
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục video")
        if folder:
            self._load_folder(folder)

    def _load_folder(self, folder: str):
        paths = [
            str(Path(folder) / f)
            for f in os.listdir(folder)
            if Path(f).suffix.lower() in VIDEO_EXTS
        ]
        if paths:
            bus.files_added.emit(paths)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.setStyleSheet(
                "QFrame#dropzone{background:rgba(108,99,255,0.1);"
                "border:1.5px dashed rgba(108,99,255,0.6);border-radius:10px;}"
            )
            self.title.setText("Thả vào đây...")

    def dragLeaveEvent(self, e):
        self.setStyleSheet("")
        self.title.setText("Kéo thư mục video vào đây")

    def dropEvent(self, e: QDropEvent):
        self.setStyleSheet("")
        self.title.setText("Kéo thư mục video vào đây")
        for url in e.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isdir(path):
                self._load_folder(path)
            elif Path(path).suffix.lower() in VIDEO_EXTS:
                bus.files_added.emit([path])
        e.acceptProposedAction()

    def mousePressEvent(self, e):
        self._browse()


class VideoDropZone(QWidget):
    """Dropzone + danh sách file + nút xóa"""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.dropzone = DropZone()
        lay.addWidget(self.dropzone)

        # header row
        hdr = QHBoxLayout()
        lbl = QLabel("Hàng đợi")
        lbl.setObjectName("lbl_secondary")
        self.count_lbl = QLabel("0 file")
        self.count_lbl.setObjectName("lbl_muted")
# TRONG CLASS VideoDropZone:
        btn_clear = QPushButton("Xóa tất cả")
        # btn_clear.setFixedWidth(80)  <-- XÓA DÒNG NÀY
        btn_clear.setMinimumWidth(90)  # <-- THÊM DÒNG NÀY
        btn_clear.setFixedHeight(28)   # <-- Tăng nhẹ height cho dễ bấm
        btn_clear.setObjectName("btn_danger")
        btn_clear.clicked.connect(self._clear_all)
        hdr.addWidget(lbl)
        hdr.addWidget(self.count_lbl)
        hdr.addStretch()
        hdr.addWidget(btn_clear)
        lay.addLayout(hdr)

        self.list_widget = QListWidget()
        self.list_widget.setMinimumHeight(140)
        self.list_widget.itemDoubleClicked.connect(self._preview)
        lay.addWidget(self.list_widget)

        bus.files_added.connect(self._add_files)

    def _add_files(self, paths: list):
        existing = {self.list_widget.item(i).file_path
                    for i in range(self.list_widget.count())}
        added = 0
        for p in paths:
            if p not in existing:
                self.list_widget.addItem(FileItem(p))
                added += 1
        self._update_count()

    def _clear_all(self):
        self.list_widget.clear()
        self._update_count()

    def _update_count(self):
        n = self.list_widget.count()
        self.count_lbl.setText(f"{n} file")

    def _preview(self, item: QListWidgetItem):
        if hasattr(item, "file_path"):
            bus.file_preview_requested.emit(item.file_path)

    def get_files(self) -> list[str]:
        return [self.list_widget.item(i).file_path
                for i in range(self.list_widget.count())
                if hasattr(self.list_widget.item(i), "file_path")]