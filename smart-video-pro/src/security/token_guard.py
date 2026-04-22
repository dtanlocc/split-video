# smart-video-pro/src/security/token_guard.py
"""
Token Guard — Python side security
Nhiệm vụ: verify session_token với Supabase trước khi chạy pipeline
"""

import ssl
import json
import urllib.request
import urllib.error
import hashlib
import os
import time
import ctypes
import subprocess
from typing import Tuple

# ==============================================================================
# CONFIG
# ==============================================================================
EDGE_FUNC_URL = "https://ezsvulvxvcjxryyhqyga.supabase.co/functions/v1/verify-license"
ANON_KEY      = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImV6c3Z1bHZ4dmNqeHJ5eWhxeWdhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY4NDY1OTgsImV4cCI6MjA5MjQyMjU5OH0.07-ynitsEw7LFyKLbWu4lt_M8wZXmmRyJWkaW73lDcw"  # anon key

# Supabase cert fingerprint (lấy bằng: openssl s_client -connect supabase.co:443)
# Cập nhật khi cert renewal
SUPABASE_CERT_SHA256 = None  # Set sau khi lấy fingerprint thực

_SUSPICIOUS_PROCESSES = {
    "x64dbg.exe", "x32dbg.exe", "ollydbg.exe", "windbg.exe",
    "idaq.exe", "idaq64.exe", "dnspy.exe", "de4dot.exe",
    "cheatengine.exe", "cheatengine-x86_64.exe",
    "processhacker.exe", "fiddler.exe", "fiddler4.exe",
    "charles.exe", "mitmproxy.exe", "wireshark.exe",
}

# ==============================================================================
# 1. ANTI-DEBUG / ANTI-MITM CHECKS
# ==============================================================================
def _is_debugger_present() -> bool:
    try:
        if ctypes.windll.kernel32.IsDebuggerPresent():
            return True
        is_remote = ctypes.c_bool(False)
        ctypes.windll.kernel32.CheckRemoteDebuggerPresent(
            ctypes.windll.kernel32.GetCurrentProcess(),
            ctypes.byref(is_remote)
        )
        return is_remote.value
    except:
        return False

def _is_mitm_tool_running() -> bool:
    """Kiểm tra các tool có thể intercept HTTPS"""
    try:
        out = subprocess.check_output(
            "tasklist /FO CSV /NH",
            shell=True, stderr=subprocess.DEVNULL
        ).decode(errors='ignore').lower()
        return any(p.lower() in out for p in _SUSPICIOUS_PROCESSES)
    except:
        return False

def _is_safe_environment() -> bool:
    return not (_is_debugger_present() or _is_mitm_tool_running())

# ==============================================================================
# 2. HWID (giống Tauri để HWID khớp nhau)
# ==============================================================================
def _get_hwid() -> str:
    parts = []
    cmds = [
        ("powershell -NoProfile -Command \"Get-WmiObject Win32_ComputerSystemProduct | Select-Object -ExpandProperty UUID\"",        "MB_UNKNOWN"),
        ("powershell -NoProfile -Command \"Get-WmiObject Win32_Processor | Select-Object -ExpandProperty ProcessorId\"",              "CPU_UNKNOWN"),
        ("powershell -NoProfile -Command \"Get-WmiObject Win32_DiskDrive | Select-Object -ExpandProperty SerialNumber\"",             "DISK_UNKNOWN"),
    ]
    for cmd, fallback in cmds:
        try:
            out = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL)
            val = out.decode().strip()
            parts.append(val if val else fallback)
        except:
            parts.append(fallback)

    raw = f"OVERLORD_{'|'.join(parts)}_AUTOCIP_SALT"
    return hashlib.sha256(raw.encode()).hexdigest()[:32].upper()

# ==============================================================================
# 3. HTTPS REQUEST VỚI SSL VERIFICATION
# ==============================================================================
def _call_edge(action: str, body: dict, timeout: int = 15) -> dict:
    payload = {**body, "action": action}
    print(f"[DEBUG] Sending to edge: {json.dumps(payload)}", flush=True)
    data    = json.dumps(payload).encode("utf-8")

    # SSL context chuẩn — verify certificate chain
    ctx = ssl.create_default_context()
    ctx.verify_mode   = ssl.CERT_REQUIRED
    ctx.check_hostname = True

    req = urllib.request.Request(
        EDGE_FUNC_URL,
        data    = data,
        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {ANON_KEY}",
        }
    )

    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))

# ==============================================================================
# 4. PUBLIC API: VERIFY TOKEN
# ==============================================================================
def verify_session_token(token: str, hwid: str) -> Tuple[bool, str]:
    """
    Verify token với Supabase trước khi chạy pipeline.
    Returns: (is_valid, error_message)
    """
    print(f"[DEBUG-1] token len={len(token) if token else 0}", flush=True)
    print(f"[DEBUG-2] hwid len={len(hwid) if hwid else 0}", flush=True)
    print(f"[DEBUG-3] safe env={_is_safe_environment()}", flush=True)
    
    local_hwid = _get_hwid()
    print(f"[DEBUG-4] local_hwid={local_hwid}", flush=True)
    print(f"[DEBUG-5] passed_hwid={hwid}", flush=True)
    print(f"[DEBUG-6] hwid match={hwid == local_hwid}", flush=True)
    # Guard 1: môi trường an toàn không?
    if not _is_safe_environment():
        return False, "Phát hiện công cụ can thiệp! Vui lòng tắt debugger/proxy."

    # Guard 2: input cơ bản
    if not token or len(token) != 64:
        return False, "Session token không hợp lệ!"

    if not hwid or len(hwid) != 32:
        return False, "HWID không hợp lệ!"

    # Guard 3: HWID khớp với máy này
    # local_hwid = _get_hwid()
    if hwid != local_hwid:
        return False, "HWID không khớp với máy hiện tại!"

    # Guard 4: Verify với Supabase
    try:
        result = _call_edge("consume_token", {
            "p_token": token,
            "p_hwid":  hwid,
        })
        if result.get("ok") is True:
            return True, ""
        else:
            return False, "Token không hợp lệ hoặc đã hết hạn!"

    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="ignore")
        try:
            err = json.loads(err).get("error", err)
        except:
            pass
        return False, f"Server từ chối: {err}"

    except Exception as e:
        return False, f"Lỗi kết nối Supabase: {str(e)}"