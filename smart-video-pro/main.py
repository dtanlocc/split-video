# main.py
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.infrastructure.llm.gemini_engine import GeminiEngine
from src.infrastructure.utils.srt_utils import SRTUtils
from src.application.highlight_orchestrator import HighlightOrchestrator
from pathlib import Path

def main():
    API_KEYS = ["...", "..."]
    # Khởi tạo các thành phần theo Dependency Injection
    engine = GeminiEngine(API_KEYS, "gemini-2.5-flash")
    utils = SRTUtils()
    orchestrator = HighlightOrchestrator(engine, utils)

    srt_files = list(Path("inputs").glob("*.srt"))
    
    # Rule: Giới hạn workers để tối ưu CPU/Network
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(orchestrator.process_video, s, Path("outputs")) for s in srt_files]
        for f in as_completed(futures):
            f.result() # Bắt lỗi nếu có

if __name__ == "__main__":
    main()