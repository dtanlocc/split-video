# src/infrastructure/ai/whisper_impl.py
import re
import gc
import av
import torch
from pathlib import Path
from typing import List
from faster_whisper import WhisperModel

from src.domain.entities import SubtitleSegment


class WhisperTranscriber:
    """
    B1: Whisper Voice Transcription
    Được chỉnh sửa để giống nhất logic SpeechToTextCLI (CPU + int8 mode)
    """

    def __init__(self, model_size: str = "medium", device: str = "cuda", compute_type: str = "int8"):
        self.model_size = model_size
        self.device = device                     # ← LẤY TỪ CONFIG
        self.compute_type = compute_type         # ← LẤY TỪ CONFIG
        self.nb_threads = 8 if device == "cpu" else 1
        self.model = None
        self._load_model()

    def _load_model(self):
        """Giống hệt phần __init__ của SpeechToTextCLI"""
        print(f"--- INITIALIZING WHISPER ---", flush=True)
        print(f"Model: {self.model_size}")
        print(f"Device: {self.device} ({self.compute_type}) with {self.nb_threads} Threads")
        
        self.model = WhisperModel(
            model_size_or_path=self.model_size,
            device=self.device,
            compute_type=self.compute_type,
            # cpu_threads=self.nb_threads
        )
        print("✅ Model loaded successfully.\n")

    def _av_get_duration(self, file_path: str) -> float:
        """Giống 100% hàm av_get_duration gốc"""
        try:
            with av.open(file_path) as container:
                if container.duration:
                    return container.duration / 1e6
                return 0.0
        except Exception as e:
            print(f"[WARN] Error reading duration: {e}")
            return 0.0

    def _clean_text(self, raw_text: str) -> str:
        """Clean giống hệt trong process_audio()"""
        clean = raw_text.strip()
        clean = re.sub(r'^[^\w\u4e00-\u9fff]+', '', clean)
        clean = re.sub(r'[^\w\u4e00-\u9fff]+$', '', clean)
        return clean.strip()

    def transcribe(self, audio_path: str, lang: str = "zh") -> List[SubtitleSegment]:
        """
        Logic giống hệt process_audio() trong code gốc bạn đưa
        """
        duration = self._av_get_duration(audio_path)
        if duration <= 0:
            print(f"[SKIP] {Path(audio_path).name} is empty (0 duration).")
            return []

        gc.collect()   # Dọn RAM trước khi chạy

        results: List[SubtitleSegment] = []

        try:
            print(f"Transcribing: {Path(audio_path).name} (Duration: {duration:.2f}s)")
            print("  -> Đang nhận diện giọng nói (Segment Mode)...")

            with open(audio_path, "rb") as binary_file:
                # GỌI TRANSCRIBE GIỐNG HỆT CODE GỐC
                segments, info = self.model.transcribe(
                    binary_file,
                    word_timestamps=False,
                    vad_filter=True,
                    language=lang,                    # Mặc định "zh" như code gốc
                )

                print(f"  -> Ngôn ngữ nhận diện: {getattr(info, 'language', 'unknown')}")

                # XỬ LÝ SEGMENT GIỐNG HỆT
                for segm in segments:
                    raw_text = getattr(segm, "text", "") or ""
                    start = float(getattr(segm, "start", 0.0))
                    end = float(getattr(segm, "end", 0.0))

                    clean = self._clean_text(raw_text)

                    if clean:
                        results.append(SubtitleSegment(
                            index=len(results) + 1,
                            start=start,
                            end=end,
                            text=clean
                        ))

                print(f"  -> ✅ Thành công! Lấy được {len(results)} câu sub.")

        except Exception as e:
            print(f"❌ Lỗi nghiêm trọng khi transcribe {Path(audio_path).name}: {e}")

        return results

    def release_resources(self):
        """Giải phóng tài nguyên an toàn để tránh treo Thread"""
        try:
            if self.model:
                # Không dùng 'del', chỉ cần gán None để giảm reference count
                self.model = None 
            
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            # TUYỆT ĐỐI KHÔNG gọi gc.collect() ở đây
            print("🧹 Đã giải phóng Whisper (VRAM cleaned).", flush=True)
        except Exception as e:
            print(f"⚠️ Cảnh báo dọn dẹp: {e}", flush=True)