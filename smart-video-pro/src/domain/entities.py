# src/domain/entities.py
"""
Domain models - Core business entities của dự án.
Không phụ thuộc vào bất kỳ thư viện bên ngoài nào (No dependencies).
"""

from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Tuple


@dataclass(slots=True)
class SubtitleSegment:
    """Đoạn subtitle từ Whisper"""
    index: int
    start: float
    end: float
    text: str

    @staticmethod
    def parse_time(t: float) -> str:
        """Định dạng thời gian chuẩn SRT (giống code gốc của bạn)"""
        h = int(t // 3600)
        t -= h * 3600
        m = int(t // 60)
        t -= m * 60
        s = int(t)
        ms = int((t - s) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    def to_srt_format(self) -> str:
        """Xuất ra định dạng SRT chuẩn"""
        return (
            f"{self.index}\n"
            f"{self.parse_time(self.start)} --> {self.parse_time(self.end)}\n"
            f"{self.text}\n\n"
        )


@dataclass(slots=True)
class VideoSegment:
    """Phân đoạn video chuẩn hóa"""
    id: str
    start_time: float
    end_time: float
    text_content: str
    metadata: Optional[Dict] = None


@dataclass(slots=True)
class HighlightSegment:
    """Đoạn highlight sau khi Gemini phân tích"""
    start: str
    end: str
    title: str = ""
    text_chunk: str = ""


@dataclass(slots=True)
class DetectionResult:
    """Kết quả từ YOLO B4"""
    frame_idx: int
    label: str
    confidence: float
    box: Tuple[float, float, float, float]   # x1, y1, x2, y2
    center: Tuple[float, float]


@dataclass(slots=True)
class CropConfig:
    """Cấu hình crop cho YOLO B4"""
    output_size: Tuple[int, int] = (720, 720)
    detect_every: int = 15
    sharpen_strength: str = "medium"
    ratio: Tuple[int, int] = (1, 1)
    enhance: bool = True               # CLAHE + unsharp mask sau khi crop  ← thêm dòng này

@dataclass(slots=True)
class AudioConfig:
    """Cấu hình audio extraction"""
    sample_rate: int = 16000
    channels: int = 1
    codec: str = "pcm_s16le"
    format: str = "wav"


@dataclass(slots=True)
class RenderConfig:
    """Cấu hình render final video (Bước cuối)"""
    output_size: Tuple[int, int] = (1080, 1920)   # Vertical 9:16
    video_speed: float = 1.03
    max_words_per_line: int = 3
    sub_font_size: int = 85
    sub_margin_v: int = 450
    title_color: str = "#FFD700"
    font_title: str = r"C:\Windows\Fonts\arialbd.ttf"
    font_sub: str = "Impact"
    max_parallel: int = 1


# Helper method để chuyển dataclass sang dict (dùng khi cần serialize JSON)
def to_dict(obj) -> dict:
    """Chuyển dataclass thành dict"""
    return asdict(obj)