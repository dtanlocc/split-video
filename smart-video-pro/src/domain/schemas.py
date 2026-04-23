# src/domain/schemas.py
import platform
from pathlib import Path
from typing import Literal, Optional, Tuple
from pydantic import BaseModel, Field


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


class GeminiConfig(BaseModel):
    min_duration_sec: int = 150
    max_duration_sec: int = 300
    model_name:       str = "gemini-2.5-flash"


class CropConfig(BaseModel):
    output_size:      Tuple[int, int] = (1080, 1920)
    sharpen_strength: str             = "medium"
    enhance:          bool            = True
    crop_mode: Literal["square_1:1", "fill_9:16"] = "square_1:1"
    
        # 🔥 Thêm field mới cho FFmpeg adaptive config
    ffmpeg_codec: str = "h264_nvenc"  # "h264_nvenc" hoặc "libx264"
    ffmpeg_preset: str = "p4"         # "fast", "p2", "p4", "p6", "p7"
    
    # Optional fields cho tương lai
    yolo_model: Optional[str] = None  # Override model path nếu cần
    batch_size: Optional[int] = None  # Override batch size nếu cần


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
    video_path:     str
    mode:           Literal["full", "no-crop"]
    gemini_api_key: str

    # ★ Security fields — bắt buộc phải có
    session_token:  str
    hwid:           str

    stt_config:     STTConfig    = Field(default_factory=STTConfig)
    gemini_config:  GeminiConfig = Field(default_factory=GeminiConfig)
    crop_config:    CropConfig   = Field(default_factory=CropConfig)
    render_config:  RenderConfig = Field(default_factory=RenderConfig)


class AppConfig(BaseModel):
    gemini_api_key:       str   = ""
    license_key:          str   = ""
    lang_code:            str   = "vi"
    whisper_model:        str   = "medium"
    whisper_device:       str   = "cuda"
    whisper_compute_type: str   = "float16"
    min_duration:         int   = 150
    max_duration:         int   = 300
    sharpen_strength:     str   = "medium"
    title_color:          str   = "#FFD700"
    sub_bg_color:         str   = "255, 0, 0, 160"
    max_words_per_line:   int   = 3
    sub_margin_v:         int   = 250
    sub_font_size:        int   = 85
    max_parallel:         int   = 1
    video_speed:          float = 1.03
    font_title_file:      str   = Field(default_factory=_get_default_bold_font)