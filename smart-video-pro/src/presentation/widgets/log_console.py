# src/presentation/widgets/log_console.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCharFormat, QColor, QTextCursor
from datetime import datetime
from src.presentation.utils.signal_bus import bus

# Màu theo level (giống HTML)
COLORS = {
    "ok": "#1fc98a",      # xanh lá
    "inf": "#6c63ff",     # tím
    "info": "#6c63ff",
    "warn": "#f5a820",    # vàng
    "error": "#ff5060",   # đỏ
    "err": "#ff5060",
    "dim": "#4a5068"      # xám
}

class LogConsole(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # Header
        header = QHBoxLayout()
        title = QLabel("System Log")
        title.setStyleSheet("font-size:11px; color:#8890aa; text-transform:uppercase; letter-spacing:0.6px;")

        self.filter_lbl = QLabel("Chế độ: Errors + Alerts")
        self.filter_lbl.setStyleSheet("color:#4a5068; font-size:10px;")

        self.btn_verbose = QPushButton("Verbose")
        self.btn_verbose.setCheckable(True)
        self.btn_verbose.setFixedWidth(80)
        self.btn_verbose.toggled.connect(self._toggle_verbose)

        self.btn_clear = QPushButton("Xóa")
        self.btn_clear.setFixedWidth(60)
        self.btn_clear.clicked.connect(self.clear)

        header.addWidget(title)
        header.addWidget(self.filter_lbl)
        header.addStretch()
        header.addWidget(self.btn_verbose)
        header.addWidget(self.btn_clear)
        lay.addLayout(header)

        # Log Area
        self.console = QTextEdit()
        self.console.setObjectName("log_console")
        self.console.setReadOnly(True)
        self.console.setMinimumHeight(140)
        self.console.setMaximumHeight(180)
        lay.addWidget(self.console)

        # Buffer để redraw khi chuyển verbose
        self._buffer = []  # list of (timestamp, level, message)
        self._verbose = False

        # Kết nối signal
        bus.log_emitted.connect(self.append_log)

        # Log khởi tạo
        self._append_raw("dim", "Ready — chờ video...")

    def _toggle_verbose(self, checked: bool):
        self._verbose = checked
        self.filter_lbl.setText("Tất cả log" if checked else "Errors + Alerts only")
        self._redraw()

    def append_log(self, level: str, message: str):
        """Nhận log từ bus"""
        ts = datetime.now().strftime("%H:%M:%S")
        self._buffer.append((ts, level, message))

        # Chỉ hiển thị nếu verbose hoặc là log quan trọng
        if self._verbose or level in {"ok", "warn", "error", "err"}:
            self._append_raw(level, f"[{ts}] {message}")

    def _append_raw(self, level: str, text: str):
        """Thêm text có màu vào console"""
        cursor = self.console.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(COLORS.get(level, "#8890aa")))

        cursor.insertText(text + "\n", fmt)
        self.console.setTextCursor(cursor)
        self.console.ensureCursorVisible()

    def _redraw(self):
        """Vẽ lại toàn bộ log khi chuyển chế độ verbose"""
        self.console.clear()
        for ts, level, msg in self._buffer:
            if self._verbose or level in {"ok", "warn", "error", "err"}:
                self._append_raw(level, f"[{ts}] {msg}")

    def clear(self):
        """Xóa toàn bộ log"""
        self.console.clear()
        self._buffer.clear()
        self._append_raw("dim", "Log đã được xóa.")

    def append(self, level: str, message: str):
        """Phương thức tiện ích gọi trực tiếp"""
        bus.log_emitted.emit(level, message)