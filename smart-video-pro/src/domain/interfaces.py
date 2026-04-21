# src/domain/interfaces.py
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from .entities import VideoSegment, SubtitleSegment, HighlightSegment
from .schemas import CropConfig, RenderConfig

# --- BASE INTERFACES ---
class IResourceManaged(ABC):
    """Rule: Mọi class dùng GPU/RAM nặng phải có khả năng giải phóng bộ nhớ"""
    @abstractmethod
    def release_resources(self) -> None:
        pass

# --- AI & LLM INTERFACES ---
class ILLMProvider(ABC):
    @abstractmethod
    def analyze_highlights(self, transcript: str) -> List[HighlightSegment]:
        pass

    @abstractmethod
    def generate_title(self, text_chunk: str, language: str) -> str:
        pass

class ITranscriber(IResourceManaged):
    @abstractmethod
    def transcribe(self, audio_path: str, lang: str) -> List[SubtitleSegment]:
        pass

# --- VIDEO PROCESSING INTERFACES ---
class IYOLOCropper(IResourceManaged):
    """Interface cho B4 - YOLO Crop (Đã kế thừa tính năng dọn RAM)"""
    @abstractmethod
    def process_video(self, video_path: Path, output_dir: Path, config: CropConfig) -> None:
        pass

class IVideoRenderer(ABC):
    """Interface cho B5 - Render Subtitles"""
    @abstractmethod
    def render_all(self, input_dir: Path, output_dir: Path, config: RenderConfig) -> None:
        pass

# --- DATABASE / LICENSING INTERFACES ---
class ILicenseRepository(ABC):
    @abstractmethod
    def get_license(self, key: str):
        pass
    
    @abstractmethod
    def update_usage(self, key: str, hardware_id: str, used_amount: int) -> bool:
        pass