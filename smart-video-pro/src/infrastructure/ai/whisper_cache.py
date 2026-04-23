# src/infrastructure/ai/whisper_cache.py
import torch
import threading
from pathlib import Path
from typing import Optional, List
from faster_whisper import WhisperModel
from src.domain.entities import SubtitleSegment

class WhisperModelCache:
    """Singleton cache cho Whisper model - tránh reload giữa các video"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._models: dict[str, WhisperModel] = {}
        self._lock = threading.Lock()
        self._initialized = True
    
    def get_model(self, model_size: str, device: str, compute_type: str) -> WhisperModel:
        """Lấy model từ cache hoặc load mới"""
        key = f"{model_size}_{device}_{compute_type}"
        
        with self._lock:
            if key not in self._models:
                print(f"🔍 Loading Whisper model: {model_size} ({device}/{compute_type})", flush=True)
                self._models[key] = WhisperModel(
                    model_size_or_path=model_size,
                    device=device,
                    compute_type=compute_type
                )
                print(f"✅ Model loaded & cached", flush=True)
            return self._models[key]
    
    def release(self, model_size: str = None):
        """Giải phóng model khỏi cache (khi cần free VRAM)"""
        with self._lock:
            if model_size:
                key_prefix = f"{model_size}_"
                to_delete = [k for k in self._models if k.startswith(key_prefix)]
                for k in to_delete:
                    del self._models[k]
            else:
                self._models.clear()
            
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            print(f"🧹 Whisper cache cleaned", flush=True)
    
    @classmethod
    def clear_all(cls):
        """Clear toàn bộ cache (dùng khi shutdown app)"""
        if cls._instance:
            cls._instance.release()
            cls._instance = None