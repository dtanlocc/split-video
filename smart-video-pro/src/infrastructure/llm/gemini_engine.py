# src/infrastructure/llm/gemini_engine.py
# ★ 3-LAYER LANGUAGE ENFORCEMENT — Đồng bộ với DeepSeekEngine

from google import genai
from google.genai import types
import threading
import itertools
import time
import re
import json
import langcodes
from typing import List, Optional, Dict

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
MAX_CHARS      = 30_000   # Chunk size
CHUNK_OVERLAP  = 2_000    # Overlap giữa các chunk
LANG_CONFIG    = {
    "vi": {"name": "Vietnamese", "example": "điều bất ngờ khi thói quen dọn dẹp tiết lộ mẹo cất đồ"},
    "en": {"name": "English", "example": "what happens when a simple cleaning trick reveals a hidden storage tip"},
    "ja": {"name": "Japanese", "example": "シンプルな掃除の習慣が隠れた収納のコツを明かすとき"},
    "ko": {"name": "Korean", "example": "간단한 청소 습관이 숨겨진 수납 팁을 밝혀낼 때"},
    "zh": {"name": "Chinese", "example": "当简单的清洁习惯揭示隐藏的收纳技巧时"},
    "es": {"name": "Spanish", "example": "lo que sucede cuando un truco de limpieza simple revela un consejo de almacenamiento oculto"},
    "fr": {"name": "French", "example": "ce qui se passe quand une astuce de nettoyage simple révèle un conseil de rangement caché"},
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _split_transcript_chunks(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Chia transcript thành chunks, cắt tại ranh giới dòng trống để không cắt timestamp."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunks.append(text[start:])
            break
        cut = text.rfind('\n\n', start, end)
        if cut == -1:
            cut = text.rfind('\n', start, end)
        if cut == -1:
            cut = end
        chunks.append(text[start:cut])
        start = max(start + 1, cut - overlap)
    return chunks


def _to_sec(ts: str) -> float:
    """Convert timestamp 'HH:MM:SS,mmm' → seconds."""
    try:
        h, m, s = ts.replace(",", ".").split(":")
        return float(h) * 3600 + float(m) * 60 + float(s)
    except:
        return 0.0


def _detect_language(text: str) -> str:
    """Simple language detection based on character ranges."""
    if not text:
        return "unknown"
    total = len(text)
    vi = sum(1 for c in text if '\u0300' <= c <= '\u036f' or c in 'ăâđêôơư')
    ja = sum(1 for c in text if '\u3040' <= c <= '\u30ff' or '\u4e00' <= c <= '\u9fff')
    ko = sum(1 for c in text if '\uac00' <= c <= '\ud7af')
    zh = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    lat = sum(1 for c in text if c.isascii() and c.isalpha())
    if vi / total > 0.15: return "vi"
    if ja / total > 0.20: return "ja"
    if ko / total > 0.30: return "ko"
    if zh / total > 0.30 and ja / total < 0.1: return "zh"
    if lat / total > 0.70: return "en"
    return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# GeminiEngine Class
# ─────────────────────────────────────────────────────────────────────────────

class GeminiEngine:
    """
    Gemini Engine với 3-Layer Language Enforcement — đồng bộ với DeepSeekEngine.
    
    ✅ Prompt ép ngôn ngữ tuyệt đối (Layer 1)
    ✅ Post-check + auto-translate nếu AI sinh sai language (Layer 2+3)
    ✅ Chunking với overlap, duration validation, dedup
    ✅ Key rotation robust
    """

    def __init__(self, api_keys: List[str], model_name: str):
        self.api_keys = [k.strip() for k in api_keys if k.strip()]
        if not self.api_keys:
            raise ValueError("❌ Cần ít nhất 1 Gemini API key")
        
        self.active_keys = self.api_keys.copy()
        self.api_lock = threading.Lock()
        self.model_name = model_name
        self.part_counter = itertools.count(1)
        self.client = None
        self._configure_model()
        print(f"✅ GeminiEngine initialized: model={model_name}, keys={len(self.api_keys)}", flush=True)

    def _configure_model(self):
        """Khởi tạo client Gemini với safety settings."""
        with self.api_lock:
            if not self.active_keys:
                raise RuntimeError("❌ Hết tất cả API Key.")
            self.current_key = self.active_keys[0]
            self.client = genai.Client(api_key=self.current_key)
            self.safety_settings = [
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
            ]
            print(f"🔑 Gemini Key: {self.current_key[:12]}...", flush=True)

    def _rotate_key(self):
        """Chuyển sang key tiếp theo khi key hiện tại lỗi/hết quota."""
        with self.api_lock:
            if self.current_key in self.active_keys:
                self.active_keys.remove(self.current_key)
            if not self.active_keys:
                raise RuntimeError("❌ TẤT CẢ API KEYS ĐÃ HẾT QUOTA!")
            self._configure_model()
            print(f"🔄 Rotated to new key: {self.active_keys[0][:12]}...", flush=True)

    def _call_api(self, prompt: str, max_retries: int = 3) -> Optional[str]:
        """Gọi Gemini API với retry logic."""
        for attempt in range(max_retries):
            try:
                print(f"  📡 Calling Gemini API (attempt {attempt+1}/{max_retries})...", flush=True)
                
                resp = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        safety_settings=self.safety_settings,
                        response_mime_type="application/json",
                        temperature=0.1,  # Thấp để output ổn định
                        max_output_tokens=8000,
                    )
                )
                
                if resp and resp.text and resp.text.strip():
                    content = resp.text.strip()
                    print(f"  ✅ API returned {len(content)} chars", flush=True)
                    return content
                    
            except Exception as e:
                err = str(e).lower()
                if any(k in err for k in ["resource_exhausted", "429", "quota", "permission_denied", "blocked"]):
                    print(f"  ❌ Quota/permission error — rotating key", flush=True)
                    self._rotate_key()
                    time.sleep(2)
                    continue
                print(f"  ❌ Gemini error: {type(e).__name__}: {str(e)[:150]}", flush=True)
                time.sleep(2)
                
        print(f"  ❌ All {max_retries} attempts failed", flush=True)
        return None

    def _parse_json(self, text: str) -> Optional[List[Dict]]:
        """Parse JSON từ response — handle markdown wrapper, extra text."""
        if not text:
            return None
        
        # Strip markdown fences
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^```\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*```$', '', text, flags=re.IGNORECASE)
        text = text.strip()
        
        # Try direct parse
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for key in ("highlights", "segments", "results", "clips"):
                    if isinstance(data.get(key), list):
                        return data[key]
        except json.JSONDecodeError:
            pass
        
        # Fallback: find JSON array in text
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass
        
        # Last resort: salvage truncated JSON
        last_obj = text.rfind('},')
        if last_obj > 0:
            bracket = text.find('[')
            if bracket >= 0:
                salvaged = text[bracket:last_obj + 1] + ']'
                try:
                    data = json.loads(salvaged)
                    if isinstance(data, list) and data:
                        print(f"  ⚠️ JSON bị cắt — cứu được {len(data)} segments", flush=True)
                        return data
                except json.JSONDecodeError:
                    pass
        
        print(f"  ⚠️ JSON parse failed hoàn toàn", flush=True)
        return None

    def _validate_segment(self, seg: Dict, min_sec: int, max_sec: int) -> bool:
        """Validate segment: fields + duration."""
        if not isinstance(seg, dict):
            return False
        if not all(k in seg for k in ["start", "end", "title"]):
            return False
        title = seg.get("title", "")
        if not title or not isinstance(title, str) or len(title.strip()) < 3:
            return False
        
        # Validate duration
        try:
            duration = _to_sec(seg["end"]) - _to_sec(seg["start"])
            if duration < min_sec - 5 or duration > max_sec + 30:  # ± tolerance
                return False
        except:
            return False
        
        return True

    def _translate_fallback(self, title: str, target_lang: str) -> str:
        """Auto-translate title nếu language không khớp target."""
        target_name = LANG_CONFIG.get(target_lang, {}).get("name", target_lang)
        
        translate_prompt = (
            f"Translate this title to {target_name}. "
            f"Return ONLY the translated title, no quotes, no explanation.\n\n"
            f"Original: {title}\n"
            f"Translated:"
        )
        
        try:
            resp = self.client.models.generate_content(
                model=self.model_name,
                contents=translate_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.05,
                    max_output_tokens=200,
                )
            )
            if resp and resp.text:
                translated = resp.text.strip().strip('"\'')
                if translated and len(translated) > 3:
                    return translated
        except Exception as e:
            print(f"  ⚠️ Translation failed: {e}", flush=True)
        
        # Fallback: return original
        return title

    def _build_prompt(self, chunk: str, min_sec: int, max_sec: int, target_lang: str, 
                      chunk_idx: int, total_chunks: int, time_hint: str = "") -> str:
        """Build prompt với language enforcement TRIỆT ĐỂ."""
        lang_info = LANG_CONFIG.get(target_lang, {"name": target_lang, "example": "engaging title here"})
        lang_name = lang_info["name"]
        lang_example = lang_info["example"]
        
        # Few-shot examples trong target language
        examples = json.dumps([
            {"start": "00:00:10,000", "end": "00:00:40,000", "title": lang_example},
            {"start": "00:01:20,000", "end": "00:01:55,000", "title": f"another engaging title in {lang_name}"},
        ], ensure_ascii=False, indent=2)
        
        chunk_note = ""
        if total_chunks > 1:
            chunk_note = (
                f"\n⚠️ NOTE: This is chunk {chunk_idx+1}/{total_chunks}. "
                f"Only extract segments within this chunk. {time_hint}"
            )
        
        # 🔥 CRITICAL: Explicit language enforcement in prompt
        language_rules = f"""
🔥 LANGUAGE RULES — ABSOLUTELY CRITICAL:
1. ALL titles MUST be written in **{lang_name}** language.
2. DO NOT use the transcript's original language for titles.
3. Translate the core meaning into natural {lang_name}.
4. Example CORRECT: "{lang_example}"
5. Example WRONG: "Amazing cleaning hack" (English when target is {lang_name}) — NEVER DO THIS.
"""
        
        return f"""You are a professional video editor creating titles for TikTok/Shorts/Reels.

{language_rules}

TASK: Extract the most engaging segments from this transcript.

OUTPUT FORMAT — STRICT JSON ARRAY ONLY:
[
  {{"start": "HH:MM:SS,mmm", "end": "HH:MM:SS,mmm", "title": "title in {lang_name}"}},
  ...
]

RULES:
1. Timestamps: exact format "HH:MM:SS,mmm" (e.g., "00:01:23,456")
2. Duration: each segment MUST be {min_sec}–{max_sec} seconds
3. Title: 5–18 words, engaging, natural sentence style in {lang_name}
4. Extract only 3–8 best segments per chunk
5. Return ONLY valid JSON array. No markdown, no explanation.

FEW-SHOT EXAMPLES (in {lang_name}):
{examples}

TRANSCRIPT (chunk {chunk_idx+1}/{total_chunks}):
{chunk[:45000]}

REMINDER: Titles MUST be in {lang_name}. Return JSON array only:"""

    def analyze_highlights(
        self,
        subtitle_text: str,
        min_sec: int,
        max_sec: int,
        title_language: str = "en"
    ) -> List[Dict]:
        """
        Phân tích transcript với 3-layer language enforcement.
        """
        print(f"\n🔍 Gemini.analyze_highlights()", flush=True)
        print(f"   ├─ Input: {len(subtitle_text)} chars", flush=True)
        print(f"   ├─ Duration: {min_sec}-{max_sec}s", flush=True)
        print(f"   └─ Target language: {title_language}", flush=True)
        
        if len(subtitle_text.strip()) < 200:
            print(f"  ⚠️ Input too short, returning empty", flush=True)
            return []
        
        # Chunk transcript
        chunks = _split_transcript_chunks(subtitle_text, MAX_CHARS, CHUNK_OVERLAP)
        print(f"  📦 Split into {len(chunks)} chunk(s)", flush=True)
        
        all_segments: List[Dict] = []
        target_lower = title_language.lower()
        
        for idx, chunk in enumerate(chunks):
            print(f"\n  ── Chunk {idx+1}/{len(chunks)} ({len(chunk)} chars) ──", flush=True)
            
            # Get time range hint for AI
            ts_matches = re.findall(r'\d{2}:\d{2}:\d{2},\d{3}', chunk)
            time_hint = f"Timestamps in this chunk: {ts_matches[0]} → {ts_matches[-1]}." if ts_matches else ""
            
            # Build prompt với language enforcement
            prompt = self._build_prompt(
                chunk, min_sec, max_sec, title_language,
                chunk_idx=idx, total_chunks=len(chunks), time_hint=time_hint
            )
            print(f"  📝 Prompt: {len(prompt)} chars", flush=True)
            
            # Call API
            raw = self._call_api(prompt, max_retries=3)
            if not raw:
                print(f"  ❌ Chunk {idx+1}: API call failed", flush=True)
                continue
            
            # Parse JSON
            segs = self._parse_json(raw)
            if not segs:
                print(f"  ❌ Chunk {idx+1}: JSON parse failed", flush=True)
                continue
            
            print(f"  ✅ Chunk {idx+1}: parsed {len(segs)} raw segments", flush=True)
            
            # Validate + Language enforcement (Layer 2+3)
            chunk_valid = 0
            for seg in segs:
                if not self._validate_segment(seg, min_sec, max_sec):
                    continue
                
                title = seg["title"].strip()
                detected = _detect_language(title)
                
                # 🔥 LANGUAGE ENFORCEMENT: Auto-translate if mismatch
                if detected != target_lower and detected != "unknown":
                    print(f"  ⚠️ Lang mismatch ({detected}→{target_lower}): '{title[:40]}...'", flush=True)
                    seg["title"] = self._translate_fallback(title, target_lower)
                    print(f"  ✅ Translated: '{seg['title'][:40]}...'", flush=True)
                
                all_segments.append(seg)
                chunk_valid += 1
            
            print(f"  ✅ Chunk {idx+1}: {chunk_valid} valid segments", flush=True)
            
            # Rate-limit giữa các chunk
            if idx < len(chunks) - 1:
                time.sleep(1)
        
        # Dedup + sort
        seen = set()
        final = []
        for s in sorted(all_segments, key=lambda x: _to_sec(x.get("start", ""))):
            key = s.get("start", "")
            if key and key not in seen:
                seen.add(key)
                final.append(s)
        
        print(f"\n  ✅ Final: {len(final)} segments (language enforced)", flush=True)
        return final

    def generate_title(self, text_chunk: str, target_language: str = "en") -> str:
        """Generate single title với language enforcement — dùng cho fallback."""
        if not text_chunk.strip():
            return f"Part {next(self.part_counter)}"
        
        lang_name = LANG_CONFIG.get(target_language, {}).get("name", target_language)
        
        prompt = f"""You are a professional video title writer.
Write ONE engaging title in **{lang_name}**.

RULES:
1. Natural sentence style, start lowercase (except proper nouns)
2. Include articles: a, an, the, and, of, to, in
3. Length: 10–16 words exactly
4. Add curiosity/emotion: use "why", "how", "secret", "unexpected"
5. Return ONLY the title — no quotes, no markdown

Text to summarize:
{text_chunk[:1500]}"""
        
        raw = self._call_api(prompt, max_retries=2)
        if raw:
            clean = raw.strip().strip('"\'').strip()
            words = clean.split()
            if clean and 8 <= len(words) <= 20:
                return clean
        
        # Fallback
        return f"Part {next(self.part_counter)}"

    def release_resources(self):
        """Cleanup resources."""
        self.client = None
        print("🧹 GeminiEngine released", flush=True)