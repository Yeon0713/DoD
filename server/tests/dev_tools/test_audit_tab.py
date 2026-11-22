"""개발자 대시보드 '감사' 탭 API: 음성 백엔드 감사 기록(voice.db 의 audit)을 가게·날마다 업무별로 센다 (감사팀 계획 12장)."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from voice import clock, repo
from voice import config as voice_config
from voice.audit import log as audit_log

DAY = dt.datetime(2026, 11, 22, 6, 0, tzinfo=clock.SEOUL)


@pytest.fixture(autouse=True)
def voice_db(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_config, "DB_PATH", tmp_path / "voice.db")


def trail(*statuses):
    return {"trail": [{"round": n, "status": s, "criterion": "card_promise" if s == "fail" else None, "reason": None, "quotes": [],
                       "calls": 1, "ms": 500} for n, s in enumerate(statuses)]}


def test_audit_tab_counts_per_job_and_picks_the_last_day():
    repo.put("store", "s005", "s005", {"id": "s005", "name": "초옹장"})
    with clock.at(DAY - dt.timedelta(days=1)):
        audit_log.record_trail("s005", "negative_reply", "voice_reply", "rv_0", trail("pass"), "r0")
    with clock.at(DAY):
        audit_log.record_trail("s005", "negative_reply", "voice_reply", "rv_1", trail("pass"), "r1")
        audit_log.record_trail("s005", "negative_reply", "voice_reply", "rv_2", trail("fail", "pass"), "r2")
        audit_log.record_trail("s005", "negative_reply", "voice_reply", "rv_3", trail("fail", "fail", "fail"), "r3")
        audit_log.mark_hold("s005", "rv_3")
    client = TestClient(create_app())
    body = client.get("/api/dev_tools/audit").json()
    assert body["store_id"] == "s005" and body["days"] == ["2026-11-22", "2026-11-21"] and body["day"] == "2026-11-22"
    [job] = body["jobs"]
    assert (job["results"], job["first_pass"], job["pass_after_return"], job["final_fail"], job["hold"]) == (3, 1, 1, 1, 1)
    assert job["fail_by_criterion"] == {"card_promise": 4} and len(body["rows"]) == 6
    older = client.get("/api/dev_tools/audit", params={"store_id": "s005", "day": "2026-11-21"}).json()
    assert older["jobs"][0]["results"] == 1


def test_audit_tab_without_voice_stores():
    body = TestClient(create_app()).get("/api/dev_tools/audit").json()
    assert body == {"stores": [], "store_id": None, "days": [], "day": None, "jobs": [], "rows": []}
