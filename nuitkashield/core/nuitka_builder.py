"""
NuitkaShield — Layer 6: Nuitka Build Orchestrator (v9.1 Fixed)
Tự động hóa quá trình compile Python → native .exe
"""
from __future__ import annotations
import os
import sys
import subprocess
import platform
from pathlib import Path
from typing import List, Optional

# Các module không nên follow/bundle (giảm size + block decompile tools)
# Các module không nên follow/bundle (giảm size + chạy bằng venv ngoài)
IMPORTS = [
        "pdb", "dis", "linecache", "tokenize",
    "py_compile", "compileall",
    "ast", "code", "codeop", "idlelib", "unittest", "unittest.mock"
]
_BLOCK_IMPORTS = [

    "tkinter",
    "torch", "torchvision", "torchaudio", "numpy", "scipy", "matplotlib", "pandas",
    "cv2", "ultralytics", "av", "PIL",
    "whisper", "faster_whisper", "stable_whisper", "ctranslate2",
    "pydantic", "google-genai", "tqdm"
]

# Data files cần copy vào bundle (non-Python resources)
_INCLUDE_DATA = [
    ("yolov8n.pt", "yolov8n.pt"),
]

class NuitkaBuilder:
    def __init__(
        self,
        project_root: Path,
        entry: str = "main_cli.py",
        output_dir: Path = Path("dist"),
        output_name: str = "smart-video-pro",
        console: bool = True,
        lto: bool = True,
        jobs: int = 0,
        python_exe: Optional[str] = None,
    ):
        self.project_root = project_root.resolve()
        self.entry = entry
        self.output_dir = output_dir.resolve()
        self.output_name = output_name
        self.console = console
        self.lto = lto
        self.jobs = jobs or (os.cpu_count() or 4)
        self.python_exe = python_exe or sys.executable

    def check_nuitka(self) -> bool:
        try:
            result = subprocess.run(
                [self.python_exe, "-m", "nuitka", "--version"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                print(f"  ✅ Nuitka version: {result.stdout.strip().split()[0]}")
                return True
        except Exception:
            pass
        print("  ❌ Nuitka không tìm thấy. Cài: pip install nuitka")
        return False

    def build_command(self, shielded_entry: Path) -> List[str]:
        cmd = [self.python_exe, "-m", "nuitka"]

        # ── Core Mode ──────────────────────────────────────────────
        cmd += ["--standalone"]

        # ── Python Optimization ────────────────────────────────────
        cmd += [
            # "--python-flag=no_site",
            "--python-flag=no_warnings",
            "--python-flag=-O",
            "--python-flag=no_asserts",
        ]

        # ── Block Debug/Decompile Modules ──────────────────────────
        for mod in _BLOCK_IMPORTS:
            cmd.append(f"--nofollow-import-to={mod}")

        # ── Cleanup & Optimization ─────────────────────────────────
        cmd += ["--remove-output", "--no-pyi-file"]
        # if self.lto:
        #     cmd.append("--lto=yes")
        # cmd.append(f"--jobs={self.jobs}")

        # ── Console Mode (Nuitka 4.x standard) ─────────────────────
        cmd.append("--windows-console-mode=force" if self.console else "--windows-console-mode=disable")
        cmd.append("--include-module=zoneinfo")
        for mod in IMPORTS:
            cmd.append(f"--include-module={mod}")

        # ── Include Data Files ─────────────────────────────────────
        for src, dst in _INCLUDE_DATA:
            src_path = self.project_root / src
            if src_path.exists():
                cmd.append(f"--include-data-files={src_path}={dst}")

        # ── Package & Windows Flags ────────────────────────────────
        cmd += [
            "--include-package=src",
            "--windows-uac-admin",
            "--assume-yes-for-downloads",
            "--no-deployment-flag=excluded-module-usage",
            
        ]
        cmd += ["--remove-output", "--lto=yes", "--jobs=0"]
        cmd.append("--include-package-data=langdetect")
        cmd.append("--include-package-data=language_data")

        # ── Output ─────────────────────────────────────────────────
        self.output_dir.mkdir(parents=True, exist_ok=True)
        cmd += [
            f"--output-filename={self.output_name}",
            f"--output-dir={self.output_dir}",
        ]
        cmd.append(str(shielded_entry))
        return cmd

    def run(self, shielded_entry: Path) -> bool:
        if not self.check_nuitka():
            return False

        cmd = self.build_command(shielded_entry)

        print(f"\n⚙️  Running Nuitka compilation...")
        print(f"  Entry: {shielded_entry}")
        print(f"  Output: {self.output_dir / self.output_name}")
        print(f"  Jobs: {self.jobs} parallel")
        print(f"  LTO: {'yes' if self.lto else 'no'}\n")

        result = subprocess.run(cmd, cwd=str(self.project_root))

        if result.returncode == 0:
            # SỬA ĐOẠN NÀY ĐỂ TRỎ VÀO THƯ MỤC .dist
            dist_folder_name = Path(shielded_entry).stem + ".dist"
            exe_path = self.output_dir / dist_folder_name / (
                self.output_name + (".exe" if platform.system() == "Windows" else "")
            )
            
            if exe_path.exists():
                size_mb = exe_path.stat().st_size / (1024 * 1024)
                print(f"\n✅ Compilation successful!")
                print(f"   Output: {exe_path}")
                print(f"   Size: {size_mb:.1f} MB")
                return True
            else:
                print(f"\n⚠️  Compilation done but output not found: {exe_path}")
                return False
        else:
            print(f"\n❌ Nuitka compilation failed (exit code {result.returncode})")
            return False