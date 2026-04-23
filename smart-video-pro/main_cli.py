# smart-video-pro/main_cli.py
import sys
import json
import asyncio
import argparse
from pydantic import ValidationError

from src.domain.schemas import RunPipelineRequest
from src.application.pipeline_manager import PipelineManager
from src.security.token_guard import verify_session_token

# =====================================================================
# ENTRY POINT - FIX QUAN TRỌNG
# =====================================================================
async def main():
    if sys.platform == "win32":
        import multiprocessing
        multiprocessing.set_start_method("spawn", force=True)

    parser = argparse.ArgumentParser(description="AutoClip AI Core Engine")
    parser.add_argument("--payload", type=str, required=True)
    args = parser.parse_args()

    try:
        parsed = json.loads(args.payload)
    except Exception as e:
        sys.stdout.write(json.dumps({"stage": -1, "pct": 0, "status": "err", "msg": f"Payload JSON lỗi: {e}"}) + "\n")
        sys.stdout.flush()
        sys.exit(1)

    session_token = parsed.get("session_token", "")
    hwid = parsed.get("hwid", "")
    is_valid, err_msg = verify_session_token(session_token, hwid)
    if not is_valid:
        sys.stdout.write(json.dumps({"stage": -1, "pct": 0, "status": "err", "msg": f"❌ License: {err_msg}"}) + "\n")
        sys.stdout.flush()
        sys.exit(1)

    sys.stdout.write(json.dumps({"stage": 0, "pct": 3, "status": "inf", "msg": "✅ License hợp lệ, bắt đầu..."}) + "\n")
    sys.stdout.flush()

    try:
        req = RunPipelineRequest.model_validate(parsed)
    except Exception as e:
        sys.stdout.write(json.dumps({"stage": -1, "pct": 0, "status": "err", "msg": f"Config lỗi: {e}"}) + "\n")
        sys.stdout.flush()
        sys.exit(1)

    manager = PipelineManager(output_base_dir="./workspace")
    worker_task = asyncio.create_task(manager.start_worker())
    await manager.add_task(req)
    await manager.queue.join()
    
    manager.is_running = False
    worker_task.cancel()
    try: await worker_task
    except asyncio.CancelledError: pass

# 🔥 FIX 3: Guard bắt buộc cho Windows + multiprocessing
if __name__ == "__main__":
    asyncio.run(main())