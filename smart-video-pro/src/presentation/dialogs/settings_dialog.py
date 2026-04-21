import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QWidget, QLabel, QLineEdit, QComboBox, QSpinBox,
    QDoubleSpinBox, QPushButton, QGroupBox, QFormLayout,
    QColorDialog, QCheckBox, QFileDialog, QFrame,
    QScrollArea, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon
from src.presentation.utils.signal_bus import bus

CONFIG_PATH = Path("config.json")

FONT_PRESETS = {
    "Nhật (YuGothic)":   r"C\:/Windows/Fonts/YuGothM.ttc",
    "Hàn (Malgun)":       r"C\:/Windows/Fonts/malgun.ttf",
    "Latin (Arial Bold)": r"C:/Windows/Fonts/arialbd.ttf",
    "Tùy chỉnh...":       "",
}


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_config(cfg: dict):
    CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── Helper builders ──────────────────────────────────────────────────────────

def _make_scroll(inner: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(inner)
    return scroll


def _group(title: str) -> tuple[QGroupBox, QFormLayout]:
    gb = QGroupBox(title)
    fl = QFormLayout(gb)
    fl.setContentsMargins(12, 16, 12, 12)
    fl.setSpacing(10)
    fl.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
    return gb, fl


def _lbl(text: str) -> QLabel:
    l = QLabel(text)
    l.setObjectName("lbl_secondary")
    return l


# ── Tab widgets ──────────────────────────────────────────────────────────────

class GeneralTab(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)

        gb, fl = _group("Thư mục")
        self.output_dir = QLineEdit(cfg.get("output_dir", "verify_results/final"))
        self.temp_dir   = QLineEdit(cfg.get("temp_dir",   "verify_results/tmp"))
        for le, lbl in [(self.output_dir, "Output folder"), (self.temp_dir, "Temp folder")]:
            row = QHBoxLayout()
            row.addWidget(le)
            btn = QPushButton("...")
            btn.setFixedWidth(28)
            btn.setFixedHeight(28)
            le._btn = btn
            row.addWidget(btn)
            w = QWidget(); w.setLayout(row)
            fl.addRow(_lbl(lbl), w)
        self.output_dir._btn.clicked.connect(
            lambda: self._browse_dir(self.output_dir))
        self.temp_dir._btn.clicked.connect(
            lambda: self._browse_dir(self.temp_dir))

        lay.addWidget(gb)
        lay.addStretch()

    def _browse_dir(self, le: QLineEdit):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục")
        if d:
            le.setText(d)

    def collect(self) -> dict:
        return {
            "output_dir": self.output_dir.text(),
            "temp_dir":   self.temp_dir.text(),
        }


class Step1Tab(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)

        gb, fl = _group("Bước 1 — Whisper transcribe")
        self.lang = QLineEdit(cfg.get("lang_code", "ja"))
        self.lang.setPlaceholderText("en, ja, ko, vi...")
        self.lang.setFixedWidth(90)

        self.model = QComboBox()
        self.model.addItems(["base", "small", "medium", "large-v3"])
        self.model.setCurrentText(cfg.get("whisper_model", "base"))

        fl.addRow(_lbl("Mã ngôn ngữ"), self.lang)
        fl.addRow(_lbl("Model Whisper"), self.model)

        hint = QLabel("Nâng model lên 'medium' hoặc 'large-v3' nếu GPU mạnh")
        hint.setObjectName("lbl_muted")
        hint.setWordWrap(True)

        lay.addWidget(gb)
        lay.addWidget(hint)
        lay.addStretch()

    def collect(self) -> dict:
        return {
            "lang_code":     self.lang.text().strip(),
            "whisper_model": self.model.currentText(),
        }


class Step2Tab(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)

        gb, fl = _group("Bước 2 — Gemini highlight analysis")
        self.min_sec = QSpinBox()
        self.min_sec.setRange(30, 600)
        self.min_sec.setSuffix(" giây")
        self.min_sec.setValue(cfg.get("highlight_min_sec", 150))

        self.max_sec = QSpinBox()
        self.max_sec.setRange(60, 1800)
        self.max_sec.setSuffix(" giây")
        self.max_sec.setValue(cfg.get("highlight_max_sec", 300))

        self.gemini_model = QComboBox()
        self.gemini_model.addItems(["gemini-2.5-flash", "gemini-2.0-pro"])
        self.gemini_model.setCurrentText(cfg.get("gemini_model", "gemini-2.5-flash"))

        fl.addRow(_lbl("Thời lượng tối thiểu"), self.min_sec)
        fl.addRow(_lbl("Thời lượng tối đa"), self.max_sec)
        fl.addRow(_lbl("Model Gemini"), self.gemini_model)

        preview = QLabel()
        preview.setObjectName("lbl_muted")
        preview.setWordWrap(True)

        def _update_preview():
            preview.setText(
                f"Prompt sẽ chứa: «at least {self.min_sec.value()} seconds "
                f"and at most {self.max_sec.value()} seconds»"
            )

        self.min_sec.valueChanged.connect(_update_preview)
        self.max_sec.valueChanged.connect(_update_preview)
        _update_preview()

        lay.addWidget(gb)
        lay.addWidget(preview)
        lay.addStretch()

    def collect(self) -> dict:
        return {
            "highlight_min_sec": self.min_sec.value(),
            "highlight_max_sec": self.max_sec.value(),
            "gemini_model":      self.gemini_model.currentText(),
        }


class Step4Tab(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)

        gb, fl = _group("Bước 4 — YOLO smart crop")
        self.sharpen = QComboBox()
        self.sharpen.addItems(["low", "medium", "high"])
        self.sharpen.setCurrentText(cfg.get("sharpen_strength", "medium"))
        fl.addRow(_lbl("Sharpen strength"), self.sharpen)

        lay.addWidget(gb)
        lay.addStretch()

    def collect(self) -> dict:
        return {"sharpen_strength": self.sharpen.currentText()}


class ColorButton(QPushButton):
    """Nút chọn màu với preview swatch"""
    def __init__(self, color: str = "#FFD700", parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(32, 32)
        self._refresh()
        self.clicked.connect(self._pick)

    def _refresh(self):
        self.setStyleSheet(
            f"QPushButton{{background:{self._color};"
            f"border:0.5px solid rgba(255,255,255,0.2);border-radius:5px;}}"
        )

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self)
        if c.isValid():
            self._color = c.name()
            self._refresh()

    def color(self) -> str:
        return self._color


class Step5Tab(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)

        # ── Subtitle ─────────────────────────────────────────
        gb_sub, fl_sub = _group("Subtitle")

        title_row = QHBoxLayout()
        self.title_color_btn = ColorButton(cfg.get("title_color", "#FFD700"))
        self.title_color_inp = QLineEdit(cfg.get("title_color", "#FFD700"))
        self.title_color_inp.setFixedWidth(90)
        self.title_color_btn.clicked.connect(
            lambda: self.title_color_inp.setText(self.title_color_btn.color())
        )
        title_row.addWidget(self.title_color_btn)
        title_row.addWidget(self.title_color_inp)
        title_row.addStretch()
        w_title = QWidget(); w_title.setLayout(title_row)
        fl_sub.addRow(_lbl("Màu tiêu đề"), w_title)

        fill = cfg.get("sub_fill_rgba", "255, 0, 0, 160")
        self.fill_rgba = QLineEdit(fill)
        self.fill_rgba.setPlaceholderText("R, G, B, A")
        fl_sub.addRow(_lbl("Fill màu nền sub (RGBA)"), self.fill_rgba)

        self.max_words = QSpinBox()
        self.max_words.setRange(1, 10)
        self.max_words.setValue(cfg.get("max_words_per_line", 3))
        fl_sub.addRow(_lbl("Từ tối đa / dòng"), self.max_words)

        self.margin_v = QSpinBox()
        self.margin_v.setRange(0, 800)
        self.margin_v.setSuffix(" px")
        self.margin_v.setValue(cfg.get("sub_margin_v", 250))
        fl_sub.addRow(_lbl("Sub margin V (tăng = lên cao)"), self.margin_v)

        self.font_size = QSpinBox()
        self.font_size.setRange(20, 200)
        self.font_size.setValue(cfg.get("sub_font_size", 85))
        fl_sub.addRow(_lbl("Font size sub"), self.font_size)

        lay.addWidget(gb_sub)

        # ── Font tiêu đề ──────────────────────────────────────
        gb_font, fl_font = _group("Font tiêu đề")

        self.font_preset = QComboBox()
        self.font_preset.addItems(list(FONT_PRESETS.keys()))
        self.font_preset.currentTextChanged.connect(self._on_preset)
        fl_font.addRow(_lbl("Preset ngôn ngữ"), self.font_preset)

        font_path_row = QHBoxLayout()
        self.font_path = QLineEdit(cfg.get("font_title_file", r"C\:/Windows/Fonts/YuGothM.ttc"))
        btn_browse_font = QPushButton("...")
        btn_browse_font.setFixedWidth(28)
        btn_browse_font.setFixedHeight(28)
        btn_browse_font.clicked.connect(self._browse_font)
        font_path_row.addWidget(self.font_path)
        font_path_row.addWidget(btn_browse_font)
        w_fp = QWidget(); w_fp.setLayout(font_path_row)
        fl_font.addRow(_lbl("Font path"), w_fp)

        lay.addWidget(gb_font)

        # ── Render ────────────────────────────────────────────
        gb_r, fl_r = _group("Render")
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.5, 2.0)
        self.speed.setSingleStep(0.01)
        self.speed.setDecimals(2)
        self.speed.setValue(cfg.get("video_speed", 1.03))
        fl_r.addRow(_lbl("Video speed"), self.speed)

        lay.addWidget(gb_r)
        lay.addStretch()

    def _on_preset(self, key: str):
        path = FONT_PRESETS.get(key, "")
        if path:
            self.font_path.setText(path)

    def _browse_font(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Chọn font", "C:/Windows/Fonts",
            "Font files (*.ttf *.ttc *.otf)"
        )
        if f:
            self.font_path.setText(f)

    def collect(self) -> dict:
        return {
            "title_color":       self.title_color_inp.text().strip(),
            "sub_fill_rgba":     self.fill_rgba.text().strip(),
            "max_words_per_line": self.max_words.value(),
            "sub_margin_v":      self.margin_v.value(),
            "sub_font_size":     self.font_size.value(),
            "font_title_file":   self.font_path.text().strip(),
            "video_speed":       self.speed.value(),
        }


class QuotaTab(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)

        # ── Usage summary ─────────────────────────────────────
        from src.presentation.widgets.status_bar import QuotaPill
        summary_frame = QFrame()
        summary_frame.setObjectName("card")
        sf_lay = QVBoxLayout(summary_frame)
        sf_lay.setSpacing(8)

        used  = cfg.get("quota_used_this_month", 0)
        limit = cfg.get("quota_monthly_limit", 600)

        self.used_lbl = QLabel(f"{used} / {limit} video đã render tháng này")
        self.used_lbl.setStyleSheet("font-size:18px; font-weight:500; color:#f5a820;")
        sf_lay.addWidget(self.used_lbl)

        from PyQt6.QtWidgets import QProgressBar
        self.usage_bar = QProgressBar()
        self.usage_bar.setRange(0, 100)
        pct = int(used / limit * 100) if limit else 0
        self.usage_bar.setValue(pct)
        self.usage_bar.setTextVisible(False)
        self.usage_bar.setFixedHeight(6)
        self.usage_bar.setStyleSheet(
            "QProgressBar{background:#1e2230;border-radius:3px;}"
            "QProgressBar::chunk{background:#f5a820;border-radius:3px;}"
        )
        sf_lay.addWidget(self.usage_bar)

        lay.addWidget(summary_frame)

        # ── Settings ──────────────────────────────────────────
        gb, fl = _group("Giới hạn")
        self.monthly_limit = QSpinBox()
        self.monthly_limit.setRange(1, 9999)
        self.monthly_limit.setSuffix(" video / tháng")
        self.monthly_limit.setValue(limit)
        fl.addRow(_lbl("Giới hạn tháng"), self.monthly_limit)

        self.warn_pct = QSpinBox()
        self.warn_pct.setRange(10, 99)
        self.warn_pct.setSuffix(" %")
        self.warn_pct.setValue(cfg.get("quota_warn_pct", 80))
        fl.addRow(_lbl("Cảnh báo khi đạt"), self.warn_pct)

        lay.addWidget(gb)

        # ── API ───────────────────────────────────────────────
        gb_api, fl_api = _group("API Keys")
        self.api_key = QLineEdit(cfg.get("gemini_api_key", ""))
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("AIzaSy...")
        fl_api.addRow(_lbl("Gemini API Key"), self.api_key)

        self.key_rotation = QCheckBox("Dùng key tiếp theo khi hết quota")
        self.key_rotation.setChecked(cfg.get("key_rotation", True))
        fl_api.addRow("", self.key_rotation)

        lay.addWidget(gb_api)
        lay.addStretch()

    def collect(self) -> dict:
        return {
            "quota_monthly_limit": self.monthly_limit.value(),
            "quota_warn_pct":      self.warn_pct.value(),
            "gemini_api_key":      self.api_key.text().strip(),
            "key_rotation":        self.key_rotation.isChecked(),
        }


# ── Main Dialog ──────────────────────────────────────────────────────────────

from PyQt6.QtWidgets import QStackedWidget, QListWidget # Nhớ import QStackedWidget

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cài đặt — AutoClip AI")
        # Tăng kích thước rộng rãi hơn
        self.setMinimumSize(780, 560)
        self.setModal(True)

        cfg = _load_config()

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 1. Cột Menu Trái (Side Nav) ──────────────────────────
        self.nav = QListWidget()
        self.nav.setObjectName("side_nav")
        self.nav.setFixedWidth(180)
        
        # Đã trừu tượng hóa các từ ngữ kỹ thuật
        nav_items = [
            "Chung",
            "Âm thanh (Giọng nói)",
            "Phân tích (AI)",
            "Khung hình (Crop)",
            "Phụ đề & Render",
            "Quota & Key"
        ]
        self.nav.addItems(nav_items)
        self.nav.setCurrentRow(0)

        # ── 2. Cột Nội Dung Phải ─────────────────────────────────
        content_wrapper = QWidget()
        content_wrapper.setStyleSheet("background-color: #12141a;")
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(24, 24, 24, 16)
        content_layout.setSpacing(16)

        self.stack = QStackedWidget()
        
        # Khởi tạo các Tab (Lưu ý: Bạn cũng nên vào các class Tab bên trên để đổi title Text tiếng Việt tương ứng)
        self.t_general = GeneralTab(cfg)
        self.t_step1   = Step1Tab(cfg)
        self.t_step2   = Step2Tab(cfg)
        self.t_step4   = Step4Tab(cfg)
        self.t_step5   = Step5Tab(cfg)
        self.t_quota   = QuotaTab(cfg)

        self.stack.addWidget(_make_scroll(self.t_general))
        self.stack.addWidget(_make_scroll(self.t_step1))
        self.stack.addWidget(_make_scroll(self.t_step2))
        self.stack.addWidget(_make_scroll(self.t_step4))
        self.stack.addWidget(_make_scroll(self.t_step5))
        self.stack.addWidget(_make_scroll(self.t_quota))

        # Nút chuyển trang
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        content_layout.addWidget(self.stack)

        # ── 3. Nút Lưu / Hủy ─────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        
        btn_cancel = QPushButton("Hủy")
        btn_cancel.setFixedWidth(90)
        btn_cancel.clicked.connect(self.reject)

        self.btn_save = QPushButton("Lưu cài đặt")
        self.btn_save.setObjectName("btn_primary")
        self.btn_save.setFixedWidth(130)
        self.btn_save.clicked.connect(self._save)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(self.btn_save)
        
        content_layout.addLayout(btn_row)

        # Gắn vào layout chính
        root.addWidget(self.nav)
        root.addWidget(content_wrapper)

    # Trong SettingsDialog._save()
    def _save(self):
        cfg = _load_config()
        for tab in (self.t_general, self.t_step1, ...):
            cfg.update(tab.collect())
        
        # Quota theo video
        cfg["quota_used_this_month"] = cfg.get("quota_used_this_month", 0)
        _save_config(cfg)
        bus.settings_saved.emit()