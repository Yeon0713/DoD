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


@contextmanager
def slot() -> Iterator[None]:
    """CLOVA 를 부르는 동안 자리 하나를 잡는다."""
    with _semaphore:
        yield
