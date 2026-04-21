"""Abstract classes for Dependency Inversion."""
# src/domain/interfaces.py
from abc import ABC, abstractmethod
from typing import List

from .entities import VideoSegment

class ILLMProvider(ABC):
    @abstractmethod
    def analyze_highlights(self, transcript: str) -> list[dict]:
        pass

    @abstractmethod
    def generate_title(self, text_chunk: str, language: str) -> str:
        pass
    
class IVideoProcessor(ABC):
    @abstractmethod
    def process(self, video_path: str) -> List[VideoSegment]:
        pass

class IResourceManaged(ABC):
    """Rule: Mọi class dùng GPU phải có khả năng giải phóng bộ nhớ"""
    @abstractmethod
    def release_resources(self):
        pass
    
from abc import ABC, abstractmethod
from pathlib import Path
from .entities import CropConfig

class IYOLOCropper(ABC):
    """Interface cho B4"""
    
    @abstractmethod
    def process_video(self, video_path: Path, output_dir: Path, config: CropConfig = None):
        pass

    @abstractmethod
    def release_resources(self):
        pass