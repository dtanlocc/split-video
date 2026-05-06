"""
render_service.py - STABLE SEQUENTIAL RENDERING
✅ Whisper model được load 1 lần trước khi render, tránh race condition
✅ max_workers=1 để đảm bảo ổn định (Whisper + VRAM không thread-safe)
✅ Exception được re-raise để caller biết video nào thực sự thất bại
"""
from pathlib import Path
from src.domain.schemas import RenderConfig
from src.infrastructure.video.renderer_impl import VideoRendererImpl
import os
import sys
import torch
from concurrent.futures import ThreadPoolExecutor, as_completed


class RenderService:
    def __init__(self, renderer: VideoRendererImpl):
        self.renderer = renderer

    def render_all(
        self,
        input_dir: Path,
        output_dir: Path,
        config: RenderConfig = None,
        lang_code: str = "en",
    ):
        videos = list(input_dir.glob("*.mp4"))
        if not videos:
            print("⚠️ Không tìm thấy video nào.", flush=True)
            return

        # ── Pre-load Whisper model 1 lần duy nhất, trước khi spawn thread ──────
        # Lý do: _load_whisper() dùng `if self.whisper_model is not None: return`
        # nhưng khi nhiều thread chạy song song, check này không thread-safe.
        # Load trước ở đây thì mọi thread đều thấy model đã sẵn sàng.
        whisper_model_name = getattr(config, "whisper_model", "small") if config else "small"
        self.renderer._load_whisper(whisper_model_name)

        # ── Tính max_workers ────────────────────────────────────────────────────
        # Whisper + GPU rendering KHÔNG thread-safe:
        # - stable-whisper dùng CUDA context không chia sẻ được giữa threads
        # - VRAM bị chia sẻ không kiểm soát khi chạy song song
        # → Luôn dùng max_workers=1, tôn trọng config.max_parallel nếu người dùng
        #   muốn thử nghiệm nhưng cảnh báo rõ ràng.
        config_parallel = getattr(config, "max_parallel", 1) if config else 1

        if config_parallel > 1:
            print(
                f"⚠️ max_parallel={config_parallel} nhưng Whisper/GPU rendering "
                f"không thread-safe. Buộc về 1 để tránh mất video.",
                flush=True,
            )
        max_workers = 1  # Giữ cứng = 1

        vram_gb = 0
        if torch.cuda.is_available():
            vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3

        print(
            f"🚀 Bắt đầu render {len(videos)} video với {max_workers} worker(s)...",
            flush=True,
        )
        print(f"   VRAM: {vram_gb:.1f}GB", flush=True)

        success_count = 0
        fail_count = 0

        # ── Sequential render (ThreadPoolExecutor với 1 worker = tuần tự + future API) ──
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self._render_one, video, output_dir, config, lang_code
                ): video
                for video in videos
            }

            for i, future in enumerate(as_completed(futures), 1):
                video = futures[future]
                try:
                    future.result()  # Re-raises nếu có exception
                    success_count += 1
                    print(f"✅ [{i}/{len(videos)}] Xong: {video.name}", flush=True)
                except Exception as e:
                    fail_count += 1
                    print(
                        f"❌ [{i}/{len(videos)}] Lỗi {video.name}: {e}",
                        flush=True,
                    )

                # Clear VRAM sau mỗi video
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

        print(
            f"\n✅ Hoàn tất Final Render! "
            f"{success_count} thành công, {fail_count} thất bại. "
            f"Kết quả: {output_dir.resolve()}",
            flush=True,
        )

    def _render_one(
        self,
        video: Path,
        output_dir: Path,
        config: RenderConfig,
        lang_code: str,
    ):
        """
        Wrapper gọi process_single_video và đảm bảo exception được propagate.
        
        VideoRendererImpl.process_single_video() bắt tất cả exception và chỉ print()
        → caller không biết video có thực sự thành công không.
        
        Fix: kiểm tra output file tồn tại sau khi chạy xong.
        Nếu không có file output → coi là thất bại và raise exception.
        """
        expected_output = output_dir / f"{video.stem}.mp4"

        # Gọi renderer (nó tự bắt exception bên trong)
        self.renderer.process_single_video(video, output_dir, config, lang_code)

        # Kiểm tra output thực sự tồn tại
        if not expected_output.exists():
            raise RuntimeError(
                f"process_single_video hoàn thành nhưng không tạo ra file: "
                f"{expected_output.name}. "
                f"Kiểm tra log phía trên để tìm nguyên nhân."
            )