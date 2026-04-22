from pydantic import BaseModel, Field

class AppConfig(BaseModel):
    # API Keys & License
    gemini_api_key: str = Field(default="", description="Key nhập từ UI")
    license_key: str = Field(default="", description="Mã kích hoạt phần mềm")
    
    # B1 & B2 Config
    lang_code: str = "vi"
    whisper_model: str = "medium"
    min_duration: int = 150
    max_duration: int = 300
    
    # B4 Config
    sharpen_strength: str = "medium"
    
    # B5 Config
    title_color: str = "#FFD700"
    sub_bg_color: str = "255, 0, 0, 160"
    max_words_per_line: int = 3
    sub_margin_v: int = 250
    sub_font_size: int = 85
    max_parallel: int = 1
    font_title_file: str = "C:/Windows/Fonts/arialbd.ttf"