"""음성 백엔드 데이터를 Harness 실행 맥락(RunContext)으로 잇는다.

Harness 는 ctx.snapshot 에서 store_id 와 store(name, category)만 쓴다 (Harness.spec.StoreView).
에이전트 도구는 VoiceStore 의 data(그 가게의 저장소 내용)를 읽는다. 도구가 가게를 ctx 로만 알아서 다른 가게를 볼 수 없다.
"""

import datetime as dt
from dataclasses import dataclass

import httpx

from app.core.clova import Post
from Harness.spec import RunContext
from voice import clock, config, repo, weather

post: Post = httpx.post  # 테스트에서 가짜를 넣는다


@dataclass
class VoiceStore:
    store_id: str
    store: dict
    data: dict[str, list[dict]]  # repo.kinds_of(store_id)
    now: dt.datetime

    def reviews(self) -> list[dict]:
        """지금까지 쓰인 리뷰. 시계를 옮겨 가며 시험할 때 '아직 안 쓰인' 목업 리뷰를 보지 않게 한다."""
        return [r for r in self.data.get("review", []) if clock.parse(r["written_at"]) <= self.now]

    def review(self, review_id: str | None) -> dict | None:
        return next((r for r in self.reviews() if r["id"] == review_id), None)

    @property
    def menus(self) -> list[dict]:
        return self.store.get("menus") or []


def load(store_id: str) -> VoiceStore | None:
    store = repo.store(store_id)
    if store is None:
        return None
    data = repo.kinds_of(store_id)
    if store_id != config.DEMO_STORE_ID:  # 시연 가게는 시계를 고정한 시나리오 날씨를 그대로 쓴다
        found = weather.from_db(store_id)  # 메인 서버가 매일 자정에 받아 둔 기상청 날씨 (voice/weather.py)
        if found:
            data["weather"] = found
    return VoiceStore(store_id, store, data, clock.now())


def run_context(view: VoiceStore, now: dt.datetime | None = None) -> RunContext:
    return RunContext(snapshot=view, now=now or clock.now(), post=post, store_facts=list(view.store.get("facts") or []))
