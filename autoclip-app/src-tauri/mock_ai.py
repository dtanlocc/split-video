# mock_ai.py
import sys
import json
import time

def emit(stage, pct, status, msg):
    # In ra chuẩn JSON để Rust đọc, flush=True bắt buộc phải có
    print(json.dumps({"stage": stage, "pct": pct, "status": status, "msg": msg}), flush=True)

def main():
    emit(0, 0, "inf", "Bắt đầu khởi động AI Core...")
    time.sleep(1)

    stages = [
        (0, "Transcribe (Whisper)..."),
        (1, "Phân tích Highlight (Gemini)..."),
        (2, "Cắt Video (FFmpeg)..."),
        (3, "Smart Crop (YOLO)..."),
        (4, "Render & Export...")
    ]

    for stage_idx, stage_name in stages:
        for p in range(1, 21): # Chạy từ 1% đến 20% mỗi bước
            pct = (stage_idx * 20) + p
            emit(stage_idx, pct, "inf", f"Đang {stage_name}")
            time.sleep(0.1) # Giả lập thời gian AI xử lý

    emit(5, 100, "ok", "Hoàn tất toàn bộ pipeline!")

if __name__ == "__main__":
    main()