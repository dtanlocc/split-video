import google.generativeai as genai
import json
from langdetect import detect
import langcodes
import re
from pathlib import Path
import srt
import time
import threading # BẮT BUỘC thêm thư viện này để chạy đa luồng an toàn
from concurrent.futures import ThreadPoolExecutor, as_completed

# === CẤU HÌNH ===
API_KEYS = [
 "AIzaSyBJOUyGvGvS1zP55Mqq1E8A2wEj86ILY0I",
    "AIzaSyDne16vvX_E78-8-Nk3Pl3d7dUEGALTpxY",
]
MODEL_NAME = "gemini-2.5-flash"
VIDEO_DIR = Path(r"C:\TOOL-AUTOCLIP\inputs")

# === QUẢN LÝ API KEY AN TOÀN TRONG ĐA LUỒNG ===
active_keys = API_KEYS.copy() # Danh sách các key còn sống
api_lock = threading.Lock()   # Khóa để tránh đụng độ giữa các luồng
model = None

from google.generativeai.types import HarmCategory, HarmBlockThreshold

def configure_model():
    global model
    with api_lock:
        if not active_keys:
            raise RuntimeError("❌ Hết API key.")
        api_key = active_keys[0]
        genai.configure(api_key=api_key)
        
        # Thêm cấu hình này để không bị lỗi "Candidate was blocked"
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        
        model = genai.GenerativeModel(
            model_name=MODEL_NAME,
            safety_settings=safety_settings
        )
        print(f"🔑 API Key: {api_key[:8]}... đã sẵn sàng.")

def rotate_key(failed_key):
    """Xóa key lỗi khỏi danh sách và chuyển sang key tiếp theo."""
    global model
    with api_lock:
        # Nếu key lỗi vẫn còn trong danh sách thì loại bỏ
        if failed_key in active_keys:
            active_keys.remove(failed_key)
            print(f"⚠️ Loại bỏ API key hết quota: {failed_key[:8]}... (Còn lại {len(active_keys)} keys hoạt động)")

        # Nếu danh sách rỗng -> Dừng toàn bộ chương trình
        if not active_keys:
            raise RuntimeError("❌ TOÀN BỘ API KEYS ĐÃ HẾT QUOTA. CHƯƠNG TRÌNH DỪNG LẠI.")

        # Thiết lập lại model với key mới
        new_key = active_keys[0]
        genai.configure(api_key=new_key)
        model = genai.GenerativeModel(MODEL_NAME)
        print(f"🔄 Đã chuyển sang API key mới: {new_key[:8]}...")


# ===== HÀM PHỤ =====
def time_to_sec(t):
    h, m, s_ms = t.split(":")
    s, ms = s_ms.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

def read_subtitle_file(path):
    return Path(path).read_text(encoding="utf-8")

def extract_json_from_text(text):
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        print("⚠️ Không tìm thấy JSON hợp lệ trong phản hồi.")
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        print("❌ Lỗi parse JSON:", e)
        return None

def get_subs_in_range(subs, start_t, end_t):
    start_sec = time_to_sec(start_t)
    end_sec = time_to_sec(end_t)
    return " ".join(
        s.content.replace('\n', ' ') for s in subs
        if s.end.total_seconds() > start_sec and s.start.total_seconds() < end_sec
    )


def build_highlight_prompt(subtitle_text):
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

# def generate_title(text_chunk):
#     if not text_chunk.strip():
#         return "(Không có lời thoại)"
        
#     try:
#         lang_code = detect(text_chunk)
#         # Tự động lấy tên ngôn ngữ chuẩn
#         lang_name = langcodes.Language.get(lang_code).display_name("en")
#     except:
#         lang_name = "Vietnamese"

#     prompt = (
#         f"The following dialogue is a highlight from a video.\n"
#         f"Write a **title** in the **original language** of the dialogue (**{lang_name}**).\n"
#         f"Requirements:\n"
#         f"- Title must be engaging, natural in tone, and written as **only one single sentence**.\n"
#         f"- Title length: **9–15 words**, always under 20 words.\n"
#         f"- Avoid words or content that are violent, graphic, shocking, or overly sensitive.\n"
#         f"- Only return the result in plain text format, no explanation, no extra text.\n\n"
#         f"Dialogue:\n{text_chunk}"
#     )

#     response = safe_generate_content(prompt)
    
#     # KIỂM TRA PHẢN HỒI TRƯỚC KHI TRẢ VỀ
#     try:
#         if response and response.text:
#             return response.text.strip()
#         else:
#             return "(Gemini từ chối tạo tiêu đề do chính sách an toàn)"
#     except Exception as e:
#         return f"(Lỗi nội dung: {str(e)[:50]})"
def generate_title(text_chunk):
    # TỰ ĐỘNG KHỞI TẠO BỘ ĐẾM NẾU CHƯA CÓ
    if not hasattr(generate_title, "part_counter"):
        generate_title.part_counter = 1

    # NẾU TEXT TRỐNG -> TRẢ VỀ PART VÀ TỰ CỘNG THÊM 1
    if not text_chunk.strip():
        title = f"Part {generate_title.part_counter}"
        generate_title.part_counter += 1
        return title
        
    # NẾU CÓ CHỮ -> GỌI AI NHƯ BÌNH THƯỜNG
    try:
        lang_code = detect(text_chunk)
        # Tự động lấy tên ngôn ngữ chuẩn
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

    response = safe_generate_content(prompt)
    
    # KIỂM TRA PHẢN HỒI TRƯỚC KHI TRẢ VỀ
    try:
        if response and response.text:
            return response.text.strip()
        else:
            return "(Gemini từ chối tạo tiêu đề do chính sách an toàn)"
    except Exception as e:
        return f"(Lỗi nội dung: {str(e)[:50]})"

def safe_generate_content(prompt, max_retries=8):
    """
    Gọi Gemini có retry, tự động chuyển API key và dừng khi hết tất cả key.
    """
    retries = 0
    while retries < max_retries:
        # Lấy key hiện hành để biết key nào gây ra lỗi (nếu có)
        with api_lock:
            if not active_keys:
                raise RuntimeError("❌ Tất cả API keys đều đã hết quota.")
            current_key = active_keys[0]

        try:
            return model.generate_content(prompt)
        except Exception as e:
            err = str(e)
            # 1. Xử lý lỗi do Quota / API Key
            if any(k in err for k in ["RESOURCE_EXHAUSTED", "quota", "429", "API key not valid", "PERMISSION_DENIED"]):
                print(f"⚠️ Phát hiện lỗi Quota với key {current_key[:8]}. Đang đổi key...")
                rotate_key(current_key) 
                time.sleep(2)
                continue # Đổi key xong thử lại ngay, KHÔNG cộng dồn vào max_retries

            # 2. Xử lý các lỗi khác (Mạng, server overload...)
            print(f"⚠️ Lỗi kết nối/Hệ thống ({retries+1}/{max_retries}): {err[:80]}...")
            retries += 1
            time.sleep(3)

    raise RuntimeError("❌ Thất bại hoàn toàn sau nhiều lần thử lại do lỗi hệ thống (không phải lỗi quota).")


def process_video(srt_path: Path):
    try:
        video_name = srt_path.stem.replace(".English", "")
        out_path = VIDEO_DIR / f"highlights_{video_name}.json"

        subtitle_text = read_subtitle_file(srt_path)
        subs = list(srt.parse(subtitle_text))

        existing_data = []
        if out_path.exists():
            try:
                existing_data = json.loads(out_path.read_text(encoding="utf-8"))
                print(f"⏩ Tiếp tục {video_name} (đã có {len(existing_data)} đoạn)...")
            except:
                print(f"⚠️ File {out_path.name} bị lỗi JSON, ghi đè lại từ đầu.")
                existing_data = []

        processed_ranges = {(d["start"], d["end"]) for d in existing_data}

        print(f"\n🎬 Đang xử lý video: {video_name}")
        response = safe_generate_content(build_highlight_prompt(subtitle_text))
        segments = extract_json_from_text(response.text)
        
        if not segments:
            print(f"🚫 {video_name}: Không có đoạn highlight nào được phát hiện.")
            return

        print(f"🧠 {video_name}: Đang tạo tiêu đề cho từng đoạn...")
        for i, seg in enumerate(segments, 1):
            key = (seg["start"], seg["end"])
            if key in processed_ranges:
                print(f" {i}. ⏱ {seg['start']} → {seg['end']} (đã có, bỏ qua)")
                continue

            print(f" {i}. ⏱ {seg['start']} → {seg['end']}")
            chunk_text = get_subs_in_range(subs, seg["start"], seg["end"])
            
            try:
                title = generate_title(chunk_text)
            except Exception as e:
                print(f"⚠️ Lỗi tạo tiêu đề, thử lại... {e}")
                time.sleep(2)
                try:
                    title = generate_title(chunk_text)
                except:
                    title = "(Lỗi tạo tiêu đề)"
                    
            seg["title"] = title
            existing_data.append(seg)
            print(f"    📌 {title}")

            # Lưu tạm
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)

        print(f"💾 Đã lưu đầy đủ: {out_path.name}")

    except Exception as e:
        print(f"❌ Lỗi khi xử lý {srt_path.name}: {e}")


# ===== MAIN: XỬ LÝ SONG SONG =====
def main():
    print("📂 Đang quét thư mục video...")
    srt_files = list(VIDEO_DIR.glob("*.srt"))
    if not srt_files:
        print("⚠️ Không tìm thấy file .srt nào.")
        return

    # Cấu hình model lần đầu tiên
    try:
        configure_model()
    except RuntimeError as e:
        print(e)
        return

    max_workers = min(5, len(srt_files))
    print(f"🚀 Bắt đầu xử lý {len(srt_files)} file (song song {max_workers} luồng)...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_video, s) for s in srt_files]
        for f in as_completed(futures):
            f.result() # ép chờ để bắt lỗi kịp thời

    print("✅ Hoàn tất toàn bộ!")


if __name__ == "__main__":
    main()