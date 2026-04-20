from src.infrastructure.llm.gemini_engine import GeminiEngine
from src.infrastructure.utils.srt_utils import SRTUtils
from src.application.highlight_orchestrator import HighlightOrchestrator
from pathlib import Path

def test_b2():
    API_KEYS = [
 "AIzaSyBJOUyGvGvS1zP55Mqq1E8A2wEj86ILY0I",
    "AIzaSyDne16vvX_E78-8-Nk3Pl3d7dUEGALTpxY",
] # Dùng key thật của bạn
    engine = GeminiEngine(API_KEYS, "gemini-2.0-flash")
    utils = SRTUtils()
    orchestrator = HighlightOrchestrator(engine, utils)
    
    srt_input = Path("test_assets/sample.srt")
    output_dir = Path("test_output")
    
    print("🚀 Running B2 (AI Analysis)...")
    orchestrator.process_video(srt_input, output_dir)
    
    # Kiểm tra 1: File JSON có được tạo ra không?
    json_path = output_dir / f"highlights_{srt_input.stem}.json"
    assert json_path.exists()
    
    # Kiểm tra 2: Nội dung JSON có đúng cấu trúc logic của bạn không?
    import json
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert "start" in data[0]
        assert "end" in data[0]
        assert "title" in data[0]
        print(f"✅ B2 Passed: Title mẫu: {data[0]['title']}")

if __name__ == "__main__":
    test_b2()