import asyncio
from src.domain.entities import RunPipelineRequest

class VideoPipelineBuilder:
    def __init__(self, request: RunPipelineRequest, websocket):
        self.req = request
        self.ws = websocket  # Kênh giao tiếp với UI
        self.steps = []

    async def _emit(self, stage: int, pct: int, msg: str, status: str = "inf"):
        """Gắn Observer Pattern đẩy data realtime về UI"""
        await self.ws.send_json({
            "stage": stage, "pct": pct, "msg": msg, "status": status
        })

    def build_stt(self):
        # Truyền Dependency Injection ở đây
        self.steps.append(lambda: self._run_stt())
        return self

    async def _run_stt(self):
        await self._emit(0, 10, f"Khởi động Whisper {self.req.stt_config.model}...")
        # Gọi Whisper Infrastructure
        # whisper_repo.transcribe(self.req.stt_config)
        await asyncio.sleep(2) # Mô phỏng
        await self._emit(0, 100, "SRT tạo xong", "ok")

    # ... Tương tự cho build_gemini(), build_yolo(), build_render()

    async def execute(self):
        try:
            for step in self.steps:
                await step()
            await self._emit(5, 100, "Hoàn tất Pipeline!", "ok")
        except Exception as e:
            await self._emit(-1, 0, f"Lỗi hệ thống: {str(e)}", "err")