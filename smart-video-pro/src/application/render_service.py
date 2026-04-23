# src/application/render_service.py
from pathlib import Path
from src.domain.schemas import RenderConfig
from src.infrastructure.video.renderer_impl import VideoRendererImpl
import os
import psutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

class RenderService:
    """
    Application Layer - Điều phối Final Render
    Chịu trách nhiệm gọi renderer để xuất video 9:16 có Title Area + Dynamic Crop
    """

    def __init__(self, renderer: VideoRendererImpl):
        self.renderer = renderer

    def render_all(self, input_dir: Path, output_dir: Path, config: RenderConfig = None):
        videos = list(input_dir.glob("*.mp4"))
        if not videos:
            print("⚠️ Không tìm thấy video nào.")
            return

        # 🔥 Auto-detect max parallel dựa trên CPU cores + RAM
        cpu_cores = os.cpu_count() or 4
        ram_gb = psutil.virtual_memory().total / (1024**3) if 'psutil' in sys.modules else 8
        # Rule: 1 worker per 2 cores, tối đa 4, tối thiểu 1
        max_workers = min(4, max(1, cpu_cores // 2))
        # Giảm nếu RAM thấp (<8GB → max 2 workers)
        if ram_gb < 8:
            max_workers = min(max_workers, 2)
        
        print(f"🚀 Bắt đầu render {len(videos)} video với {max_workers} workers...", flush=True)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit tất cả tasks
            futures = {
                executor.submit(self.renderer.process_single_video, video, output_dir, config): video 
                for video in videos
            }
            
            # Wait và log progress
            for i, future in enumerate(as_completed(futures), 1):
                video = futures[future]
                try:
                    future.result()  # Reraise exception nếu có
                    print(f"✅ [{i}/{len(videos)}] Xong: {video.name}", flush=True)
                except Exception as e:
                    print(f"❌ [{i}/{len(videos)}] Lỗi {video.name}: {e}", flush=True)
                    # Continue với video khác, không dừng toàn bộ
        
        print(f"\n✅ Hoàn tất Final Render! Kết quả: {output_dir.resolve()}", flush=True)