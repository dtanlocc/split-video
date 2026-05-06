# src/domain/schemas.py
import platform
from pathlib import Path
from typing import Any, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field, model_validator


def _get_default_bold_font() -> str:
    system = platform.system()
    if system == "Windows":
        return str(Path("C:/Windows/Fonts/arialbd.ttf"))
    elif system == "Darwin":
        return "/System/Library/Fonts/HelveticaNeue.ttc"
    else:
        for p in [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/noto/NotoSans-Bold.ttf",
        ]:
            if Path(p).exists():
                return p
    return ""


class STTConfig(BaseModel):
    lang:         str = "vi"
    model:        str = "medium"
    device:       str = Field(default="cuda")
    compute_type: str = Field(default="float16")


class LLMConfig(BaseModel):
    # ★ Default 0 để dễ phát hiện khi không được set từ ngoài
    # Pipeline sẽ dùng fallback hợp lý nếu nhận 0
    min_duration_sec: int = 150
    max_duration_sec: int = 300
    model_name:       str = "gemini-2.5-flash"
    title_language:   Optional[str] = None


class GeminiConfig(LLMConfig):
    model_name: str = "gemini-2.5-flash"


class DeepSeekConfig(LLMConfig):
    model_name:        str   = "deepseek-chat"
    max_output_tokens: int   = 4096
    temperature:       float = 0.1


class CropConfig(BaseModel):
    output_size:      Tuple[int, int] = (1080, 1920)
    sharpen_strength: str             = "medium"
    enhance:          bool            = True
    crop_mode: Literal["square_1:1", "fill_9:16"] = "square_1:1"
    ffmpeg_codec:  str           = "h264_nvenc"
    ffmpeg_preset: str           = "p4"
    yolo_model:    Optional[str] = None
    batch_size:    Optional[int] = None


class RenderConfig(BaseModel):
    title_color:        str   = "#FFD700"
    sub_bg_color:       str   = "255, 0, 0, 160"
    font_title_file:    str   = Field(default_factory=_get_default_bold_font)
    video_speed:        float = 1.03
    max_words_per_line: int   = 3
    sub_margin_v:       int   = 250
    sub_font_size:      int   = 85
    max_parallel:       int   = 1


class RunPipelineRequest(BaseModel):
    video_path: str
    mode: Literal["full", "no-crop"]

    llm_backend: Literal["gemini", "deepseek"] = "gemini"
    gemini_api_key:   str       = ""
    gemini_api_keys:  List[str] = Field(default_factory=list)
    deepseek_api_key:  str       = ""
    deepseek_api_keys: List[str] = Field(default_factory=list)

    session_token: str
    hwid:          str

    stt_config:     STTConfig     = Field(default_factory=STTConfig)
    gemini_config:  GeminiConfig  = Field(default_factory=GeminiConfig)
    deepseek_config: DeepSeekConfig = Field(default_factory=DeepSeekConfig)
    crop_config:    CropConfig    = Field(default_factory=CropConfig)
    render_config:  RenderConfig  = Field(default_factory=RenderConfig)

    @model_validator(mode='before')
    @classmethod
    def pre_process(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # ── Normalize API keys ────────────────────────────────────────
        gemini_keys = [k.strip() for k in data.get("gemini_api_keys", []) if k.strip()]
        if not gemini_keys and data.get("gemini_api_key", "").strip():
            gemini_keys = [data["gemini_api_key"].strip()]
        data["gemini_api_keys"] = gemini_keys

        deepseek_keys = [k.strip() for k in data.get("deepseek_api_keys", []) if k.strip()]
        if not deepseek_keys and data.get("deepseek_api_key", "").strip():
            deepseek_keys = [data["deepseek_api_key"].strip()]
        data["deepseek_api_keys"] = deepseek_keys

        # ── ★ FIX: Đồng bộ min/max duration vào CẢ HAI config ────────
        # Rust gửi min_duration_sec trong gemini_config.
        # DeepSeekConfig kế thừa LLMConfig nên cũng cần nhận giá trị này.
        #
        # Lấy min/max từ gemini_config (nơi Rust luôn ghi vào)
        g_cfg = data.get("gemini_config", {})
        min_sec = g_cfg.get("min_duration_sec", 150)
        max_sec = g_cfg.get("max_duration_sec", 300)

        # Đảm bảo là int hợp lệ (tránh null/None từ JSON)
        try:
            min_sec = int(min_sec) if min_sec else 150
            max_sec = int(max_sec) if max_sec else 300
        except (TypeError, ValueError):
            min_sec, max_sec = 150, 300

        # Ghi vào gemini_config
        data.setdefault("gemini_config", {})
        data["gemini_config"]["min_duration_sec"] = min_sec
        data["gemini_config"]["max_duration_sec"] = max_sec

        # ★ Ghi vào deepseek_config — đây là chỗ bị thiếu trước đây
        data.setdefault("deepseek_config", {})
        data["deepseek_config"]["min_duration_sec"] = min_sec
        data["deepseek_config"]["max_duration_sec"] = max_sec

        # Giữ title_language nhất quán
        title_lang = g_cfg.get("title_language") or data.get("deepseek_config", {}).get("title_language")
        if title_lang:
            data["gemini_config"]["title_language"]   = title_lang
            data["deepseek_config"]["title_language"]  = title_lang

        return data

    def get_min_sec(self) -> int:
        """Helper: lấy min_duration_sec theo backend đang dùng."""
        if self.llm_backend == "deepseek":
            return self.deepseek_config.min_duration_sec
        return self.gemini_config.min_duration_sec

    def get_max_sec(self) -> int:
        """Helper: lấy max_duration_sec theo backend đang dùng."""
        if self.llm_backend == "deepseek":
            return self.deepseek_config.max_duration_sec
        return self.gemini_config.max_duration_sec


class AppConfig(BaseModel):
    gemini_api_key:       str       = ""
    gemini_api_keys:      List[str] = Field(default_factory=list)
    license_key:          str       = ""
    lang_code:            str       = "en"
    whisper_model:        str       = "medium"
    whisper_device:       str       = "cuda"
    whisper_compute_type: str       = "float16"
    min_duration:         int       = 150
    max_duration:         int       = 300
    sharpen_strength:     str       = "medium"
    title_color:          str       = "#FFD700"
    sub_bg_color:         str       = "255, 0, 0, 160"
    max_words_per_line:   int       = 3
    sub_margin_v:         int       = 250
    sub_font_size:        int       = 85
    max_parallel:         int       = 1
    video_speed:          float     = 1.03
    font_title_file:      str       = Field(default_factory=_get_default_bold_font)


class ProgressEvent(BaseModel):
    stage: Literal[
        "init", "audio", "stt", "ai", "cut", "crop", "render", "complete"
    ]
    pct:    int            = Field(ge=0, le=100)
    status: Literal["inf", "ok", "err", "warn"]
    msg:    str
    meta:   Optional[dict] = None

    def to_json(self) -> str:
        return self.model_dump_json(ensure_ascii=False)