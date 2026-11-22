"""음성 백엔드 테스트 공통 설정. 실제 저장소, 실제 CLOVA, 실제 기록 파일을 건드리지 않는다.

기본은 CLOVA 키가 없는 상태라 에이전트가 꺼지고 템플릿·규칙으로만 돈다 (시나리오 테스트).
에이전트를 시험할 때는 clova_on 으로 키를 넣고 가짜 CLOVA(Harness.tests.fakes.FakeClova)를 context.post 에 넣는다.
인스타도 기본은 꺼져 있다 (토큰 없음, Graph API 를 부르면 실패). ig_on 으로 켜고 가짜 Graph(FakeGraph)를 넣는다.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import clova_usage_log
from app.core.config import settings
from Harness import cache, limiter, runner, trace
from voice import clock, config, context, notebook, prepared_snapshot, tts
from voice.dialog import echo
from voice.instagram import graph, media, posts, story_event
from voice.jobs import revise_jobs

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "s001_baseline.json"


class NoGraph:
    def __call__(self, *args, **kwargs):
        raise AssertionError("인스타 Graph API 를 부르면 안 되는 곳에서 불렀어요")


class FakeGraph:
    """graph.post / graph.get 자리에 넣는 가짜 Instagram Graph API. 부른 것을 calls 에 (method, path, params) 로 남긴다.
    fail: {"media_publish": (190, "토큰 만료")} 처럼 주면 그 경로에서 오류를 돌려준다. status: 컨테이너 상태 차례."""

    def __init__(self, fail: dict | None = None, status: list[str] | None = None):
        self.calls: list[tuple[str, str, dict]] = []
        self.fail = fail or {}
        self.status = list(status or [])
        self.children = 0

    def _reply(self, method: str, url: str, params: dict):
        import httpx

        path = url.split("/v23.0/", 1)[1] if "/v23.0/" in url else url
        params = {k: v for k, v in params.items() if k != "access_token"}
        self.calls.append((method, path, params))
        for key, (code, message) in self.fail.items():
            if path.endswith(key):
                return httpx.Response(400, json={"error": {"message": message, "code": code}})
        if method == "DELETE":
            return httpx.Response(200, json={"success": True})
        if method == "POST" and path.endswith("/media"):
            if params.get("is_carousel_item"):
                self.children += 1
                return httpx.Response(200, json={"id": f"child_{self.children}"})
            return httpx.Response(200, json={"id": {"CAROUSEL": "carousel_1", "STORIES": "story_1"}.get(params.get("media_type"), "single_1")})
        if method == "POST" and path.endswith("/media_publish"):
            return httpx.Response(200, json={"id": "media_1"})
        if path.endswith("content_publishing_limit"):
            return httpx.Response(200, json={"data": [{"quota_usage": 1, "config": {"quota_total": 100, "quota_duration": 86400}}]})
        fields = params.get("fields", "")
        if fields == "status_code":
            return httpx.Response(200, json={"status_code": self.status.pop(0) if self.status else "FINISHED", "id": path})
        if fields == "permalink":
            return httpx.Response(200, json={"permalink": "https://www.instagram.com/p/TEST/", "id": path})
        return httpx.Response(200, json={"id": "17841400000000000", "username": "choongjang_namyang", "profile_picture_url": None})

    def post(self, url, data=None, timeout=None):
        return self._reply("POST", url, data or {})

    def get(self, url, params=None, timeout=None):
        return self._reply("GET", url, params or {})

    def delete(self, url, params=None, timeout=None):
        return self._reply("DELETE", url, params or {})

    def paths(self, method: str | None = None) -> list[str]:
        return [path for m, path, _ in self.calls if method in (None, m)]


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
    monkeypatch.setattr(config, "_DOTENV", {})  # 개발 PC 의 server/.env (VOICE_AGENT_* 등)에 흔들리지 않는다
    monkeypatch.setattr(tts, "ENABLED", False)  # 목소리 모델을 올리지 않는다
    monkeypatch.setattr(settings, "voice_stt", False)  # 네이버 CSR 을 부르지 않는다 (test_stt.py 는 따로 켠다)
    monkeypatch.setattr(prepared_snapshot, "ENABLED", False)  # 밤사이 준비 저장본(실제 CLOVA 답글)을 쓰지 않고 늘 새로 준비한다
    monkeypatch.setattr(settings, "instagram_access_token", "")
    monkeypatch.setattr(settings, "instagram_user_id", "")
    monkeypatch.setattr(settings, "instagram_graph_version", "v23.0")
    monkeypatch.setattr(settings, "media_host", "base_url")
    monkeypatch.setattr(settings, "public_media_base_url", "https://media.example.test")
    monkeypatch.setattr(graph, "post", NoGraph())
    monkeypatch.setattr(graph, "get", NoGraph())
    monkeypatch.setattr(graph, "delete", NoGraph())
    monkeypatch.setattr(graph, "sleep", lambda seconds: None)
    monkeypatch.setattr(media, "MEDIA_DIR", tmp_path / "voice_media")
    monkeypatch.setattr(posts, "kick", lambda: None)  # 게시 작업은 시험에서 /v1/dev/run 으로 돌린다
    monkeypatch.setattr(settings, "poster_image_engine", "mock")  # Codex 로 그리지 않는다
    monkeypatch.setattr(story_event, "spawn", lambda target, *args: target(*args))  # 이벤트 포스터를 뒤에서 그리지 않고 바로
    monkeypatch.setattr(notebook, "spawn", lambda target, *args: target(*args))  # 수첩 규칙 판정을 뒤에서 하지 않고 바로
    monkeypatch.setattr(revise_jobs, "spawn", lambda target, *args: target(*args))  # 고쳐 쓰기를 뒤에서 하지 않고 바로 (감사팀 9장)
    cache.clear()
    tts._cache.clear()  # 합성해 둔 목소리 (시험마다 새로)
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


@pytest.fixture
def ig_on(monkeypatch):
    """인스타를 켠다 (토큰과 IG 사용자 id). 돌려준 함수에 FakeGraph 를 넣으면 graph.post / graph.get 으로 쓴다."""
    monkeypatch.setattr(settings, "instagram_access_token", "test-token")
    monkeypatch.setattr(settings, "instagram_user_id", "17841400000000000")

    def use(fake: FakeGraph) -> FakeGraph:
        monkeypatch.setattr(graph, "post", fake.post)
        monkeypatch.setattr(graph, "get", fake.get)
        monkeypatch.setattr(graph, "delete", fake.delete)
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
        """예전 '아쉬운 리뷰에 바로 답하기' 자리: True 면 부정 리뷰 답글 대리(묻지 않고 올림), 아니면 인턴 (인사과 4-a)."""
        rank = "assistant" if value is True else "intern"
        return self.client.post("/v1/dev/hr", json={"store_id": "s001", "ranks": {"negative_reply": rank}}).json()

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


def step_key(response: dict) -> str | None:
    return (response.get("briefing") or {}).get("step_key")


def walk_to(donna: "Donna", key: str, *, start: str = "오늘 일정 브리핑해 줘") -> dict:
    """브리핑을 처음부터 듣고 step_key 가 key 인 단계까지 간다 (v0.2.1 H: 요약 → "상세 브리핑을 시작할까요?" → 상세).
    상세 브리핑 물음에는 "응", 그 밖에 묻는 단계는 대답하지 않고 넘긴다 (앱의 auto_next). 그 단계가 없으면 끝(end) 응답을 돌려준다."""
    response = donna.turn(start)
    for _ in range(20):
        if step_key(response) == key or response["type"] == "end":
            return response
        response = donna.turn("응") if step_key(response) == "detail_ask" else donna.turn(event="auto_next")
    raise AssertionError(f"{key} 단계에 닿지 못했어요")


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
        """예전 '아쉬운 리뷰에 바로 답하기' 자리: True 면 부정 리뷰 답글 대리(묻지 않고 올림), 아니면 인턴 (인사과 4-a)."""
        rank = "assistant" if value is True else "intern"
        return self.client.post("/v1/dev/hr", json={"store_id": "s005", "ranks": {"negative_reply": rank}}).json()

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


# 2026-11-20 에이전트 조직 개편으로 더한 사원 (VOICE_AGENT_<이름>). 예전 에이전트만 가짜 CLOVA 로 보는 시험은 이들을 끈다
NEW_AGENTS = ("FIXCARD", "FIELD", "SAME", "MANUAL", "TOPIC", "CAPTION", "HOLIDAY", "NOTEBOOK")


def new_agents_off(monkeypatch) -> None:
    for name in NEW_AGENTS:
        monkeypatch.setenv(f"VOICE_AGENT_{name}", "false")


def no_morning_tasks(store_id: str = "s005") -> None:
    """밤사이 리뷰에서 나온 오늘 알바생 할 일 제안을 사장님이 '안 해'라고 한 것으로 둔다. 그대로 두면 그날 처음 "도나야"로 부르는 말
    앞에 도나가 놓친 할 일부터 묻는다 (jobs/staff_tasks.py, 2026-11-20). 할 일 묻기를 보는 시험은 keep_tasks=True 로 남겨 둔다."""
    from voice import clock, proposals
    from voice.jobs import briefing

    for found in proposals.for_briefing(store_id, clock.now().date().isoformat()):
        proposals.decline(found["id"], "test")
    briefing.refresh_steps(store_id)


def choongjang(*, permission=None, at: str | None = "2026-11-17T15:35:00+09:00", keep_tasks: bool = False) -> Choongjang:
    """초옹장 픽스처(11/17 09:02, 브리핑 준비) → (permission=True 면 부정 리뷰 답글 대리, 아니면 픽스처대로 인턴) → (at) 시계를 옮기고 하린이 가입한 뒤 할 일 화면을 연다 (출근).
    at=None 이면 하린은 아직 안 들어온 상태 그대로다 (2026-11-18 픽스처: 시연에서 초대한다)."""
    donna = Choongjang()
    assert donna.client.post("/v1/dev/fixtures", json={"fixture": "s005_choongjang"}).json()["store_id"] == "s005"
    if permission is not None:
        donna.settings(permission)
    if not keep_tasks:
        no_morning_tasks()
    if at:
        donna.clock(at)
        donna.join("하린")
        donna.staff_today("st_harin")
        donna.notices()  # 그때까지 쌓인 알림은 비운다
    return donna


def hr_log(store_id: str = "s005") -> list[tuple[str, str]]:
    """인사과에 남은 반응 (업무, 반응) 순서대로 (voice/hr.py, 9장 3단계). 시나리오 파일의 지난 기록(hist_)은 뺀다."""
    from voice import hr

    return [(e["job"], e["reaction"]) for e in hr.events(store_id) if not e["ref"].startswith("hist_")]
