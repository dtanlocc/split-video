# src/domain/entities.py
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Tuple

@dataclass(slots=True)
class SubtitleSegment:
    """Đoạn subtitle nhận diện từ AI Voice"""
    index: int
    start: float
    end: float
    text: str

    @staticmethod
    def parse_time(t: float) -> str:
        """Định dạng thời gian chuẩn SRT"""
        h = int(t // 3600)
        t -= h * 3600
        m = int(t // 60)
        t -= m * 60
        s = int(t)
        ms = int((t - s) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    def to_srt_format(self) -> str:
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
    """Đoạn highlight sau khi LLM phân tích"""
    start: str
    end: str
    title: str = ""
    text_chunk: str = ""

@dataclass(slots=True)
class DetectionResult:
    """Kết quả bounding box từ YOLO"""
    frame_idx: int
    label: str
    confidence: float
    box: Tuple[float, float, float, float]   # x1, y1, x2, y2
    center: Tuple[float, float]

def to_dict(obj) -> dict:
    """Helper: Chuyển dataclass thành dict để serialize"""
    return asdict(obj)

@dataclass(slots=True)
class AudioConfig:
    """Cấu hình audio extraction"""
    sample_rate: int = 16000
    channels: int = 1
    codec: str = "pcm_s16le"
    format: str = "wav"