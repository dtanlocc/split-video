# src/infrastructure/llm/deepseek_engine.py
import json
import re
import time
import threading
from typing import List, Optional, Dict
from openai import OpenAI, RateLimitError, AuthenticationError, APIStatusError

LANG_CONFIG = {
    "vi": {"name": "Vietnamese", "example": "điều bất ngờ khi thói quen dọn dẹp tiết lộ mẹo cất đồ"},
    "en": {"name": "English", "example": "what happens when a simple cleaning trick reveals a hidden storage tip"},
    "ja": {"name": "Japanese", "example": "シンプルな掃除の習慣が隠れた収納のコツを明かすとき"},
    "ko": {"name": "Korean", "example": "간단한 청소 습관이 숨겨진 수납 팁을 밝혀낼 때"},
    "zh": {"name": "Chinese", "example": "当简单的清洁习惯揭示隐藏的收纳技巧时"},
    "es": {"name": "Spanish", "example": "lo que sucede cuando un truco de limpieza simple revela un consejo de almacenamiento oculto"},
    "fr": {"name": "French", "example": "ce qui se passe quand une astuce de nettoyage simple révèle un conseil de rangement caché"},
}

# ─────────────────────────────────────────────────────────────────────────────
# Chunking config
# Mỗi chunk ~30k chars → đủ để DeepSeek đọc mà không tốn quá nhiều token
# Overlap 2k chars ở ranh giới để AI không bỏ sót đoạn nằm giữa 2 chunk
# ─────────────────────────────────────────────────────────────────────────────
CHUNK_SIZE   = 30_000   # chars mỗi chunk
CHUNK_OVERLAP = 2_000   # chars overlap giữa các chunk


def _split_transcript_chunks(text: str, chunk_size: int, overlap: int) -> List[str]:
    """
    Chia transcript thành các chunk, cắt tại ranh giới dòng trống
    (giữa 2 subtitle block) để không cắt giữa timestamp.
    """
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunks.append(text[start:])
            break

        # Tìm dòng trống gần nhất trước end để cắt sạch
        cut = text.rfind('\n\n', start, end)
        if cut == -1:
            cut = text.rfind('\n', start, end)
        if cut == -1:
            cut = end

        chunks.append(text[start:cut])
        # Bước tiếp theo lùi lại overlap để không bỏ sót
        start = max(start + 1, cut - overlap)

    return chunks


class DeepSeekEngine:
    def __init__(self, api_keys: List[str], model_name: str = "deepseek-chat"):
        self.api_keys = [k.strip() for k in api_keys if k.strip()]
        if not self.api_keys:
            raise ValueError("❌ Cần ít nhất 1 DeepSeek API key")
        self.active_keys = self.api_keys.copy()
        self.api_lock    = threading.Lock()
        self.model_name  = model_name
        self.client      = self._create_client()
        print(f"✅ DeepSeekEngine initialized: model={model_name}, keys={len(self.api_keys)}", flush=True)

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _create_client(self) -> OpenAI:
        with self.api_lock:
            if not self.active_keys:
                raise RuntimeError("❌ Hết API key")
            return OpenAI(
                api_key=self.active_keys[0],
                base_url="https://api.deepseek.com",
                timeout=180,
            )

    def _rotate_key(self):
        with self.api_lock:
            if len(self.active_keys) <= 1:
                raise RuntimeError("❌ Không còn key nào để retry")
            failed = self.active_keys.pop(0)
            print(f"⚠️ Rotated away from key: {failed[:10]}...", flush=True)
            self.client = OpenAI(
                api_key=self.active_keys[0],
                base_url="https://api.deepseek.com",
                timeout=180,
            )

    # ── API call ──────────────────────────────────────────────────────────────

    def _call_api(self, prompt: str, max_retries: int = 3) -> Optional[str]:
        for attempt in range(max_retries):
            try:
                print(f"  📡 Calling API (attempt {attempt+1}/{max_retries})...", flush=True)
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a helpful assistant that outputs valid JSON only.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=8000,   # ← tăng từ 4096 để tránh bị cắt
                )
                content = response.choices[0].message.content
                if content and content.strip():
                    print(f"  ✅ API returned {len(content)} chars", flush=True)
                    return content.strip()
                print(f"  ⚠️ API returned empty content", flush=True)

            except AuthenticationError:
                print(f"  ❌ Auth error — rotating key", flush=True)
                self._rotate_key()
                time.sleep(1)
            except RateLimitError:
                print(f"  ❌ Rate limit — waiting 5s", flush=True)
                time.sleep(5)
            except APIStatusError as e:
                print(f"  ❌ API error {e.status_code}: {str(e)[:100]}", flush=True)
                if e.status_code in [429, 402, 403]:
                    self._rotate_key()
                    time.sleep(3)
                else:
                    time.sleep(2)
            except Exception as e:
                print(f"  ❌ Unexpected: {type(e).__name__}: {str(e)[:150]}", flush=True)
                time.sleep(2)

        print(f"  ❌ All {max_retries} attempts failed", flush=True)
        return None

    # ── JSON parse ────────────────────────────────────────────────────────────

    def _parse_json(self, text: str) -> Optional[List[Dict]]:
        if not text:
            return None

        # Strip markdown fences
        text = re.sub(r'^```json\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^```\s*',     '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*```$',     '', text, flags=re.IGNORECASE)
        text = text.strip()

        # Thử parse trực tiếp
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for key in ("highlights", "segments", "results"):
                    if isinstance(data.get(key), list):
                        return data[key]
        except json.JSONDecodeError:
            pass

        # Fallback: tìm mảng [...] trong text
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass

        # Fallback cuối: cứu JSON bị cắt giữa chừng
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

    # ── Validate ──────────────────────────────────────────────────────────────

    def _validate(self, seg: Dict) -> bool:
        if not isinstance(seg, dict):
            return False
        if not all(k in seg for k in ["start", "end", "title"]):
            return False
        title = seg.get("title", "")
        return bool(title and isinstance(title, str) and len(title.strip()) >= 3)

    # ── Language ──────────────────────────────────────────────────────────────

    def _detect_language(self, text: str) -> str:
        if not text:
            return "unknown"
        total = len(text)
        vi   = sum(1 for c in text if '\u0300' <= c <= '\u036f' or c in 'ăâđêôơư')
        ja   = sum(1 for c in text if '\u3040' <= c <= '\u30ff' or '\u4e00' <= c <= '\u9fff')
        ko   = sum(1 for c in text if '\uac00' <= c <= '\ud7af')
        zh   = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        lat  = sum(1 for c in text if c.isascii() and c.isalpha())
        if vi  / total > 0.15: return "vi"
        if ja  / total > 0.20: return "ja"
        if ko  / total > 0.30: return "ko"
        if zh  / total > 0.30 and ja / total < 0.1: return "zh"
        if lat / total > 0.70: return "en"
        return "unknown"

    def _translate_fallback(self, title: str, target_lang: str) -> str:
        target_name = LANG_CONFIG.get(target_lang, {}).get("name", target_lang)
        try:
            resp = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Translate this title to {target_name}. "
                        f"Return ONLY the translated title, no quotes.\n\n{title}"
                    ),
                }],
                temperature=0.1,
                max_tokens=200,
            )
            translated = resp.choices[0].message.content.strip().strip('"\'')
            if translated and len(translated) > 3:
                return translated
        except Exception:
            pass
        return title

    # ── Prompt ────────────────────────────────────────────────────────────────

    def _build_prompt(
        self,
        transcript_chunk: str,
        min_sec: int,
        max_sec: int,
        target_lang: str,
        chunk_idx: int,
        total_chunks: int,
        time_hint: str = "",   # "Video time range of this chunk: 00:05:00 → 00:10:00"
    ) -> str:
        lang_info   = LANG_CONFIG.get(target_lang, {"name": target_lang, "example": "engaging title here"})
        lang_name   = lang_info["name"]
        lang_example = lang_info["example"]

        chunk_note = ""
        if total_chunks > 1:
            chunk_note = (
                f"\n⚠️ NOTE: This is chunk {chunk_idx+1}/{total_chunks} of the full transcript. "
                f"Only extract segments whose timestamps fall within this chunk. "
                f"{time_hint}"
            )

        return f"""You are a professional video editor creating titles for short-form TikTok content.

🔥 LANGUAGE RULES:
- ALL titles MUST be in **{lang_name}**.
- DO NOT use any other language.
- Example title: "{lang_example}"
{chunk_note}

TASK: Extract the most engaging segments from the transcript below.

OUTPUT — strict JSON array:
[
  {{"start": "HH:MM:SS,mmm", "end": "HH:MM:SS,mmm", "title": "title in {lang_name}"}},
  ...
]

RULES:
1. Timestamps: exact format "HH:MM:SS,mmm"
2. ⚠️ DURATION: Each segment MUST be {min_sec}–{max_sec} seconds long.
   - {min_sec}s = {min_sec//60} minutes {min_sec%60} seconds
   - {max_sec}s = {max_sec//60} minutes {max_sec%60} seconds  
   - DO NOT create short clips. Each clip must cover a LONG continuous section.
   - Example: start="00:00:00,000" end="00:07:30,000" = 450 seconds ✅
   - WRONG: start="00:00:00,000" end="00:00:15,000" = 15 seconds ❌
3. Extract only 2–5 best segments from the entire video.
4. Title: 5–15 words, punchy, in {lang_name}
5. Return ONLY valid JSON array. No explanation, no markdown.

TRANSCRIPT:
{transcript_chunk}

Return JSON array only:"""

    # ── Dedup & sort ──────────────────────────────────────────────────────────

    @staticmethod
    def _to_sec(ts: str) -> float:
        try:
            h, m, s = ts.replace(",", ".").split(":")
            return float(h) * 3600 + float(m) * 60 + float(s)
        except Exception:
            return 0.0

    def _dedup_sort(self, segments: List[Dict]) -> List[Dict]:
        seen  = set()
        valid = []
        for s in sorted(segments, key=lambda x: self._to_sec(x.get("start", ""))):
            key = s.get("start", "")
            if key and key not in seen:
                seen.add(key)
                valid.append(s)
        return valid

    # ── PUBLIC: analyze_highlights ────────────────────────────────────────────

    def analyze_highlights(
        self,
        subtitle_text: str,
        min_sec: int,
        max_sec: int,
        title_language: str = "en",
    ) -> List[Dict]:
        print(f"\n🔍 DeepSeek.analyze_highlights()", flush=True)
        print(f"   ├─ Input: {len(subtitle_text)} chars", flush=True)
        print(f"   ├─ Duration: {min_sec}-{max_sec}s", flush=True)
        print(f"   └─ Target language: {title_language}", flush=True)

        if len(subtitle_text.strip()) < 200:
            print(f"  ⚠️ Input too short, skipping", flush=True)
            return []

        # ── Chia chunk ────────────────────────────────────────────────────────
        chunks = _split_transcript_chunks(subtitle_text, CHUNK_SIZE, CHUNK_OVERLAP)
        print(f"  📦 Transcript chia thành {len(chunks)} chunk(s) "
              f"(mỗi chunk ~{CHUNK_SIZE//1000}k chars, overlap {CHUNK_OVERLAP} chars)", flush=True)

        all_segments: List[Dict] = []

        for idx, chunk in enumerate(chunks):
            print(f"\n  ── Chunk {idx+1}/{len(chunks)} ({len(chunk)} chars) ──", flush=True)

            # Lấy time range của chunk để hint cho AI
            ts_matches = re.findall(r'\d{2}:\d{2}:\d{2},\d{3}', chunk)
            time_hint  = ""
            if ts_matches:
                time_hint = f"Timestamps in this chunk: {ts_matches[0]} → {ts_matches[-1]}."

            prompt = self._build_prompt(
                chunk, min_sec, max_sec, title_language,
                chunk_idx=idx, total_chunks=len(chunks),
                time_hint=time_hint,
            )
            print(f"  📝 Prompt: {len(prompt)} chars", flush=True)

            raw = self._call_api(prompt, max_retries=3)
            if not raw:
                print(f"  ❌ Chunk {idx+1}: API call failed, skipping", flush=True)
                continue

            segs = self._parse_json(raw)
            if not segs:
                print(f"  ❌ Chunk {idx+1}: JSON parse failed, skipping", flush=True)
                continue

            print(f"  ✅ Chunk {idx+1}: parsed {len(segs)} raw segments", flush=True)

            # Validate + language check
            chunk_valid = 0
            for seg in segs:
                if not self._validate(seg):
                    continue
                if not self._validate_duration(seg, min_sec, max_sec):
                    continue

                title        = seg["title"].strip()
                detected     = self._detect_language(title)
                target_lower = title_language.lower()

                if detected != target_lower and detected != "unknown":
                    print(f"  ⚠️ Lang mismatch ({detected}→{target_lower}): {title[:40]}", flush=True)
                    seg["title"] = self._translate_fallback(title, target_lower)

                all_segments.append(seg)
                chunk_valid += 1

            print(f"  ✅ Chunk {idx+1}: {chunk_valid} valid segments", flush=True)

            # Rate-limit buffer giữa các chunk
            if idx < len(chunks) - 1:
                time.sleep(1)

        # ── Gộp + dedup + sort ────────────────────────────────────────────────
        final = self._dedup_sort(all_segments)
        print(f"\n  ✅ Tổng kết: {len(final)} segments từ {len(chunks)} chunk(s)", flush=True)
        return final
    
    def _validate_duration(self, seg: Dict, min_sec: int, max_sec: int) -> bool:
        try:
            start_s = self._to_sec(seg.get("start", ""))
            end_s   = self._to_sec(seg.get("end", ""))
            duration = end_s - start_s
            if duration < min_sec or duration > max_sec:
                print(f"  ⚠️ Skip segment duration={duration:.0f}s (cần {min_sec}–{max_sec}s): {seg.get('title','')[:40]}", flush=True)
                return False
            return True
        except Exception:
            return False

    def release_resources(self):
        self.client = None
        print("🧹 DeepSeekEngine released", flush=True)