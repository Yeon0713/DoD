"""음성 백엔드 FastAPI 앱. 켜기: server/ 에서 python -m voice.run_voice (또는 uvicorn voice.main:app --port 8100)

켜져 있는 동안 스레드 하나가 30초마다 작업 큐(jobs/queue.py)를 본다.
켤 때 시연 가게(config.DEMO_FIXTURE, 기본 초옹장)가 없으면 넣고, 시계를 그 데이터의 demo.now 로 맞추고, 브리핑을 준비한다.
가게 로고와 메뉴 사진은 /static 에서 준다 (voice/static).
"""

import logging
import threading
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from voice import config, tts
from voice.api import account, dev, home, staff, tabs, turn
from voice.api import tts as tts_api
from voice.jobs import queue

logger = logging.getLogger(__name__)


def _tick(stop: threading.Event) -> None:
    while not stop.wait(config.TICK_SECONDS):
        try:
            queue.run_due()
        except Exception:
            logger.exception("작업 큐 실패")


def seed_demo() -> None:
    """시연 가게를 넣고(없을 때만) 시계를 맞춘 뒤 브리핑을 준비한다. 사장님이 허락한 것 같은 기록은 그대로 둔다."""
    if not config.DEMO_FIXTURE:
        return
    try:
        dev.seed(config.DEMO_FIXTURE, fresh=False)
        tts.prewarm(tts.FIXED)
    except Exception:
        logger.exception("시연 가게를 준비하지 못했어요")


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop = threading.Event()
    threading.Thread(target=seed_demo, daemon=True, name="voice-seed").start()
    threading.Thread(target=_tick, args=(stop,), daemon=True, name="voice-queue").start()
    yield
    stop.set()


def create_app() -> FastAPI:
    app = FastAPI(title="DONNA voice backend v0.2.1", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])  # 인증은 나중에 (14장 4번)

    @app.exception_handler(Exception)
    async def internal(request: Request, error: Exception):
        logger.exception("처리 실패 %s", request.url.path)
        return JSONResponse(status_code=500, content={"error": "internal", "message": str(error)})

    @app.get("/health")
    def health():
        return {"status": "ok"}

    for module in (home, turn, tabs, tts_api, dev, account, staff):
        app.include_router(module.router, prefix="/v1")
    account.mount(app)  # 가입·로그인: 메인 서버의 /api/auth, /api/naver, /api/stores, /api/owner_check
    app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")
    return app


app = create_app()
