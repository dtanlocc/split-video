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

        # 1. Đọc file & Resume Logic của bạn
        subtitle_text = srt_path.read_text(encoding="utf-8")
        subs = list(srt.parse(subtitle_text))
        
        existing_data = []
        if out_path.exists():
            try: existing_data = json.loads(out_path.read_text(encoding="utf-8"))
            except: pass

        processed_ranges = {(d["start"], d["end"]) for d in existing_data}

        # 2. Giai đoạn 1: Lấy Highlights
        response = self.engine.safe_generate(self.engine.build_highlight_prompt(subtitle_text))
        segments = self._extract_json(response.text)
        if not segments: return

        # 3. Giai đoạn 2: Tạo Title cho từng đoạn
        for seg in segments:
            if (seg["start"], seg["end"]) in processed_ranges: continue

            chunk_text = self.utils.get_subs_in_range(subs, seg["start"], seg["end"])
            seg["title"] = self.engine.generate_title(chunk_text)
            
            existing_data.append(seg)
            
            # Rule: Atomic Save (Ghi tạm rồi rename để bảo vệ data)
            temp_path = out_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, out_path)