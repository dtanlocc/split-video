import os
import sys
import subprocess
import hashlib
import urllib.request
import json
import ctypes
import time
import random
import threading
from pathlib import Path
from loguru import logger

# ==============================================================================
# LÕI BẢO MẬT & XÁC THỰC (HARDCORE SECURITY CORE) - ĐÃ TÍCH HỢP VÀO AUTOCIP
# ==============================================================================

LICENSE_FILE = Path("system.lic")
_ENCRYPTED_RAM_TOKEN = None
_ROLLING_KEY_SEED = int(time.time() * 1000) % 999999

# Secret obfuscation (sau này build PyInstaller sẽ XOR thêm)
def SECRET(s): return s
SUPABASE_URL = SECRET(os.getenv("SUPABASE_URL", "https://gfihmymecoykcogqykbl.supabase.co"))
SUPABASE_ANON_KEY = SECRET(os.getenv("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdmaWhteW1lY295a2NvZ3F5a2JsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzA5NjU4MTMsImV4cCI6MjA4NjU0MTgxM30.SWsdEyLWkOu2tKZS3ZFKk2riCR5uxubXbFvz0a12e_Q"))

logger.add("logs/security.log", rotation="5 MB", retention="30 days", level="INFO")

# ------------------------------------------------------------------------------
# 1. ANTI-DEBUG & ANTI-VM
# ------------------------------------------------------------------------------
def _is_debugger_present():
    try:
        if ctypes.windll.kernel32.IsDebuggerPresent(): return True
        is_remote = ctypes.c_bool(False)
        ctypes.windll.kernel32.CheckRemoteDebuggerPresent(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(is_remote))
        return is_remote.value
    except:
        return False

def _is_vm_environment():
    try:
        vm_indicators = [
            "C:\\windows\\system32\\drivers\\vmmouse.sys",
            "C:\\windows\\system32\\drivers\\vmhgfs.sys",
            "C:\\windows\\system32\\drivers\\vboxguest.sys",
            "C:\\windows\\system32\\drivers\\vboxmouse.sys",
            "C:\\windows\\system32\\drivers\\vboxvideo.sys"
        ]
        for f in vm_indicators:
            if os.path.exists(f): return True

        class SYSTEM_INFO(ctypes.Structure):
            _fields_ = [("dwNumberOfProcessors", ctypes.c_ulong)]
        sysinfo = SYSTEM_INFO()
        ctypes.windll.kernel32.GetSystemInfo(ctypes.byref(sysinfo))
        if sysinfo.dwNumberOfProcessors < 2: return True
        return False
    except:
        return False

def is_deep_hacker_environment():
    if _is_debugger_present() or _is_vm_environment():
        return True
    t1 = time.perf_counter()
    for _ in range(5000): pass
    t2 = time.perf_counter()
    return (t2 - t1) > 0.1

# ------------------------------------------------------------------------------
# 2. MEMORY PROTECTION
# ------------------------------------------------------------------------------
def _grant_session():
    global _ENCRYPTED_RAM_TOKEN, _ROLLING_KEY_SEED
    salt = f"RUNTIME_SALT_{_ROLLING_KEY_SEED}_SECURE"
    raw_token = hashlib.sha256((get_hwid() + salt).encode()).hexdigest()
    _ENCRYPTED_RAM_TOKEN = []
    for c in raw_token:
        val = ord(c)
        val = ((val << 4) | (val >> 4)) & 0xFF
        val = val ^ (_ROLLING_KEY_SEED & 0xFF)
        _ENCRYPTED_RAM_TOKEN.append(val)

def is_session_valid():
    global _ENCRYPTED_RAM_TOKEN, _ROLLING_KEY_SEED
    if is_deep_hacker_environment():
        _ENCRYPTED_RAM_TOKEN = None
        return False
    if not _ENCRYPTED_RAM_TOKEN:
        return False

    t_start = time.perf_counter()
    try:
        decoded_chars = []
        for val in _ENCRYPTED_RAM_TOKEN:
            val = val ^ (_ROLLING_KEY_SEED & 0xFF)
            val = ((val << 4) | (val >> 4)) & 0xFF
            decoded_chars.append(chr(val))
        decrypted_token = "".join(decoded_chars)

        expected = hashlib.sha256((get_hwid() + f"RUNTIME_SALT_{_ROLLING_KEY_SEED}_SECURE").encode()).hexdigest()
        is_valid = (decrypted_token == expected)

        if is_valid:
            _ROLLING_KEY_SEED = (_ROLLING_KEY_SEED * 1664525 + 1013904223) & 0xFFFFFFFF
            _grant_session()
        return is_valid
    except:
        return False
    finally:
        if (time.perf_counter() - t_start) > 0.5:
            _ENCRYPTED_RAM_TOKEN = [0x00] * 10
            return False

# ------------------------------------------------------------------------------
# 3. HWID + LICENSE
# ------------------------------------------------------------------------------
def get_hwid():
    try:
        cmd = "wmic csproduct get uuid"
        uuid = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().split('\n')[1].strip()
        return hashlib.sha256(f"OVERLORD_{uuid}_SALT".encode()).hexdigest()[:24].upper()
    except:
        return "UNKNOWN-HWID-FATAL"

def _generate_license_hash(key: str, hwid: str):
    return hashlib.sha512(f"||{key}||<<SECURE>>||{hwid}||".encode()).hexdigest()

def check_local_license():
    if is_deep_hacker_environment():
        return False, None
    if not LICENSE_FILE.exists():
        return False, None
    try:
        data = json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
        if data.get("hash") == _generate_license_hash(data.get("key"), get_hwid()):
            _grant_session()
            return True, data.get("key")
    except:
        pass
    return False, None

def verify_key_with_server(user_key: str):
    """Gọi RPC Supabase để verify + bind HWID"""
    hwid = get_hwid()
    try:
        rpc_url = f"{SUPABASE_URL}/rest/v1/rpc/get_secure_payload"
        payload = json.dumps({'p_key': user_key, 'p_hwid': hwid, 'p_asset': 'core_blob'}).encode('utf-8')
        headers = {
            'apikey': SUPABASE_ANON_KEY,
            'Authorization': f'Bearer {SUPABASE_ANON_KEY}',
            'Content-Type': 'application/json'
        }
        req = urllib.request.Request(rpc_url, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            core_data = json.loads(response.read().decode('utf-8'))

            # Lưu license file
            LICENSE_FILE.write_text(json.dumps({
                "key": user_key,
                "hash": _generate_license_hash(user_key, hwid)
            }), encoding="utf-8")

            _grant_session()
            logger.info(f"License {user_key} activated successfully on HWID {hwid}")
            return True, core_data
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8')
        if "HWID mismatch" in err_msg:
            return False, "Key này đã được kích hoạt trên máy khác!"
        if "Invalid" in err_msg or "expired" in err_msg.lower():
            return False, "Key không tồn tại hoặc đã hết hạn!"
        return False, f"Server từ chối: {err_msg}"
    except Exception as e:
        logger.error(f"Verify server error: {e}")
        return False, f"Lỗi kết nối server: {str(e)}"

def run_security_check(emit_func):
    """Entry point cho main_cli.py"""
    is_active, key = check_local_license()
    if is_active and is_session_valid():
        emit_func(0, 3, "inf", "✅ License hợp lệ (offline)")
        return True, key

    emit_func(0, 3, "inf", "🔑 Cần kích hoạt license...")
    return False, None