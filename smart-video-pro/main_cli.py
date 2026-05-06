import sys
import os

# ==============================================================================
# ★ FREEZE SUPPORT — DÒNG ĐẦU TIÊN TUYỆT ĐỐI
# ==============================================================================
import multiprocessing
multiprocessing.freeze_support()

# ==============================================================================
# LÁ CHẮN NUITKA
# ==============================================================================
import zoneinfo, pdb, unittest, unittest.mock, cProfile, pstats
import ctypes, sqlite3, xml.etree.ElementTree, urllib.request

# ==============================================================================
# HYBRID VENV
# ==============================================================================
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

EXTERNAL_VENV = os.path.join(BASE_DIR, ".venv", "Lib", "site-packages")
if os.path.exists(EXTERNAL_VENV) and EXTERNAL_VENV not in sys.path:
    sys.path.insert(0, EXTERNAL_VENV)

# ==============================================================================
# ★ FORCE UTF-8 CHO STDIN/STDOUT/STDERR
#
# Vấn đề gốc rễ: Windows pipe mặc định dùng CP1252 (ANSI) hoặc CP850
# Khi Rust ghi UTF-8 bytes vào pipe, Python đọc bằng encoding mặc định
# → ký tự Unicode bị decode sai: ： (U+FF1A UTF-8: EF BC 9A) → ï¼š
#
# Fix: wrap stdin bằng io.TextIOWrapper với encoding='utf-8'
# PHẢI làm TRƯỚC khi import bất kỳ thứ gì dùng sys.stdin
# ==============================================================================
import io

# Wrap stdout/stderr trước
try:
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer,
        encoding="utf-8",
        line_buffering=True,
        errors="replace"
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer,
        encoding="utf-8",
        line_buffering=True,
        errors="replace"
    )
except AttributeError:
    # Trong một số môi trường (process con spawn), stdout không có .buffer
    # Bỏ qua — process con không cần stdout thật
    pass

# ★ Wrap stdin với UTF-8
# Đây là fix chính: đọc bytes từ pipe và decode UTF-8 đúng cách
try:
    sys.stdin = io.TextIOWrapper(
        sys.stdin.buffer,
        encoding="utf-8",
        errors="replace"   # Thay ký tự lỗi bằng ? thay vì crash
    )
except AttributeError:
    pass  # Process con spawn không có stdin thật

os.environ["PYTHONUNBUFFERED"] = "1"

# ==============================================================================
# IMPORTS
# ==============================================================================
import json
import asyncio
import argparse

from pydantic import ValidationError
from src.domain.schemas import RunPipelineRequest
from src.application.pipeline_manager import PipelineManager
from src.security.token_guard import verify_session_token


# ==============================================================================
# HELPERS
# ==============================================================================
def emit_json(stage, pct, status, msg, meta=None):
    obj = {"stage": stage, "pct": pct, "status": status, "msg": msg}
    if meta:
        obj["meta"] = meta
    try:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    except Exception:
        pass


def safe_stderr(msg: str):
    try:
        sys.stderr.write(msg + "\n")
        sys.stderr.flush()
    except Exception:
        pass


# ==============================================================================
# XỬ LÝ 1 JOB
# ==============================================================================
async def process_job(parsed: dict, workspace_dir: str):
    session_token = parsed.get("session_token", "")
    hwid = parsed.get("hwid", "")

    is_valid, err_msg = verify_session_token(session_token, hwid)
    # is_valid, err_msg = True, "OK"
    if not is_valid:
        emit_json("complete", 0, "err", f"❌ License: {err_msg}")
        return False

    emit_json("init", 1, "inf", "✅ License hợp lệ, đang chuẩn bị...")

    try:
        req = RunPipelineRequest.model_validate(parsed)
    except ValidationError as e:
        emit_json("complete", 0, "err", f"Config lỗi: {e}")
        return False
    except Exception as e:
        emit_json("complete", 0, "err", f"Parse config lỗi: {e}")
        return False

    manager = PipelineManager(output_base_dir=workspace_dir)
    worker_task = asyncio.create_task(manager.start_worker())
    await manager.add_task(req)
    await manager.queue.join()

    manager.is_running = False
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

    return True


# ==============================================================================
# SERVER MODE
# ==============================================================================
async def server_mode(workspace_dir: str):
    emit_json("init", 0, "inf", "🚀 Engine server khởi động, chờ job...")

    loop = asyncio.get_event_loop()

    while True:
        try:
            line = await loop.run_in_executor(None, _safe_readline)
        except Exception as e:
            safe_stderr(f"[Server] Lỗi đọc stdin: {e}")
            break

        if line is None:
            safe_stderr("[Server] stdin đóng, tắt engine.")
            break

        line = line.strip()
        if not line:
            continue

        # ★ DEBUG: in ra để kiểm tra encoding (xóa sau khi fix xong)
        safe_stderr(f"[Server] Job nhận: {repr(line[:120])}")

        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as e:
            emit_json("complete", 0, "err", f"JSON parse lỗi: {e}")
            continue

        # Kiểm tra video_path đã decode đúng chưa
        video_path = parsed.get("video_path", "")
        safe_stderr(f"[Server] video_path: {video_path}")

        try:
            await process_job(parsed, workspace_dir=workspace_dir)
        except Exception as e:
            safe_stderr(f"[Server] Job lỗi: {e}")
            emit_json("complete", 0, "err", f"❌ Lỗi không xác định: {e}")

        emit_json("_server_ready", 0, "inf", "Server sẵn sàng")


def _safe_readline() -> str | None:
    """
    Đọc 1 dòng từ stdin (đã được wrap UTF-8 ở trên).
    Trả về None nếu EOF hoặc pipe lỗi.
    """
    try:
        line = sys.stdin.readline()
        return line if line else None
    except OSError as e:
        safe_stderr(f"[Server] stdin OSError: {e}")
        return None
    except UnicodeDecodeError as e:
        # Không nên xảy ra vì đã dùng errors='replace', nhưng phòng thủ
        safe_stderr(f"[Server] stdin decode lỗi: {e}")
        return None
    except Exception as e:
        safe_stderr(f"[Server] stdin lỗi: {e}")
        return None


# ==============================================================================
# MAIN
# ==============================================================================
async def main():
    parser = argparse.ArgumentParser(description="AutoClip AI Core Engine")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--payload", type=str, help="JSON payload (one-shot)")
    group.add_argument("--server",  action="store_true", help="Server mode")

    parser.add_argument("--workspace", type=str, default="./workspace")

    args = parser.parse_args()

    if args.server:
        await server_mode(workspace_dir=args.workspace)
    else:
        # One-shot mode: --payload nhận từ command line arg
        # Command line arg trên Windows cũng có thể bị encoding sai
        # → decode lại từ bytes nếu cần
        payload_str = args.payload
        try:
            parsed = json.loads(payload_str)
        except Exception as e:
            emit_json("complete", 0, "err", f"Payload JSON lỗi: {e}")
            sys.exit(1)

        success = await process_job(parsed, workspace_dir=args.workspace)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    try:
        multiprocessing.set_start_method("spawn", force=True)
    except RuntimeError:
        pass

    asyncio.run(main())