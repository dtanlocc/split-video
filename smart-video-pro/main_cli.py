# tool-autoclip/smart-video-pro/main_cli.py
import sys
import json
import time
import argparse

# Giả lập import Pipeline Service của bạn (Comment lại khi ghép code thật)
# from src.application.pipeline_service import run_full_pipeline

def emit_progress(stage: int, pct: int, status: str, msg: str):
    """Hàm in tiến độ ra stdout để Rust đọc được"""
    # Trả về format JSON y hệt cấu trúc bạn thiết kế ở giao diện HTML
    data = {
        "stage": stage,
        "pct": pct,
        "status": status,
        "msg": msg
    }
    # flush=True cực kỳ quan trọng để đẩy data thẳng ra ống dẫn (Pipe) cho Rust
    print(json.dumps(data), flush=True) 

def main():
    parser = argparse.ArgumentParser(description="AutoClip AI Core")
    parser.add_argument("--mode", type=str, default="full", help="Pipeline mode")
    parser.add_argument("--whisper", type=str, default="medium", help="Whisper model")
    args = parser.parse_args()

    # Bắt đầu báo hiệu cho UI
    emit_progress(0, 0, "inf", "Khởi động Động cơ AI...")
    time.sleep(1) # Giả lập delay khởi động

    try:
        # Ở ĐÂY LÀ NƠI GỌI PIPELINE THẬT CỦA BẠN
        # Ví dụ: run_full_pipeline(mode=args.mode, whisper=args.whisper, progress_callback=emit_progress)
        
        # --- ĐOẠN NÀY LÀ GIẢ LẬP ĐỂ TEST UI TRƯỚC KHI GẮN AI NẶNG VÀO ---
        emit_progress(0, 15, "inf", "Đang Transcribe (Whisper)...")
        time.sleep(2)
        
        emit_progress(1, 35, "inf", "Đang phân tích Highlight (Gemini)...")
        time.sleep(2)
        
        emit_progress(2, 55, "inf", "Đang cắt Video (FFmpeg)...")
        time.sleep(2)
        
        emit_progress(3, 80, "inf", "Đang Smart Crop (YOLO)...")
        time.sleep(3)
        
        emit_progress(4, 95, "inf", "Đang Render Subtitle & Export...")
        time.sleep(2)
        
        emit_progress(5, 100, "ok", "Hoàn tất toàn bộ pipeline!")
        # ----------------------------------------------------------------

    except Exception as e:
        emit_progress(-1, 0, "err", f"Lỗi nghiêm trọng: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()