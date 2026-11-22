"""감사 기록 (voice/audit/log.py): 번호, final 표시, 보류, 하루 요약, 개발자 API."""

import datetime as dt

from voice import clock
from voice.audit import log
from voice.tests.conftest import Donna

DAY = dt.datetime(2026, 11, 22, 6, 0, tzinfo=clock.SEOUL)


def _audit(*steps):
    return {"passed": steps[-1][0] == "pass" if steps[-1][0] != "unchecked" else None, "rounds": len(steps) - 1,
            "trail": [{"round": n, "status": s, "criterion": c, "reason": None, "quotes": [], "calls": 2, "ms": 100 * (n + 1)}
                      for n, (s, c) in enumerate(steps)]}


def test_trail_numbers_and_final():
    with clock.at(DAY):
        rows = log.record_trail("s1", "negative_reply", "voice_reply", "rv_1", _audit(("fail", "card_promise"), ("pass", None)))
    assert [r["id"] for r in rows] == ["au_s1_0001", "au_s1_0002"]
    assert [r["final"] for r in rows] == [False, True] and [r["round"] for r in rows] == [0, 1]


def test_no_trail_no_rows():
    assert log.record_trail("s1", "negative_reply", "voice_reply", "rv_1", None) == []
    assert log.record_trail("s1", "negative_reply", "voice_reply", "rv_1", {"passed": True, "trail": []}) == []


def test_day_summary_counts():
    with clock.at(DAY):
        log.record_trail("s1", "negative_reply", "voice_reply", "rv_1", _audit(("pass", None)))
        log.record_trail("s1", "negative_reply", "voice_reply", "rv_2", _audit(("fail", "card_promise"), ("pass", None)))
        log.record_trail("s1", "negative_reply", "voice_reply", "rv_3",
                         _audit(("fail", "BLAME"), ("fail", "BLAME"), ("fail", "card_promise")))
        log.record_trail("s1", "negative_reply", "voice_reply", "rv_4", _audit(("unchecked", None)))
        log.mark_hold("s1", "rv_3")
    with clock.at(DAY + dt.timedelta(days=1)):
        log.record_trail("s1", "negative_reply", "voice_reply", "rv_5", _audit(("pass", None)))
    found = log.day_summary("s1", DAY.date())
    [job] = found["jobs"]
    assert (job["results"], job["first_pass"], job["pass_after_return"], job["final_fail"], job["hold"], job["unchecked"]) == (4, 1, 1, 1, 1, 1)
    assert job["fail_by_criterion"] == {"card_promise": 2, "BLAME": 2}
    assert job["calls"] == 14 and job["max_ms"] == 300


def test_dev_api_returns_summary():
    donna = Donna()
    donna.clock("2026-11-17T09:00:00+09:00")
    donna.fixtures()
    body = donna.client.get("/v1/dev/audit", params={"store_id": "s001"}).json()
    assert body["day"] == "2026-11-17" and body["jobs"] == []
    assert donna.client.get("/v1/dev/audit", params={"store_id": "nope"}).status_code == 404
