# smart-video-pro/src/application/pipeline_manager.py
# 🔥 FIX: Tắt buffering Python ngay từ đầu
import os
import sys
os.environ["PYTHONUNBUFFERED"] = "1"
if sys.version_info >= (3, 7):
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

import asyncio
import json
import traceback
import argparse
from pathlib import Path
import subprocess
import gc
import torch
import shutil
import psutil
import concurrent.futures

# Import schemas
from src.domain.schemas import RunPipelineRequest, ProgressEvent

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
from src.infrastructure.utils.hardware_profiler import detect_hardware
from src.security.token_guard import verify_session_token
from src.application.error_mapper import ErrorMessageMapper

# =====================================================================
# HÀM XỬ LÝ ĐỘC LẬP
# =====================================================================
def run_pipeline_isolated(req: RunPipelineRequest, output_base_str: str):
    output_base = Path(output_base_str)
    
    def emit(stage: str, pct: int, status: str, msg: str, meta: dict = None):
        event = ProgressEvent(stage=stage, pct=pct, status=status, msg=msg, meta=meta)
        sys.stdout.write(event.to_json() + "\n")
        sys.stdout.flush()
        if status == "err":
            sys.stderr.write(f"[ERR] {event.to_json()}\n")
            sys.stderr.flush()

    # Setup OS Priority
    try:
        p = psutil.Process(os.getpid())
        p.nice(psutil.HIGH_PRIORITY_CLASS if sys.platform == "win32" else -10)
    except: 
        pass

    # 🔥 Setup CUDA Bridge cho Windows
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

    # 🔥 Hiển thị thông tin GPU
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        emit("init", 1, "inf", f"🎮 GPU: {props.name} | VRAM: {props.total_memory/1024**3:.1f}GB")
        print(f"🎮 GPU: {props.name} | VRAM: {props.total_memory/1024**3:.1f}GB", flush=True)

    video_path = Path(req.video_path)
    video_name = video_path.stem
    work_dir = output_base / video_name
    work_dir.mkdir(parents=True, exist_ok=True)

    emit("init", 5, "inf", f"Bắt đầu xử lý: {video_name}")

    try:
        # BƯỚC 0: TÁCH AUDIO
        emit("audio", 10, "inf", "Đang trích xuất Audio...")
        wav_path = work_dir / f"{video_name}.wav"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(video_path),
            "-vn", "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le",
            "-threads", "4", str(wav_path)
        ], capture_output=True, check=True)

        # BƯỚC 1: STT (WHISPER)
        emit("stt", 20, "inf", f"Đang nhận diện giọng nói (Model - {req.stt_config.model})...")
        out_srt = work_dir / f"{video_name}.srt"
        
        transcriber = WhisperTranscriber(
            model_size=req.stt_config.model,
            device=req.stt_config.device,
            compute_type=req.stt_config.compute_type
        )
        results = transcriber.transcribe(str(wav_path), lang=req.stt_config.lang)
        
        if not results:
            raise Exception("Whisper không nhận diện được giọng nói")
            
        with open(out_srt, "w", encoding="utf-8") as f:
            for seg in results:
                f.write(seg.to_srt_format())
        
        transcriber.release_resources()
        del transcriber
        
        # 🔥 Clear GPU cache sau mỗi bước lớn
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        gc.collect()

        # BƯỚC 2: GEMINI HIGHLIGHT
        # highlight_json = work_dir / f"highlights_{video_name}.json"
        emit("ai", 40, "inf", "Đang phân tích kịch bản bằng AI...")
        
        try:
            engine = GeminiEngine(api_keys=[req.gemini_api_key], model_name=req.gemini_config.model_name)
            orchestrator = HighlightOrchestrator(engine, SRTUtils())
            orchestrator.process_video(
                out_srt, 
                work_dir, 
                min_sec=req.gemini_config.min_duration_sec, 
                max_sec=req.gemini_config.max_duration_sec
            )
            highlight_json = work_dir / f"highlights_{video_name}.json"
            if not highlight_json.exists():
                raise Exception("AI không tạo ra được kịch bản Highlight nào!")
        except Exception as gemini_err:
            raise Exception(f"Lỗi AI Gemini: {str(gemini_err)}")

        # BƯỚC 3: CẮT VIDEO (FFMPEG)
        emit("cut", 60, "inf", "Đang chia nhỏ video theo kịch bản AI...")
        cut_output_dir = work_dir / "cuts"
        cut_output_dir.mkdir(exist_ok=True)
        FFmpegHandler().cut_highlights(video_path, highlight_json, cut_output_dir)

        # BƯỚC 4: YOLO SMART CROP (ADAPTIVE MODE)
        if req.mode == "full":
            emit("crop", 75, "inf", "🔍 Đang quét phần cứng để tối ưu YOLO...")
            
            hw = detect_hardware()
            req.crop_config.ffmpeg_codec = hw.config["ffmpeg_codec"]
            req.crop_config.ffmpeg_preset = hw.config["ffmpeg_preset"]
            
            emit("crop", 75, "inf", f"🖥️ {hw.gpu_name} | VRAM: {hw.vram_gb}GB | RAM: {hw.ram_gb}GB")
            
            yolo_output_dir = work_dir / "yolo_crops"
            yolo_output_dir.mkdir(exist_ok=True)

            specific_cut_dir = cut_output_dir / video_path.stem
            valid_exts = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
            cut_files = [f for f in specific_cut_dir.iterdir() if f.is_file() and f.suffix.lower() in valid_exts] if specific_cut_dir.exists() else []

            if not cut_files:
                raise Exception("Không tìm thấy video nào cắt ra từ FFmpeg!")

            emit("crop", 76, "inf", f"✅ Tìm thấy {len(cut_files)} cảnh. Bắt đầu Virtual Cameraman...")

            # 🔥 Tối ưu batch size dựa trên VRAM
            optimal_batch = hw.config["batch_size"]
            
            cropper = YOLOImpl(
                model_path=hw.config["yolo_model"],
                device="auto",
                batch_size=optimal_batch,
                use_half=hw.config["use_half"],
                queue_raw=hw.config["queue_raw"],
                queue_result=hw.config["queue_result"]
            )

            for i, cut_file in enumerate(cut_files, 1):
                emit("crop", 77 + i*2, "inf", f"Processing clip {i}/{len(cut_files)}: {cut_file.name}")
                cropper.process_video(cut_file, yolo_output_dir, config=req.crop_config)
                
                # 🔥 Clear cache sau mỗi video
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

            cropper.release_resources()
            del cropper
            
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            gc.collect()

            emit("crop", 85, "inf", "✅ YOLO Adaptive hoàn tất!")
            
        else:
            emit("crop", 75, "inf", "Đang crop 1:1 và đóng gói 9:16...")
            yolo_output_dir = work_dir / "simple_crops"
            yolo_output_dir.mkdir(exist_ok=True)

            specific_cut_dir = cut_output_dir / video_path.stem
            valid_exts = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
            cut_files = [f for f in specific_cut_dir.iterdir() if f.is_file() and f.suffix.lower() in valid_exts] if specific_cut_dir.exists() else []

            if not cut_files:
                raise Exception("Không tìm thấy video nào cắt ra từ FFmpeg!")

            for cut_file in cut_files:
                probe = subprocess.run([
                    "ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=width,height", "-of", "json", str(cut_file)
                ], capture_output=True, text=True)
                info = json.loads(probe.stdout)
                w, h = info["streams"][0]["width"], info["streams"][0]["height"]
                side = min(w, h)
                x, y = (w - side) // 2, (h - side) // 2

                TITLE_H, VIDEO_H, OUT_W, OUT_H = int(1920 * 0.19), 1080, 1080, 1920
                out_path = yolo_output_dir / f"{cut_file.stem}.mp4"
                
                cmd = [
                    "ffmpeg", "-y", "-i", str(cut_file),
                    "-vf", f"crop={side}:{side}:{x}:{y},scale={OUT_W}:{VIDEO_H},pad={OUT_W}:{OUT_H}:0:{TITLE_H}:black",
                    "-c:v", "h264_nvenc", "-preset", "p2", "-cq", "24",
                    "-c:a", "aac", "-b:a", "192k", str(out_path)
                ]
                subprocess.run(cmd, capture_output=True, check=True)
                emit("crop", 80, "inf", f"Đã xử lý: {cut_file.name}")

            emit("crop", 85, "inf", "Simple Crop hoàn tất!")

        # BƯỚC 5: FINAL RENDER
        emit("render", 90, "inf", "Đang render phụ đề và chèn hiệu ứng...")
        final_dir = work_dir / "final"
        final_dir.mkdir(exist_ok=True)
        renderer = VideoRendererImpl()
        render_service = RenderService(renderer)
        render_service.render_all(yolo_output_dir, final_dir, config=req.render_config)

        emit("complete", 100, "ok", f"Hoàn tất xử lý video: {video_name}!")
        return "SUCCESS"

    except Exception as e:
        mapped = ErrorMessageMapper.map(e)
        
        emit("complete", 0, "err", mapped["user_msg"], meta={
            "suggestion": mapped["suggestion"],
            "retry_possible": mapped["retry_possible"],
            "technical": mapped["technical"]
        })
        
        import time
        dump = {
            "timestamp": time.time(),
            "video": str(video_path),
            "error": str(e),
            "traceback": traceback.format_exc()
        }
        crash_dir = Path("crash_dumps")
        crash_dir.mkdir(exist_ok=True)
        try:
            with open(crash_dir / f"crash_{int(time.time())}.json", "w", encoding="utf-8") as f:
                json.dump(dump, f, ensure_ascii=False, indent=2)
            sys.stderr.write(f"💥 Crash dump saved\n")
            sys.stderr.flush()
        except: 
            pass
        
        emit("complete", 0, "err", f"❌ Pipeline failed: {str(e)}")
        raise e
    
    finally:
        # 🔥 Cleanup toàn bộ GPU memory
        gc.collect()
        if torch.cuda.is_available(): 
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        from src.infrastructure.ai.whisper_cache import WhisperModelCache
        WhisperModelCache.clear_all()


# =====================================================================
# MANAGER CHÍNH
# =====================================================================
class PipelineManager:
    def __init__(self, output_base_dir: str = "workspace"):
        self.queue = asyncio.Queue()
        self.output_base = Path(output_base_dir)
        self.output_base.mkdir(parents=True, exist_ok=True)
        self.is_running = False

    def emit(self, stage: str, pct: int, status: str, msg: str):
        # 🔥 FIX: stage là string, không phải int
        log_obj = {"stage": stage, "pct": pct, "status": status, "msg": msg}
        sys.stdout.write(json.dumps(log_obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    async def start_worker(self):
        self.is_running = True
        loop = asyncio.get_running_loop()
        
        with concurrent.futures.ProcessPoolExecutor(max_workers=1, mp_context=torch.multiprocessing.get_context("spawn")) as pool:
            while self.is_running:
                req: RunPipelineRequest = await self.queue.get()
                try:
                    await loop.run_in_executor(pool, run_pipeline_isolated, req, str(self.output_base))
                except Exception as e:
                    self.emit("complete", 0, "err", f"❌ Lỗi pipeline: {str(e)}")
                finally:
                    self.queue.task_done()

    async def add_task(self, req: RunPipelineRequest):
        await self.queue.put(req)
        self.emit("init", 0, "inf", f"Đã thêm vào hàng đợi: {Path(req.video_path).name}")