from PyQt6.QtWidgets import QStatusBar, QLabel, QWidget, QHBoxLayout, QProgressBar
from PyQt6.QtCore import Qt, QTimer
from src.presentation.utils.signal_bus import bus


class QuotaPill(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(6)

        self.lbl = QLabel("Tháng này:")
        self.lbl.setStyleSheet("color:#4a5068; font-size:11px;")

        self.bar = QProgressBar()
        self.bar.setFixedWidth(60)
        self.bar.setFixedHeight(4)
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet(
            "QProgressBar{background:#1e2230;border-radius:2px;}"
            "QProgressBar::chunk{background:#f5a820;border-radius:2px;}"
        )

        self.val_lbl = QLabel("0 / 600")
        self.val_lbl.setStyleSheet("color:#f5a820; font-size:11px; font-weight:500;")

        lay.addWidget(self.lbl)
        lay.addWidget(self.bar)
        lay.addWidget(self.val_lbl)

        bus.quota_updated.connect(self._update)

    def _update(self, used: int, limit: int):
        pct = int(used / limit * 100) if limit else 0
        self.bar.setValue(pct)
        self.val_lbl.setText(f"{used} / {limit}")
        color = "#ff5060" if pct >= 90 else "#f5a820" if pct >= 70 else "#1fc98a"
        self.val_lbl.setStyleSheet(
            f"color:{color}; font-size:11px; font-weight:500;"
        )
        chunk_color = color
        self.bar.setStyleSheet(
            "QProgressBar{background:#1e2230;border-radius:2px;}"
            f"QProgressBar::chunk{{background:{chunk_color};border-radius:2px;}}"
        )


class AppStatusBar(QStatusBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizeGripEnabled(False)

        self._msg_lbl = QLabel("Ready")
        self._msg_lbl.setStyleSheet("color:#4a5068; font-size:11px;")

        self._elapsed_lbl = QLabel("")
        self._elapsed_lbl.setStyleSheet("color:#4a5068; font-size:11px;")

        self._quota = QuotaPill()

        self.addWidget(self._msg_lbl)
        self.addPermanentWidget(self._elapsed_lbl)
        self.addPermanentWidget(self._quota)

        self._elapsed = 0
        self._timer = QTimer()
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

        bus.video_started.connect(self._on_start)
        bus.pipeline_finished.connect(self._on_done)
        bus.pipeline_error.connect(self._on_error)

    def _on_start(self, name, idx, total):
        self._elapsed = 0
        self._timer.start()
        self._msg_lbl.setText(f"Đang xử lý  {name}  ({idx}/{total})")

    def _on_done(self):
        self._timer.stop()
        self._msg_lbl.setText("Hoàn tất!")
        self._msg_lbl.setStyleSheet("color:#1fc98a; font-size:11px;")

    def _on_error(self, msg):
        self._timer.stop()
        self._msg_lbl.setText(f"Lỗi: {msg[:80]}")
        self._msg_lbl.setStyleSheet("color:#ff5060; font-size:11px;")

    def _tick(self):
        self._elapsed += 1
        m, s = divmod(self._elapsed, 60)
        self._elapsed_lbl.setText(f"{m:02d}:{s:02d}")

    def set_message(self, msg: str):
        self._msg_lbl.setText(msg)
        self._msg_lbl.setStyleSheet("color:#4a5068; font-size:11px;")