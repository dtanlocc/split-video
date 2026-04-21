import os
import sys
import re
import json
import textwrap
import unicodedata
import subprocess
from PIL import Image, ImageDraw
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Thêm thư viện nhận diện giọng nói có word-level timestamp
import stable_whisper

# ==================== 1. CẤU HÌNH HỆ THỐNG ==================== #
FFMPEG_BIN_FOLDER = r"C:\ffmpeg\bin"
INPUT_FOLDER = Path(r"C:\TOOL-AUTOCLIP\smart-video-pro\verify_results\yolo_outputs")
OUTPUT_FOLDER = INPUT_FOLDER / "outputs"

# Cấu hình Font

# tiếng Nhật
# FONT_TITLE_FILE = "C\\:/Windows/Fonts/YuGothM.ttc"  # Font cho tiêu đề (cần thoát dấu :)

# tiếng hàn
# FONT_TITLE_FILE = "C\\:/Windows/Fonts/malgun.ttf"  

# tiếng latinh
FONT_TITLE_FILE = "C\\:Windows/Fonts/arialbd.ttf"  # Font cho tiêu đề (cần thoát dấu :)


FONT_SUB_NAME = "Impact"                            

# Cấu hình Video
MAX_PARALLEL_JOBS = 1    
VIDEO_SPEED = 1.03       

# Cấu hình AI Whisper (Tải model 1 lần duy nhất để tối ưu tốc độ)
WHISPER_MODEL_NAME = "small" # Có thể nâng lên 'small' hoặc 'medium' nếu VGA mạnh
print(f"⏳ Đang tải AI Model '{WHISPER_MODEL_NAME}' vào bộ nhớ. Vui lòng đợi...")
# whisper_model = stable_whisper.load_model(WHISPER_MODEL_NAME)
whisper_model = stable_whisper.load_model(WHISPER_MODEL_NAME, device="cuda")

# ==================== 2. CẤU HÌNH SUBTITLES ==================== #
MAX_WORDS_PER_LINE = 3   
SUB_ALIGNMENT = 2        
SUB_MARGIN_V = 450      
SUB_FONT_SIZE = 85       

os.environ["PATH"] = FFMPEG_BIN_FOLDER + os.pathsep + os.environ["PATH"]

# ==================== 3. HÀM HỖ TRỢ (HELPERS) ==================== #
def escape_ffmpeg_path(path_str):
    return str(path_str).replace("\\", "/").replace(":", "\\:").replace("'", "'\\\\\\''")

def get_video_resolution(video_path: Path):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", str(video_path)]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True, encoding="utf-8")
    data = json.loads(result.stdout)
    return data["streams"][0]["width"], data["streams"][0]["height"]

def get_visual_length(text):
    length = 0
    for char in text:
        length += 1.8 if unicodedata.east_asian_width(char) in ('W', 'F') else 1.0
    return length

def get_balanced_wrap(text, target_lines):
    low, high = 1, len(text)
    best_lines = [text]
    while low <= high:
        mid = (low + high) // 2
        lines = textwrap.wrap(text, width=mid, break_long_words=True)
        if len(lines) <= target_lines:
            best_lines = lines
            high = mid - 1
        else:
            low = mid + 1
    return best_lines

def get_optimal_text_layout(text, max_box_width=980, max_font_size=85, min_font_size=40):
    char_width_ratio = 0.65
    for num_lines in range(1, 9):
        lines = get_balanced_wrap(text, num_lines)
        max_visual_len = max(get_visual_length(line) for line in lines) if lines else 1
        calc_fontsize = int(max_box_width / (max_visual_len * char_width_ratio))
        calc_fontsize = min(calc_fontsize, max_font_size)
        if calc_fontsize >= min_font_size:
            return lines, calc_fontsize
    return get_balanced_wrap(text, 8), min_font_size

def chunk_words(words, n):
    for i in range(0, len(words), n):
        yield words[i:i + n]

def fmt_ass_time(t):
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"

# ==================== 4. XỬ LÝ VIDEO CHI TIẾT ==================== #
import os
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw

def process_single_video(video_path: Path):
    ass_file = None
    bg_title_png = None
    try:
        print(f"\n🎬 Đang xử lý: {video_path.name}")
        orig_w, orig_h = get_video_resolution(video_path)
        
        # --- A. TÍNH TOÁN LAYOUT TIÊU ĐỀ ---
        raw_title = video_path.stem.split('#')[0].replace('_', ' ').upper()
        lines, title_fs = get_optimal_text_layout(raw_title)
        
        # Tính toán kích thước box dựa trên độ dài text thực tế
        max_visual_len = max(get_visual_length(line) for line in lines) if lines else 1
        char_width_ratio = 0.65 
        text_w_est = int(max_visual_len * title_fs * char_width_ratio)
        
        text_padding = 40 
        box_w = min(1040, text_w_est + text_padding * 2) 
        box_x = (1080 - box_w) // 2 
        
        line_gap = int(title_fs * 0.2)
        box_h = len(lines) * (title_fs + line_gap) - line_gap + text_padding * 2
        
        # Tính vị trí Y (Neo phía trên video chính)
        fg_w = 1080
        fg_h = int(1080 * orig_h / orig_w)
        fg_w, fg_h = fg_w & ~1, fg_h & ~1 
        
        video_top_y = (1920 - fg_h) // 2
        box_y = video_top_y - box_h - 40
        if box_y < 120: box_y = 120

        # --- B. TẠO FILE ẢNH NỀN TIÊU ĐỀ BO GÓC ---
        video_id = "".join(filter(str.isalnum, video_path.stem))[:15]
        bg_title_png = OUTPUT_FOLDER / f"bg_box_{video_id}.png"
        
        overlay_img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
        draw_bg = ImageDraw.Draw(overlay_img)
        dynamic_radius = 40 
        
        draw_bg.rounded_rectangle(
            [(0, 0), (box_w, box_h)], 
            radius=dynamic_radius, 
            fill=(0, 0, 0, 160)
        )
        overlay_img.save(bg_title_png)

        # --- C. NHẬN DIỆN VÀ TẠO FILE SUBTITLE ---
        print(f"🧠 Đang trích xuất Word-Level Subtitles cho: {video_path.name}")
        result = whisper_model.transcribe(str(video_path), language="en")
        
        has_subtitles = False
        
        # KIỂM TRA: Chỉ tạo phụ đề nếu Whisper thực sự nghe được có chữ
        if result.text.strip() and result.segments:
            has_subtitles = True
            print("✅ Đã nhận diện được giọng nói. Đang tạo file Subtitle...")
            ass_file = OUTPUT_FOLDER / f"temp_{video_id}.ass"
            
            with open(ass_file, "w", encoding="utf-8") as f:
                f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nScaledBorderAndShadow: yes\n\n")
                f.write("[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
                f.write(f"Style: Default,{FONT_SUB_NAME},{SUB_FONT_SIZE},&H00FFFFFF,&H0000FFFF,&H00000000,&H66000000,-1,0,0,0,100,100,0,0,1,5,0,{SUB_ALIGNMENT},10,10,{SUB_MARGIN_V},1\n\n")
                f.write("[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
                
                for seg in result.segments:
                    # Bỏ qua nếu đoạn âm thanh không có từ nào (chống lỗi)
                    if not hasattr(seg, 'words') or not seg.words: 
                        continue
                    
                    word_groups = list(chunk_words(seg.words, MAX_WORDS_PER_LINE))
                    for group in word_groups:
                        clean_words = [w.word.strip() for w in group]
                        for i, w in enumerate(group):
                            ws, we = w.start / VIDEO_SPEED, (group[i+1].start if i < len(group)-1 else w.end) / VIDEO_SPEED
                            parts = [f"{{\\1c&H00FFFF&}}{cw}{{\\1c&HFFFFFF&}}" if j == i else cw for j, cw in enumerate(clean_words)]
                            highlighted = " ".join(parts).replace("'", "’")
                            f.write(f"Dialogue: 0,{fmt_ass_time(ws)},{fmt_ass_time(we)},Default,,0,0,0,,{highlighted}\n")
        else:
            print("⚠️ Không phát hiện giọng nói trong video (hoặc chỉ có tiếng ồn/nhạc). Bỏ qua bước Subtitle.")

        # --- D. THIẾT LẬP FFMEG FILTER ---
        TITLE_COLOR = "#FFD700" 

        draw_text_cmds = []
        for i, line in enumerate(lines):
            line_esc = line.replace(":", "\\:").replace("'", "’").replace(",", "\\,")
            y_pos_text = box_y + text_padding + i * (title_fs + line_gap)
            text_cmd = (
                f"drawtext=text='{line_esc}':fontcolor={TITLE_COLOR}:fontsize={title_fs}:fontfile='{FONT_TITLE_FILE}':"
                f"x=(w-text_w)/2:y={y_pos_text}:borderw=4:bordercolor=black:shadowx=5:shadowy=5:shadowcolor=black@0.8"
            )
            draw_text_cmds.append(text_cmd)
        
        text_filter = ",".join(draw_text_cmds)
        
        # Tùy biến: Có ghép Filter ASS hay không dựa vào biến has_subtitles
        if has_subtitles and ass_file and ass_file.exists():
            ass_path_esc = escape_ffmpeg_path(ass_file)
            text_and_sub_filter = f"[vid_with_box]{text_filter},ass='{ass_path_esc}',setpts=PTS/{VIDEO_SPEED}[final_v];"
        else:
            text_and_sub_filter = f"[vid_with_box]{text_filter},setpts=PTS/{VIDEO_SPEED}[final_v];"

        filter_complex = (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:10,curves=all='0/0 0.5/0.4 1/1'[bg];"
            f"[0:v]scale={fg_w}:{fg_h},curves=all='0/0 0.5/0.4 1/1'[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[vid_combined];"
            f"[vid_combined][1:v]overlay={box_x}:{box_y}[vid_with_box];"
            f"{text_and_sub_filter}"  # <--- Nơi tự động có hoặc không có Sub
            f"[0:a]atempo={VIDEO_SPEED}[final_a]"
        )

        # --- E. THỰC THI FFmpeg ---
        out_file = OUTPUT_FOLDER / f"{video_path.stem}.mp4"
        cmd = [
            "ffmpeg", "-y", 
            "-i", str(video_path), 
            "-i", str(bg_title_png), 
            "-filter_complex", filter_complex,
            "-map", "[final_v]", 
            "-map", "[final_a]?", 
            "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "24", 
            "-c:a", "aac", "-b:a", "192k", 
            str(out_file)
        ]
        
        print("🚀 Đang render video...")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            print(f"❌ Lỗi FFmpeg: {result.stderr}")
        else:
            print(f"✅ Xong: {out_file.name}")

    except Exception as e:
        print(f"❌ Lỗi hệ thống: {e}")
    finally:
        # Dọn dẹp file tạm
        for f in [ass_file, bg_title_png]:
            if f and f.exists():
                try: os.remove(f)
                except: pass

# ==================== 5. CHƯƠNG TRÌNH CHÍNH ==================== #
if __name__ == "__main__":
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    video_list = list(INPUT_FOLDER.glob("*.mp4"))
    
    if not video_list:
        print("📂 Không tìm thấy video nào trong thư mục input.")
    else:
        print(f"🚀 Bắt đầu xử lý {len(video_list)} video...")
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_JOBS) as executor:
            executor.map(process_single_video, video_list)
    
    print("🎉 HOÀN TẤT TOÀN BỘ!")