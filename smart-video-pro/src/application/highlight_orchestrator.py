import json
import os
import re
import srt
from pathlib import Path

class HighlightOrchestrator:
    def __init__(self, engine, srt_utils):
        self.engine = engine
        self.utils = srt_utils

    def _extract_json(self, text):
        match = re.search(r"\[.*\]", text, re.DOTALL)
        return json.loads(match.group(0)) if match else None

    def process_video(self, srt_path: Path, output_dir: Path):
        video_name = srt_path.stem.replace(".English", "")
        out_path = output_dir / f"highlights_{video_name}.json"

        subtitle_text = srt_path.read_text(encoding="utf-8")
        subs = list(srt.parse(subtitle_text))
        
        # Load existing data (resume)
        existing_data = []
        if out_path.exists():
            try:
                existing_data = json.loads(out_path.read_text(encoding="utf-8"))
            except:
                pass

        processed_ranges = {(d["start"], d["end"]) for d in existing_data}

        print(f"🧠 Gửi prompt tìm Highlight cho {video_name}...")
        response = self.engine.safe_generate(self.engine.build_highlight_prompt(subtitle_text))
        
        if not response or not response.text:
            print("❌ Gemini không trả về kết quả. Bỏ qua video này.")
            return

        segments = self._extract_json(response.text)
        if not segments:
            print("❌ Không extract được JSON từ Gemini.")
            return

        print(f"✅ Tìm được {len(segments)} đoạn highlight tiềm năng.")

        for seg in segments:
            key = (seg["start"], seg["end"])
            if key in processed_ranges:
                continue

            chunk_text = self.utils.get_subs_in_range(subs, seg["start"], seg["end"])
            seg["title"] = self.engine.generate_title(chunk_text)
            
            existing_data.append(seg)

            # Atomic Save
            temp_path = out_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, out_path)

        print(f"💾 Đã lưu {len(existing_data)} highlight vào {out_path.name}")
            
    # Trong HighlightOrchestrator.py
    def process_multiple(self, srt_dir: Path, output_dir: Path):
        """Thêm hàm này để giống code cũ"""
        srt_files = list(srt_dir.glob("*.srt"))
        for srt_path in srt_files:
            print(f"\n🎬 Đang xử lý: {srt_path.name}")
            self.process_video(srt_path, output_dir)