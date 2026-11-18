"""음성 백엔드 테스트 공통 설정. 실제 저장소, 실제 CLOVA, 실제 기록 파일을 건드리지 않는다.

기본은 CLOVA 키가 없는 상태라 에이전트가 꺼지고 템플릿·규칙으로만 돈다 (시나리오 테스트).
에이전트를 시험할 때는 clova_on 으로 키를 넣고 가짜 CLOVA(Harness.tests.fakes.FakeClova)를 context.post 에 넣는다.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import clova_usage_log
from app.core.config import settings
from Harness import cache, limiter, runner, trace
from voice import clock, config, context, prepared_snapshot, stt, tts
from voice.dialog import echo

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "s001_baseline.json"


class NoClova:
    """에이전트가 꺼진 시나리오에서 CLOVA 를 부르면 기록해 둔다 (브리핑 단계 LLM 0회 확인)."""

    def __init__(self):
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("CLOVA 를 부르면 안 되는 곳에서 불렀어요")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "voice.db")
    monkeypatch.setattr(clova_usage_log, "LOG_PATH", tmp_path / "clova_usage.db")
    monkeypatch.setattr(trace, "TRACE_PATH", tmp_path / "harness_trace.db")
    monkeypatch.setattr(cache, "CACHE_PATH", None)  # 에이전트 결과 캐시는 메모리만 (진짜 캐시 파일을 읽거나 쓰지 않는다)
    monkeypatch.setattr(settings, "clova_studio_api_key", "")
    monkeypatch.setattr(limiter, "sleep", lambda seconds: None)
    monkeypatch.setattr(runner, "clock", lambda: 0.0)
    monkeypatch.setattr(context, "post", NoClova())
    monkeypatch.setattr(config, "DEMO_FIXTURE", "")  # 켤 때 시연 가게를 넣지 않는다
    monkeypatch.setattr(tts, "ENABLED", False)  # 목소리 모델을 올리지 않는다
    monkeypatch.setattr(stt, "ENABLED", False)  # 받아 적기 모델도 (test_stt.py 는 가짜 모델로 켠다)
    monkeypatch.setattr(prepared_snapshot, "ENABLED", False)  # 밤사이 준비 저장본(실제 CLOVA 답글)을 쓰지 않고 늘 새로 준비한다
    cache.clear()
    echo.forget()  # 도나가 한 말 기억 (시험마다 새로)
    clock.set_now(None)
    yield
    clock.set_now(None)
    cache.clear()


@pytest.fixture
def clova_on(monkeypatch):
    """에이전트를 켠다. 돌려준 함수에 가짜 CLOVA 를 넣으면 context.post 로 쓴다."""
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")

    def use(fake):
        monkeypatch.setattr(context, "post", fake)
        return fake

    return use


def baseline() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class Donna:
    """앱처럼 /v1 을 부르는 도우미."""

    def __init__(self):
        from voice.main import create_app

        self.client = TestClient(create_app())
        self.number = 0
        self.session_id = "sess_20261117_s001"

    def fixtures(self, payload: dict | None = None) -> dict:
        return self.client.post("/v1/dev/fixtures", json=payload or baseline()).json()

    def clock(self, now: str) -> dict:
        return self.client.post("/v1/dev/clock", json={"now": now}).json()

    def run(self, job: str) -> dict:
        return self.client.post("/v1/dev/run", json={"store_id": "s001", "job": job}).json()

    def home(self) -> dict:
        return self.client.get("/v1/home", params={"store_id": "s001"}).json()

    def state(self) -> dict:
        return self.client.get("/v1/dev/state", params={"store_id": "s001"}).json()

    def review(self, **body) -> dict:
        return self.client.post("/v1/dev/reviews", json={"store_id": "s001", **body}).json()

    def settings(self, value) -> dict:
        return self.client.patch("/v1/settings", json={"store_id": "s001", "negative_review_auto_reply": value}).json()

    def turn(self, text: str | None = None, *, event: str | None = None, request_id: str | None = None, source: str = "voice",
             addressed: bool = False, expect: int = 200, **context_fields) -> dict:
        self.number += 1
        body = {
            "request_id": request_id or f"req_{self.number:04d}", "store_id": "s001", "session_id": self.session_id,
            "client_time": "2026-11-17T09:02:11+09:00",
            "utterance": None if text is None else {"text": text, "confidence": 0.93, "source": source, "addressed": addressed},
            "event": event, "context": {"last_turn_id": None, "donna_was_speaking": False, "heard_until": None, **context_fields},
        }
        response = self.client.post("/v1/turn", json=body)
        assert response.status_code == expect, response.text
        return response.json()


def prepared(payload: dict | None = None, *, permission=None) -> Donna:
    """13장 기준 데이터를 넣고 11/17 09:00 에 브리핑을 준비한 상태."""
    donna = Donna()
    donna.clock("2026-11-17T09:00:00+09:00")
    donna.fixtures(payload)
    if permission is not None:
        donna.settings(permission)
    donna.run("prepare_briefing")
    return donna


@pytest.fixture
def donna() -> Donna:
    return prepared()


class Choongjang(Donna):
    """초옹장(s005) 시연 데이터로 /v1 을 부르는 도우미. 알바생 화면·알림·시연 리뷰도 부른다."""

    def __init__(self):
        super().__init__()
        self.session_id = "sess_20261117_s005"
        self.tokens: dict[str, str] = {}

    def get(self, path: str, **params) -> dict:
        response = self.client.get(path, params={"store_id": "s005", **params})
        assert response.status_code == 200, response.text
        return response.json()

    def turn(self, text: str | None = None, **kw) -> dict:
        self.number += 1
        body = {"request_id": kw.get("request_id") or f"req_{self.number:04d}", "store_id": "s005", "session_id": self.session_id,
                "utterance": None if text is None else {"text": text, "source": "voice", "addressed": kw.get("addressed", False)},
                "event": kw.get("event"), "notice_id": kw.get("notice_id")}
        response = self.client.post("/v1/turn", json=body)
        assert response.status_code == 200, response.text
        return response.json()

    def settings(self, value) -> dict:
        return self.client.patch("/v1/settings", json={"store_id": "s005", "negative_review_auto_reply": value}).json()

    def state(self) -> dict:
        return self.get("/v1/dev/state")

    def notices(self) -> list[dict]:
        return self.get("/v1/notices")["notices"]

    def demo_review(self, name: str) -> str:
        response = self.client.post("/v1/dev/demo_review", json={"store_id": "s005", "name": name})
        assert response.status_code == 200, response.text
        return response.json()["review_id"]

    def staff_token(self, staff_id: str) -> str:
        """가입한 알바생의 로그인 표시 (시험에서는 서버가 바로 준다)."""
        from voice import staff

        if staff_id not in self.tokens:
            self.tokens[staff_id] = staff.issue_token(staff_id)
        return self.tokens[staff_id]

    def as_staff(self, staff_id: str) -> dict:
        return {"X-Staff-Token": self.staff_token(staff_id)}

    def staff_today(self, staff_id: str = "st_harin") -> dict:
        response = self.client.get("/v1/staff/today", headers=self.as_staff(staff_id))
        assert response.status_code == 200, response.text
        return response.json()

    def staff_post(self, path: str, staff_id: str | None = None, **body):
        """staff_id 를 주면 그 알바생으로 로그인한 요청 (X-Staff-Token)."""
        return self.client.post(f"/v1/staff{path}", json=body, headers=self.as_staff(staff_id) if staff_id else {})

    def join(self, name: str = "하린") -> str:
        """초대·가입을 건너뛰고 가입한 상태로 (개발자 모드 '하린 바로 가입'과 같다). 알바생 번호를 돌려준다."""
        joined = self.client.post("/v1/dev/staff_join", json={"store_id": "s005", "name": name}).json()
        self.tokens[joined["staff_id"]] = joined["token"]
        return joined["staff_id"]

    def open_notice(self) -> dict:
        """앱처럼: 알림을 읽고, 묻는 알림이면 turn(event: notice)로 연다."""
        found = [n for n in self.notices() if n["opens_turn"]]
        assert found, "열 알림이 없어요"
        return self.turn(event="notice", notice_id=found[-1]["id"])


def choongjang(*, permission=True, at: str | None = "2026-11-17T15:35:00+09:00") -> Choongjang:
    """초옹장 픽스처(11/17 09:02, 브리핑 준비) → 허락 설정 → (at) 시계를 옮기고 하린이 가입한 뒤 할 일 화면을 연다 (출근).
    at=None 이면 하린은 아직 안 들어온 상태 그대로다 (2026-11-18 픽스처: 시연에서 초대한다)."""
    donna = Choongjang()
    assert donna.client.post("/v1/dev/fixtures", json={"fixture": "s005_choongjang"}).json()["store_id"] == "s005"
    if permission is not None:
        donna.settings(permission)
    if at:
        donna.clock(at)
        donna.join("하린")
        donna.staff_today("st_harin")
        donna.notices()  # 그때까지 쌓인 알림은 비운다
    return donna
