import sys
import json
import asyncio
import argparse
from pydantic import ValidationError

from src.domain.schemas import RunPipelineRequest
from src.application.pipeline_manager import PipelineManager
from src.security.token_guard import verify_session_token

async def main():
    parser = argparse.ArgumentParser(description="AutoClip AI Core Engine")
    parser.add_argument("--payload", type=str, required=True)
    args = parser.parse_args()

    # 1. PARSE PAYLOAD
    try:
        parsed = json.loads(args.payload)
    except Exception as e:
        print(json.dumps({"stage": -1, "pct": 0, "status": "err", "msg": f"Payload JSON không hợp lệ: {e}"}), flush=True)
        sys.exit(1)

    # 2. SECURITY GATE: Verify session token
    session_token = parsed.get("session_token", "")
    hwid          = parsed.get("hwid", "")

    is_valid, err_msg = verify_session_token(session_token, hwid)
    if not is_valid:
        print(json.dumps({"stage": -1, "pct": 0, "status": "err", "msg": f"❌ Xác thực thất bại: {err_msg}"}), flush=True)
        sys.exit(1)

    print(json.dumps({"stage": 0, "pct": 3, "status": "inf", "msg": "✅ License hợp lệ, bắt đầu xử lý..."}), flush=True)

    # 3. VALIDATE SCHEMA
    try:
        # Pydantic sẽ tự động kiểm tra, lúc nãy nó cần String mà mình lại ép thành List nên nó báo lỗi
        request_data = RunPipelineRequest.model_validate(parsed)
    except ValidationError as e:
        error_msgs = [" -> ".join([str(loc) for loc in err["loc"]]) + f": {err['msg']}" for err in e.errors()]
        print(json.dumps({"stage": -1, "pct": 0, "status": "err", "msg": f"Sai định dạng Config: {' | '.join(error_msgs)}"}), flush=True)
        sys.exit(1)

    # 4. CHẠY PIPELINE
    manager     = PipelineManager(output_base_dir="./workspace")
    worker_task = asyncio.create_task(manager.start_worker())

    await manager.add_task(request_data)
    await manager.queue.join()      # Chờ xử lý xong

    manager.is_running = False
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

if __name__ == "__main__":
    asyncio.run(main())