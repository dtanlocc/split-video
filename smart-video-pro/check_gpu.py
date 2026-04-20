import torch
import ctranslate2
import os

import os
import sys
import torch

def setup_cuda_path():
    """
    Rule: Dynamic DLL Loading
    Tự động tìm và nạp các thư viện CUDA từ Torch để faster-whisper có thể sử dụng GPU trên Windows.
    """
    if sys.platform == "win32":
        # Tìm đường dẫn đến thư mục lib của torch
        torch_lib_path = os.path.join(os.path.dirname(torch.__file__), "lib")
        
        if os.path.exists(torch_lib_path):
            # Kỹ thuật chuyên nghiệp của Python 3.8+: Nạp thư mục DLL vào runtime
            os.add_dll_directory(torch_lib_path)
            print(f"✅ Đã nạp CUDA DLLs từ: {torch_lib_path}")
            
            # Cập nhật thêm PATH cho các thư viện cũ
            os.environ["PATH"] = torch_lib_path + os.pathsep + os.environ["PATH"]
        else:
            print("⚠️ Cảnh báo: Không tìm thấy thư mục Torch Lib.")

# Gọi hàm này TRƯỚC KHI import faster-whisper hoặc ctranslate2
setup_cuda_path()

# Sau đó mới import các thứ khác
from faster_whisper import WhisperModel

print("--- KIỂM TRA HỆ THỐNG ---")
# 1. Kiểm tra PyTorch
cuda_available = torch.cuda.is_available()
print(f"PyTorch CUDA: {'✅ CÓ' if cuda_available else '❌ KHÔNG'}")
if cuda_available:
    print(f"Device Name: {torch.cuda.get_device_name(0)}")

# 2. Kiểm tra CTranslate2 (Thứ mà B1 dùng)
try:
    # Thử khởi tạo một phép tính nhỏ trên GPU
    generator = ctranslate2.Encoder("WhisperModel", device="cuda")
    print("CTranslate2 GPU: ✅ CÓ")
except Exception as e:
    # Nếu lỗi ở đây thường là do thiếu DLL (cuBLAS/cuDNN)
    print(f"CTranslate2 GPU: ❌ KHÔNG (Lỗi: {str(e)[:100]})")

# 3. Kiểm tra biến môi trường (Nếu chạy Windows)
print(f"PATH có chứa CUDA: {'cuda' in os.environ['PATH'].lower()}")