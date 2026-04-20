import os
import json
import torch
from pathlib import Path
from src.infrastructure.video.audio_extractor import AudioExtractor
from src.domain.entities import AudioConfig
from src.infrastructure.ai.whisper_impl import WhisperTranscriber
from src.infrastructure.llm.gemini_engine import GeminiEngine
from src.infrastructure.utils.srt_utils import SRTUtils
from src.application.highlight_orchestrator import HighlightOrchestrator

import os
import sys
import torch

def setup_cuda_path():
    """
    Rule: Dynamic DLL Loading
    Tự động tìm và nạp các thư viện CUDA từ Torch để faster-whisper có thể sử dụng GPU trên Windows.
    """
    if sys.platform == "win32":
        # Tìm đường dẫn đến thư mục lib của torch
        torch_lib_path = os.path.join(os.path.dirname(torch.__file__), "lib")
        
        if os.path.exists(torch_lib_path):
            # Kỹ thuật chuyên nghiệp của Python 3.8+: Nạp thư mục DLL vào runtime
            os.add_dll_directory(torch_lib_path)
            print(f"✅ Đã nạp CUDA DLLs từ: {torch_lib_path}")
            
            # Cập nhật thêm PATH cho các thư viện cũ
            os.environ["PATH"] = torch_lib_path + os.pathsep + os.environ["PATH"]
        else:
            print("⚠️ Cảnh báo: Không tìm thấy thư mục Torch Lib.")

# Gọi hàm này TRƯỚC KHI import faster-whisper hoặc ctranslate2
setup_cuda_path()

# Sau đó mới import các thứ khác
from faster_whisper import WhisperModel

# --- CẤU HÌNH TEST ---
VIDEO_PATH = "tests/test_assets/sample.mp4" # <--- Bỏ video của bạn vào đây
API_KEYS = [
 "AIzaSyBJOUyGvGvS1zP55Mqq1E8A2wEj86ILY0I",
    "AIzaSyDne16vvX_E78-8-Nk3Pl3d7dUEGALTpxY",
]     # <--- Key Gemini của bạn
OUTPUT_DIR = Path("verify_results")
OUTPUT_DIR.mkdir(exist_ok=True)
import torch
import ctranslate2

def check_gpu_status():
    print("\n" + "="*30)
    print("🔍 KIỂM TRA TRẠNG THÁI GPU")
    print("="*30)
    
    # Kiểm tra Torch (Backend chính)
    cuda_available = torch.cuda.is_available()
    print(f"🔹 PyTorch CUDA Available: {cuda_available}")
    
    if cuda_available:
        print(f"🔹 GPU Name: {torch.cuda.get_device_name(0)}")
        print(f"🔹 Compute Capability: {torch.cuda.get_device_capability(0)}")
        
        # Kiểm tra ctranslate2 (Backend mà faster-whisper sử dụng)
        # Nếu không có CUDA, ctranslate2 sẽ tự hạ xuống CPU
        cuda_devices = ctranslate2.get_cuda_device_count()
        print(f"🔹 CTranslate2 CUDA Devices: {cuda_devices}")
    else:
        print("⚠️ CẢNH BÁO: PyTorch không tìm thấy GPU. Sẽ chạy bằng CPU (Rất chậm).")
    print("="*30 + "\n")
def verify_step_0():
    print("\n" + "="*30)
    print("STEP 0: TRÍCH XUẤT AUDIO (FFMPEG)")
    print("="*30)
    config = AudioConfig(sample_rate=16000, channels=1)
    extractor = AudioExtractor(config)
    
    out_wav = extractor.extract_single(VIDEO_PATH)
    
    print(f"✅ Đã tạo file: {out_wav}")
    print(f"📊 Dung lượng: {os.path.getsize(out_wav) / 1024:.2f} KB")
    print(f"👉 HÀNH ĐỘNG: Bạn hãy mở file .wav này lên nghe thử. Phải là Mono, 16kHz.")
    input("Nhấn Enter để tiếp tục B1...")

import os
import sys
import torch
import shutil

def setup_cuda_bridge():
    """
    Kỹ thuật Software Engineer: Binary Bridge.
    Đánh tráo tên file DLL để ctranslate2 (CUDA 12) chạy trên nền Torch (CUDA 11.8).
    """
    if sys.platform != "win32": return

    # 1. Tìm thư mục chứa DLL của Torch (CUDA 11.8)
    torch_lib_path = os.path.join(os.path.dirname(torch.__file__), "lib")
    if not os.path.exists(torch_lib_path):
        print("❌ Không tìm thấy Torch Lib.")
        return

    # 2. Ép hệ thống nhận diện thư mục này
    os.add_dll_directory(torch_lib_path)
    os.environ["PATH"] = torch_lib_path + os.pathsep + os.environ["PATH"]

    # 3. Danh sách các file cần 'đóng giả'
    # Tên gốc (bạn có) -> Tên giả (thư viện đòi)
    bridge_map = {
        "cublas64_11.dll": "cublas64_12.dll",
        "cublasLt64_11.dll": "cublasLt64_12.dll"
    }

    print(f"🛠️ Đang thiết lập Cầu nối Binary (CUDA 11.8 -> 12)...")
    for src_name, dst_name in bridge_map.items():
        src_path = os.path.join(torch_lib_path, src_name)
        dst_path = os.path.join(torch_lib_path, dst_name)
        
        if os.path.exists(src_path):
            if not os.path.exists(dst_path):
                try:
                    # Kỹ thuật: Tạo bản sao để lừa runtime
                    shutil.copy(src_path, dst_path)
                    print(f"   ✅ Đã tạo cầu nối: {dst_name}")
                except Exception as e:
                    print(f"   ❌ Lỗi khi tạo cầu nối: {e}")
            else:
                print(f"   ✔ Cầu nối {dst_name} đã sẵn sàng.")
        else:
            print(f"   ⚠ Cảnh báo: Không tìm thấy {src_name}. Hãy chắc chắn bạn đã cài torch cu118.")

# GỌI HÀM NÀY NGAY ĐẦU TIÊN
setup_cuda_bridge()

# Bây giờ mới import các thứ khác
from faster_whisper import WhisperModel

def verify_step_1():
    print("\n" + "="*30)
    print("STEP 1: NHẬN DIỆN GIỌNG NÓI (GPU)")
    print("="*30)
    from src.infrastructure.ai.whisper_impl import WhisperTranscriber
    
    transcriber = WhisperTranscriber(model_size="small")
    wav_path = "tests/test_assets/sample.wav"
    
    results = transcriber.transcribe(wav_path, lang="en") # Theo log của bạn là tiếng Anh
    
    # QUAN TRỌNG: Ghi file ra đĩa để B2 có dữ liệu đọc
    out_srt = OUTPUT_DIR / "test_output.srt"
    with open(out_srt, "w", encoding="utf-8") as f:
        for seg in results:
            # Đảm bảo seg là object có hàm to_srt_format
            f.write(seg.to_srt_format())
            
    print(f"✅ Đã lưu file SRT thành công: {out_srt}")
    transcriber.release_resources()
    print("👉 Nhấn Enter để bắt đầu B2 (Gemini Analysis)...")
    input()

def verify_step_2():
    print("\n" + "="*30)
    print("STEP 2: PHÂN TÍCH HIGHLIGHT (GEMINI)")
    print("="*30)
    from src.infrastructure.llm.gemini_engine import GeminiEngine
    from src.infrastructure.utils.srt_utils import SRTUtils
    from src.application.highlight_orchestrator import HighlightOrchestrator
    
    # Sử dụng đúng API Keys của bạn
    engine = GeminiEngine(API_KEYS, "gemini-1.5-flash")
    utils = SRTUtils()
    orchestrator = HighlightOrchestrator(engine, utils)
    
    srt_path = OUTPUT_DIR / "test_output.srt"
    
    print(f"🧠 Đang gửi kịch bản qua Gemini để tìm Highlight...")
    orchestrator.process_video(srt_path, OUTPUT_DIR)
    
    json_path = OUTPUT_DIR / f"highlights_{srt_path.stem}.json"
    
    if json_path.exists():
        import json
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        print(f"\n📊 KẾT QUẢ ĐỐI CHỨNG LOGIC B2:")
        for i, item in enumerate(data, 1):
            print(f"Segment {i}:")
            print(f"   ⏱ Thời gian: {item['start']} -> {item['end']}")
            print(f"   📌 Tiêu đề AI: {item['title']}") 
            # Soi xem title có đúng 9-15 từ và đúng ngôn ngữ (English) không
    else:
        print("❌ Lỗi: Không tạo được file JSON. Kiểm tra lại API Key hoặc Prompt.")

if __name__ == "__main__":
    # Chạy lần lượt để bạn quan sát
    check_gpu_status()
    verify_step_0()
    verify_step_1()
    verify_step_2()