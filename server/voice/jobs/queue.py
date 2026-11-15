"""작업 큐: 정해진 시각에 할 일 (문서 11장 '하루의 흐름').

  prepare_briefing  출근 한 시간 전 (open_time - 60분). 끝나면 다음 영업일 것을 다시 넣는다. 쉬는 요일은 건너뛴다
  auto_reply        아쉬운 리뷰가 들어오고 10분 뒤 (허락은 돌 때 다시 본다)
  post_scheduled    예약한 답글을 올릴 시각

run_due(지금까지) 는 예정 시각이 지난 작업을 시각 순서로 돌린다. 작업은 clock.at(예정 시각) 안에서 돌아서,
dev/clock 으로 시계를 한꺼번에 옮겨도 그 작업이 원래 돌았어야 할 시각에 돈 것으로 적힌다.
서버에서는 main.py 의 스레드가 30초마다 부른다.
"""

import datetime as dt
import logging
import threading

from app.core.seoul_time import at_time
from voice import clock, config, repo
from voice.clock import iso, parse

logger = logging.getLogger(__name__)
_running = threading.Lock()


def add(store_id: str, kind: str, due_at: dt.datetime, payload: dict | None = None) -> dict:
    job_id = f"{store_id}:{kind}:{iso(due_at)}:{(payload or {}).get('review_id', '')}"
    existing = repo.get("job", job_id)
    if existing:
        return existing
    return repo.put("job", job_id, store_id, {"id": job_id, "store_id": store_id, "kind": kind, "due_at": iso(due_at),
                                              "payload": payload or {}, "done": False})


def next_prepare_at(store: dict, after: dt.datetime) -> dt.datetime:
    """after 보다 뒤의 첫 브리핑 준비 시각 (쉬는 요일 건너뜀)."""
    closed = set(store.get("closed_weekdays") or [])
    for n in range(0, 8):
        day = after.date() + dt.timedelta(days=n)
        moment = at_time(day, store["open_time"]) - config.PREPARE_BEFORE_OPEN
        if moment > after and day.weekday() not in closed:
            return moment
    raise ValueError("일주일 내내 쉬는 가게예요")


def schedule_prepare(store_id: str, after: dt.datetime | None = None) -> dict | None:
    store = repo.store(store_id)
    if store is None:
        return None
    return add(store_id, "prepare_briefing", next_prepare_at(store, after or clock.now()))


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
