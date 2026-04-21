# src/application/highlight_service.py

class HighlightService:
    def __init__(self, llm_provider: ILLMProvider):
        self.llm = llm_provider

    def process_video_highlights(self, srt_content: str, lang_hint: str):
        # 1. Gửi prompt lấy segment
        segments = self.llm.analyze_highlights(srt_content)
        
        # 2. Với mỗi segment, tạo title (Sử dụng ThreadPool ở lớp ngoài để song song hóa)
        for seg in segments:
            # Logic cắt chunk từ SRT
            title = self.llm.generate_title(seg['text'], lang_hint)
            seg['title'] = title
            
        return segments
    
    
# src/application/highlight_service.py
import json
import os
from pathlib import Path

class HighlightService:
    def __init__(self, gemini_manager):
        self.gemini = gemini_manager

    def save_atomic_json(self, data, file_path: Path):
        """Rule: Atomic Write để bảo vệ Integrity của JSON"""
        temp_file = file_path.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp_file, file_path) # Thao tác nguyên tử của OS

    def process(self, srt_path: Path, output_dir: Path):
        # 1. Read & Parse SRT (Sử dụng giải thuật tối ưu)
        # 2. Call Gemini Manager lấy segments
        # 3. Với mỗi segment, lấy Title
        # 4. Save atomic
        pass