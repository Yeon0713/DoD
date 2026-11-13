"""LLM 메뉴 후보를 뒤에서 부르기 테스트. 진짜 CLOVA 를 부르지 않고 가짜 응답을 넣는다.

server/ 폴더에서 `python -m pytest` 로 실행한다.
"""

import json
import threading

import httpx
import pytest

from app.analysis.input_shapes import Menu
from app.core.config import settings
from app.menu_board import menu_candidates as module
from app.menu_board.menu_candidates import EMPTY, candidates_in_background

STORE = {"store_id": "s_test", "name": "테스트국수", "category": "국수"}
MENUS = [Menu(menu_id=m, name=n, category="MAIN", price=8000) for m, n in [("1", "물냉면"), ("2", "온면"), ("3", "만두")]]


class FakeClova:
    """정해 둔 답을 돌려준다. gate 가 있으면 열릴 때까지 기다린다(진행 중 상태를 만들려고)."""

    def __init__(self, answer: dict | str, status: int = 200, gate: threading.Event | None = None):
        self.answer = json.dumps(answer, ensure_ascii=False) if isinstance(answer, dict) else answer
        self.status = status
        self.gate = gate
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.gate is not None:
            self.gate.wait(timeout=5)
        return httpx.Response(self.status, json={"result": {"message": {"content": self.answer}}})


@pytest.fixture(autouse=True)
def clova_key(monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    module.forget_all()
    yield
    module.wait_for_background()
    module.forget_all()


def test_first_call_returns_empty_and_next_call_returns_the_result():
    fake = FakeClova({"menu_ids": ["2"], "reason": "추운 날엔 온면이 어울려요"})
    assert candidates_in_background(STORE, MENUS, "WINTER", post=fake) == EMPTY  # 기다리지 않는다
    module.wait_for_background()
    assert candidates_in_background(STORE, MENUS, "WINTER", post=fake).menu_ids == ("2",)
    assert fake.calls == 1


def test_same_key_is_not_asked_twice_while_in_progress():
    gate = threading.Event()
    fake = FakeClova({"menu_ids": ["2"], "reason": "잘 어울려요"}, gate=gate)
    candidates_in_background(STORE, MENUS, "WINTER", post=fake)
    candidates_in_background(STORE, list(reversed(MENUS)), "WINTER", post=fake)  # 같은 키(메뉴 묶음이 같다)
    gate.set()
    module.wait_for_background()
    assert fake.calls == 1
    other = FakeClova({"menu_ids": ["3"], "reason": "잘 어울려요"})
    candidates_in_background(STORE, MENUS, "LOCAL_FESTIVAL", post=other)  # 다른 키는 따로 묻는다
    module.wait_for_background()
    assert other.calls == 1


def test_failed_key_is_not_asked_again_for_an_hour(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(module, "_now", lambda: clock[0])
    failing = FakeClova("", status=500)
    candidates_in_background(STORE, MENUS, "WINTER", post=failing)
    module.wait_for_background()
    good = FakeClova({"menu_ids": ["2"], "reason": "잘 어울려요"})
    clock[0] += 59 * 60  # 59분 뒤: 아직 다시 묻지 않는다
    assert candidates_in_background(STORE, MENUS, "WINTER", post=good) == EMPTY
    module.wait_for_background()
    assert good.calls == 0
    clock[0] += module.RETRY_AFTER_FAILURE_SECONDS - 59 * 60  # 실패 뒤 1시간: 다시 맡긴다
    assert candidates_in_background(STORE, MENUS, "WINTER", post=good) == EMPTY
    module.wait_for_background()
    assert good.calls == 1
    assert candidates_in_background(STORE, MENUS, "WINTER", post=good).menu_ids == ("2",)
    assert module.RETRY_AFTER_FAILURE_SECONDS == 60 * 60


def test_failure_of_one_key_does_not_hold_back_other_keys(monkeypatch):
    monkeypatch.setattr(module, "_now", lambda: 1000.0)
    candidates_in_background(STORE, MENUS, "WINTER", post=FakeClova("", status=500))
    module.wait_for_background()
    other = FakeClova({"menu_ids": ["3"], "reason": "잘 어울려요"})
    candidates_in_background(STORE, MENUS, "LOCAL_FESTIVAL", post=other)
    module.wait_for_background()
    assert other.calls == 1


def test_without_key_nothing_is_asked(monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "")
    fake = FakeClova({"menu_ids": ["2"], "reason": "잘 어울려요"})
    assert candidates_in_background(STORE, MENUS, "WINTER", post=fake) == EMPTY
    assert module._in_progress == {}  # 뒤에서 맡긴 일도 없다
    module.wait_for_background()
    assert fake.calls == 0
