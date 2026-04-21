
import cv2
import torch
import subprocess
import numpy as np
from ultralytics import YOLO
import numpy.typing as npt 
from tqdm import tqdm
from pathlib import Path
import math
from multiprocessing import Pool

# ==== CẤU HÌNH ==== #
input_dir = Path(r"inputs")
output_dir = Path(r"outputs")
output_dir.mkdir(exist_ok=True)

output_size = (720, 720)
# output_size = (1080, 1440)

detect_every = 15
device = "cuda" if torch.cuda.is_available() else "cpu"
model_path = "yolov8n.pt"

# ==== NÉT ==== #
sharpen_strength = "medium"   # "low", "medium", "high"

class Kalman1D:
    def __init__(self, process_variance=1e-2, measurement_variance=1):
        self.x = None  # Khởi tạo là None thay vì 0
        self.P = 1
        self.Q = process_variance
        self.R = measurement_variance
        
    def update(self, z):
        if self.x is None:
            self.x = z  # Gán giá trị đo được đầu tiên làm state ban đầu
            
        self.P += self.Q
        K = self.P / (self.P + self.R)
        self.x += K * (z - self.x)
        self.P *= (1 - K)
        return self.x

# ==== HÀM TIỆN ÍCH ==== #
def horizontal_flip(frame: npt.NDArray) -> npt.NDArray:
    return np.fliplr(frame)

def enhance_crop(frame: npt.NDArray, output_size=(720,720), strength="medium") -> npt.NDArray:
    """CLAHE + Sharpen trước ở độ phân giải nhỏ, Resize sau cùng"""
    # 1. CLAHE
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8,8))
    l2 = clahe.apply(l)
    lab = cv2.merge((l2,a,b))
    frame = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    # 2. Tham số sharpen
    if strength == "low":
        alpha, beta, sigma = 1.1, -0.1, 0.8
    elif strength == "high":
        alpha, beta, sigma = 1.4, -0.4, 1.5
    else:  # medium
        alpha, beta, sigma = 1.2, -0.2, 1.0

    blurred = cv2.GaussianBlur(frame, (0, 0), sigmaX=sigma)
    sharp = cv2.addWeighted(frame, alpha, blurred, beta, 0)

    # 3. Resize nội suy bước cuối
    final_frame = cv2.resize(sharp, output_size, interpolation=cv2.INTER_LANCZOS4)
    return final_frame


def crop_center_ratio(frame: npt.NDArray, cx:int, cy:int, ratio=(1,1)) -> npt.NDArray:
    """Crop theo center + tỉ lệ 3:4"""
    h, w = frame.shape[:2]
    target_w = min(w, int(h * ratio[0]/ratio[1]))
    target_h = min(h, int(w * ratio[1]/ratio[0]))
    x1 = max(0, int(cx - target_w/2))
    y1 = max(0, int(cy - target_h/2))
    x2 = min(w, x1 + target_w)
    y2 = min(h, y1 + target_h)
    return frame[y1:y2, x1:x2]

def do_cmd(cmd):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
    for line in p.stdout:
        print(line, end='')
    p.wait()
import multiprocessing as mp

def process_video(args):
    input_path_str, input_root = args
    input_path = Path(input_path_str)
    print(f"\n🎬 Đang xử lý: {input_path}")
    stem = input_path.stem

    rel_path = input_path.relative_to(input_root).parent
    output_subdir = output_dir / rel_path
    output_subdir.mkdir(parents=True, exist_ok=True)
    final_output = output_subdir / f"{stem}.mp4"

    cap = cv2.VideoCapture(str(input_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    yolo_input_h = 480
    yolo_input_w = int(orig_w * (yolo_input_h / orig_h))
    scale_x = orig_w / yolo_input_w
    scale_y = orig_h / yolo_input_h

    model = YOLO(model_path).to(device)
    kalman_x = Kalman1D()
    kalman_y = Kalman1D()
    bbox_current = None
    frame_id = 0
    prev_cx, prev_cy = None, None
    dynamic_detect_every = detect_every
    target_bbox = None

    # === CẤU HÌNH FFMPEG PIPE === #
    # Định dạng rawvideo yêu cầu phải khai báo chính xác kích thước và pixel format
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{output_size[0]}x{output_size[1]}",  # Output width x height
        "-pix_fmt", "bgr24",  # OpenCV dùng BGR
        "-r", str(fps),       # FPS thô truyền vào
        "-i", "-",            # Input 0: stdin (pipe từ Python)
        "-i", str(input_path),# Input 1: Video gốc để lấy Audio
        "-map", "0:v:0",      # Lấy Video từ stdin
        "-map", "1:a:0?",     # Lấy Audio từ video gốc (nếu có)
        "-c:v", "h264_nvenc",
        "-preset", "p4",
        "-cq", "24",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(final_output)
    ]

    # Mở luồng FFmpeg (Nhận dữ liệu thô từ Python qua chuẩn stdin)
    process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    with tqdm(desc=f"📹 {stem}", unit="frame") as pbar:
        while True:
            ret, orig_frame = cap.read()
            if not ret:
                break

            resized = cv2.resize(orig_frame, (yolo_input_w, yolo_input_h))

            if frame_id % dynamic_detect_every == 0:
                results = model.predict(resized, device=device, verbose=False, conf=0.6, iou=0.5, classes=[0])
                boxes = results[0].boxes.xyxy.cpu().numpy()
                if len(boxes) > 0:
                    centers = []
                    for b in boxes:
                        x1, y1, x2, y2 = b
                        cx = (x1 + x2) / 2 * scale_x
                        cy = (y1 + y2) / 2 * scale_y
                        w = (x2 - x1) * scale_x
                        h = (y2 - y1) * scale_y
                        centers.append((cx, cy, w, h))
                    
                    if target_bbox is None:
                        areas = [w*h for _, _, w, h in centers]
                        target_idx = np.argmax(areas)
                        target_bbox = centers[target_idx][:2]
                    else:
                        distances = [((cx - target_bbox[0])**2 + (cy - target_bbox[1])**2)**0.5 for cx, cy, _, _ in centers]
                        min_idx = np.argmin(distances)
                        if distances[min_idx] < 100:
                            target_bbox = centers[min_idx][:2]
                        else:
                            areas = [w*h for _, _, w, h in centers]
                            max_idx = np.argmax(areas)
                            target_bbox = centers[max_idx][:2]
                    
                    bbox_current = target_bbox

                    if prev_cx is not None and prev_cy is not None:
                        dx = target_bbox[0] - prev_cx
                        dy = target_bbox[1] - prev_cy
                        distance = (dx ** 2 + dy ** 2) ** 0.5
                        if distance > 20:
                            dynamic_detect_every = max(5, detect_every // 2)
                        else:
                            dynamic_detect_every = detect_every
                    prev_cx, prev_cy = target_bbox

            cx, cy = bbox_current if bbox_current else (orig_w // 2, orig_h // 2)
            smooth_cx = int(kalman_x.update(cx))
            smooth_cy = int(kalman_y.update(cy))

            # Crop và xử lý ảnh
            crop = crop_center_ratio(orig_frame, smooth_cx, smooth_cy, ratio=(3,4))
            crop = enhance_crop(crop, output_size=output_size, strength=sharpen_strength)
            crop = horizontal_flip(crop)

            # 🔥 ĐẨY FRAME TRỰC TIẾP VÀO FFMPEG 🔥
            process.stdin.write(crop.tobytes())

            frame_id += 1
            pbar.update(1)

    cap.release()
    # Đóng luồng stdin để báo cho FFmpeg biết đã hết video và tiến hành render file output
    process.stdin.close()
    process.wait()

# ==== CHẠY NHIỀU FOLDER ==== #
if __name__ == "__main__":
    # BẮT BUỘC KHAI BÁO CÁI NÀY ĐỂ TRÁNH DEADLOCK GPU TRÊN LINUX/WINDOWS
    mp.set_start_method('spawn', force=True) 

    all_video_files = []
    for folder in input_dir.rglob("*"):
        if folder.is_dir():
            mp4_files = list(folder.glob("*.mp4"))
            all_video_files.extend(mp4_files)

    if not all_video_files:
        print("❌ Không tìm thấy video nào trong tất cả thư mục con.")
    else:
        # Cân nhắc hạ xuống 2 nếu GPU của bạn có VRAM < 8GB
        n_processes = min(2, len(all_video_files)) 
        args_list = [(str(p), input_dir) for p in all_video_files]
        
        with mp.Pool(processes=n_processes) as pool:
            pool.map(process_video, args_list)