"""Domain models (VideoSegment, DetectionBox) - No dependencies."""
# src/domain/entities.py
from dataclasses import dataclass, asdict
from typing import List, Optional

@dataclass(slots=True)
class VideoSegment:
    """Định nghĩa một phân đoạn video chuẩn hóa"""
    id: str
    start_time: float
    end_time: float
    text_content: str
    metadata: Optional[dict] = None

@dataclass(slots=True)
class DetectionResult:
    """Kết quả từ YOLO B4"""
    frame_idx: int
    label: str
    confidence: float
    box: tuple[float, float, float, float] # x1, y1, x2, y2

@dataclass(slots=True)
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    codec: str = "pcm_s16le"
    format: str = "wav"
    
@dataclass(slots=True)
class HighlightSegment:
    start: str
    end: str
    title: str = ""
    text_chunk: str = ""
    
# src/domain/entities.py
from dataclasses import dataclass

@dataclass(slots=True)
class SubtitleSegment:
    index: int
    start: float
    end: float
    text: str

    @staticmethod
    def parse_time(t: float) -> str:
        """Logic định dạng thời gian của bạn"""
        h = int(t // 3600)
        t -= h * 3600
        m = int(t // 60)
        t -= m * 60
        s = int(t)
        ms = int((t - s) * 1000) # Ép kiểu int để ra đúng 3 chữ số miligiây
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    def to_srt_format(self) -> str:
        return f"{self.index}\n{self.parse_time(self.start)} --> {self.parse_time(self.end)}\n{self.text}\n\n"