# src/infrastructure/utils/hardware_profiler.py
import os
import platform
import psutil
import torch
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class HardwareProfile:
    os_name: str
    cpu_cores: int
    ram_gb: float
    has_gpu: bool
    gpu_name: str
    vram_gb: float
    is_low_end: bool
    config: Dict[str, Any]

def detect_hardware() -> HardwareProfile:
    os_name = platform.system()
    cpu_cores = os.cpu_count() or 4
    ram_gb = psutil.virtual_memory().total / (1024**3)
    
    has_gpu = False
    gpu_name = "CPU"
    vram_gb = 0.0
    
    try:
        if torch.cuda.is_available():
            has_gpu = True
            gpu_name = torch.cuda.get_device_name(0)
            vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    except Exception:
        pass  # Driver lỗi → fallback CPU an toàn

    is_low_end = (not has_gpu) or (vram_gb < 4.0) or (ram_gb < 8.0)

    # 🎯 Bảng cấu hình thích ứng
    if not has_gpu:
        cfg = {"yolo_model": "yolov8n.pt", "batch_size": 1, "use_half": False, 
               "queue_raw": 16, "queue_result": 16, "ffmpeg_codec": "libx264", "ffmpeg_preset": "fast"}
    elif vram_gb < 4.0:
        cfg = {"yolo_model": "yolov8n.pt", "batch_size": 2, "use_half": False, 
               "queue_raw": 24, "queue_result": 24, "ffmpeg_codec": "h264_nvenc", "ffmpeg_preset": "p4"}
    elif vram_gb < 6.0:
        cfg = {"yolo_model": "yolov8n.pt", "batch_size": 4, "use_half": True, 
               "queue_raw": 48, "queue_result": 32, "ffmpeg_codec": "h264_nvenc", "ffmpeg_preset": "p4"}
    elif vram_gb < 8.0:
        cfg = {"yolo_model": "yolov8n.pt", "batch_size": 6, "use_half": True, 
               "queue_raw": 64, "queue_result": 48, "ffmpeg_codec": "h264_nvenc", "ffmpeg_preset": "p5"}
    else:
        cfg = {"yolo_model": "yolov8n.pt", "batch_size": 8, "use_half": True, 
               "queue_raw": 128, "queue_result": 64, "ffmpeg_codec": "h264_nvenc", "ffmpeg_preset": "p6"}

    # RAM thấp → giảm queue/batch tránh OOM hệ thống
    if ram_gb < 6.0:
        cfg["queue_raw"] = max(16, cfg["queue_raw"] // 2)
        cfg["batch_size"] = max(1, cfg["batch_size"] // 2)

    return HardwareProfile(
        os_name=os_name, cpu_cores=cpu_cores, ram_gb=round(ram_gb, 1),
        has_gpu=has_gpu, gpu_name=gpu_name, vram_gb=round(vram_gb, 1),
        is_low_end=is_low_end, config=cfg
    )