"""서버 전체 CLOVA 동시 호출 한도.

기존 기능은 모듈마다 WORKERS = 2 를 따로 두어 합치면 더 많이 동시에 부를 수 있다.
하네스의 모든 에이전트 호출은 이 세마포어 하나를 지난다. 429(요청 한도)를 받으면 잠깐 기다렸다 다시 부른다.
"""

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

MAX_CONCURRENT = 2  # 동시에 CLOVA 를 부르는 수
RATE_LIMIT_WAIT_SECONDS = 10  # 429 를 받으면 기다리는 시간
RATE_LIMIT_RETRIES = 1  # 429 뒤 다시 부르는 횟수

_semaphore = threading.BoundedSemaphore(MAX_CONCURRENT)
sleep = time.sleep  # 테스트에서 바꾼다


def set_max_concurrent(count: int) -> None:
    """동시 호출 한도를 바꾼다. 측정 스크립트가 빨리 돌 때 쓴다 (서버는 기본값 그대로)."""
    global MAX_CONCURRENT, _semaphore
    MAX_CONCURRENT = count
    _semaphore = threading.BoundedSemaphore(count)


class SlotBusy(Exception):
    """기다릴 수 있는 시간 안에 자리를 잡지 못했다."""


@contextmanager
def slot(wait: float | None = None) -> Iterator[float]:
    """CLOVA 를 부르는 동안 자리 하나를 잡고, 자리를 기다린 초를 준다 (바로 잡으면 0).
    wait 가 있으면 그만큼만 기다리고, 못 잡으면 SlotBusy (엄격한 예산, H4)."""
    semaphore = _semaphore  # set_max_concurrent 가 바꿔도 잡은 객체에서 푼다
    waited = 0.0
    if not semaphore.acquire(blocking=False):
        asked = time.perf_counter()
        if not semaphore.acquire(timeout=wait):
            raise SlotBusy
        waited = time.perf_counter() - asked
    try:
        yield waited
    finally:
        semaphore.release()


# ── 429 기다리기: 응답 헤더를 따른다 ──
# 헤더에 다시 부를 때(Retry-After, x-ratelimit-reset-*)가 있으면 그만큼, 없으면 RATE_LIMIT_WAIT_SECONDS. 길어도 상한까지만.
# 기다린 횟수·시간을 세고, 처음 받은 한도 헤더(ratelimit·retry-after 가 든 이름)를 한 번 출력해 둔다.

RATE_LIMIT_MAX_WAIT_SECONDS = 60
_rate_lock = threading.Lock()
rate_limit_stats = {"waits": 0, "seconds": 0.0}
first_rate_limit_headers: dict[str, str] | None = None
_DURATION_RE = __import__("re").compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)?")


def rate_limit_headers(headers) -> dict[str, str]:
    """한도와 관련된 헤더만 (이름은 소문자)."""
    return {str(k).lower(): str(v) for k, v in dict(headers or {}).items()
            if "ratelimit" in str(k).lower() or "retry-after" in str(k).lower()}


def _seconds(text: str) -> float | None:
    """'7', '1.5', '6s', '1m30s', '500ms' → 초. 못 읽으면 None."""
    text = text.strip()
    parts = _DURATION_RE.findall(text)
    if not parts or not text[0].isdigit():
        return None
    scale = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "": 1}
    return sum(float(number) * scale[unit] for number, unit in parts)


def wait_seconds(headers) -> float:
    """429 응답 헤더로 기다릴 초를 정한다."""
    found = rate_limit_headers(headers)
    candidates = [found["retry-after"]] if "retry-after" in found else [v for k, v in found.items() if "reset" in k]
    values = [s for s in (_seconds(v) for v in candidates) if s is not None and s > 0]
    seconds = max(values) if values else RATE_LIMIT_WAIT_SECONDS
    return min(seconds, RATE_LIMIT_MAX_WAIT_SECONDS)


def wait_after_429(headers) -> float:
    """헤더를 따라 기다리고 센다. 처음 받은 한도 헤더는 한 번 출력한다. 기다린 초를 돌려준다."""
    global first_rate_limit_headers
    seconds = wait_seconds(headers)
    with _rate_lock:
        rate_limit_stats["waits"] += 1
        rate_limit_stats["seconds"] += seconds
        first = first_rate_limit_headers is None
        if first:
            first_rate_limit_headers = rate_limit_headers(headers)
    if first:
        print(f"[429] CLOVA 한도 헤더: {first_rate_limit_headers or '(한도 헤더 없음)'} → {seconds:g}초 기다림", flush=True)
    sleep(seconds)
    return seconds


def rate_limit_snapshot() -> dict:
    with _rate_lock:
        return {"waits": rate_limit_stats["waits"], "seconds": round(rate_limit_stats["seconds"], 1)}
