"""이름과 키(보통 가게 id)마다 하나씩 있는 락.

같은 가게에서 겹치면 안 되는 일을 차례로 돌린다 (다른 가게끼리는 서로 기다리지 않는다).
  turn     /v1/turn 하나 (세션을 읽고 → 뜻 판정을 기다리고 → 세션을 쓰는 사이에 다른 말이 끼지 않게)
  prepare  브리핑 준비 (작업 큐와 사장님의 "응"이 같은 가게 브리핑을 한꺼번에 다시 만들지 않게)
"""

import threading

_locks: dict[tuple[str, str], threading.Lock] = {}
_guard = threading.Lock()


def lock(name: str, key: str) -> threading.Lock:
    with _guard:
        return _locks.setdefault((name, key), threading.Lock())
