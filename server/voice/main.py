"""음성 백엔드 FastAPI 앱. 켜기: server/ 에서 python -m voice.run_voice (또는 uvicorn voice.main:app --port 8100)

켜져 있는 동안 스레드 하나가 30초마다 작업 큐(jobs/queue.py)를 본다.
"""

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from voice import config
from voice.api import dev, home, turn
from voice.jobs import queue

logger = logging.getLogger(__name__)


def _tick(stop: threading.Event) -> None:
    while not stop.wait(config.TICK_SECONDS):
        try:
            queue.run_due()
        except Exception:
            logger.exception("작업 큐 실패")


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop = threading.Event()
    threading.Thread(target=_tick, args=(stop,), daemon=True, name="voice-queue").start()
    yield
    stop.set()


def create_app() -> FastAPI:
    app = FastAPI(title="DONNA voice backend v0.2.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])  # 인증은 나중에 (14장 4번)

    @app.exception_handler(Exception)
    async def internal(request: Request, error: Exception):
        logger.exception("처리 실패 %s", request.url.path)
        return JSONResponse(status_code=500, content={"error": "internal", "message": str(error)})

    @app.get("/health")
    def health():
        return {"status": "ok"}

    for module in (home, turn, dev):
        app.include_router(module.router, prefix="/v1")
    return app


app = create_app()
