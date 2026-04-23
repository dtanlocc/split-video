"""
scan_structure.py - Chạy ở thư mục gốc project để in cấu trúc thư mục
python scan_structure.py
"""
import os
from pathlib import Path

IGNORE = {
    '__pycache__', '.git', 'node_modules', '.venv', 'venv',
    'env', '.mypy_cache', '.pytest_cache', 'dist', 'build',
    '.next', 'target', '.cargo', 'yolov8n.pt', 'logs'
}

def print_tree(path: Path, prefix: str = "", max_depth: int = 6, depth: int = 0):
    if depth > max_depth:
        return

    try:
        entries = sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    except PermissionError:
        return

    entries = [e for e in entries if e.name not in IGNORE and not e.name.startswith('.')]

    for i, entry in enumerate(entries):
        is_last = (i == len(entries) - 1)
        connector = "└── " if is_last else "├── "
        
        if entry.is_dir():
            print(f"{prefix}{connector}📁 {entry.name}/")
            extension = "    " if is_last else "│   "
            print_tree(entry, prefix + extension, max_depth, depth + 1)
        else:
            size = entry.stat().st_size
            size_str = f"{size/1024:.1f}KB" if size > 1024 else f"{size}B"
            print(f"{prefix}{connector}📄 {entry.name} ({size_str})")

if __name__ == "__main__":
    root = Path(".")
    print(f"\n📦 PROJECT: {root.resolve().name}")
    print("=" * 60)
    print_tree(root)
    print("=" * 60)
    print("✅ Xong!")