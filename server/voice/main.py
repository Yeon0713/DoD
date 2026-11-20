"""음성 백엔드 FastAPI 앱. 켜기: server/ 에서 python -m voice.run_voice (또는 uvicorn voice.main:app --port 8100)

켜져 있는 동안 스레드 두 개가 30초마다 작업 큐(jobs/queue.py)의 두 줄(아쉬운 리뷰 알림, 나머지)을 따로 본다.
켤 때 시연 가게(config.DEMO_FIXTURE, 기본 초옹장)가 없으면 넣고, 시계를 그 데이터의 demo.now 로 맞추고, 브리핑을 준비한다.
가게 로고와 메뉴 사진은 /static 에서 준다 (voice/static). 인스타에 올릴 사진은 /media 에서 준다 (instagram/media.py).
"""

import logging
import threading
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from voice import config
from voice.api import account, dev, home, instagram, staff, tabs, turn
from voice.api import stt as stt_api, tts as tts_api
from voice.instagram import media
from voice.jobs import queue

logger = logging.getLogger(__name__)


def _tick(stop: threading.Event, lane: str) -> None:
    """줄 하나(jobs/queue.py LANES)를 30초마다 돌린다. 아쉬운 리뷰 알림 줄은 브리핑 준비가 오래 걸려도 기다리지 않는다."""
    while not stop.wait(config.TICK_SECONDS):
        try:
            queue.run_due(lane=lane)
        except Exception:
            logger.exception("작업 큐 실패 (%s)", lane)


def seed_demo() -> None:
    """시연 가게를 넣고(없을 때만) 시계를 맞춘 뒤 브리핑을 준비한다. 사장님이 허락한 것 같은 기록은 그대로 둔다."""
    if not config.DEMO_FIXTURE:
        return
    try:
        dev.seed(config.DEMO_FIXTURE, fresh=False)
    except Exception:
        logger.exception("시연 가게를 준비하지 못했어요")


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop = threading.Event()
    threading.Thread(target=seed_demo, daemon=True, name="voice-seed").start()
    for lane in queue.LANES:
        threading.Thread(target=_tick, args=(stop, lane), daemon=True, name=f"voice-queue-{lane}").start()
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

    for module in (home, turn, tabs, stt_api, tts_api, instagram, dev, account, staff):
        app.include_router(module.router, prefix="/v1")
    account.mount(app)  # 가입·로그인: 메인 서버의 /api/auth, /api/naver, /api/stores, /api/owner_check
    app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")
    # 인스타에 올릴 사진 (MEDIA_HOST=base_url 일 때 인스타 서버가 PUBLIC_MEDIA_BASE_URL/media/... 로 가져간다)
    media.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=media.MEDIA_DIR), name="media")
    return app


app = create_app()
