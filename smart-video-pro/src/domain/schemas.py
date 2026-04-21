# src/domain/schemas.py
from pydantic import BaseModel, Field
from typing import Literal, Tuple

class STTConfig(BaseModel):
    lang: str = Field(default="vi", description="Mã ngôn ngữ ISO")
    model: Literal["base", "small", "medium", "large-v3"] = "medium"

class GeminiConfig(BaseModel):
    min_duration_sec: int = Field(ge=10, default=150)
    max_duration_sec: int = Field(le=600, default=300)
    model_name: Literal["gemini-2.5-flash", "gemini-2.0-pro"] = "gemini-2.5-flash"

class CropConfig(BaseModel):
    output_size: Tuple[int, int] = (1080, 1920)
    detect_every: int = 15
    sharpen_strength: Literal["low", "medium", "high"] = "medium"
    enhance: bool = True

class RenderConfig(BaseModel):
    title_color: str = "#FFD700"
    sub_bg_color: str = "255, 0, 0, 160"
    font_title_file: str = r"C:\Windows\Fonts\arialbd.ttf"
    video_speed: float = 1.03
    max_words_per_line: int = 3
    sub_margin_v: int = 250
    sub_font_size: int = 85

# Khối Request Tổng nhận từ UI -> Python
class RunPipelineRequest(BaseModel):
    video_path: str
    mode: Literal["full", "no-crop"]
    gemini_api_key: str = Field(..., description="Key bắt buộc phải có")
    stt_config: STTConfig
    gemini_config: GeminiConfig
    crop_config: CropConfig
    render_config: RenderConfig