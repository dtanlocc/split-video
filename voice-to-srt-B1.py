import os
import sys
import re
import gc
import av # Thư viện PyAV từ custom_widgets của bạn
import torch
from pathlib import Path
from typing import Optional, List
from faster_whisper import WhisperModel

# --- CẤU HÌNH HARDCODE ---
# MODEL_SIZE = "large-v2"
MODEL_SIZE = "small"

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE_TYPE = "float16" if DEVICE == "cuda" else "float32"
NB_THREADS = 1

# --- HÀM HỖ TRỢ TỪ CUSTOM_WIDGETS (Đã bỏ phần Qt) ---
def av_get_duration(file_path: str) -> float:
    try:
        with av.open(file_path) as container:
            # container.duration đơn vị là microsecond
            if container.duration:
                ret = container.duration / 1e6
                return ret
            return 0.0
    except Exception as e:
        print(f"[WARN] Error reading duration: {e}")
        return 0.0

class Subtitle:
    def __init__(self, text: str, start: float = 0.0, end: float = 0.0):
        self.text = text
        self.start = start
        self.end = end

    @staticmethod
    def parse_time(t: float) -> str:
        h = int(t // 3600)
        t -= h * 3600
        m = int(t // 60)
        t -= m * 60
        s = int(t)
        ms = int((t - s) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

class SpeechToTextCLI:
    def __init__(self):
        print(f"--- INITIALIZING ---")
        print(f"Model: {MODEL_SIZE}")
        print(f"Device: {DEVICE} ({COMPUTE_TYPE})")
        
        self.model = WhisperModel(
            model_size_or_path=MODEL_SIZE, 
            device=DEVICE, 
            compute_type=COMPUTE_TYPE, 
            cpu_threads=NB_THREADS
        )
        print("Model loaded successfully.\n")

    def sanitize_filename(self, name: str, output_dir: Path, max_length: int = 250) -> str:
        output_dir_len = len(str(output_dir.resolve()))
        allowed_length = max_length - output_dir_len - 15 
        if allowed_length < 10: allowed_length = 10 

        clean_name = re.sub(r'[<>:"/\\|?*]', '_', name)
        clean_name = "".join(c for c in clean_name if c.isprintable())
        
        if len(clean_name) > allowed_length:
            clean_name = clean_name[:allowed_length]
        return clean_name.strip()

    def process_audio(self, audio_file: Path, output_dir: Path, lang: str = "zh") -> bool:
        stem_name = audio_file.stem
        input_path_str = str(audio_file.resolve())
        duration = 0.0

        try:
            duration = av_get_duration(input_path_str)
        except Exception as e:
            print(f"Error getting duration for {audio_file.name}: {e}. Treating as empty.")
            duration = 0.0

        subtitles = []
        gc.collect()  # Dọn RAM trước khi chạy file mới

        if duration > 0.0:
            print(f"Transcribing: {audio_file.name} (Duration: {duration:.2f}s)")
            
            try:
                print("  -> Đang nhận diện giọng nói (Segment Mode)...")
                with open(input_path_str, "rb") as binary_file:
                    
                    # GỌI MODEL VỚI CẤU HÌNH TỐI ƯU NHẤT
                    segments, info = self.model.transcribe(
                        binary_file, 
                        word_timestamps=False, 
                        vad_filter=True, 
                        language=lang,
                    )
                    
                    print(f"  -> Ngôn ngữ nhận diện: {getattr(info, 'language', 'unknown')}")

              
                    # BÓC TÁCH TỪNG CÂU (SEGMENT) THAY VÌ TỪNG CHỮ
                    temp_subs = []
                    for segm in segments:
                        raw_text = getattr(segm, "text", "") or ""
                        start = float(getattr(segm, "start", 0.0))
                        end = float(getattr(segm, "end", 0.0))

                        # Dọn dẹp rác đầu cuối
                        clean = raw_text.strip()
                        clean = re.sub(r'^[^\w\u4e00-\u9fff]+', '', clean)
                        clean = re.sub(r'[^\w\u4e00-\u9fff]+$', '', clean)
                        
                        if clean:
                            temp_subs.append(Subtitle(clean, start, end))
                    
                    subtitles = temp_subs
                    print(f"  -> ✅ Thành công! Lấy được {len(subtitles)} câu sub.")
            
            except Exception as e:
                print(f"❌ Lỗi nghiêm trọng khi dịch file {audio_file.name}: {e}")
                # Vẫn return True để vòng lặp ngoài không bị dừng hẳn
                return True 

        else:
            print(f"[SKIP] {audio_file.name} is empty (0 duration).")

        # --- Ghi File SRT ---
        out_file = output_dir.joinpath(f"{stem_name}.srt")
        try:
            with open(out_file, "w", encoding="utf-8") as f:
                for idx, sub in enumerate(subtitles, start=1):
                    f.write(f"{idx}\n")
                    f.write(f"{Subtitle.parse_time(sub.start)} --> {Subtitle.parse_time(sub.end)}\n")
                    f.write(f"{sub.text}\n\n")
        except Exception as e:
            print(f"Write srt error: {e}")
            return False 

        return True

def scan_files(input_path: Path) -> List[Path]:
    audio_extensions = {'.wav'}
    files = []
    if input_path.is_file():
        if input_path.suffix.lower() in audio_extensions:
            files.append(input_path)
    elif input_path.is_dir():
        # Quét đệ quy (rglob) hoặc 1 cấp (glob) tùy bạn, ở đây dùng glob 1 cấp như code cũ
        for file_path in input_path.glob("*"):
            if file_path.is_file() and file_path.suffix.lower() in audio_extensions:
                files.append(file_path)
    return files

if __name__ == "__main__":
    # --- XỬ LÝ ARGUMENTS ---
    if len(sys.argv) < 3:
        print("\nTool SRT CLI - Hardcoded Large-v3")
        print("Usage: python script.py <input_path> <output_path> [lang_code]")
        print("Example: python script.py \"D:\\Audio\" \"D:\\Subs\" zh")
        sys.exit(1)

    input_arg = Path(sys.argv[1])
    output_arg = Path(sys.argv[2])
    lang_arg = sys.argv[3] if len(sys.argv) > 3 else "zh"

    if not input_arg.exists():
        print(f"Error: Input path '{input_arg}' not found.")
        sys.exit(1)

    output_arg.mkdir(parents=True, exist_ok=True)

    # 1. Quét File
    audio_files = scan_files(input_arg)
    if not audio_files:
        print("No audio files found.")
        sys.exit(0)
    
    print(f"Found {len(audio_files)} files to process.")

    # 2. Khởi tạo Model
    processor = SpeechToTextCLI()

    # 3. Chạy Loop
    for i, f in enumerate(audio_files, 1):
        print(f"\n[{i}/{len(audio_files)}] ----------------------------------------")
        processor.process_audio(f, output_arg, lang=lang_arg)

    print("\nBatch processing finished!")
