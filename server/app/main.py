import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.error_response import register_error_handlers
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
        return {"status": "ok", "boot_id": BOOT_ID}

    for name, router in load_modules():
        app.include_router(router, prefix=f"/api/{name}", tags=[name])

    return app


app = create_app()
