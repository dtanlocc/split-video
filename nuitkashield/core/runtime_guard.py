"""
NuitkaShield — Layer 7: Runtime Protection Guard
Template inject vào entry point (main_cli.py).
Chạy trước mọi thứ, kiểm tra môi trường, thoát êm nếu phát hiện.

Thiết kế "fail-silent": không raise exception, không log — chỉ exit.
Điều này khiến attacker khó biết check nào bị trigger.
"""

# =============================================================================
# GUARD STUB — đây là string template, được inject vào đầu main_cli.py
# Sau đó Nuitka compile toàn bộ thành native binary.
# =============================================================================

GUARD_STUB = r'''
# ── NuitkaShield Runtime Guard ─────────────────────────────────────────────
import sys as _sys, os as _os, time as _time, ctypes as _ct
import threading as _th, hashlib as _hx, struct as _st
import subprocess as _sp, platform as _pl, uuid as _ud

class _𝔊:
    """Runtime protection — tên Unicode khó tìm trong decompiled output."""

    # Delay ngẫu nhiên trước khi exit (4–8s) → không lộ timing pattern
    _EXIT_DELAY = (4, 8)

    # Danh sách process đáng ngờ (debugger, proxy, reverse tool)
    _BAD_PROCS = {
        "x64dbg", "x32dbg", "ollydbg", "windbg", "idaq", "idaq64",
        "ida64", "ida32", "radare2", "r2", "ghidra", "ghidrarun",
        "dnspy", "de4dot", "dotpeek", "ilspy", "reflector",
        "cheatengine", "cheatengine-x86_64",
        "processhacker", "procmon", "procexp", "procexp64",
        "fiddler", "fiddler4", "charles", "mitmproxy", "burpsuite",
        "wireshark", "dumpcap", "tshark",
        "frida", "frida-server", "fridadump",
        "scylla", "scylla_x64", "scylla_x86",
        "apimonitor", "apimonitor-x86",
        "regshot", "autoruns", "autorunsc",
        "pestudio", "lordpe", "peview", "cff explorer",
    }

    # Mutex Windows — các tool thường tạo mutex riêng
    _BAD_MUTEX = [
        "OLLYDBG_MUTEX", "WINDBG_MUTEX",
    ]

    @classmethod
    def _𝔢𝔵𝔦𝔱(cls):
        """Thoát không để lại dấu vết."""
        delay = __import__("random").uniform(*cls._EXIT_DELAY)
        _time.sleep(delay)
        _os._exit(0)  # Hard exit — bỏ qua atexit, finalizers

    @classmethod
    def _𝔡𝔟𝔤(cls) -> int:
        """Anti-debug: nhiều kỹ thuật, trả về score."""
        score = 0
        if _sys.platform != "win32":
            return 0
        try:
            # IsDebuggerPresent
            if _ct.windll.kernel32.IsDebuggerPresent():
                score += 3
            # CheckRemoteDebuggerPresent
            _𝔟 = _ct.c_bool(False)
            _ct.windll.kernel32.CheckRemoteDebuggerPresent(
                _ct.windll.kernel32.GetCurrentProcess(),
                _ct.byref(_𝔟)
            )
            if _𝔟.value:
                score += 3
            # NtQueryInformationProcess — DebugPort
            try:
                _ntdll = _ct.windll.ntdll
                _info = _ct.c_ulong(0)
                _status = _ntdll.NtQueryInformationProcess(
                    _ct.windll.kernel32.GetCurrentProcess(),
                    7,  # ProcessDebugPort
                    _ct.byref(_info),
                    _ct.sizeof(_info),
                    None,
                )
                if _status == 0 and _info.value != 0:
                    score += 4
            except:
                pass
        except:
            pass
        return score

    @classmethod
    def _𝔱𝔦𝔪𝔦𝔫𝔤(cls) -> int:
        """Timing check — debugger làm chậm execution đáng kể."""
        _t1 = _time.perf_counter_ns()
        _ = sum(_i * _i for _i in range(8000))
        _t2 = _time.perf_counter_ns()
        elapsed = _t2 - _t1
        if elapsed > 200_000_000:   # > 200ms — rất chậm
            return 3
        if elapsed > 80_000_000:    # > 80ms — nghi ngờ
            return 1
        return 0

    @classmethod
    def _𝔭𝔯𝔬𝔠(cls) -> int:
        """Kiểm tra process đáng ngờ đang chạy."""
        score = 0
        if _sys.platform != "win32":
            return 0
        try:
            _out = _sp.check_output(
                "tasklist /FO CSV /NH",
                shell=True, stderr=_sp.DEVNULL, timeout=5
            ).decode("utf-8", errors="ignore").lower()
            for _p in cls._BAD_PROCS:
                if _p.lower() in _out:
                    score += 2
                    if score >= 4:
                        break
        except:
            pass
        return score

    @classmethod
    def _𝔳𝔪(cls) -> int:
        """VM detection — kiểm tra artifacts của hypervisor."""
        score = 0
        # MAC vendor fingerprint
        try:
            _mac = _ud.getnode()
            _mac_str = ":".join(f"{(_mac >> _i & 0xff):02x}" for _i in range(0, 48, 8))
            _vm_vendors = [
                "00:0c:29",  # VMware
                "00:50:56",  # VMware
                "08:00:27",  # VirtualBox
                "00:1c:42",  # Parallels
                "00:16:3e",  # Xen
                "02:42:",    # Docker
            ]
            if any(_mac_str.startswith(_v) for _v in _vm_vendors):
                score += 2
        except:
            pass
        # CPU core count thấp = suspicious (VM thường 1-2 cores)
        _cores = _os.cpu_count() or 4
        if _cores <= 1:
            score += 2
        # Kiểm tra registry VM artifacts (Windows)
        if _sys.platform == "win32":
            try:
                import winreg as _wr
                _vm_keys = [
                    (r"SOFTWARE\VMware, Inc.\VMware Tools", "vmware"),
                    (r"SOFTWARE\Oracle\VirtualBox Guest Additions", "vbox"),
                    (r"SOFTWARE\Parallels\Parallels Tools", "parallels"),
                ]
                for _key, _ in _vm_keys:
                    try:
                        _wr.OpenKey(_wr.HKEY_LOCAL_MACHINE, _key)
                        score += 2
                        break
                    except:
                        pass
            except:
                pass
        return score

    @classmethod
    def _𝔰𝔱𝔞𝔠𝔨(cls) -> int:
        """
        Stack depth check — debugger thường inject frames.
        Nếu stack sâu bất thường tại startup → đáng ngờ.
        """
        import traceback as _tb
        depth = len(_tb.extract_stack())
        if depth > 20:  # Startup bình thường < 10 frames
            return 2
        return 0

    @classmethod
    def 𝔯𝔲𝔫(cls):
        """Master check — gọi khi startup và định kỳ."""
        total = (
            cls._𝔡𝔟𝔤()
            + cls._𝔱𝔦𝔪𝔦𝔫𝔤()
            + cls._𝔳𝔪()
            + cls._𝔭𝔯𝔬𝔠()
        )
        # Threshold = 4: không quá nhạy, nhưng đủ để catch rõ ràng
        if total >= 4:
            cls._𝔢𝔵𝔦𝔱()


# ── Startup check ─────────────────────────────────────────────────────────
_𝔊.𝔯𝔲𝔫()

# ── Periodic background check mỗi 45 giây ────────────────────────────────
def _𝔓():
    while True:
        _time.sleep(45)
        _𝔊.𝔯𝔲𝔫()

_𝔭𝔯𝔬𝔱_𝔱 = _th.Thread(target=_𝔓, daemon=True, name="")
_𝔭𝔯𝔬𝔱_𝔱.start()
# ── End Guard ──────────────────────────────────────────────────────────────
'''


# =============================================================================
# SECURITY PATCH cho token_guard.py
# Vấn đề: ANON_KEY và EDGE_FUNC_URL hardcode plaintext
# Fix: encrypt tại build time, decode tại runtime
# =============================================================================

def generate_secure_constants(anon_key: str, edge_url: str, build_key: bytes) -> str:
    """
    Tạo đoạn code Python thay thế các constant nhạy cảm trong token_guard.py.
    Thay vì hardcode string → lưu dưới dạng XOR-encoded bytes.
    """
    import struct

    def xor_encode(text: str, key: bytes) -> str:
        raw = text.encode("utf-8")
        enc = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
        return enc.hex()

    key16 = build_key[:16]
    anon_hex = xor_encode(anon_key, key16)
    url_hex = xor_encode(edge_url, key16)
    key_hex = key16.hex()

    return f'''
# ── Encrypted constants (NuitkaShield) ─────────────────────────────
import struct as _𝔰𝔱
def _𝔡𝔠(_h: str, _k: bytes) -> str:
    _r = bytes.fromhex(_h)
    return bytes(_b ^ _k[_i % len(_k)] for _i,_b in enumerate(_r)).decode("utf-8")
_𝔎 = bytes.fromhex("{key_hex}")
EDGE_FUNC_URL = _𝔡𝔠("{url_hex}", _𝔎)
ANON_KEY      = _𝔡𝔠("{anon_hex}", _𝔎)
del _𝔡𝔠, _𝔎   # Xóa khỏi namespace sau khi dùng
# ── End encrypted constants ─────────────────────────────────────────
'''