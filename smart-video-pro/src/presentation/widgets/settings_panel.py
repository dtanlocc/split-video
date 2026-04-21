# src/presentation/widgets/settings_panel.py
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QStackedWidget,
    QLabel, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPushButton,
    QGroupBox, QFormLayout, QColorDialog, QCheckBox, QFileDialog,
    QFrame, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from pathlib import Path
import json

from .license_manager import LicenseManager

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

class SettingsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = _load_config()

        main_lay = QHBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # ==================== SIDE NAV ====================
        self.nav = QListWidget()
        self.nav.setObjectName("side_nav")
        self.nav.setFixedWidth(180)

        nav_items = [
            "Chung",
            "Bước 1 — Whisper",
            "Bước 2 — Gemini",
            "Bước 4 — YOLO",
            "Bước 5 — Render",
            "Quota & License"
        ]
        self.nav.addItems(nav_items)
        self.nav.currentRowChanged.connect(self._switch_tab)

        main_lay.addWidget(self.nav)

        # ==================== CONTENT STACK ====================
        self.stack = QStackedWidget()
        main_lay.addWidget(self.stack)

        # Tạo các tab
        self.tab_general = self._create_general_tab()
        self.tab_b1 = self._create_b1_tab()
        self.tab_b2 = self._create_b2_tab()
        self.tab_b4 = self._create_b4_tab()
        self.tab_b5 = self._create_b5_tab()
        self.tab_quota = self._create_quota_tab()

        self.stack.addWidget(self.tab_general)
        self.stack.addWidget(self.tab_b1)
        self.stack.addWidget(self.tab_b2)
        self.stack.addWidget(self.tab_b4)
        self.stack.addWidget(self.tab_b5)
        self.stack.addWidget(self.tab_quota)

        self.nav.setCurrentRow(0)

        # Nút lưu
        save_btn = QPushButton("💾 Lưu tất cả cài đặt")
        save_btn.setStyleSheet("background:#6c63ff; color:white; font-weight:600; padding:10px;")
        save_btn.clicked.connect(self._save_all)
        main_lay.addWidget(save_btn, alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

    def _switch_tab(self, idx):
        self.stack.setCurrentIndex(idx)

    # ====================== TABS ======================
    def _create_general_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 24, 24, 24)

        gb = QGroupBox("Thư mục")
        fl = QFormLayout(gb)
        fl.setSpacing(12)

        self.out_dir = QLineEdit(self.cfg.get("output_dir", "verify_results/final"))
        self.temp_dir = QLineEdit(self.cfg.get("temp_dir", "verify_results/tmp"))

        fl.addRow("Output folder:", self.out_dir)
        fl.addRow("Temp folder:", self.temp_dir)

        lay.addWidget(gb)
        lay.addStretch()
        return w

    def _create_b1_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 24, 24, 24)

        gb = QGroupBox("Bước 1 — Whisper Transcribe")
        fl = QFormLayout(gb)

        self.lang_code = QLineEdit(self.cfg.get("lang_code", "ja"))
        self.whisper_model = QComboBox()
        self.whisper_model.addItems(["base", "small", "medium", "large-v3"])
        self.whisper_model.setCurrentText(self.cfg.get("whisper_model", "medium"))

        fl.addRow("Ngôn ngữ (ISO):", self.lang_code)
        fl.addRow("Model Whisper:", self.whisper_model)

        lay.addWidget(gb)
        lay.addStretch()
        return w

    def _create_b2_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 24, 24, 24)

        gb = QGroupBox("Bước 2 — Gemini Highlight Analysis")
        fl = QFormLayout(gb)

        self.min_sec = QSpinBox()
        self.min_sec.setRange(30, 600)
        self.min_sec.setValue(self.cfg.get("highlight_min_sec", 150))
        self.min_sec.setSuffix(" giây")

        self.max_sec = QSpinBox()
        self.max_sec.setRange(60, 1800)
        self.max_sec.setValue(self.cfg.get("highlight_max_sec", 300))
        self.max_sec.setSuffix(" giây")

        self.gemini_model = QComboBox()
        self.gemini_model.addItems(["gemini-2.5-flash", "gemini-2.0-pro"])
        self.gemini_model.setCurrentText(self.cfg.get("gemini_model", "gemini-2.5-flash"))

        fl.addRow("Thời lượng tối thiểu:", self.min_sec)
        fl.addRow("Thời lượng tối đa:", self.max_sec)
        fl.addRow("Model Gemini:", self.gemini_model)

        lay.addWidget(gb)
        lay.addStretch()
        return w

    def _create_b4_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 24, 24, 24)

        gb = QGroupBox("Bước 4 — YOLO Smart Crop")
        fl = QFormLayout(gb)

        self.sharpen = QComboBox()
        self.sharpen.addItems(["low", "medium", "high"])
        self.sharpen.setCurrentText(self.cfg.get("sharpen_strength", "medium"))

        fl.addRow("Sharpen strength:", self.sharpen)

        lay.addWidget(gb)
        lay.addStretch()
        return w

    def _create_b5_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 24, 24, 24)

        # Subtitle
        gb_sub = QGroupBox("Phụ đề & Tiêu đề")
        fl_sub = QFormLayout(gb_sub)

        self.title_color_btn = QPushButton(self.cfg.get("title_color", "#FFD700"))
        self.title_color_btn.setStyleSheet(f"background:{self.cfg.get('title_color', '#FFD700')}; min-width:60px;")
        self.title_color_btn.clicked.connect(self._pick_title_color)

        self.sub_fill = QLineEdit(self.cfg.get("sub_fill_rgba", "255, 0, 0, 160"))
        self.max_words = QSpinBox(); self.max_words.setValue(self.cfg.get("max_words_per_line", 3))
        self.margin_v = QSpinBox(); self.margin_v.setValue(self.cfg.get("sub_margin_v", 250))
        self.font_size = QSpinBox(); self.font_size.setValue(self.cfg.get("sub_font_size", 85))

        fl_sub.addRow("Màu tiêu đề:", self.title_color_btn)
        fl_sub.addRow("Màu nền sub (RGBA):", self.sub_fill)
        fl_sub.addRow("Từ tối đa / dòng:", self.max_words)
        fl_sub.addRow("Sub margin V:", self.margin_v)
        fl_sub.addRow("Font size:", self.font_size)

        # Font
        gb_font = QGroupBox("Font Tiêu đề")
        fl_font = QFormLayout(gb_font)
        self.font_path = QLineEdit(self.cfg.get("font_title_file", r"C\:/Windows/Fonts/YuGothM.ttc"))
        browse_font = QPushButton("...")
        browse_font.clicked.connect(self._browse_font)
        fl_font.addRow("Font path:", self.font_path)

        lay.addWidget(gb_sub)
        lay.addWidget(gb_font)
        lay.addStretch()
        return w

    def _create_quota_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 24, 24, 24)

        # Quota
        gb_quota = QGroupBox("Giới hạn sử dụng")
        flq = QFormLayout(gb_quota)
        self.monthly_limit = QSpinBox()
        self.monthly_limit.setRange(10, 5000)
        self.monthly_limit.setValue(self.cfg.get("quota_monthly_limit", 600))

        self.used = QSpinBox()
        self.used.setValue(self.cfg.get("quota_used_this_month", 0))

        flq.addRow("Giới hạn video/tháng:", self.monthly_limit)
        flq.addRow("Đã dùng:", self.used)

        lay.addWidget(gb_quota)

        # License
        lay.addWidget(LicenseManager())

        # API Keys
        gb_api = QGroupBox("API Keys")
        fla = QFormLayout(gb_api)
        self.gemini_key = QLineEdit(self.cfg.get("gemini_api_key", ""))
        self.gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
        fla.addRow("Gemini API Key:", self.gemini_key)

        lay.addWidget(gb_api)
        lay.addStretch()
        return w

    # ====================== HELPER ======================
    def _pick_title_color(self):
        color = QColorDialog.getColor(QColor(self.title_color_btn.text()), self)
        if color.isValid():
            hex_color = color.name()
            self.title_color_btn.setText(hex_color)
            self.title_color_btn.setStyleSheet(f"background:{hex_color};")

    def _browse_font(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn font", "C:/Windows/Fonts", "Fonts (*.ttf *.ttc *.otf)")
        if path:
            self.font_path.setText(path)

    def _save_all(self):
        cfg = _load_config()

        # Thu thập dữ liệu
        cfg.update({
            "output_dir": self.out_dir.text(),
            "temp_dir": self.temp_dir.text(),
            "lang_code": self.lang_code.text(),
            "whisper_model": self.whisper_model.currentText(),
            "highlight_min_sec": self.min_sec.value(),
            "highlight_max_sec": self.max_sec.value(),
            "gemini_model": self.gemini_model.currentText(),
            "sharpen_strength": self.sharpen.currentText(),
            "title_color": self.title_color_btn.text(),
            "sub_fill_rgba": self.sub_fill.text(),
            "max_words_per_line": self.max_words.value(),
            "sub_margin_v": self.margin_v.value(),
            "sub_font_size": self.font_size.value(),
            "font_title_file": self.font_path.text(),
            "quota_monthly_limit": self.monthly_limit.value(),
            "quota_used_this_month": self.used.value(),
            "gemini_api_key": self.gemini_key.text().strip(),
        })

        _save_config(cfg)
        QMessageBox.information(self, "Thành công", "Đã lưu tất cả cài đặt!")