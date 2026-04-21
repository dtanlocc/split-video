# src/presentation/widgets/license_manager.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QGroupBox, QFrame
)
from PyQt6.QtCore import Qt
from pathlib import Path
import json
import hashlib
import time

CONFIG_PATH = Path("config.json")


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except:
            pass
    return {}


def _save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


class LicenseManager(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = _load_config()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox("🔑 License & Kích Hoạt")
        group.setStyleSheet("QGroupBox{font-weight:600;}")
        fl = QVBoxLayout(group)
        fl.setSpacing(12)

        # Status
        self.status_lbl = QLabel()
        self.status_lbl.setWordWrap(True)
        fl.addWidget(self.status_lbl)

        # Key Input
        key_row = QHBoxLayout()
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("Nhập License Key của bạn...")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setMinimumWidth(320)

        self.btn_activate = QPushButton("Kích Hoạt")
        self.btn_activate.setFixedWidth(110)
        self.btn_activate.clicked.connect(self.activate_license)

        key_row.addWidget(self.key_input)
        key_row.addWidget(self.btn_activate)
        fl.addLayout(key_row)

        # Info
        info = QLabel(
            "• License vĩnh viễn\n"
            "• Hỗ trợ cập nhật miễn phí\n"
            "• Sử dụng trên 1 máy tính"
        )
        info.setStyleSheet("color:#8890aa; font-size:10px;")
        fl.addWidget(info)

        lay.addWidget(group)

        self._update_status()

    def _update_status(self):
        cfg = _load_config()
        activated = cfg.get("license_activated", False)
        expire = cfg.get("license_expire", None)

        if activated:
            status_text = "✅ <b>License ĐÃ KÍCH HOẠT</b>"
            if expire:
                status_text += f"<br>🔄 Hạn sử dụng: {expire}"
            color = "#1fc98a"
        else:
            status_text = "🔒 <b>Chưa kích hoạt License</b><br>Bạn đang dùng phiên bản Trial"
            color = "#ff5060"

        self.status_lbl.setText(status_text)
        self.status_lbl.setStyleSheet(f"color:{color}; padding:8px; background:#181b24; border-radius:6px;")

    def activate_license(self):
        key = self.key_input.text().strip()
        if not key:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập License Key!")
            return

        # === KIỂM TRA LICENSE (Bạn có thể thay bằng server check) ===
        if self._validate_key(key):
            cfg = _load_config()
            cfg["license_activated"] = True
            cfg["license_key"] = key
            cfg["license_activate_date"] = time.strftime("%Y-%m-%d")
            cfg["license_expire"] = "Vĩnh viễn"   # hoặc tính theo ngày

            _save_config(cfg)
            self._update_status()
            self.key_input.clear()

            QMessageBox.information(
                self, 
                "Thành công", 
                "✅ License đã được kích hoạt thành công!\n\nCảm ơn bạn đã tin tưởng AutoClip AI."
            )
        else:
            QMessageBox.critical(
                self, 
                "License không hợp lệ", 
                "License Key bạn nhập không đúng hoặc đã hết hạn.\n\nVui lòng liên hệ nhà cung cấp."
            )

    def _validate_key(self, key: str) -> bool:
        """
        Hàm kiểm tra License Key.
        Hiện tại dùng phương pháp đơn giản (bạn có thể nâng cấp lên server sau).
        """
        # Ví dụ: Key hợp lệ nếu dài > 20 và chứa chữ cái + số
        if len(key) < 20:
            return False

        # Bạn có thể tạo key thật bằng cách:
        # hashlib.sha256("tên_người_dùng + secret_salt".encode()).hexdigest()[:32]
        
        # Hiện tại chấp nhận hầu hết key dài để test
        return True

    def is_activated(self) -> bool:
        """Kiểm tra license ở các chỗ khác"""
        cfg = _load_config()
        return cfg.get("license_activated", False)