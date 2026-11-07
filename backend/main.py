"""AIGamebuddy local backend. Run: uvicorn main:app --host 127.0.0.1 --port 8766"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from screen_capture import ScreenCapture

capture = ScreenCapture()

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    capture.close()

app = FastAPI(title="AIGamebuddy Backend", version="0.1.0", lifespan=lifespan)

@app.get("/health")
def health():
    return {"status": "ok", "service": "AIGamebuddy", "version": "0.1.0"}

@app.get("/monitors")
def monitors():
    try:
        return {"monitors": capture.monitors()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Monitor enumeration failed: {exc}") from exc

@app.get("/frame")
def frame(monitor: int = 1):
    try:
        return Response(content=capture.jpeg(monitor), media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Screen capture failed: {exc}") from exc
