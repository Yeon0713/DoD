"""작업 큐: 정해진 시각에 할 일 (문서 11장 '하루의 흐름').

  prepare_briefing  출근 한 시간 전 (open_time - 60분). 끝나면 다음 영업일 것을 다시 넣는다. 쉬는 요일은 건너뛴다
  auto_reply        아쉬운 리뷰가 들어오고 10분 뒤 (허락은 돌 때 다시 본다)
  post_scheduled    예약한 답글을 올릴 시각
  review_alert      영업 중 아쉬운 리뷰: 바로 알림 / review_remind 15분 뒤 다시 알림 / review_fallback 25분 대답 없음 처리
                    (review_fix_carry 는 예전 자동 답글 뒤 할 일 질문. 이미 잡힌 작업만 돈다)
  hr_batch          사원 업무의 영업 중 묶음 창: 첫 건 30분 뒤 알림 한 번 (jobs/hr_batch.py)
  instagram_publish 인스타 게시물을 올릴 시각 (지금 올릴 것은 instagram/posts.kick 이 바로 돌린다)
  refresh_briefing  오늘 브리핑이 있으면 다시 만든다 (알림 줄의 작업이 브리핑을 바꿔야 할 때 이 줄로 넘긴다)

run_due(지금까지) 는 예정 시각이 지난 작업을 시각 순서로 돌린다. 작업은 clock.at(예정 시각) 안에서 돌아서,
dev/clock 으로 시계를 한꺼번에 옮겨도 그 작업이 원래 돌았어야 할 시각에 돈 것으로 적힌다.
시계를 멈춰 둔 동안에는 fixtures 로 넣은 가게(가게 문서 fixture)의 작업만 돈다. 같은 서버에 앱으로 들어온 실제 가게가 있어도
가짜 시각으로 그 가게 리뷰에 답글을 쓰지 않는다 (2026-11-21, 시계를 옮기면 실제 가게 작업까지 돌아 5분 넘게 멈췄다).

줄(lane) 두 개
  alert  아쉬운 리뷰 알림(review_alert·remind·fallback), 사원 업무 묶음 창 알림(hr_batch). 30분 안에 알려야 해서, 브리핑 준비가
         답글을 쓰느라(LLM, 리뷰마다 수십 초) 오래 걸려도 기다리지 않는다
  slow   나머지 (브리핑 준비, 바로 답하기, 예약 답글, 인스타 게시, 브리핑 다시 만들기)
서버에서는 main.py 의 스레드가 줄마다 하나씩 30초마다 run_due(lane=…) 를 부른다.
lane 없이 부르면(dev/clock, 시험) 두 줄을 모두 잡고 모든 작업을 시각 순서대로 돌린다.

실패: 작업이 예외로 끝나면 끝난 것으로 적지 않고 RETRY_DELAYS 뒤에 다시 한다 (attempts, last_error).
그래도 실패하면 status: failed 로 끝내고 활동 기록에 남긴다. 성공하면 status: done.
"""

import contextlib
import datetime as dt
import logging
import threading

from app.core.seoul_time import at_time
from voice import activity, clock, config, hours, repo
from voice.clock import iso, parse

logger = logging.getLogger(__name__)

ALERT_KINDS = frozenset({"review_alert", "review_remind", "review_fallback", "hr_batch"})  # hr_batch: 사원 업무 묶음 창 알림 (인사과 4-c)
LANES = ("alert", "slow")  # 두 줄을 모두 잡을 때도 이 순서로 잡는다 (서로 기다리다 멈추지 않게)
RETRY_DELAYS = (dt.timedelta(minutes=1), dt.timedelta(minutes=5))  # 첫 실패 뒤 1분, 두 번째 실패 뒤 5분. 세 번째 실패면 끝
KIND_NAMES = {
    "prepare_briefing": "브리핑 준비", "auto_reply": "아쉬운 리뷰 바로 답하기", "post_scheduled": "예약한 답글 올리기",
    "review_alert": "아쉬운 리뷰 알림", "review_remind": "아쉬운 리뷰 다시 알림", "review_fallback": "아쉬운 리뷰 대답 없음 처리",
    "instagram_publish": "인스타 게시", "refresh_briefing": "브리핑 다시 만들기", "hr_batch": "묶어서 묻기 알림",
    "hr_night": "밤 9시 인사과 보고",
}
_locks = {lane: threading.Lock() for lane in LANES}


def lane_of(kind: str) -> str:
    return "alert" if kind in ALERT_KINDS else "slow"


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


def _pending(until: dt.datetime, lane: str | None = None) -> list[dict]:
    jobs = []
    for store_id in repo.store_ids():
        if clock.fixed() and not (repo.store(store_id) or {}).get("fixture"):
            continue  # 시계를 멈춘 동안(시연)은 fixtures 로 넣은 가게만. 앱으로 들어온 실제 가게는 실제 시각일 때만 돈다 (2026-11-21)
        jobs += [j for j in repo.all_of("job", store_id)
                 if not j["done"] and parse(j["due_at"]) <= until and (lane is None or lane_of(j["kind"]) == lane)]
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
    if job["kind"] in ("review_alert", "review_remind", "review_fallback", "review_fix_carry"):  # 영업 중 아쉬운 리뷰 (jobs/review_loop.py)
        from voice.jobs import review_loop

        step = {"review_alert": review_loop.alert, "review_remind": review_loop.remind, "review_fallback": review_loop.fallback,
                "review_fix_carry": review_loop.carry}[job["kind"]]
        return step(store_id, job["payload"]["review_id"]) is not None
    if job["kind"] == "hr_batch":  # 사원 업무의 영업 중 묶음 창 (jobs/hr_batch.py)
        from voice.jobs import hr_batch

        return hr_batch.send(store_id, job["payload"]["batch_id"]) is not None
    if job["kind"] == "instagram_publish":
        from voice.instagram import posts

        published = posts.publish(store_id, job["payload"]["post_id"])
        return bool(published and published["status"] == "published")
    if job["kind"] == "hr_night":  # 밤 9시 인사과 보고 알림 (jobs/hr_night.py)
        from voice.jobs import hr_night

        return hr_night.run(store_id)
    if job["kind"] == "refresh_briefing":
        return bool(briefing.current(store_id) and briefing.prepare(store_id))
    raise ValueError(f"모르는 작업: {job['kind']}")


def _run_one(job: dict) -> None:
    """작업 하나를 돌리고 결과를 적는다. 예외가 나도 큐는 계속 돈다 (다시 하거나 실패로 끝낸다)."""
    error = None
    with clock.at(parse(job["due_at"])):
        try:
            run_job(job)
        except Exception as exc:
            logger.exception("작업 실패 %s", job["id"])
            error = f"{type(exc).__name__}: {exc}"
    attempts = job.get("attempts", 0) + 1
    if error is None:
        job.update(done=True, status="done", attempts=attempts)
    elif attempts <= len(RETRY_DELAYS):
        job.update(attempts=attempts, last_error=error, due_at=iso(clock.now() + RETRY_DELAYS[attempts - 1]))
    else:
        job.update(done=True, status="failed", attempts=attempts, last_error=error)
        name = KIND_NAMES.get(job["kind"], job["kind"])
        activity.log(job["store_id"], "donna", f"{name} 작업을 {attempts}번 해 봤지만 끝내지 못했어요", f"job_failed:{job['id']}")
    repo.put("job", job["id"], job["store_id"], job)


def run_due(until: dt.datetime | None = None, lane: str | None = None) -> list[str]:
    """예정 시각이 지난 작업을 돌린다. lane 이 있으면 그 줄의 작업만, 없으면 모두. 돈 작업 id 목록 (다시 할 작업 포함)."""
    until = until or clock.now()
    done: list[str] = []
    with contextlib.ExitStack() as held:
        for name in LANES if lane is None else (lane,):
            held.enter_context(_locks[name])
        for _ in range(1000):  # 작업이 작업을 더하므로 다시 본다
            pending = _pending(until, lane)
            if not pending:
                break
            job = pending[0]
            _run_one(job)
            done.append(job["id"])
    return done
