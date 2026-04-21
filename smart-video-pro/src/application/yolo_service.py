# src/application/yolo_service.py
from pathlib import Path
from src.domain.interfaces import IYOLOCropper
from src.domain.entities import CropConfig

class YOLOService:
    """Application Layer - Orchestrator cho B4"""
    
    def __init__(self, yolo_cropper: IYOLOCropper):
        self.cropper = yolo_cropper

    def crop_highlights(self, video_path: Path, output_dir: Path, config: CropConfig = None):
        """Use Case chính"""
        if config is None:
            config = CropConfig()
            
        print(f"🎯 B4: Bắt đầu YOLO Smart Crop → {video_path.name}")
        self.cropper.process_video(video_path, output_dir, config)
        self.cropper.release_resources()