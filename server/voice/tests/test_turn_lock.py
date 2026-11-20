"""같은 가게의 /v1/turn 은 차례로 처리한다 (겹친 말에 단계가 두 번 넘어가거나 한 번만 넘어가지 않게, 같은 요청은 한 번만)."""

import threading
import time

from voice import repo
from voice.dialog import turn as dialog
from voice.jobs import briefing
from voice.tests.conftest import choongjang


def _slow_understanding(monkeypatch, seconds: float = 0.3):
    real = dialog.understand

    def slow(*args, **kwargs):
        time.sleep(seconds)  # 판정 에이전트(최대 3초)를 기다리는 사이
        return real(*args, **kwargs)

    monkeypatch.setattr(dialog, "understand", slow)


def _turn(request_id: str, text: str = "다음") -> dict:
    return {"store_id": "s005", "request_id": request_id, "session_id": "sess_concurrent",
            "utterance": {"text": text, "addressed": True}}


def _together(*requests: dict) -> list[dict]:
    results: list[dict | None] = [None] * len(requests)

    def run(index: int, request: dict) -> None:
        results[index] = dialog.handle(request)

    threads = [threading.Thread(target=run, args=(i, r)) for i, r in enumerate(requests)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    return results


def _steps() -> list[str]:
    """오늘 브리핑에 있는 단계 이름 (순서대로)."""
    brief = briefing.current("s005")
    return [key for key in briefing.STEP_KEYS if brief["steps"].get(key)]


def test_overlapping_turns_advance_one_step_each(monkeypatch):
    choongjang()
    steps = _steps()
    _slow_understanding(monkeypatch)
    first, second = _together(_turn("r1"), _turn("r2"))
    assert sorted([first["briefing"]["step_key"], second["briefing"]["step_key"]], key=steps.index) == steps[:2]
    assert repo.get("session", "sess_concurrent")["step"] == steps[1]


def test_same_request_twice_at_once_runs_once(monkeypatch):
    choongjang()
    steps = _steps()
    _slow_understanding(monkeypatch)
    first, second = _together(_turn("r1"), _turn("r1"))
    assert first == second and first["briefing"]["step_key"] == steps[0]
    follow = dialog.handle(_turn("r2"))
    assert follow["briefing"]["step_key"] == steps[1]
