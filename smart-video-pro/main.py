from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from src.domain.entities import RunPipelineRequest
from src.application.pipeline_usecase import VideoPipelineBuilder
from src.application.quota_service import QuotaService
from datetime import datetime

app = FastAPI()
quota_svc = QuotaService(monthly_limit=600)

@app.websocket("/ws/pipeline")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        # 1. Chờ UI gửi cấu hình config (JSON)
        config_data = await ws.receive_json()
        
        # 2. Map JSON -> Entity (Pydantic tự động validate)
        request = RunPipelineRequest(**config_data)

        # 3. Kiểm tra Quota thương mại
        current_month = datetime.now().strftime("%Y-%m")
        if not quota_svc.check_and_deduct(current_month):
            await ws.send_json({"stage": -1, "msg": "Hết Quota tháng này!", "status": "err"})
            return

        # 4. Chạy Pipeline (Builder Pattern)
        builder = VideoPipelineBuilder(request, ws)
        pipeline = builder.build_stt() \
                          .build_gemini()
        
        if request.mode == "with-yolo":
            pipeline = pipeline.build_yolo()
            
        await pipeline.build_render().execute()

    except WebSocketDisconnect:
        print("UI disconnected")
    except Exception as e:
        await ws.send_json({"stage": -1, "msg": str(e), "status": "err"})

if __name__ == "__main__":
    import uvicorn
    # Chạy ngầm ở một port (vd: 8999)
    uvicorn.run(app, host="127.0.0.1", port=8999, log_level="info")