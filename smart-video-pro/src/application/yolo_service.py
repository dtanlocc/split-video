from pathlib import Path
from src.domain.interfaces import IYOLOCropper
from src.domain.schemas import CropConfig

class YOLOService:
    """Application Layer - Orchestrator cho B4"""
    
    def __init__(self, yolo_cropper: IYOLOCropper):
        self.cropper = yolo_cropper

    def crop_highlights(self, video_path: Path, output_dir: Path, config: CropConfig = None):
        """Use Case chính"""
        if config is None:
            config = CropConfig()
            
        # print đã được tắt để tránh rác Terminal UI, chỉ gửi tín hiệu ngầm
        self.cropper.process_video(video_path, output_dir, config)
        
        # ĐÃ BỎ DÒNG NÀY: Không xoá YOLO model ở đây. Ta giữ nó trên VRAM để xử lý video tiếp theo cho lẹ.
        # Xoá ở file pipeline_manager.py lúc đã chạy xong toàn bộ list.