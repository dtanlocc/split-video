# src/presentation/ui/main_window.py
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QLabel, QPushButton, QFrame
)
from PyQt6.QtCore import Qt
from src.presentation.widgets.pipeline_panel import PipelinePanel
from src.presentation.widgets.outputs_panel import OutputsPanel
from src.presentation.widgets.settings_panel import SettingsPanel
from src.presentation.widgets.step_progress import StepProgressPanel
from src.presentation.widgets.log_console import LogConsole
from src.presentation.utils.signal_bus import bus


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoClip AI — v2.1.0")
        self.setMinimumSize(1280, 780)
        self.resize(1360, 820)

        with open("src/presentation/styles/dark_theme.qss", encoding="utf-8") as f:
            self.setStyleSheet(f.read())

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Topbar
        self.topbar = QFrame(objectName="topbar")
        tb = QHBoxLayout(self.topbar)
        tb.setContentsMargins(20, 12, 20, 12)

        logo = QLabel("AutoClip AI")
        logo.setStyleSheet("font-size:18px; font-weight:700; color:#6366f1;")
        tb.addWidget(logo)
        tb.addWidget(QLabel("v2.1.0"))
        tb.addStretch()

        # Quota
        self.quota_lbl = QLabel("Tháng này: 0 / 600")
        self.quota_lbl.setStyleSheet("background:#1f2333; padding:6px 16px; border-radius:20px; color:#a5b4fc;")
        tb.addWidget(self.quota_lbl)

        # Nav
        for text in ["Run", "Outputs", "Settings"]:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, t=text: self.switch_tab(t))
            tb.addWidget(btn)
            if text == "Run":
                btn.setChecked(True)

        root.addWidget(self.topbar)

        # Content
        self.stack = QStackedWidget()
        root.addWidget(self.stack)

        self.run_screen = self._create_run_screen()
        self.outputs_screen = OutputsPanel()
        self.settings_screen = SettingsPanel()

        self.stack.addWidget(self.run_screen)
        self.stack.addWidget(self.outputs_screen)
        self.stack.addWidget(self.settings_screen)

        bus.quota_updated.connect(self._update_quota)

    def _create_run_screen(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(20)

        self.pipeline = PipelinePanel()
        right = QVBoxLayout()
        right.setSpacing(16)
        self.progress = StepProgressPanel()
        self.log = LogConsole()

        right.addWidget(self.progress)
        right.addWidget(self.log)

        lay.addWidget(self.pipeline, 4)
        lay.addLayout(right, 5)
        return w

    def switch_tab(self, name):
        idx = 0 if name == "Run" else 1 if name == "Outputs" else 2
        self.stack.setCurrentIndex(idx)

    def _update_quota(self, used, limit):
        self.quota_lbl.setText(f"Tháng này: {used} / {limit}")