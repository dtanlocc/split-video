# src/presentation/widgets/outputs_panel.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
    QFrame, QPushButton, QScrollArea
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QIcon
from pathlib import Path
from src.presentation.utils.signal_bus import bus
import os

class OutputCard(QFrame):
    """Card hiển thị một video output"""
    def __init__(self, video_path: str, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.setObjectName("card")
        self.setFixedHeight(180)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # Thumbnail
        thumb_frame = QFrame()
        thumb_frame.setFixedHeight(110)
        thumb_frame.setStyleSheet("background:#12141a; border-radius:6px;")
        thumb_lay = QVBoxLayout(thumb_frame)
        thumb_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(140, 100)
        self.thumb_label.setStyleSheet("background:#1e2230; border-radius:4px;")
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Load thumbnail (nếu có file .jpg cùng tên)
        self._load_thumbnail()

        thumb_lay.addWidget(self.thumb_label)

        # Duration badge
        p = Path(video_path)
        dur = "2:45"  # Có thể parse thực tế sau
        dur_label = QLabel(dur)
        dur_label.setStyleSheet(
            "background:rgba(0,0,0,0.7); color:#fff; font-size:9px; "
            "padding:1px 6px; border-radius:8px;"
        )
        dur_label.setFixedWidth(48)
        thumb_lay.addWidget(dur_label, alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        lay.addWidget(thumb_frame)

        # Info
        name = QLabel(p.name)
        name.setStyleSheet("font-weight:500; font-size:11.5px; color:#dde1f0;")
        name.setWordWrap(True)
        name.setMaximumHeight(32)

        meta = QLabel("1080×1920 • 9:16")
        meta.setStyleSheet("color:#8890aa; font-size:10px;")

        lay.addWidget(name)
        lay.addWidget(meta)

        # Click để mở video
        self.mousePressEvent = lambda e: self._play_video()

    def _load_thumbnail(self):
        """Thử load thumbnail nếu có file ảnh cùng tên"""
        p = Path(self.video_path)
        thumb_path = p.with_suffix(".jpg")
        if thumb_path.exists():
            pix = QPixmap(str(thumb_path))
            if not pix.isNull():
                self.thumb_label.setPixmap(
                    pix.scaled(140, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                )
        else:
            # Fallback icon
            self.thumb_label.setText("🎬")
            self.thumb_label.setStyleSheet("font-size:42px; color:#6c63ff;")

    def _play_video(self):
        bus.file_preview_requested.emit(self.video_path)


class OutputsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.output_dir = Path("verify_results/final")

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(16, 16, 16, 16)
        main_lay.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel("📤 Video đã xử lý")
        title.setStyleSheet("font-size:13px; font-weight:600; color:#dde1f0;")
        self.count_lbl = QLabel("0 video")
        self.count_lbl.setStyleSheet("color:#8890aa; font-size:11px;")

        refresh_btn = QPushButton("↻ Làm mới")
        refresh_btn.clicked.connect(self.refresh_outputs)

        header.addWidget(title)
        header.addWidget(self.count_lbl)
        header.addStretch()
        header.addWidget(refresh_btn)
        main_lay.addLayout(header)

        # Scrollable Grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.grid_widget = QWidget()
        self.grid = QGridLayout(self.grid_widget)
        self.grid.setSpacing(14)
        scroll.setWidget(self.grid_widget)

        main_lay.addWidget(scroll)

        # Load ban đầu
        self.refresh_outputs()

        # Auto refresh khi pipeline xong
        bus.pipeline_finished.connect(self.refresh_outputs)

    def refresh_outputs(self):
        """Quét thư mục output và hiển thị grid"""
        # Xóa grid cũ
        for i in reversed(range(self.grid.count())):
            widget = self.grid.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        if not self.output_dir.exists():
            empty = QLabel("Chưa có video nào được xử lý")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color:#4a5068; font-size:14px; padding:60px;")
            self.grid.addWidget(empty, 0, 0)
            self.count_lbl.setText("0 video")
            return

        videos = list(self.output_dir.glob("*.mp4"))
        videos.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        self.count_lbl.setText(f"{len(videos)} video")

        row = col = 0
        for video in videos:
            card = OutputCard(str(video))
            self.grid.addWidget(card, row, col)

            col += 1
            if col > 3:  # 4 cột
                col = 0
                row += 1