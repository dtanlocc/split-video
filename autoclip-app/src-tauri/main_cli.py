# src-tauri/main_cli.py
import sys
import json
import asyncio
import argparse
import traceback
from pathlib import Path
# from loguru import logger

from src.domain.schemas import RunPipelineRequest
from src.application.pipeline_manager import PipelineManager
from tool_autoclip.smart_video_pro.main_cli import map_ui_to_pipeline
from src.infrastructure.security.security_core import run_security_check

# logger.add("logs/autoclip.log", rotation="10 MB", level="INFO")

def emit(stage: int, pct: int, status: str, msg: str):
    print(json.dumps({"stage": stage, "pct": pct, "status": status, "msg": msg}), flush=True)

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", type=str, required=True)
    parser.add_argument("--video", type=str, required=True)
    parser.add_argument("--config", type=str, required=True)
    args = parser.parse_args()

    emit(0, 0, "inf", "🚀 Khởi động AutoClip AI Pro...")

    try:
        ui_data = json.loads(args.config)
        ui_data["video_path"] = args.video
        ui_data["mode"] = args.mode

        request: RunPipelineRequest = map_ui_to_pipeline(ui_data)

        # ====================== SECURITY CHECK ======================
        success, license_key = run_security_check(emit)
        if not success:
            # Gửi tín hiệu đặc biệt cho Rust hiển thị popup nhập key
            emit(-2, 0, "activation_required", "Vui lòng nhập License Key để tiếp tục")
            sys.exit(0)   # Thoát nhẹ, không crash

        # License đã OK → tiếp tục pipeline
        manager = PipelineManager(output_base_dir="workspace")
        worker_task = asyncio.create_task(manager.start_worker())
        await manager.add_task(request)

        await manager.queue.join()

        manager.is_running = False
        worker_task.cancel()

        emit(6, 100, "ok", f"✅ Hoàn tất video: {Path(args.video).name}")

    except Exception as e:
        # logger.exception("Pipeline crashed")
        emit(-1, 0, "err", f"❌ Lỗi nghiêm trọng: {str(e)}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())