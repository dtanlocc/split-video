# src/application/error_mapper.py
from typing import Optional

class ErrorMessageMapper:
    """Chuyển lỗi kỹ thuật → message thân thiện cho user"""
    
    _MAPPINGS = {
        # CUDA/VRAM errors
        "CUDA out of memory": {
            "user_msg": "💾 Card đồ họa không đủ bộ nhớ",
            "suggestion": "Thử giảm độ phân giải video hoặc đóng ứng dụng khác để giải phóng VRAM",
            "retry_possible": True
        },
        "cuDNN error": {
            "user_msg": "⚙️ Lỗi driver đồ họa",
            "suggestion": "Cập nhật driver NVIDIA lên phiên bản mới nhất",
            "retry_possible": False
        },
        
        # FFmpeg errors
        "ffmpeg": {
            "user_msg": "🎬 Lỗi xử lý video",
            "suggestion": "Kiểm tra file video không bị hỏng và có codec hỗ trợ",
            "retry_possible": True
        },
        
        # License errors
        "License": {
            "user_msg": "🔑 License không hợp lệ",
            "suggestion": "Vui lòng kiểm tra lại key hoặc liên hệ support@yourcompany.com",
            "retry_possible": False
        },
        
        # Default
        "default": {
            "user_msg": "❌ Đã xảy ra lỗi",
            "suggestion": "Vui lòng thử lại hoặc liên hệ hỗ trợ nếu lỗi tiếp diễn",
            "retry_possible": True
        }
    }
    
    @classmethod
    def map(cls, error: Exception) -> dict:
        error_str = str(error)
        
        # Tìm mapping phù hợp (ưu tiên match chính xác)
        for key, value in cls._MAPPINGS.items():
            if key.lower() in error_str.lower():
                return {
                    "technical": error_str,
                    "user_msg": value["user_msg"],
                    "suggestion": value["suggestion"],
                    "retry_possible": value["retry_possible"]
                }
        
        # Fallback default
        default = cls._MAPPINGS["default"]
        return {
            "technical": error_str,
            "user_msg": default["user_msg"],
            "suggestion": default["suggestion"],
            "retry_possible": default["retry_possible"]
        }