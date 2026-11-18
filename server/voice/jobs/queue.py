"""작업 큐: 정해진 시각에 할 일 (문서 11장 '하루의 흐름').

  prepare_briefing  출근 한 시간 전 (open_time - 60분). 끝나면 다음 영업일 것을 다시 넣는다. 쉬는 요일은 건너뛴다
  auto_reply        아쉬운 리뷰가 들어오고 10분 뒤 (허락은 돌 때 다시 본다)
  post_scheduled    예약한 답글을 올릴 시각
  review_alert      영업 중 아쉬운 리뷰: 바로 알림 / review_remind 15분 뒤 다시 알림 / review_fallback 25분 대답 없음 처리
  instagram_publish 인스타 게시물을 올릴 시각 (지금 올릴 것은 instagram/posts.kick 이 바로 돌린다)

run_due(지금까지) 는 예정 시각이 지난 작업을 시각 순서로 돌린다. 작업은 clock.at(예정 시각) 안에서 돌아서,
dev/clock 으로 시계를 한꺼번에 옮겨도 그 작업이 원래 돌았어야 할 시각에 돈 것으로 적힌다.
서버에서는 main.py 의 스레드가 30초마다 부른다.
"""

import datetime as dt
import logging
import threading

from app.core.seoul_time import at_time
from voice import clock, config, hours, repo
from voice.clock import iso, parse

logger = logging.getLogger(__name__)
_running = threading.Lock()


def add(store_id: str, kind: str, due_at: dt.datetime, payload: dict | None = None) -> dict:
    payload = payload or {}
    job_id = f"{store_id}:{kind}:{iso(due_at)}:{payload.get('review_id') or payload.get('post_id') or ''}"
    existing = repo.get("job", job_id)
    if existing:
        return existing
    return repo.put("job", job_id, store_id, {"id": job_id, "store_id": store_id, "kind": kind, "due_at": iso(due_at),
                                              "payload": payload or {}, "done": False})


def next_prepare_at(store: dict, after: dt.datetime, settings: dict | None = None) -> dt.datetime:
    """after 보다 뒤의 첫 브리핑 준비 시각 (쉬는 요일 건너뜀). 그날 여는 시각 1시간 전, 사장님이 고른 알림 시각이
    그보다 이르면 알림 시각 (알림을 받고 부르면 이미 준비돼 있게)."""
    for n in range(0, 8):
        day = after.date() + dt.timedelta(days=n)
        today = hours.on(store, day)
        if today is None:
            continue
        moment = at_time(day, today["open"]) - config.PREPARE_BEFORE_OPEN
        notify = hours.notify_time(store, settings or {}, day)
        if notify:
            moment = min(moment, at_time(day, notify))
        if moment > after:
            return moment
    raise ValueError("일주일 내내 쉬는 가게예요")


def schedule_prepare(store_id: str, after: dt.datetime | None = None) -> dict | None:
    store = repo.store(store_id)
    if store is None:
        return None
    return add(store_id, "prepare_briefing", next_prepare_at(store, after or clock.now(), repo.settings(store_id)))


def reschedule_prepare(store_id: str) -> dict | None:
    """장사 시간이나 알림 시각이 바뀌면, 아직 돌지 않은 준비 작업을 빼고 새 시각으로 다시 넣는다."""
    now = clock.now()
    for job in repo.all_of("job", store_id):
        if job["kind"] == "prepare_briefing" and not job["done"] and parse(job["due_at"]) > now:
            repo.put("job", job["id"], store_id, {**job, "done": True, "skipped": True})
    return schedule_prepare(store_id, after=now)


def _pending(until: dt.datetime) -> list[dict]:
    jobs = []
    for store_id in repo.store_ids():
        jobs += [j for j in repo.all_of("job", store_id) if not j["done"] and parse(j["due_at"]) <= until]
    return sorted(jobs, key=lambda j: j["due_at"])


def run_job(job: dict) -> object:
    from voice.jobs import auto_reply, briefing

    store_id = job["store_id"]
    if job["kind"] == "prepare_briefing":
        result = briefing.prepare(store_id)
        schedule_prepare(store_id, after=clock.now())
        return result is not None
    if job["kind"] == "auto_reply":
        reviewed = auto_reply.reply_now(store_id, job["payload"]["review_id"])
        if reviewed and briefing.current(store_id):  # 준비한 뒤 새 일이 생기면 브리핑을 다시 만든다
            briefing.prepare(store_id)
        return reviewed is not None
    if job["kind"] == "post_scheduled":
        return auto_reply.post_scheduled(store_id)
    if job["kind"] in ("review_alert", "review_remind", "review_fallback"):  # 영업 중 아쉬운 리뷰 (jobs/review_loop.py)
        from voice.jobs import review_loop

        step = {"review_alert": review_loop.alert, "review_remind": review_loop.remind, "review_fallback": review_loop.fallback}[job["kind"]]
        return step(store_id, job["payload"]["review_id"]) is not None
    if job["kind"] == "instagram_publish":
        from voice.instagram import posts

        published = posts.publish(store_id, job["payload"]["post_id"])
        return bool(published and published["status"] == "published")
    raise ValueError(f"모르는 작업: {job['kind']}")


def run_due(until: dt.datetime | None = None) -> list[str]:
    """예정 시각이 지난 작업을 모두 돌린다. 돈 작업 id 목록."""
    until = until or clock.now()
    done: list[str] = []
    with _running:
        for _ in range(1000):  # 작업이 작업을 더하므로 다시 본다
            pending = _pending(until)
            if not pending:
                break
            job = pending[0]
            with clock.at(parse(job["due_at"])):
                try:
                    run_job(job)
                except Exception:  # 작업 하나가 실패해도 큐는 계속 돈다
                    logger.exception("작업 실패 %s", job["id"])
            job["done"] = True
            repo.put("job", job["id"], job["store_id"], job)
            done.append(job["id"])
    return done
