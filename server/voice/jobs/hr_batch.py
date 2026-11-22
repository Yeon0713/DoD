"""사원 업무의 영업 중 묶음 창 (인사과 9-0 a, donna-voice/docs/agent-structure.md 9장 4-c).

영업 중에 사원 업무(부정 리뷰 답글, 리뷰 교정 할 일)가 생기면 바로 알리지 않고 모은다. 첫 건이 생기고 HR_BATCH_WINDOW(30분,
문 닫기 전이면 그 전) 뒤에 알림 한 번(notice hr_batch, opens_turn)으로 보내고, 사장님이 알림을 열면 jobs/batch_ask 로 묶어 묻는다.
대답이 없으면 다음 아침 브리핑에서 묻는다 (답글은 아쉬운 리뷰 단계, 할 일은 알바생 할 일 단계).

저장: repo 종류 hr_batch, id hb_<가게>_<번호> {id, store_id, items: [{job, ref}], due_at, sent_at, created_at}
"""

import datetime as dt

from voice import clock, config, hours, notices, repo, speech
from voice.clock import iso
from voice.context import VoiceStore
from voice.jobs import batch_ask, queue

KIND = "hr_batch"


def _open_window(store_id: str) -> dict | None:
    return next((b for b in repo.all_of(KIND, store_id) if b["sent_at"] is None), None)


def _due(store: dict, now: dt.datetime) -> dt.datetime:
    due = now + config.HR_BATCH_WINDOW
    found = hours.business_day(store, now)  # 자정 넘김 가게의 새벽은 어제 영업
    if found:
        due = min(due, hours.close_at(*found))
    return due


def add(store_id: str, job: str, ref: str) -> dict:
    """묶음 창에 한 건을 넣는다. 열린 창이 없으면 새로 열고 보낼 때를 잡는다."""
    with repo.lock():
        found = _open_window(store_id)
        if found is None:
            now = clock.now()
            bid = f"hb_{store_id}_{repo.next_number(f'hr_batch:{store_id}'):04d}"  # repo 키는 가게를 가리지 않는다
            due = _due(repo.store(store_id), now)
            found = {"id": bid, "store_id": store_id, "items": [], "due_at": iso(due), "sent_at": None, "created_at": iso(now)}
            queue.add(store_id, KIND, due, {"batch_id": bid})
        item = {"job": job, "ref": ref}
        if item not in found["items"]:
            found = {**found, "items": found["items"] + [item]}
        return repo.put(KIND, found["id"], store_id, found)


def send(store_id: str, batch_id: str) -> dict | None:
    """작업 hr_batch: 창을 닫고, 아직 정하지 않은 것이 있으면 알림 한 번으로 보낸다."""
    from voice.context import load

    with repo.lock():
        found = repo.get(KIND, batch_id)
        if found is None or found["sent_at"]:
            return None
        found = repo.put(KIND, batch_id, store_id, {**found, "sent_at": iso(clock.now())})
    view = load(store_id)
    live = batch_ask._live(view, found["items"]) if view else []
    if not live:
        return None
    return notices.push(store_id, KIND, f"확인할 것이 {speech.count(len(live), '개')} 있어요", opens_turn=True, alert_id=batch_id)


def ask(view: VoiceStore, batch_id: str) -> dict | None:
    """알림을 연 뒤: 그 창에 모인 것 중 아직 정하지 않은 것을 묶어 묻는다."""
    found = repo.get(KIND, batch_id)
    return batch_ask.ask(view, found["items"], "batch") if found else None

