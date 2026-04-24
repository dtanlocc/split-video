"""
render_service.py - OPTIMIZED PARALLEL RENDERING
✅ Auto-detect workers dựa trên GPU + RAM
✅ Giới hạn workers để không tràn VRAM
"""
from pathlib import Path
from src.domain.schemas import RenderConfig
from src.infrastructure.video.renderer_impl import VideoRendererImpl
import os
import psutil
import sys
import torch
from concurrent.futures import ThreadPoolExecutor, as_completed

class RenderService:
    def __init__(self, renderer: VideoRendererImpl):
        self.renderer = renderer

    def render_all(self, input_dir: Path, output_dir: Path, config: RenderConfig = None):
        videos = list(input_dir.glob("*.mp4"))
        if not videos:
            print("⚠️ Không tìm thấy video nào.")
            return

        # 🔥 Auto-detect max parallel dựa trên GPU VRAM + RAM
        cpu_cores = os.cpu_count() or 4
        ram_gb = psutil.virtual_memory().total / (1024**3)
        
        # 🔥 Kiểm tra VRAM nếu có GPU
        vram_gb = 0
        if torch.cuda.is_available():
            vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
        
        # Rule: 
        # - Nếu có GPU >= 8GB: 4 workers
        # - Nếu có GPU 4-8GB: 2 workers
        # - Nếu có GPU < 4GB hoặc CPU only: 1-2 workers
        if vram_gb >= 8:
            max_workers = min(4, cpu_cores // 2)
        elif vram_gb >= 4:
            max_workers = min(2, cpu_cores // 2)
        else:
            max_workers = 1
        
        # Giảm nếu RAM thấp (<8GB → max 2 workers)
        if ram_gb < 8:
            max_workers = min(max_workers, 2)
        
        print(f"🚀 Bắt đầu render {len(videos)} video với {max_workers} workers...", flush=True)
        print(f"   RAM: {ram_gb:.1f}GB | VRAM: {vram_gb:.1f}GB", flush=True)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.renderer.process_single_video, video, output_dir, config): video 
                for video in videos
            }
            
            for i, future in enumerate(as_completed(futures), 1):
                video = futures[future]
                try:
                    future.result()
                    print(f"✅ [{i}/{len(videos)}] Xong: {video.name}", flush=True)
                    
                    # 🔥 Clear cache sau mỗi video
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        
                except Exception as e:
                    print(f"❌ [{i}/{len(videos)}] Lỗi {video.name}: {e}", flush=True)
        
        print(f"\n✅ Hoàn tất Final Render! Kết quả: {output_dir.resolve()}", flush=True)