# src/presentation/widgets/step_progress.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QFrame
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont
from src.presentation.utils.signal_bus import bus

STAGE_NAMES = [
    "Transcribe (Whisper)",
    "Gemini Analysis",
    "FFmpeg Cut",
    "YOLO Smart Crop",
    "Render + Subtitle"
]


class StageRow(QWidget):
    def __init__(self, index: int, name: str, parent=None):
        super().__init__(parent)
        self.index = index
        self.name = name

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(10)

        # Dot
        self.dot = QLabel("●")
        self.dot.setFixedWidth(18)
        self.dot.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Name
        self.name_lbl = QLabel(name)
        self.name_lbl.setStyleSheet("color:#8890aa; font-size:11.5px;")

        # Progress Bar nhỏ
        self.progress = QProgressBar()
        self.progress.setFixedHeight(5)
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)

        # Percent
        self.pct_lbl = QLabel("—")
        self.pct_lbl.setFixedWidth(42)
        self.pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pct_lbl.setStyleSheet("color:#4a5068; font-size:10.5px;")

        lay.addWidget(self.dot)
        lay.addWidget(self.name_lbl, 1)
        lay.addWidget(self.progress, 3)
        lay.addWidget(self.pct_lbl)

    def set_state(self, state: str, pct: int = 0):
        """state: wait | run | done | skip"""
        if state == "done":
            self.dot.setStyleSheet("color:#1fc98a; font-size:14px;")
            self.progress.setValue(100)
            self.progress.setStyleSheet("QProgressBar::chunk{background:#1fc98a;}")
            self.pct_lbl.setText("100%")
            self.pct_lbl.setStyleSheet("color:#1fc98a; font-size:10.5px;")
        elif state == "run":
            self.dot.setStyleSheet("color:#6c63ff; font-size:14px;")
            self.progress.setValue(pct)
            self.progress.setStyleSheet("QProgressBar::chunk{background:#6c63ff;}")
            self.pct_lbl.setText(f"{pct}%")
            self.pct_lbl.setStyleSheet("color:#8880ff; font-size:10.5px;")
        elif state == "skip":
            self.dot.setStyleSheet("color:#3a3f52; font-size:14px;")
            self.progress.setValue(0)
            self.pct_lbl.setText("skip")
            self.pct_lbl.setStyleSheet("color:#3a3f52;")
        else:  # wait
            self.dot.setStyleSheet("color:#4a5068; font-size:14px;")
            self.progress.setValue(0)
            self.pct_lbl.setText("—")
            self.pct_lbl.setStyleSheet("color:#4a5068; font-size:10.5px;")


class StepProgressPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = QFrame()
        card.setObjectName("card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)

        # Big Progress
        self.big_pct = QLabel("0%")
        self.big_pct.setFont(QFont("Segoe UI", 42, QFont.Weight.Bold))
        self.big_pct.setStyleSheet("color:#f8fafc;")

        self.current_stage = QLabel("Chưa bắt đầu")
        self.current_stage.setStyleSheet("color:#8880ff; font-size:13.5px; font-weight:500;")

        self.video_name = QLabel("")
        self.video_name.setStyleSheet("color:#4a5068; font-size:11px;")

        self.big_bar = QProgressBar()
        self.big_bar.setFixedHeight(9)
        self.big_bar.setRange(0, 100)
        self.big_bar.setTextVisible(False)

        # ETA
        self.eta_lbl = QLabel("")
        self.eta_lbl.setStyleSheet("color:#8890aa; font-size:10.5px;")

        lay.addWidget(self.big_pct)
        lay.addWidget(self.current_stage)
        lay.addWidget(self.video_name)
        lay.addWidget(self.big_bar)
        lay.addWidget(self.eta_lbl)

        # Stages
        stages_box = QVBoxLayout()
        stages_box.setSpacing(8)
        self.stage_rows: list[StageRow] = []

        for i, name in enumerate(STAGE_NAMES):
            row = StageRow(i, name)
            self.stage_rows.append(row)
            stages_box.addWidget(row)

        lay.addLayout(stages_box)
        root.addWidget(card)

        # Connect signals
        bus.progress_updated.connect(self._on_progress)
        bus.stage_progress.connect(self._on_stage_progress)
        bus.video_started.connect(self._on_video_started)
        bus.pipeline_finished.connect(self._on_finished)

    @pyqtSlot(int, str, int)
    def _on_progress(self, pct: int, stage_name: str, stage_idx: int):
        self.big_bar.setValue(pct)
        self.big_pct.setText(f"{pct}%")
        self.current_stage.setText(stage_name)

        # Update stage rows
        for i, row in enumerate(self.stage_rows):
            if i < stage_idx:
                row.set_state("done")
            elif i == stage_idx:
                row.set_state("run", pct % 100)  # local progress
            else:
                row.set_state("wait")

    @pyqtSlot(int, int)
    def _on_stage_progress(self, stage_idx: int, pct: int):
        if 0 <= stage_idx < len(self.stage_rows):
            self.stage_rows[stage_idx].set_state("run", pct)

    @pyqtSlot(str, int, int)
    def _on_video_started(self, name: str, idx: int, total: int):
        self.video_name.setText(f"{name} ({idx}/{total})")
        self.reset()

    def _on_finished(self):
        self.big_bar.setValue(100)
        self.big_pct.setText("100%")
        self.current_stage.setText("Hoàn tất!")
        self.current_stage.setStyleSheet("color:#1fc98a; font-weight:600;")
        for row in self.stage_rows:
            row.set_state("done")

    def reset(self):
        self.big_bar.setValue(0)
        self.big_pct.setText("0%")
        self.current_stage.setText("Chưa bắt đầu")
        self.current_stage.setStyleSheet("color:#8880ff; font-size:13.5px; font-weight:500;")
        self.video_name.setText("")
        self.eta_lbl.setText("")
        for row in self.stage_rows:
            row.set_state("wait")