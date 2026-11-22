"""도나 알림 (GET /v1/notices). 사장님 앱이 홈에서 몇 초마다 읽는다. 한 번 읽은 알림은 다시 주지 않는다.

2026-11-18 (팀 개선안, donna-voice/docs/test-scenarios-closed-loop.md): 영업 중에 온 아쉬운 리뷰는 도나가 먼저 알린다.
  negative_review  아쉬운 리뷰가 왔어요. opens_turn: 앱이 소리를 내고 turn(event: notice)로 열어 도나가 묻는다
  staff_checked    알바생이 교정 카드를 확인했어요 (say 를 읽는다)
  reply_fallback   대답이 없어 사과 답글만 먼저 올렸어요 / 초안으로 남겼어요 (say 를 읽는다)
  staff_joined     알바생이 알바생 화면에 들어왔어요 (소리만)
  story_event      비 오는 날 이벤트 포스터를 다 그렸어요 (opens_turn, alert_id = 이벤트 id) / 못 그렸어요·올렸어요 (say 를 읽는다)
  revise_ready     뒤에서 고친 글을 다시 물어요 (opens_turn, alert_id = 고쳐 쓰기 작업 id, jobs/revise_jobs.py)
끝난 고리의 negative_review, 25분이 지난 negative_review 는 읽을 때 버린다 (시계를 한꺼번에 옮겨도 지난 알림이 몰려 울리지 않게).
"""

import datetime as dt

from voice import clock, config, repo, speech
from voice.clock import iso, parse

OPEN_STATES = {"alerted", "reminded", "auto_posted"}


def push(store_id: str, kind: str, text: str, *, say: list[str] | None = None, opens_turn: bool = False,
         alert_id: str | None = None) -> dict:
    from voice.dialog import echo

    echo.remember(store_id, [*(say or []), text])  # 앱이 소리 내어 읽는다. 마이크로 다시 들어오면 흘려듣게
    notice_id = f"nt_{store_id}_{repo.next_number(f'notice:{store_id}'):04d}"  # repo 키는 가게를 가리지 않으므로 가게 id 를 넣는다
    return repo.put("notice", notice_id, store_id, {
        "id": notice_id, "kind": kind, "text": text, "say": say or [], "opens_turn": opens_turn,
        "alert_id": alert_id, "at": iso(clock.now()), "seen": False,
    })


def _alive(notice: dict, now: dt.datetime) -> bool:
    if notice["kind"] == "story_event" and notice["opens_turn"]:  # 이미 대답한 포스터는 다시 묻지 않는다
        event = repo.get("story_event", notice["alert_id"]) if notice.get("alert_id") else None
        return bool(event) and event["state"] == "ready"
    if notice["kind"] == "revise_ready":  # 고치는 사이 사장님이 정했거나 날이 바뀌었으면 묻지 않는다
        job = repo.get("revise_job", notice["alert_id"]) if notice.get("alert_id") else None
        return bool(job) and job["state"] in ("ready", "failed")
    if notice["kind"] not in ("negative_review", "negative_auto") or not notice["opens_turn"]:
        return True
    alert = repo.get("alert", notice["alert_id"]) if notice.get("alert_id") else None
    return bool(alert) and alert["state"] in OPEN_STATES and now - parse(notice["at"]) <= config.ALERT_FALLBACK_AFTER


def view(notice: dict) -> dict:
    return {"id": notice["id"], "kind": notice["kind"], "text": notice["text"], "time_label": speech.clock_label(parse(notice["at"])),
            "say": notice["say"], "opens_turn": notice["opens_turn"], "alert_id": notice.get("alert_id")}


def unseen(store_id: str) -> list[dict]:
    """아직 안 읽은 알림 (오래된 것부터). 읽은 것으로 적는다."""
    now = clock.now()
    fresh = []
    for notice in sorted(repo.all_of("notice", store_id), key=lambda n: n["id"]):
        if notice["seen"] or parse(notice["at"]) > now:
            continue
        repo.put("notice", notice["id"], store_id, {**notice, "seen": True})
        if _alive(notice, now):
            fresh.append(view(notice))
    # 같은 리뷰 알림이 둘(처음 알림, 다시 알림)이면 마지막 것만
    last = {n["alert_id"]: n["id"] for n in fresh if n["kind"] == "negative_review"}
    return [n for n in fresh if n["kind"] != "negative_review" or last[n["alert_id"]] == n["id"]]
