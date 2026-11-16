"""요청 모양 (문서 4장, 9장). 응답은 dict 로 만들어 돌려준다 (모양은 jobs/briefing.py, dialog/turn.py)."""

from typing import Literal

from pydantic import BaseModel


class Utterance(BaseModel):
    text: str
    confidence: float = 1.0
    source: Literal["voice"] = "voice"  # v0.2.1 부터 칩이 없다
    addressed: bool = False  # "도나야"로 불러서 한 말 (부르는 말은 앱이 떼고 보낸다). 가게 말로 넘기지 않는다
    started_at: str | None = None
    ended_at: str | None = None


class HeardUntil(BaseModel):
    turn_id: str
    say_index: int


class TurnContext(BaseModel):
    last_turn_id: str | None = None
    donna_was_speaking: bool = False
    heard_until: HeardUntil | None = None


class TurnRequest(BaseModel):
    request_id: str
    store_id: str
    session_id: str | None = None
    client_time: str | None = None
    utterance: Utterance | None = None
    event: Literal["auto_next"] | None = None
    context: TurnContext = TurnContext()


class SettingsPatch(BaseModel):
    store_id: str
    negative_review_auto_reply: bool | None


class ReviewIn(BaseModel):
    store_id: str
    platform: str = "baemin"
    rating: int
    text: str
    written_at: str
    order_channel: Literal["delivery", "hall"] = "delivery"


class ClockIn(BaseModel):
    now: str | None = None  # 비우면 실제 시계로 돌아간다


class RunIn(BaseModel):
    store_id: str
    job: Literal["collect", "label_reviews", "auto_reply", "prepare_briefing", "post_scheduled"]
