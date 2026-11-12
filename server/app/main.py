import datetime as dt
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.error_response import register_error_handlers
from app.core.seoul_time import clock_shift, now_seoul, set_clock_shift
from app.modules import load_modules

# 서버가 켜질 때마다 새로 정해지는 값. 앱이 이 값이 바뀐 것을 보면 이 기기에 저장한 값을 지우고 처음부터 시작한다.
# (서버의 계산 결과와 고친 설정도 서버를 다시 켜면 사라지므로, 앱도 같이 처음 상태로 맞춘다)
BOOT_ID = uuid.uuid4().hex


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    # 모든 오류를 {"error": {"code", "message"}} 모양으로 통일
    register_error_handlers(app)

    # 웹 프론트가 다른 주소에서 이 서버를 부를 수 있게 허용
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    def health():
        """서버가 살아 있는지 확인용. 배포 후 로드밸런서도 이 주소를 확인한다.

        boot_id: 서버가 켜질 때마다 바뀌는 값. 앱(mobile/src/lib/storage.ts)이 켜질 때 이 값을 보고 초기화를 정한다.
        """
        body = {"status": "ok", "boot_id": BOOT_ID}
        if settings.dev_clock_enabled:
            # 앱도 같은 만큼 시계를 앞당기게 알려 준다 (mobile/src/lib/storage.ts)
            body["clock_shift_minutes"] = int(clock_shift().total_seconds() // 60)
        return body

    if settings.dev_clock_enabled:

        @app.post("/dev/clock", tags=["system"])
        def move_clock(days: float = 0, hours: float = 0):
            """로컬 시험용. 서버 시계를 실제 시각에서 days일 hours시간 뒤로 맞춘다 (0, 0 이면 원래대로)."""
            set_clock_shift(dt.timedelta(days=days, hours=hours))
            return {"now": now_seoul().isoformat(), "clock_shift_minutes": int(clock_shift().total_seconds() // 60)}

        @app.post("/dev/reset", tags=["system"])
        def reset_demo():
            """로컬 시험용 초기화 (앱 시작 화면 메뉴 › 초기화). 등록한 가게와 불러온 리뷰, 등록 기록, 고친 설정과 계산 결과,
            로그인 중인 표를 지우고 시계를 실제 시각으로 돌린다. 목업 가게 파일(s001~s003)은 그대로다."""
            from app.data_pipeline import registered_stores, store_snapshot_cache
            from app.modules.auth import router as auth_router
            from app.modules.stores import router as stores_router

            removed = registered_stores.reset_all()
            store_snapshot_cache.clear_all()
            for state in (auth_router._pending, auth_router._results, auth_router._mock_codes, stores_router._previews):
                state.clear()
            set_clock_shift(dt.timedelta(0))
            return {"removed_stores": removed}

    for name, router in load_modules():
        app.include_router(router, prefix=f"/api/{name}", tags=[name])

    return app


app = create_app()
