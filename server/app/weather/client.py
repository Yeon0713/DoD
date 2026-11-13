"""기상청 API허브(apihub.kma.go.kr) 호출. 인증키 붙이기, 제한된 재시도, 오류 종류 구분을 한곳에서 한다.

- typ01 (지점정보, ASOS 일자료): 글자(텍스트) 응답 → get_text
- typ02 (단기·중기예보, 초단기실황): JSON 응답, 여러 쪽(page) → get_items 가 모든 쪽을 모은다

인증키는 주소의 authKey 로 보내야 해서 요청 주소에 들어간다. 그래서 오류 문구에 주소를 넣지 않고,
httpx 오류는 주소가 빠진 우리 오류로 바꿔서 낸다 (로그에 키가 남지 않게).
공공데이터포털(data.go.kr)의 serviceKey 와 주소(apis.data.go.kr)는 쓰지 않는다.
"""

import json
import re
import time
from collections.abc import Callable

import httpx

from app.core.config import settings

BASE_URL = "https://apihub.kma.go.kr"
RETRIES = 3  # 시간 초과, 연결 실패, 서버 5xx 일 때만 다시 시도한다
PAGE_SIZE = 1000


class KmaError(Exception):
    """기상청 API 오류. code 는 화면·로그에서 종류를 구분하는 값."""

    code = "KMA_ERROR"


class KmaAuthError(KmaError):
    """인증키가 틀렸거나 그 API 활용신청이 승인되지 않았다."""

    code = "KMA_AUTH"


class KmaRateLimitError(KmaError):
    """호출 한도를 넘었다. 다시 시도해도 소용없으므로 바로 멈춘다."""

    code = "KMA_RATE_LIMIT"


class KmaTimeoutError(KmaError):
    code = "KMA_TIMEOUT"


class KmaNoDataError(KmaError):
    """자료가 아직 발표되지 않았거나 없다. 부르는 쪽이 직전 발표 시각으로 다시 시도한다."""

    code = "KMA_NO_DATA"


class KmaInvalidRequestError(KmaError):
    """요청 값이 틀렸다 (예: 그 구역코드로는 중기 기온예보를 주지 않음)."""

    code = "KMA_INVALID_REQUEST"


class KmaResponseError(KmaError):
    """응답 모양이 예상과 다르다 (JSON 대신 XML·오류 글, 칸 이름 줄 없음 등)."""

    code = "KMA_BAD_RESPONSE"


# 단기예보 활용가이드의 결과 코드 (resultCode / returnReasonCode)
_RESULT_CODES: dict[str, type[KmaError]] = {
    "03": KmaNoDataError,
    "10": KmaInvalidRequestError,
    "11": KmaInvalidRequestError,
    "20": KmaAuthError,  # SERVICE_ACCESS_DENIED
    "21": KmaAuthError,  # TEMPORARILY_DISABLE_THE_SERVICEKEY
    "22": KmaRateLimitError,  # LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS
    "30": KmaAuthError,  # SERVICE_KEY_IS_NOT_REGISTERED
    "31": KmaAuthError,  # DEADLINE_HAS_EXPIRED
    "32": KmaAuthError,  # UNREGISTERED_IP
    "33": KmaAuthError,  # UNSIGNED_CALL
}


class KmaClient:
    def __init__(
        self,
        auth_key: str,
        base_url: str = BASE_URL,
        timeout: float = 10,
        retries: int = RETRIES,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not auth_key:
            raise KmaAuthError("기상청 인증키(KMA_API_KEY)가 비어 있어요")
        self._key = auth_key
        self._base = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=timeout)
        self._retries = retries
        self._sleep = sleep

    @classmethod
    def from_settings(cls) -> "KmaClient":
        return cls(settings.kma_api_key)

    def get_text(self, path: str, params: dict) -> str:
        """typ01 글자 응답. 한글이 EUC-KR 로 올 수 있어 UTF-8 이 아니면 CP949 로 읽는다."""
        content = self._request(path, params).content
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("cp949", errors="replace")
        _raise_hub_error(text)
        return text

    def get_items(self, path: str, params: dict, page_size: int = PAGE_SIZE) -> list[dict]:
        """typ02 JSON 응답의 items.item 을 모든 쪽에서 모은다."""
        items: list[dict] = []
        page = 1
        while True:
            res = self._request(path, {**params, "dataType": "JSON", "pageNo": page, "numOfRows": page_size})
            body = _typ02_body(res.text)
            got = _items_of(body)
            items.extend(got)
            total = int(body.get("totalCount") or 0)
            if not got or len(items) >= total:
                return items
            page += 1

    def _request(self, path: str, params: dict) -> httpx.Response:
        url = self._base + path
        for attempt in range(1, self._retries + 1):
            last = attempt == self._retries
            try:
                res = self._http.get(url, params={**params, "authKey": self._key})
            except httpx.TimeoutException:
                if last:
                    raise KmaTimeoutError(f"기상청 응답이 늦어요 ({path})") from None
            except httpx.TransportError:
                if last:
                    raise KmaTimeoutError(f"기상청에 연결하지 못했어요 ({path})") from None
            else:
                if res.status_code < 500:
                    _raise_status(res, path)
                    return res
                if last:
                    raise KmaResponseError(f"기상청 서버 오류 {res.status_code} ({path})")
            self._sleep(0.5 * attempt)
        raise AssertionError("unreachable")


def _raise_status(res: httpx.Response, path: str) -> None:
    if res.status_code == 200:
        return
    _raise_hub_error(res.text)  # API허브는 401·403 등에 {"result": {...}} 를 준다
    if res.status_code in (401, 403):
        raise KmaAuthError(f"인증키가 틀렸거나 활용신청이 승인되지 않았어요 ({path})")
    if res.status_code == 429:
        raise KmaRateLimitError(f"호출 한도를 넘었어요 ({path})")
    raise KmaResponseError(f"기상청 응답 {res.status_code} ({path})")


def _raise_hub_error(text: str) -> None:
    """API허브 공통 오류 {"result": {"status": 401, "message": "유효한 인증키가 아닙니다."}}"""
    stripped = text.lstrip()
    if not stripped.startswith("{"):
        return
    try:
        data = json.loads(stripped)
    except ValueError:
        return
    result = data.get("result") if isinstance(data, dict) else None
    if not isinstance(result, dict) or "response" in data:
        return
    status, message = int(result.get("status") or 0), str(result.get("message") or "")
    if status in (401, 403):
        raise KmaAuthError(f"인증키 또는 활용신청 문제: {message}")
    if status == 429 or "초과" in message:
        raise KmaRateLimitError(f"호출 한도 초과: {message}")
    raise KmaResponseError(f"기상청 오류 {status}: {message}")


def _typ02_body(text: str) -> dict:
    """typ02 응답에서 body 를 꺼낸다. 결과 코드가 정상(00)이 아니면 종류에 맞는 오류를 낸다."""
    stripped = text.lstrip()
    if stripped.startswith("<"):  # dataType=JSON 이어도 오류는 XML 로 오는 때가 있다
        code = re.search(r"<(?:resultCode|returnReasonCode)>\s*(\d+)\s*<", stripped)
        message = re.search(r"<(?:resultMsg|returnAuthMsg|errMsg)>\s*([^<]*)<", stripped)
        _raise_result(code.group(1) if code else "", message.group(1) if message else "XML 응답")
        raise KmaResponseError("JSON 대신 XML 이 왔어요")
    _raise_hub_error(stripped)
    try:
        response = json.loads(stripped)["response"]
    except (ValueError, KeyError, TypeError):
        raise KmaResponseError(f"JSON 응답 모양이 달라요: {stripped[:80]!r}") from None
    header = response.get("header") or {}
    _raise_result(str(header.get("resultCode", "")), str(header.get("resultMsg", "")))
    return response.get("body") or {}


def _raise_result(code: str, message: str) -> None:
    if code in ("00", "0"):
        return
    raise _RESULT_CODES.get(code, KmaResponseError)(f"기상청 결과 코드 {code or '?'}: {message}")


def _items_of(body: dict) -> list[dict]:
    items = body.get("items")
    if not items:  # 자료가 없으면 "" 로 오기도 한다
        return []
    item = items.get("item") or []
    return item if isinstance(item, list) else [item]
