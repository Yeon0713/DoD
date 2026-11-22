"""요청 모양 (문서 4장, 9장). 응답은 dict 로 만들어 돌려준다 (모양은 jobs/briefing.py, dialog/turn.py)."""

from typing import Literal

from pydantic import BaseModel, Field


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
    event: Literal["auto_next", "notice", "night_hr", "called"] | None = None  # called: "도나야"만 불렀다  # notice: 사장님 앱이 도나 알림(negative_review)을 열었다
    notice_id: str | None = None
    context: TurnContext = TurnContext()


class BriefingNotifyPatch(BaseModel):
    on: bool | None = None
    time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")  # null 이면 기본(문 열기 1시간 전)


class DayHours(BaseModel):
    closed: bool = False
    open: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    close: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class HoursPatch(BaseModel):
    days: list[DayHours] = Field(min_length=7, max_length=7)  # 월요일부터


class SettingsPatch(BaseModel):
    """보낸 것만 바꾼다. negative_review_auto_reply 는 없앴다(인사과 4-a). 앱이 바뀔 때까지 와도 무시한다."""

    store_id: str
    negative_review_auto_reply: bool | None = None
    briefing_notify: BriefingNotifyPatch | None = None
    hours: HoursPatch | None = None
    # 아쉬운 리뷰 답글에 붙일 사장님이 정한 보상 한 문장 (불만 종류 packaging, missing, taste_temp, hall_service). null 은 지움
    compensation: dict[str, str | None] | None = None
    # 비 오는 날 스토리 이벤트 (instagram/story_event.py): headline, offer(손님 혜택 한 문장), staff_task(알바생 할 일). null 은 지움
    story_event: dict[str, str | None] | None = None


class ReviewIn(BaseModel):
    store_id: str
    platform: str = "baemin"
    rating: int
    text: str
    written_at: str | None = None  # 비우면 지금 (백엔드 시계)
    order_channel: Literal["delivery", "hall"] = "delivery"
    menus: list[str] = []  # 손님이 주문한 메뉴 (배달 앱 리뷰에 보이는 것)


class DemoReviewIn(BaseModel):
    store_id: str
    name: str  # 픽스처 demo_reviews 의 이름 (leak, missing, cold, hall)
    written_at: str | None = None


class ClockIn(BaseModel):
    now: str | None = None  # 비우면 실제 시계로 돌아간다


class RunIn(BaseModel):
    store_id: str
    job: Literal["collect", "label_reviews", "auto_reply", "prepare_briefing", "post_scheduled", "instagram_publish"]


class StoryEventIn(BaseModel):
    store_id: str


class InstagramConnectIn(BaseModel):
    store_id: str | None = None  # 앱은 {} 로 부른다. 비우면 시연 가게


class InstagramPostIn(BaseModel):
    store_id: str
    kind: Literal["feed", "story"]
    post_at: str | None = None  # 비우면 지금 올린다
