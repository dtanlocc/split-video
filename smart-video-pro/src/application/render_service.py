# src/application/render_service.py
from pathlib import Path
from src.domain.entities import RenderConfig
from src.infrastructure.video.renderer_impl import VideoRendererImpl


class RenderService:
    """
    Application Layer - Điều phối Final Render
    Chịu trách nhiệm gọi renderer để xuất video 9:16 có Title Area + Dynamic Crop
    """

    def __init__(self, renderer: VideoRendererImpl):
        self.renderer = renderer

    def render_all(self, input_dir: Path, output_dir: Path, config: RenderConfig = None):
        """
        Render tất cả video trong thư mục input thành video 9:16 final
        """
        if config is None:
            config = RenderConfig()

        video_count = len(list(input_dir.glob("*.mp4")))
        
        print(f"🎬 Bắt đầu Final Render ({video_count} video) → Định dạng 9:16")
        print(f"   • Title Area: ~19% chiều cao")
        print(f"   • Video Content: Dynamic crop theo chủ thể (YOLO)")
        print(f"   • Tốc độ: {config.video_speed}x | Max parallel: {config.max_parallel}\n")

        if video_count == 0:
            print("⚠️ Không tìm thấy video nào trong thư mục input.")
            return

        # Gọi renderer thực hiện render
        self.renderer.render_all(input_dir, output_dir, config)

        print(f"\n✅ Hoàn tất Final Render! Kết quả nằm tại: {output_dir.resolve()}")