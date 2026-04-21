# import json
# import subprocess
# from pathlib import Path
# import re
# from datetime import timedelta
# import gc
# import time
# from multiprocessing import Pool, cpu_count

# # === CẤU HÌNH ===
# INPUT_DIR = Path("inputs")
# OUTPUT_DIR = Path("outputs")
# OUTPUT_DIR.mkdir(exist_ok=True)

# # === HÀM HỖ TRỢ ===
# def to_seconds(timestamp):
#     h, m, s = timestamp.replace(",", ".").split(":")
#     return float(h) * 3600 + float(m) * 60 + float(s)

# def from_seconds(seconds):
#     td = timedelta(seconds=seconds)
#     total_seconds = int(td.total_seconds())
#     # FIX 5: Dùng round thay vì int để tránh sai số dấu phẩy động
#     ms = round((seconds - total_seconds) * 1000)
#     h = total_seconds // 3600
#     m = (total_seconds % 3600) // 60
#     s = total_seconds % 60
#     return f"{h:02}:{m:02}:{s:02},{ms:03}"

# def sanitize_filename(name):
#     return re.sub(r'[\\/*?:"<>|\r\n]', "", name).strip()[:180]

# def parse_srt(srt_path):
#     with open(srt_path, "r", encoding="utf-8") as f:
#         blocks = f.read().strip().split("\n\n")
#     subs = []
#     for block in blocks:
#         lines = block.strip().splitlines()
#         if len(lines) >= 3:
#             start_str, end_str = lines[1].split(" --> ")
#             content = "\n".join(lines[2:])
#             subs.append((to_seconds(start_str), to_seconds(end_str), content))
#     return subs

# def write_srt(subs, out_path):
#     cleaned_subs = []
#     for start, end, content in subs:
#         start = max(0, start)
#         end = max(start + 0.001, end)
#         cleaned_subs.append([start, end, content])

#     for i in range(len(cleaned_subs) - 1):
#         if cleaned_subs[i][1] > cleaned_subs[i+1][0]:
#             cleaned_subs[i][1] = cleaned_subs[i+1][0] - 0.001

#     with open(out_path, "w", encoding="utf-8") as f:
#         for i, (start, end, content) in enumerate(cleaned_subs, 1):
#             f.write(f"{i}\n")
#             f.write(f"{from_seconds(start)} --> {from_seconds(end)}\n")
#             f.write(f"{content}\n\n")

# # === HÀM XỬ LÝ TỪNG CLIP ===
# def process_clip(args):
#     video_path, video_stem, i, segment, subtitle_data = args

#     try:
#         start = to_seconds(segment["start"])
#         end = to_seconds(segment["end"])
#         duration = end - start

#         lines = segment["title"].strip().splitlines()
#         title_line = lines[0] if lines else f"clip"
#         hashtags = lines[1] if len(lines) > 1 else ""
#         full_name = f"{title_line} {hashtags}".strip()
        
#         # FIX 3: Thêm Clip_{i}_ để tránh 2 clip trùng tên đè nhau
#         safe_filename = sanitize_filename(f"{full_name}")

#         sub_output_dir = OUTPUT_DIR / video_stem
#         sub_output_dir.mkdir(exist_ok=True)

#         output_video_path = sub_output_dir / f"{safe_filename}.mp4"
#         output_srt_path = sub_output_dir / f"{safe_filename}.srt"

   
#         cmd = [
#             "ffmpeg", "-y",
#             "-loglevel", "error",
#             "-hwaccel", "cuda",
#             "-ss", str(start),         
#             "-i", str(video_path),
#             "-t", str(duration),
#             "-c:v", "h264_nvenc",      
#             "-preset", "p4",           
#             "-cq", "24",               
#             "-c:a", "copy",            
#             str(output_video_path)
#         ]

#         print(f" ✂️ [{video_stem}] Đang cắt: {safe_filename}")
#         subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL)

#         if subtitle_data:
#             # FIX 4: min(duration, sub_end - start) để sub không dài hơn video
#             selected_subs = [
#                 (max(0, sub_start - start), min(duration, sub_end - start), content)
#                 for sub_start, sub_end, content in subtitle_data
#                 if sub_end > start and sub_start < end
#             ]
#             write_srt(selected_subs, output_srt_path)
#             print(f" 📝 Đã xuất Subtitle cho clip {i}")

#     except subprocess.CalledProcessError as e:
#         print(f"❌ FFmpeg lỗi ở clip {i}: {e}")
#     except Exception as e:
#         print(f"❌ Lỗi clip {i}: {e}")

#     gc.collect()
#     time.sleep(0.05)

# # === MAIN ===
# if __name__ == "__main__":
#     for video_path in INPUT_DIR.glob("*.mp4"):
#         video_stem = video_path.stem
#         json_path = INPUT_DIR / f"highlights_{video_stem}.json"
#         srt_path = INPUT_DIR / f"{video_stem}.srt"

#         if not json_path.exists():
#             print(f"⚠️ Không có JSON cho {video_stem}")
#             continue

#         with open(json_path, "r", encoding="utf-8") as f:
#             segments = json.load(f)

#         subtitle_data = []
#         if srt_path.exists():
#             subtitle_data = parse_srt(srt_path)

#         print(f"\n🎞️ Đang xử lý video: {video_stem} ({len(segments)} đoạn)")

#         tasks = [
#             (video_path, video_stem, i+1, segment, subtitle_data)
#             for i, segment in enumerate(segments)
#         ]

#         # FIX 1: Giới hạn số luồng (Card NVIDIA thường chịu tối đa 3-8 luồng NVENC)
#         max_nvenc_sessions = min(5, cpu_count()) 
        
#         with Pool(processes=max_nvenc_sessions) as pool:
#             pool.map(process_clip, tasks)

#     print("\n✅ Đã xử lý xong tất cả video và subtitle.")

import json
import subprocess
from pathlib import Path
import re
from datetime import timedelta
import gc
import time
from multiprocessing import Pool, cpu_count

# === CẤU HÌNH ===
INPUT_DIR = Path(r"C:\TOOL-AUTOCLIP\backup")
OUTPUT_DIR = Path(r"C:\TOOL-AUTOCLIP\backuppp")
OUTPUT_DIR.mkdir(exist_ok=True)

# === HÀM HỖ TRỢ ===
def to_seconds(timestamp):
    h, m, s = timestamp.replace(",", ".").split(":")
    return float(h) * 3600 + float(m) * 60 + float(s)

def from_seconds(seconds):
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    # FIX 5: Dùng round thay vì int để tránh sai số dấu phẩy động
    ms = round((seconds - total_seconds) * 1000)
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|\r\n]', "", name).strip()[:180]

def parse_srt(srt_path):
    with open(srt_path, "r", encoding="utf-8") as f:
        blocks = f.read().strip().split("\n\n")
    subs = []
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) >= 3:
            start_str, end_str = lines[1].split(" --> ")
            content = "\n".join(lines[2:])
            subs.append((to_seconds(start_str), to_seconds(end_str), content))
    return subs

def write_srt(subs, out_path):
    cleaned_subs = []
    for start, end, content in subs:
        start = max(0, start)
        end = max(start + 0.001, end)
        cleaned_subs.append([start, end, content])

    for i in range(len(cleaned_subs) - 1):
        if cleaned_subs[i][1] > cleaned_subs[i+1][0]:
            cleaned_subs[i][1] = cleaned_subs[i+1][0] - 0.001

    with open(out_path, "w", encoding="utf-8") as f:
        for i, (start, end, content) in enumerate(cleaned_subs, 1):
            f.write(f"{i}\n")
            f.write(f"{from_seconds(start)} --> {from_seconds(end)}\n")
            f.write(f"{content}\n\n")

# === HÀM XỬ LÝ TỪNG CLIP ===
def process_clip(args):
    video_path, video_stem, i, segment, subtitle_data = args

    try:
        start = to_seconds(segment["start"])
        end = to_seconds(segment["end"])
        duration = end - start

        lines = segment["title"].strip().splitlines()
        title_line = lines[0] if lines else f"clip"
        hashtags = lines[1] if len(lines) > 1 else ""
        full_name = f"{title_line} {hashtags}".strip()
        
        # Đã bỏ qua Clip_{i}_ vì bạn muốn dùng hệ thống Part 1, Part 2
        safe_filename = sanitize_filename(f"{full_name}")

        sub_output_dir = OUTPUT_DIR / video_stem
        sub_output_dir.mkdir(exist_ok=True)

        output_video_path = sub_output_dir / f"{safe_filename}.mp4"
        output_srt_path = sub_output_dir / f"{safe_filename}.srt"

        cmd = [
            "ffmpeg", "-y",
            "-loglevel", "error",
            "-hwaccel", "cuda",
            "-ss", str(start),         
            "-i", str(video_path),
            "-t", str(duration),
            "-c:v", "h264_nvenc",      
            "-preset", "p4",           
            "-cq", "24",               
            "-c:a", "copy",            
            str(output_video_path)
        ]

        print(f" ✂️ [{video_stem}] Đang cắt: {safe_filename}")
        subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL)

        if subtitle_data:
            # FIX 4: min(duration, sub_end - start) để sub không dài hơn video
            selected_subs = [
                (max(0, sub_start - start), min(duration, sub_end - start), content)
                for sub_start, sub_end, content in subtitle_data
                if sub_end > start and sub_start < end
            ]
            write_srt(selected_subs, output_srt_path)
            print(f" 📝 Đã xuất Subtitle cho clip {i}")

    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg lỗi ở clip {i}: {e}")
    except Exception as e:
        print(f"❌ Lỗi clip {i}: {e}")

    gc.collect()
    time.sleep(0.05)

# === MAIN ===
if __name__ == "__main__":
    for video_path in INPUT_DIR.glob("*.mp4"):
        video_stem = video_path.stem
        json_path = INPUT_DIR / f"highlights_{video_stem}.json"
        srt_path = INPUT_DIR / f"{video_stem}.srt"

        if not json_path.exists():
            print(f"⚠️ Không có JSON cho {video_stem}")
            continue

        with open(json_path, "r", encoding="utf-8") as f:
            segments = json.load(f)

        # ---------------------------------------------------------
        # XỬ LÝ ĐÁNH SỐ PART CHO "(Không có lời thoại)"
        # ---------------------------------------------------------
        part_counter = 1
        for seg in segments:
            title_text = seg.get("title", "").strip()
            lines = title_text.splitlines()
            
            # Kiểm tra xem dòng tiêu đề đầu tiên có phải là (Không có lời thoại) không
            if lines and lines[0].strip() == "(Không có lời thoại)":
                lines[0] = f"(Không có lời thoại) Part {part_counter}"
                seg["title"] = "\n".join(lines)
                part_counter += 1
        # ---------------------------------------------------------

        subtitle_data = []
        if srt_path.exists():
            subtitle_data = parse_srt(srt_path)

        print(f"\n🎞️ Đang xử lý video: {video_stem} ({len(segments)} đoạn)")

        tasks = [
            (video_path, video_stem, i+1, segment, subtitle_data)
            for i, segment in enumerate(segments)
        ]

        # FIX 1: Giới hạn số luồng (Card NVIDIA thường chịu tối đa 3-8 luồng NVENC)
        max_nvenc_sessions = min(5, cpu_count()) 
        
        with Pool(processes=max_nvenc_sessions) as pool:
            pool.map(process_clip, tasks)

    print("\n✅ Đã xử lý xong tất cả video và subtitle.")