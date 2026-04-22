import asyncio
import json
import traceback
from pathlib import Path
import subprocess
import gc
import torch
import os
import sys
import shutil
import psutil
import concurrent.futures

# Import schemas
from src.domain.schemas import RunPipelineRequest

# Import Services
from src.infrastructure.ai.whisper_impl import WhisperTranscriber
from src.infrastructure.llm.gemini_engine import GeminiEngine
from src.infrastructure.utils.srt_utils import SRTUtils
from src.application.highlight_orchestrator import HighlightOrchestrator
from src.infrastructure.video.ffmpeg_handler import FFmpegHandler
from src.infrastructure.ai.yolo_impl import YOLOImpl
from src.application.yolo_service import YOLOService
from src.application.render_service import RenderService
from src.infrastructure.video.renderer_impl import VideoRendererImpl


# =====================================================================
# HÀM XỬ LÝ ĐỘC LẬP (Nằm ngoài class để chạy ở Tiến trình khác)
# =====================================================================
def run_pipeline_isolated(req: RunPipelineRequest, output_base_str: str):
    """Toàn bộ logic xử lý video được bưng ra đây để chạy độc lập (Bypass GIL 100%)"""
    output_base = Path(output_base_str)
    
    # 1. Hàm emit cục bộ (Print thẳng ra stdout để Tauri hứng)
    def emit(stage: int, pct: int, status: str, msg: str):
        print(json.dumps({"stage": stage, "pct": pct, "status": status, "msg": msg}), flush=True)

    # 2. Setup OS Priority
    try:
        p = psutil.Process(os.getpid())
        p.nice(psutil.HIGH_PRIORITY_CLASS)
    except:
        pass

    # 3. Setup CUDA Bridge cho Windows
    if sys.platform == "win32":
        torch_lib_path = os.path.join(os.path.dirname(torch.__file__), "lib")
        if os.path.exists(torch_lib_path):
            os.add_dll_directory(torch_lib_path)
            bridge_map = {
                "cublas64_11.dll": "cublas64_12.dll",
                "cublasLt64_11.dll": "cublasLt64_12.dll"
            }
            for src, dst in bridge_map.items():
                src_p = os.path.join(torch_lib_path, src)
                dst_p = os.path.join(torch_lib_path, dst)
                if os.path.exists(src_p) and not os.path.exists(dst_p):
                    shutil.copy(src_p, dst_p)

    video_path = Path(req.video_path)
    video_name = video_path.stem
    work_dir = output_base / video_name
    work_dir.mkdir(parents=True, exist_ok=True)

    emit(0, 5, "inf", f"Bắt đầu xử lý: {video_name}")

    # ==========================================
    # BƯỚC 0: TÁCH AUDIO
    # ==========================================
    emit(0, 10, "inf", "Đang trích xuất Audio...")
    wav_path = work_dir / f"{video_name}.wav"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le",
        "-threads", "4", str(wav_path)
    ], capture_output=True, check=True)

    # ==========================================
    # BƯỚC 1: STT (WHISPER)
    # ==========================================
    emit(1, 20, "inf", f"Đang nhận diện giọng nói (Whisper - {req.stt_config.model})...")
    out_srt = work_dir / f"{video_name}.srt"
    
    transcriber = WhisperTranscriber(
        model_size=req.stt_config.model,
        device=req.stt_config.device,
        compute_type=req.stt_config.compute_type
    )
    results = transcriber.transcribe(str(wav_path), lang=req.stt_config.lang)
    
    if not results:
        raise Exception("Whisper không nhận diện được giọng nói (Video không có tiếng?)")
        
    with open(out_srt, "w", encoding="utf-8") as f:
        for seg in results:
            f.write(seg.to_srt_format())
    
    try: transcriber.release_resources()
    except: pass
    del transcriber
    gc.collect()
    if torch.cuda.is_available(): torch.cuda.empty_cache()

    # ==========================================
    # BƯỚC 2: GEMINI HIGHLIGHT
    # ==========================================
    # emit(2, 40, "inf", f"Đang phân tích kịch bản bằng AI ({req.gemini_config.model_name})...")
    # if not req.gemini_api_key or len(req.gemini_api_key) < 10:
    #     raise Exception("Vui lòng nhập API Key hợp lệ cho Gemini!")

    try:
        # engine = GeminiEngine(api_keys=[req.gemini_api_key], model_name=req.gemini_config.model_name)
        # orchestrator = HighlightOrchestrator(engine, SRTUtils())
        # orchestrator.process_video(
        #     out_srt, 
        #     work_dir, 
        #     min_sec=req.gemini_config.min_duration_sec, 
        #     max_sec=req.gemini_config.max_duration_sec
        # )
        highlight_json = work_dir / f"highlights_{video_name}.json"
        if not highlight_json.exists():
            raise Exception("AI không tạo ra được kịch bản Highlight nào!")
    except Exception as gemini_err:
        raise Exception(f"Lỗi AI Gemini: {str(gemini_err)}")

    # ==========================================
    # BƯỚC 3: CẮT VIDEO (FFMPEG)
    # ==========================================
    emit(3, 60, "inf", "Đang chia nhỏ video theo kịch bản AI...")
    cut_output_dir = work_dir / "cuts"
    cut_output_dir.mkdir(exist_ok=True)
    handler = FFmpegHandler()
    handler.cut_highlights(video_path, highlight_json, cut_output_dir)

    # ==========================================
    # BƯỚC 4: YOLO SMART CROP
    # ==========================================
    if req.mode == "full":
        emit(4, 75, "inf", "Đang điều hướng camera thông minh (YOLO Crop)...")
        yolo_output_dir = work_dir / "yolo_crops"
        yolo_output_dir.mkdir(exist_ok=True)
        
        specific_cut_dir = cut_output_dir / video_path.stem 
        valid_exts = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
        cut_files = [f for f in specific_cut_dir.iterdir() if f.is_file() and f.suffix.lower() in valid_exts] if specific_cut_dir.exists() else []

        if not cut_files:
            raise Exception("Không tìm thấy video nào cắt ra từ FFmpeg!")
        emit(4, 76, "inf", f"Tìm thấy {len(cut_files)} cảnh quay. Bắt đầu Virtual Cameraman...")
        
        cropper = YOLOImpl()
        yolo_service = YOLOService(cropper) 
        for cut_file in cut_files:
            yolo_service.crop_highlights(cut_file, yolo_output_dir, config=req.crop_config)
        
        try: cropper.release_resources()
        except: pass
        del cropper
        del yolo_service
        gc.collect()
        if torch.cuda.is_available(): torch.cuda.empty_cache()
        emit(4, 85, "inf", "YOLO Crop hoàn tất!")
    else:
        pass

    # ==========================================
    # BƯỚC 5: FINAL RENDER
    # ==========================================
    emit(5, 90, "inf", "Đang render phụ đề và chèn hiệu ứng...")
    final_dir = work_dir / "final"
    final_dir.mkdir(exist_ok=True)
    renderer = VideoRendererImpl()
    render_service = RenderService(renderer)
    render_service.render_all(yolo_output_dir, final_dir, config=req.render_config)

    emit(6, 100, "ok", f"Hoàn tất xử lý video: {video_name}!")
    return "SUCCESS"


# =====================================================================
# MANAGER CHÍNH CỦA APP
# =====================================================================
class PipelineManager:
    def __init__(self, output_base_dir: str = "workspace"):
        self.queue = asyncio.Queue()
        self.output_base = Path(output_base_dir)
        self.output_base.mkdir(parents=True, exist_ok=True)
        self.is_running = False

    def emit(self, stage: int, pct: int, status: str, msg: str):
        print(json.dumps({"stage": stage, "pct": pct, "status": status, "msg": msg}), flush=True)

    async def start_worker(self):
        self.is_running = True
        loop = asyncio.get_running_loop()
        
        # TẠO MỘT TIẾN TRÌNH (PROCESS) ĐỘC LẬP
        with concurrent.futures.ProcessPoolExecutor(max_workers=1) as pool:
            while self.is_running:
                req: RunPipelineRequest = await self.queue.get()
                try:
                    # Giao toàn bộ việc nặng cho Tiến trình mới
                    # Nó sẽ được chạy trên một môi trường Python thứ 2, sạch sẽ 100%
                    await loop.run_in_executor(pool, run_pipeline_isolated, req, str(self.output_base))
                except BaseException as e:
                    self.emit(-1, 0, "err", f"❌ Lỗi: {str(e)}")
                    traceback.print_exc()
                finally:
                    self.queue.task_done()

    async def add_task(self, req: RunPipelineRequest):
        await self.queue.put(req)
        self.emit(0, 0, "inf", f"Đã thêm vào hàng đợi: {Path(req.video_path).name}")