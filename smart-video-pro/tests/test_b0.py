from src.infrastructure.video.audio_extractor import AudioExtractor
from src.domain.entities import AudioConfig
import os

def test_b0():
    config = AudioConfig(sample_rate=16000, channels=1)
    extractor = AudioExtractor(config)
    
    video_input = "test_assets/sample.mp4"
    try:
        output_wav = extractor.extract_single(video_input)
        
        # Kiểm tra 1: File có tồn tại không?
        assert os.path.exists(output_wav)
        # Kiểm tra 2: Dung lượng file có > 0 không?
        assert os.path.getsize(output_wav) > 0
        
        print(f"✅ B0 Passed: {output_wav}")
    except Exception as e:
        print(f"❌ B0 Failed: {e}")

if __name__ == "__main__":
    test_b0()