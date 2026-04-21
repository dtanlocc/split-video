# verify_pipeline.py
import os
import sys
import json
import subprocess
import torch
import shutil
import traceback
from pathlib import Path

# ====================== CUDA SETUP (Chỉ gọi 1 lần) ======================
def setup_cuda():
    """Setup CUDA DLLs và Binary Bridge cho Windows"""
    if sys.platform != "win32":
        return

    # Dynamic DLL Loading
    torch_lib_path = os.path.join(os.path.dirname(torch.__file__), "lib")
    if os.path.exists(torch_lib_path):
        os.add_dll_directory(torch_lib_path)
        os.environ["PATH"] = torch_lib_path + os.pathsep + os.environ.get("PATH", "")
        print(f"✅ Đã nạp CUDA DLLs từ: {torch_lib_path}")

    # Binary Bridge (CUDA 11.8 → 12)
    bridge_map = {
        "cublas64_11.dll": "cublas64_12.dll",
        "cublasLt64_11.dll": "cublasLt64_12.dll"
    }
    for src_name, dst_name in bridge_map.items():
        src_path = os.path.join(torch_lib_path, src_name)
        dst_path = os.path.join(torch_lib_path, dst_name)
        if os.path.exists(src_path) and not os.path.exists(dst_path):
            try:
                shutil.copy(src_path, dst_path)
                print(f" ✅ Đã tạo cầu nối: {dst_name}")
            except Exception as e:
                print(f" ❌ Lỗi tạo cầu nối {dst_name}: {e}")


# Gọi setup CUDA ngay từ đầu (chỉ 1 lần)
setup_cuda()

# ====================== IMPORT SAU KHI SETUP CUDA ======================
from src.infrastructure.video.audio_extractor import AudioExtractor
from src.domain.entities import AudioConfig, SubtitleSegment
from src.infrastructure.ai.whisper_impl import WhisperTranscriber
from src.infrastructure.llm.gemini_engine import GeminiEngine
from src.infrastructure.utils.srt_utils import SRTUtils
from src.application.highlight_orchestrator import HighlightOrchestrator
from src.infrastructure.video.ffmpeg_handler import FFmpegHandler
from src.infrastructure.ai.yolo_impl import YOLOImpl
from src.application.yolo_service import YOLOService
from src.application.render_service import RenderService
from src.infrastructure.video.renderer_impl import VideoRendererImpl
from src.domain.schemas import CropConfig, RenderConfig

# ====================== CẤU HÌNH TEST ======================
VIDEO_PATH = "tests/test_assets/sample.mp4"
API_KEYS = [
    # "AIzaSyCuXdWPGhEPEXWJ9NaBasA_6Y9Yl49AJQQ",
    # "AIzaSyAuUIN9JgFpD6q7AVkbO_sKeFjFBKlk0_w"
    # "AIzaSyDG7UHA2aYt2cQLOocFetq9YXI3ywpAfjE"
    "AIzaSyBQAhk8fz78ZWs2-gLXXDHZDkECKUjXV5Y"
]

OUTPUT_DIR = Path("verify_results")
OUTPUT_DIR.mkdir(exist_ok=True)


def check_gpu_status():
    print("\n" + "="*30)
    print("🔍 KIỂM TRA TRẠNG THÁI GPU")
    print("="*30)

    cuda_available = torch.cuda.is_available()
    print(f"🔹 PyTorch CUDA Available: {cuda_available}")

    if cuda_available:
        print(f"🔹 GPU Name: {torch.cuda.get_device_name(0)}")
        print(f"🔹 Compute Capability: {torch.cuda.get_device_capability(0)}")
        print(f"🔹 CTranslate2 CUDA Devices: {ctranslate2.get_cuda_device_count() if 'ctranslate2' in globals() else 'N/A'}")
    else:
        print("⚠️ CẢNH BÁO: PyTorch không tìm thấy GPU. Sẽ chạy bằng CPU.")
    print("="*30 + "\n")


def verify_step_0():
    print("\n" + "="*30)
    print("STEP 0: TRÍCH XUẤT AUDIO")
    print("="*30)

    wav_path = Path("tests/test_assets/sample.wav")

    cmd = [
        "ffmpeg", "-y", "-i", VIDEO_PATH,
        "-vn", "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le",
        str(wav_path)
    ]

    print("🔨 Đang chạy FFmpeg extract audio...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0 and wav_path.exists():
        size_mb = wav_path.stat().st_size / (1024 * 1024)
        print(f"✅ Tạo thành công: {wav_path}")
        print(f"📊 Dung lượng: {size_mb:.2f} MB")
    else:
        print("❌ Lỗi FFmpeg:", result.stderr)

    input("Nhấn Enter để tiếp tục Step 1...")


def verify_step_1():
    print("\n" + "="*30)
    print("STEP 1: NHẬN DIỆN GIỌNG NÓI (Whisper)")
    print("="*30)

    transcriber = WhisperTranscriber(model_size="large-v3")

    wav_path = "tests/test_assets/sample.wav"
    results = transcriber.transcribe(wav_path, lang="en")

    out_srt = OUTPUT_DIR / "test_output.srt"
    with open(out_srt, "w", encoding="utf-8") as f:
        for seg in results:
            f.write(seg.to_srt_format())

    print(f"✅ Đã lưu SRT: {out_srt} ({len(results)} câu)")
    transcriber.release_resources()

    input("Nhấn Enter để tiếp tục Step 2...")


def verify_step_2():
    print("\n" + "="*30)
    print("STEP 2: PHÂN TÍCH HIGHLIGHT (GEMINI)")
    print("="*30)

    engine = GeminiEngine(API_KEYS, "gemini-2.5-flash")
    utils = SRTUtils()
    orchestrator = HighlightOrchestrator(engine, utils)

    srt_path = OUTPUT_DIR / "test_output.srt"
    print(f"🧠 Đang gửi kịch bản qua Gemini để tìm Highlight...")

    orchestrator.process_video(srt_path, OUTPUT_DIR)

    json_path = OUTPUT_DIR / f"highlights_{srt_path.stem}.json"
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"\n📊 Tìm được {len(data)} highlight:")
        for i, item in enumerate(data, 1):
            print(f"  {i:2d}. [{item['start']} → {item['end']}] {item.get('title', '')}")
    else:
        print("❌ Không tạo được file JSON highlights.")


def verify_step_3():
    print("\n" + "="*30)
    print("STEP 3: CẮT VIDEO (B3)")
    print("="*30)

    handler = FFmpegHandler()
    video_path = Path(VIDEO_PATH)
    json_path = OUTPUT_DIR / "highlights_test_output.json"   # Lưu ý tên file
    output_base = Path("verify_results/outputs")

    if json_path.exists():
        handler.cut_highlights(video_path, json_path, output_base)
    else:
        print("❌ Không tìm thấy JSON highlights. Hãy chạy Step 2 trước.")


def verify_step_4():
    print("\n" + "="*30)
    print("STEP 4: YOLO SMART CROP (FOLDER MODE)")
    print("="*30)

    cropper = YOLOImpl()
    service = YOLOService(cropper)

    # 1. Định nghĩa thư mục nguồn và thư mục đích
    input_dir = Path("verify_results/outputs/sample")
    output_dir = Path("verify_results/yolo_outputs")
    output_dir.mkdir(parents=True, exist_ok=True) # Tạo folder output nếu chưa có

    # 2. Lấy danh sách tất cả file video (hỗ trợ nhiều định dạng)
    video_extensions = ("*.mp4", "*.avi", "*.mov", "*.mkv", "*.webm")
    video_files = []
    for ext in video_extensions:
        video_files.extend(input_dir.glob(ext))

    if not video_files:
        print(f"❌ Không tìm thấy video nào trong thư mục: {input_dir}")
        return

    print(f"🚀 Tìm thấy {len(video_files)} video. Bắt đầu quy trình Virtual Cameraman...")

    # 3. Chạy vòng lặp xử lý từng video
    for video_path in video_files:
        print(f"\n🎬 Bắt đầu xử lý: {video_path.name}")
        
        try:
            service.crop_highlights(
                video_path=video_path,
                output_dir=output_dir,
                config=CropConfig(output_size=(1080, 1920))
            )
            print(f"✅ Đã xong: {video_path.name}")
        except Exception as e:
            print(f"❌ Lỗi khi xử lý {video_path.name}: {str(e)}")

    print("\n✨ TẤT CẢ VIDEO ĐÃ ĐƯỢC XỬ LÝ XONG!")



def verify_step_final():
    print("\n" + "="*40)
    print("FINAL RENDER - Bước Cuối Cùng")
    print("="*40)

    renderer = VideoRendererImpl()
    service = RenderService(renderer)

    service.render_all(
        input_dir=Path("verify_results/yolo_outputs"),
        output_dir=Path("verify_results/final"),
        config=RenderConfig(video_speed=1.03, max_parallel=1)
    )


# ====================== MAIN ======================
if __name__ == "__main__":
    print("=" * 70)
    print("🚀 BẮT ĐẦU VERIFY FULL PIPELINE")
    print("=" * 70)

    try:
        # check_gpu_status()        # Bỏ comment nếu cần kiểm tra GPU

        verify_step_0()
        # verify_step_1()
        # verify_step_2()
        # verify_step_3()             # Hiện đang active
        # verify_step_4()
        # verify_step_final()

    except Exception as e:
        print(f"\n❌ LỖI KHÔNG MONG MUỐN: {e}")
        traceback.print_exc()
    finally:
        print("\n🏁 KẾT THÚC VERIFY PIPELINE")