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
        self.model = None
        self.current_key = None
        # Logic Part Counter của bạn (An toàn đa luồng bằng itertools)
        self.part_counter = itertools.count(1)
        self._configure_model()

    def _configure_model(self):
        """Logic Safety Settings và API Key của bạn"""
        with self.api_lock:
            if not self.active_keys:
                raise RuntimeError("❌ Hết API key.")
            self.current_key = self.active_keys[0]
            genai.configure(api_key=self.current_key)
            
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
            self.model = genai.GenerativeModel(model_name=self.model_name, safety_settings=safety_settings)

    def rotate_key(self):
        """Logic đổi key khi lỗi quota của bạn"""
        with self.api_lock:
            if self.current_key in self.active_keys:
                self.active_keys.remove(self.current_key)
            self._configure_model()

    def safe_generate(self, prompt: str, max_retries=8):
        """Logic Retry và Call Gemini của bạn"""
        for i in range(max_retries):
            try:
                return self.model.generate_content(prompt)
            except Exception as e:
                err = str(e)
                if any(k in err for k in ["RESOURCE_EXHAUSTED", "quota", "429", "PERMISSION_DENIED"]):
                    self.rotate_key()
                    time.sleep(2)
                    continue
                time.sleep(3)
        return None

    def build_highlight_prompt(self, subtitle_text: str):
        """Logic Prompt 1: Tìm highlight (60s-180s)"""
        return (
            "Below is the transcript of a video.\n"
            "Analyze the content and identify segments that are emotionally intense, action-packed, thought-provoking, or otherwise compelling highlights.\n"
            "Each selected segment must have complete meaning — do not cut off in the middle of a sentence or idea.\n"
            "Only include segments that are **at least 60 seconds** and **at most 180 seconds** long.\n"
            "Return the result as a JSON list in the following format:\n"
            '[{\"start\": \"00:00:15,000\", \"end\": \"00:00:55,000\"}, ...]\n\n'
            "Return **only plain JSON**, with no extra explanation or markdown formatting.\n\n"
            f"{subtitle_text}"
        )

    def generate_title(self, text_chunk: str):
        """Logic Prompt 2: Detect ngôn ngữ và tạo tiêu đề theo kịch bản của bạn"""
        if not text_chunk.strip():
            return f"Part {next(self.part_counter)}"
            
        try:
            lang_code = detect(text_chunk)
            lang_name = langcodes.Language.get(lang_code).display_name("en")
        except:
            lang_name = "Vietnamese"

        prompt = (
            f"The following dialogue is a highlight from a video.\n"
            f"Write a **title** in the **original language** of the dialogue (**{lang_name}**).\n"
            f"Requirements:\n"
            f"- Title must be engaging, natural in tone, and written as **only one single sentence**.\n"
            f"- Title length: **9–15 words**, always under 20 words.\n"
            f"- Avoid words or content that are violent, graphic, shocking, or overly sensitive.\n"
            f"- Only return the result in plain text format, no explanation, no extra text.\n\n"
            f"Dialogue:\n{text_chunk}"
        )
        resp = self.safe_generate(prompt)
        return resp.text.strip() if resp and resp.text else "(Gemini Refused)"