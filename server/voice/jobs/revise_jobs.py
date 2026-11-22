"""뒤에서 고치고 알리기 (감사팀 계획 9장, 결정 10).

사장님이 말로 고쳐 달라고 하면("좀 더 부드럽게") 고쳐 쓰기(LLM)와 감사를 대화 요청 안에서 기다리지 않는다. 앱이 /v1/turn 을 5초에
끊기 때문이다 (known-bugs B9). 바로 "고쳐서 알려 드릴게요"라고 답하고, 뒤에서 고친 뒤 알림(revise_ready)으로 다시 묻는다.

  start(...)   작업을 만들고 뒤에서 돌린다. 같은 대상에 도는 작업이 있으면 취소하고, 앞 지시를 이어 붙인다
  cancel(...)  사장님이 고치는 동안 "응"·"안 해"로 정했다. 늦게 끝난 결과는 버린다
  expire(...)  날이 바뀐 뒤 남은 작업 (다음 브리핑 준비 때)
작업 하나 = work(job) 를 뒤에서 부르고, 돌려받은 apply() 를 저장소 락 안에서 부른다. apply 는 그때 상태를 다시 읽어
"ready"(고침) | "failed"(못 고침) | "discard"(그 사이 처리됨) 를 돌려준다. 버리지 않았으면 알림을 보낸다 (target post 는 알리지 않는다).

저장 (voice.db docs, 종류 revise_job, 계획 10-1)
  {id: rv_<가게>_<번호>, store_id, target: alert | batch | instagram | post, ref, job, instruction, items, mode,
   state: running | ready | failed | canceled | expired, notice_id, created_at, done_at}
target: alert(영업 중 아쉬운 리뷰 알림), batch(묶어 묻기의 답글들), instagram(오늘 인스타 글), post(할 일을 빼고 승인한 부정 답글, 결정 15)
"""

import logging
import threading
from collections.abc import Callable

from voice import clock, notices, repo
from voice.clock import parse

logger = logging.getLogger(__name__)

KIND = "revise_job"
NOTICE = "revise_ready"
LIVE = {"running"}


def spawn(target, *args) -> None:
    """뒤에서 돌린다 (작업 큐는 30초마다 보므로 쓰지 않는다). 시험은 바로 부르도록 바꾼다."""
    threading.Thread(target=target, args=args, daemon=True).start()


def get(job_id: str) -> dict | None:
    return repo.get(KIND, job_id)


def _save(job: dict) -> dict:
    return repo.put(KIND, job["id"], job["store_id"], job)


def _running(store_id: str, target: str, ref: str | None = None) -> list[dict]:
    return [j for j in repo.all_of(KIND, store_id) if j["state"] in LIVE and j["target"] == target and ref in (None, j["ref"])]


def start(store_id: str, target: str, ref: str, job: str | None, instruction: str,
          work: Callable[[dict], Callable[[], str]], prepare: Callable[[dict], None] | None = None, **extra) -> dict:
    """작업을 만들고 뒤에서 돌린다. 같은 대상에 도는 작업은 취소하고 그 지시를 앞에 이어 붙인다 (9-3).
    prepare(job) 은 뒤에서 돌리기 전에 부른다 (대상에 작업 id 를 적어 둘 때)."""
    with repo.lock():
        before = _running(store_id, target, ref)
        for old in before:
            _save({**old, "state": "canceled", "done_at": clock.iso(clock.now())})
        joined = ", ".join([*(old["instruction"] for old in before), instruction])
        jid = f"rv_{store_id}_{repo.next_number(f'revise_job:{store_id}'):04d}"
        created = _save({"id": jid, "store_id": store_id, "target": target, "ref": ref, "job": job, "instruction": joined,
                         "state": "running", "notice_id": None, "created_at": clock.iso(clock.now()), "done_at": None, **extra})
    if prepare:
        prepare(created)
    spawn(_run, jid, work)
    return created


def _run(job_id: str, work: Callable[[dict], Callable[[], str]]) -> None:
    job = get(job_id)
    if job is None or job["state"] not in LIVE:  # 돌기 전에 취소됐다 (또 고쳐 달라고 함 등)
        return
    try:
        apply = work(job)
    except Exception:  # 고쳐 쓰다 터져도 사장님께는 못 고쳤다고 알린다
        logger.exception("뒤에서 고치기 실패 %s", job_id)
        apply = lambda: "failed"  # noqa: E731
    finish(job_id, apply)


def finish(job_id: str, apply: Callable[[], str]) -> dict | None:
    """결과를 넣는다. 그 사이 취소·만료됐거나 대상이 처리됐으면 버린다."""
    with repo.lock():
        job = get(job_id)
        if job is None or job["state"] not in LIVE:
            return None
        outcome = apply()
        state = "canceled" if outcome == "discard" else outcome
        job = _save({**job, "state": state, "done_at": clock.iso(clock.now())})
    if state == "canceled" or job["target"] == "post":
        return job
    text = "고친 글을 확인해 주세요" if state == "ready" else "글을 고치지 못했어요"
    notice = notices.push(job["store_id"], NOTICE, text, opens_turn=True, alert_id=job["id"])
    return _save({**job, "notice_id": notice["id"]})


def cancel(store_id: str, target: str, ref: str | None = None) -> int:
    """도는 작업을 취소한다 (ref 를 비우면 그 대상의 작업 모두). 취소한 수."""
    with repo.lock():
        found = _running(store_id, target, ref)
        for job in found:
            _save({**job, "state": "canceled", "done_at": clock.iso(clock.now())})
    return len(found)


def expire(store_id: str) -> int:
    """오늘 전에 시작해 아직 도는 작업을 만료로 (브리핑 준비 때)."""
    today = clock.now().date()
    with repo.lock():
        found = [j for j in repo.all_of(KIND, store_id) if j["state"] in LIVE and parse(j["created_at"]).date() < today]
        for job in found:
            _save({**job, "state": "expired", "done_at": clock.iso(clock.now())})
    return len(found)
