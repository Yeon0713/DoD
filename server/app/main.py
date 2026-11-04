from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.modules import load_modules


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    # 웹 프론트가 다른 주소에서 이 서버를 부를 수 있게 허용
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    def health():
        """서버가 살아 있는지 확인용. 배포 후 로드밸런서도 이 주소를 확인한다."""
        return {"status": "ok"}

    for name, router in load_modules():
        app.include_router(router, prefix=f"/api/{name}", tags=[name])

    return app


app = create_app()
