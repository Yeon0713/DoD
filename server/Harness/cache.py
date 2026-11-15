"""에이전트 결과 캐시. 키는 (에이전트, 가게, 입력 해시, 프롬프트 버전).

에이전트가 스스로 만든 제안(source == "AGENT")만 기억한다. 물러나기 결과는 기억하지 않아 다음 계산 때 다시 시도한다.
서버 메모리에만 있어 서버를 다시 켜면 비워진다 (기존 답글 초안 캐시와 같다).
"""

import hashlib
import json
import threading

_results: dict[tuple[str, str, str, str], object] = {}
_guard = threading.Lock()


def digest(value: object) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def get(key: tuple[str, str, str, str]) -> object | None:
    with _guard:
        return _results.get(key)


def put(key: tuple[str, str, str, str], value: object) -> None:
    with _guard:
        _results[key] = value


def clear() -> None:
    with _guard:
        _results.clear()
