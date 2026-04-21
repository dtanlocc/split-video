import google.generativeai as genai
import threading
import itertools
import time
from langdetect import detect
import langcodes
from google.generativeai.types import HarmCategory, HarmBlockThreshold

class GeminiEngine:
    def __init__(self, api_keys: list[str], model_name: str):
        self.active_keys = api_keys.copy()
        self.api_lock = threading.Lock()
        self.model_name = model_name
        self.part_counter = itertools.count(1)
        self._configure_model()

    def _configure_model(self):
        with self.api_lock:
            if not self.active_keys:
                raise RuntimeError("❌ Hết tất cả API Key.")
            self.current_key = self.active_keys[0]
            genai.configure(api_key=self.current_key)
            
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
            self.model = genai.GenerativeModel(
                model_name=self.model_name, 
                safety_settings=safety_settings
            )
            print(f"🔑 Đang dùng key: {self.current_key[:12]}...")

    def rotate_key(self):
        with self.api_lock:
            if self.current_key in self.active_keys:
                self.active_keys.remove(self.current_key)
            if not self.active_keys:
                raise RuntimeError("❌ TẤT CẢ API KEYS ĐÃ HẾT QUOTA!")
            self._configure_model()

    def safe_generate(self, prompt: str, max_retries=8):
        """Phiên bản an toàn + debug"""
        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(prompt)
                if response and response.text:
                    print(f"✅ Gemini thành công (attempt {attempt+1})")
                    return response
                else:
                    print(f"⚠️ Gemini trả về rỗng (attempt {attempt+1})")
            except Exception as e:
                err = str(e)
                print(f"❌ Lỗi Gemini (attempt {attempt+1}): {err[:150]}...")
                
                if any(k in err for k in ["RESOURCE_EXHAUSTED", "429", "quota", "PERMISSION_DENIED"]):
                    print("🔄 Đang rotate API Key...")
                    self.rotate_key()
                    time.sleep(2)
                    continue
                time.sleep(3)
        
        print("❌ safe_generate() thất bại hoàn toàn sau nhiều lần thử!")
        return None

    def build_highlight_prompt(self, subtitle_text: str):
        return (
            "Below is the transcript of a video.\n"
            "Analyze the content and identify segments that are emotionally intense, action-packed, thought-provoking, or otherwise compelling highlights.\n"
            "Each selected segment must have complete meaning — do not cut off in the middle of a sentence.\n"
            "Only include segments that are **at least 60 seconds** and **at most 180 seconds** long.\n"
            "Return the result as a JSON list in this exact format:\n"
            '[{\"start\": \"00:00:15,000\", \"end\": \"00:01:45,000\"}, ...]\n\n'
            "Return **ONLY** the JSON, no explanation, no markdown.\n\n"
            f"Transcript:\n{subtitle_text}"
        )

    def generate_title(self, text_chunk: str):
        if not text_chunk.strip():
            return f"Part {next(self.part_counter)}"
            
        try:
            lang_code = detect(text_chunk)
            lang_name = langcodes.Language.get(lang_code).display_name("en")
        except:
            lang_name = "English"

        prompt = (
            f"The following is a highlight from a video.\n"
            f"Write a **short, engaging title** in **{lang_name}**.\n"
            f"- 9 to 15 words only.\n"
            f"- One single natural sentence.\n"
            f"- No violent or sensitive words.\n"
            f"Return only the title, no extra text.\n\n"
            f"Dialogue: {text_chunk}"
        )
        
        resp = self.safe_generate(prompt, max_retries=5)
        return resp.text.strip() if resp and resp.text else f"Part {next(self.part_counter)}"