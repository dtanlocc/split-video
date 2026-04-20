# src/infrastructure/ai/whisper_impl.py
import os
import re
import gc
import av
import torch
from pathlib import Path
from faster_whisper import WhisperModel
from src.domain.entities import SubtitleSegment

class WhisperTranscriber:
    def __init__(self, model_size="small"):
        self.model_size = model_size
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.compute_type = "float16" if self.device == "cuda" else "float32"
        self.nb_threads = 1
        self.model = None

    def _av_get_duration(self, file_path: str) -> float:
        """Hàm hỗ trợ từ custom_widgets của bạn - GIỮ NGUYÊN"""
        try:
            with av.open(file_path) as container:
                if container.duration:
                    return container.duration / 1e6
                return 0.0
        except Exception as e:
            print(f"[WARN] Error reading duration: {e}")
            return 0.0

    def load_model(self):
        if self.model is None:
            # Khởi tạo model đúng thông số hardcode của bạn
            self.model = WhisperModel(
                model_size_or_path=self.model_size, 
                device=self.device, 
                compute_type=self.compute_type, 
                cpu_threads=self.nb_threads
            )

    def transcribe(self, audio_path: str, lang: str = "zh") -> list[SubtitleSegment]:
        self.load_model()
        
        # Lấy duration để check file trống như logic của bạn
        duration = self._av_get_duration(audio_path)
        if duration <= 0:
            return []

        gc.collect() # Dọn RAM trước khi chạy file mới như logic của bạn
        results = []

        try:
            # MỞ FILE BINARY ĐÚNG NHƯ LOGIC GỐC CỦA BẠN
            with open(audio_path, "rb") as binary_file:
                # GỌI MODEL VỚI CẤU HÌNH Y HỆT BẢN GỐC
                segments, info = self.model.transcribe(
                    binary_file, 
                    word_timestamps=False, 
                    vad_filter=True, 
                    language=lang,
                )

                # BÓC TÁCH TỪNG CÂU (SEGMENT)
                for segm in segments:
                    raw_text = getattr(segm, "text", "") or ""
                    start = float(getattr(segm, "start", 0.0))
                    end = float(getattr(segm, "end", 0.0))

                    # Logic Clean bằng Regex chuẩn 100% của bạn
                    clean = raw_text.strip()
                    clean = re.sub(r'^[^\w\u4e00-\u9fff]+', '', clean)
                    clean = re.sub(r'[^\w\u4e00-\u9fff]+$', '', clean)
                    
                    if clean:
                        # Index tự tăng để ghi SRT
                        results.append(SubtitleSegment(
                            index=len(results) + 1,
                            start=start,
                            end=end,
                            text=clean
                        ))
            return results
        except Exception as e:
            print(f"❌ Lỗi: {e}")
            return []

    def release_resources(self):
        if self.model:
            del self.model
            self.model = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()