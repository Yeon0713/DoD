"""그날 한 일 기록 (일정 탭의 done[], 문서 16-2).

도나가 한 일(리뷰 읽기, 답글 예약·올리기)과 사장님이 한 일(브리핑 듣기, 허락)을 한 줄씩 남긴다.
같은 key 는 한 번만 적는다 (브리핑을 두 번 끝까지 들어도 한 줄).
"""

import datetime as dt

from voice import clock, repo
from voice.clock import iso, parse


def log(store_id: str, actor: str, text: str, key: str, at: dt.datetime | None = None) -> dict:
    moment = at or clock.now()
    doc_id = f"{store_id}:{moment.date().isoformat()}:{key}"
    existing = repo.get("activity", doc_id)
    if existing:
        return existing
    return repo.put("activity", doc_id, store_id, {"id": doc_id, "actor": actor, "text": text, "at": iso(moment)})


def on(store_id: str, day: dt.date) -> list[dict]:
    items = [a for a in repo.all_of("activity", store_id) if parse(a["at"]).date() == day and parse(a["at"]) <= clock.now()]
    return sorted(items, key=lambda a: a["at"])


def between(store_id: str, start: dt.date, end: dt.date) -> list[dict]:
    return [a for a in repo.all_of("activity", store_id) if start <= parse(a["at"]).date() <= end]
