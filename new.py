import os
from pathlib import Path

def create_project_structure():
    project_name = "smart-video-pro"
    base_path = Path(project_name)

    # Danh sách các thư mục cần tạo theo Clean Architecture
    folders = [
        "src/domain",               # Entities & Interfaces
        "src/application",          # Use Cases & Orchestrator
        "src/infrastructure/ai",    # B1 (Whisper) & B4 (YOLO)
        "src/infrastructure/video", # B3 (FFmpeg)
        "src/infrastructure/llm",   # B2 (Prompt)
        "src/infrastructure/utils", # Step 0 (Text Normalization)
        "src/presentation/ui",      # PySide6 Views
        "src/presentation/viewmodels",
        "assets/models",            # Chứa yolov8n.pt, v.v.
        "assets/icons",
        "configs",                  # YAML/JSON configs
        "tests",
    ]

    # Danh sách các file khởi tạo ban đầu với mô tả vai trò
    files = {
        "pyproject.toml": "# Project dependencies (managed by uv)",
        "src/main.py": '"""Entry point to start the Desktop Application."""',
        "src/domain/entities.py": '"""Domain models (VideoSegment, DetectionBox) - No dependencies."""',
        "src/domain/interfaces.py": '"""Abstract classes for Dependency Inversion."""',
        "src/application/pipeline_service.py": '"""Orchestrator to manage Step 0 -> B4 logic."""',
        "src/infrastructure/utils/text_cleaner.py": '"""Step 0: High-performance text normalization."""',
        "src/infrastructure/ai/whisper_impl.py": '"""B1: Speech-to-Text implementation."""',
        "src/infrastructure/llm/prompt_engine.py": '"""B2: Prompting logic for segment analysis."""',
        "src/infrastructure/video/ffmpeg_core.py": '"""B3: FFmpeg wrapper for zero-copy cutting."""',
        "src/infrastructure/ai/yolo_impl.py": '"""B4: GPU-accelerated object detection."""',
        "src/presentation/ui/main_window.py": '"""Main View using PySide6."""',
        "src/presentation/thread_manager.py": '"""Multi-threading for background AI tasks."""',
    }

    print(f"🚀 Initializing project: {project_name}")

    # Tạo thư mục
    for folder in folders:
        path = base_path / folder
        path.mkdir(parents=True, exist_ok=True)
        # Tạo file __init__.py để biến thư mục thành python package
        (path / "__init__.py").touch()

    # Tạo file
    for file_path, content in files.items():
        full_path = base_path / file_path
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

    print(f"✅ Structure created successfully!")
    print(f"Next step: Run 'uv init' in {project_name} folder.")

if __name__ == "__main__":
    create_project_structure()