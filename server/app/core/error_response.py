"""오류 응답 모양 통일. 모든 오류를 아래 모양으로 돌려준다.

    {"error": {"code": "INVALID_DATE_RANGE", "message": "사람이 읽는 설명", "details": [...]}}

code 는 프론트가 오류 종류를 구분하는 값이고, details 는 입력값 오류일 때만 붙는다.
"""

import datetime as dt
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# HTTP 상태 번호별 기본 code
STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    422: "INVALID_INPUT",
    500: "INTERNAL_ERROR",
}


class ApiError(Exception):
    """모듈에서 직접 오류를 낼 때 쓴다. 예) raise ApiError(400, "INVALID_DATE_RANGE", "설명")"""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def check_date_range(from_date: dt.date | None, to_date: dt.date | None) -> None:
    """?from=...&to=... 기간이 거꾸로면 400 오류를 낸다."""
    if from_date and to_date and from_date > to_date:
        raise ApiError(400, "INVALID_DATE_RANGE", "from 날짜가 to 날짜보다 늦습니다.")


def _error_body(code: str, message: str, details: list[dict] | None = None) -> dict:
    error = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"error": error}


def register_error_handlers(app: FastAPI) -> None:
    """main.py 에서 한 번 부른다. 이후 모든 오류가 같은 모양으로 나간다."""

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status_code, content=_error_body(exc.code, exc.message))

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException):
        code = STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(code, str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        details = [
            {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422, content=_error_body("INVALID_INPUT", "요청 값이 올바르지 않습니다.", details)
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        logger.exception("처리하지 못한 오류: %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500, content=_error_body("INTERNAL_ERROR", "서버 내부 오류가 발생했습니다.")
        )
