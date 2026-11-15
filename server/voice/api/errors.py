"""오류 응답 (문서 4-5)."""

from fastapi.responses import JSONResponse


def store_not_found() -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "store_not_found"})
