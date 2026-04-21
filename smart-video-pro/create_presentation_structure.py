# create_presentation_structure.py
import os
from pathlib import Path

def create_structure():
    base = Path("src/presentation")
    
    structure = {
        "": ["__init__.py"],
        "styles": ["dark_theme.qss", "__init__.py"],
        "widgets": ["__init__.py", "pipeline_panel.py", "video_dropzone.py", 
                   "step_progress.py", "log_console.py", "status_bar.py"],
        "dialogs": ["__init__.py", "settings_dialog.py", "about_dialog.py"],
        "resources": ["__init__.py"],  # sau này bỏ icon, logo vào đây
        "utils": ["__init__.py", "signal_bus.py"],
        "viewmodels": ["__init__.py", "main_viewmodel.py"]
    }

    print("🚀 Đang tạo cấu trúc Presentation Layer...\n")
    
    for folder, files in structure.items():
        dir_path = base / folder
        dir_path.mkdir(parents=True, exist_ok=True)
        
        for file in files:
            file_path = dir_path / file
            if not file_path.exists():
                file_path.touch()
                print(f"   ✅ Tạo: {file_path}")
            else:
                print(f"   ⏭️  Đã tồn tại: {file_path}")
    
    print("\n✅ Hoàn tất! Cấu trúc Presentation Layer đã được tạo.")
    print(f"📂 Đường dẫn: {base.resolve()}")

if __name__ == "__main__":
    create_structure()