import sys
import os

# ==============================================================================
# LÁ CHẮN CHỐNG "ĐẬP CHUỘT" (ANTI-WHACK-A-MOLE SHIELD)
# Ép Nuitka không được vứt bỏ các thư viện lõi (Standard Libraries) 
# mà bọn PyTorch, YOLO, Whisper rất hay "xài lén" ngầm.
# ==============================================================================
import zoneinfo
import pdb
import unittest
import unittest.mock
import cProfile
import pstats
import ctypes
import sqlite3
import multiprocessing
import xml.etree.ElementTree
import urllib.request
# ==============================================================================

# 1. CƠ CHẾ HYBRID VENV (PHẢI NẰM Ở ĐÂY)
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

EXTERNAL_VENV = os.path.join(BASE_DIR, ".venv", "Lib", "site-packages")
if os.path.exists(EXTERNAL_VENV) and EXTERNAL_VENV not in sys.path:
    sys.path.insert(0, EXTERNAL_VENV)

# ==============================================================================
# 2. BÂY GIỜ MỚI ĐƯỢC IMPORT CÁC THƯ VIỆN KHÁC
# ==============================================================================
import json
import asyncio
import argparse
import pdb
from pydantic import ValidationError  # <--- BÂY GIỜ NÓ SẼ TÌM THẤY TRONG .VENV!

from src.domain.schemas import RunPipelineRequest
from src.application.pipeline_manager import PipelineManager
from src.security.token_guard import verify_session_token

# 3. FIX ĐƯỜNG DẪN PAYLOAD 
def fix_path(path_str):
    if not path_str: return path_str
    return os.path.abspath(path_str.replace('\\', '/'))

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