"""계획 엔진의 입력과 출력 데이터 모양, 그리고 화면과 주고받는 코드값 목록.

- 입력: 매장 설정, 리뷰와 분류 결과, 손님 주문 주기, 우리 매장 달력, 위험 신호, 매출 이상, 행사, 경기
- 출력: 할 일(PlanItem), 승인 없는 알림(NoticeItem), 알림 묶음(NotificationBatch)

필드 이름은 공통 문서의 C1, C2, C3 계약을 따른다. API 모듈(modules/)도 이 모양을 그대로 응답에 쓴다.
"""

import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

# ── 코드값 ── 영어 대문자로 주고받고, 화면 문구는 프론트가 한국어로 바꾼다.

Daypart = Literal["LUNCH", "DINNER", "NIGHT"]  # 점심, 저녁, 야간
Weekday = Literal["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
SlotName = Literal["OPENING", "AFTERNOON", "CLOSING"]  # 알림 가능 시간: 출근 후, 오후, 마감 전
TaskType = Literal["REVISIT_REPLY", "MENU_ORDER", "POSTER", "REVIEW_FIX", "REORDER_NUDGE"]
RevisitClass = Literal["QUICK", "WEEKLY", "MONTHLY", "BASIC"]  # 불만, 매주 단골, 매달 단골, 일반
BasisKind = Literal["REVIEW", "CUSTOMER", "EVENT", "GAME", "RISK_SIGNAL", "CALENDAR_DAY"]
NotifyKind = Literal["APPROVAL_REQUEST", "EXECUTE_REMINDER", "PREVIEW", "NOTICE"]
NoticeKind = Literal["WEEKLY_PREVIEW", "SALES_ANOMALY"]
Priority = Literal[1, 2, 3, 4]  # 1 불만 리뷰, 2 반복 불만 개선, 3 내일 실행할 일, 4 그 밖
Signal = Literal["HIGH", "NORMAL", "LOW"]  # 수요 신호: 많음, 보통, 적음
ReasonTag = Literal["EVENT", "GAME", "WEATHER", "SEASON"]  # 달력 이유: 행사, 경기, 날씨, 계절
Cycle = Literal["WEEKLY", "MONTHLY", "NONE"]  # 손님 주문 주기
Platform = Literal["NAVER", "BAEMIN", "YOGIYO", "COUPANG"]
Sentiment = Literal["POSITIVE", "NEGATIVE", "MIXED"]
ComplaintType = Literal["TASTE", "PORTION", "HYGIENE", "PHOTO_MISMATCH", "DELIVERY_DELAY", "SERVICE"]
ComplaintGroup = Literal["FOOD", "DELIVERY", "SERVICE"]
Labeler = Literal["HCX", "RULE"]  # 리뷰 분류를 한 주체: HyperCLOVA X, 키워드 규칙
EventKind = Literal["UNIV_FESTIVAL", "LOCAL_FESTIVAL", "LOCAL_EVENT", "MARATHON"]
GameKind = Literal["BASEBALL", "FOOTBALL", "NATIONAL_TEAM", "ESPORTS"]

# "14:00" 형식의 시각 글자
HHMM = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$", examples=["14:00"])]


# ── 입력: 매장 설정 ──


class TimeRange(BaseModel):
    start: HHMM
    end: HHMM

    @model_validator(mode="after")
    def _start_before_end(self):
        if self.start >= self.end:
            raise ValueError("시작 시각이 끝 시각보다 빨라야 합니다.")
        return self


class Dayparts(BaseModel):
    """시간대별 시작과 끝."""

    LUNCH: TimeRange
    DINNER: TimeRange
    NIGHT: TimeRange


class Slots(BaseModel):
    """알림 가능 시각 세 개."""

    OPENING: HHMM
    AFTERNOON: HHMM
    CLOSING: HHMM

    @model_validator(mode="after")
    def _in_order(self):
        if not (self.OPENING < self.AFTERNOON < self.CLOSING):
            raise ValueError("알림 시간은 출근 후 < 오후 < 마감 전 순서여야 합니다.")
        return self


class StoreSettings(BaseModel):
    store_id: str
    name: str
    category: str
    lat: float
    lng: float
    open_time: HHMM
    close_time: HHMM
    dayparts: Dayparts
    busy_dayparts: list[Daypart]  # 알림을 보내지 않는 바쁜 시간대
    slots: Slots
    closed_weekdays: list[Weekday]


# ── 입력: 리뷰와 손님 ──


class ReviewLabel(BaseModel):
    """리뷰 분류 결과."""

    sentiment: Sentiment
    complaint_types: list[ComplaintType]
    complaint_groups: list[ComplaintGroup]
    is_quick: bool  # 불만 묶음이 하나라도 있으면 true (빠른 응대 대상)
    labeler: Labeler
    labeled_at: dt.datetime


class Review(BaseModel):
    review_id: str
    platform: Platform
    written_at: dt.datetime
    rating: int = Field(ge=1, le=5)
    text: str
    customer_key: str | None = None  # 주문 이력과 이어지지 않으면 없다
    order_id: str | None = None
    label: ReviewLabel | None = None  # 아직 분류 전이면 없다


class CustomerCycle(BaseModel):
    customer_key: str
    cycle: Cycle
    next_expected_at: dt.datetime | None = None
    expected_daypart: Daypart | None = None
    intervals_days: list[int]
    computed_at: dt.datetime


# ── 입력: 우리 매장 달력과 일정 ──


class CalendarReason(BaseModel):
    tag: ReasonTag
    ref_id: str  # 근거 id. 예) game_031, event_012, season_winter
    effect: float  # 매출에 주는 효과. 0.21 이면 +21%


class CalendarCell(BaseModel):
    """달력 한 칸(날짜 × 시간대)."""

    date: dt.date
    daypart: Daypart
    signal: Signal
    baseline_sales: int
    expected_sales: int
    ratio: float
    reasons: list[CalendarReason]
    reason_text: str
    computed_at: dt.datetime


class Event(BaseModel):
    event_id: str
    kind: EventKind
    title: str
    start_at: dt.datetime
    end_at: dt.datetime
    distance_km: float


class Game(BaseModel):
    game_id: str
    kind: GameKind
    title: str  # 공식 명칭 대신 일반 표현
    start_at: dt.datetime


# ── 입력: 위험 신호와 매출 이상 ──


class RiskSignal(BaseModel):
    """같은 불만이 7일 안에 3건 쌓이면 열린다."""

    risk_id: str
    complaint_type: ComplaintType
    review_ids: list[str]
    first_at: dt.datetime
    last_at: dt.datetime
    detected_at: dt.datetime
    status: Literal["OPEN"]


class SalesAnomaly(BaseModel):
    date: dt.date
    daypart: Daypart
    actual_sales: int
    baseline_sales: int
    ratio: float
    known_reasons: list[ReasonTag]  # 그날 달력 태그. 비어 있으면 달력으로 설명되지 않는 일
    detected_at: dt.datetime


class PlanInputs(BaseModel):
    """계획 엔진에 넣는 입력 전체."""

    store: StoreSettings
    reviews: list[Review] = []
    customer_cycles: list[CustomerCycle] = []
    calendar: list[CalendarCell] = []
    risk_signals: list[RiskSignal] = []
    sales_anomalies: list[SalesAnomaly] = []
    events: list[Event] = []
    games: list[Game] = []


# ── 출력 ──


class Basis(BaseModel):
    """할 일을 만든 근거."""

    kind: BasisKind
    ref_id: str


class PlanItem(BaseModel):
    """할 일 하나."""

    plan_id: str  # {task_type}:{근거 id}:{target_date}. 다시 계산해도 같은 값
    task_type: TaskType
    revisit_class: RevisitClass | None = None  # 리뷰 답글(REVISIT_REPLY)일 때만
    basis: Basis
    target_date: dt.date
    approval_request_at: dt.datetime  # 사장님께 승인을 요청하는 시각
    execute_at: dt.datetime | None = None  # 실행 시각. 반복 불만 개선은 없다
    deadline_at: dt.datetime | None = None  # 실행 기한
    reason_line: str  # 카드에 보일 이유 한 줄
    planned_at: dt.datetime  # 이 할 일의 근거가 생긴 시각


class NoticeItem(BaseModel):
    """승인이 필요 없는 알림(월요일 주간 예고, 매출 이상)."""

    notice_id: str
    kind: NoticeKind
    slot_at: dt.datetime
    refs: list[str]  # 관련 달력 날짜, 행사·경기 id, 할 일 id
    text: str


class BatchEntry(BaseModel):
    """알림 묶음 안의 한 줄. plan_id 와 notice_id 중 하나만 있다."""

    plan_id: str | None = None
    notice_id: str | None = None
    notify_kind: NotifyKind
    priority: Priority

    @model_validator(mode="after")
    def _exactly_one_id(self):
        if (self.plan_id is None) == (self.notice_id is None):
            raise ValueError("plan_id 와 notice_id 중 하나만 있어야 합니다.")
        return self


class NotificationBatch(BaseModel):
    """알림 가능 시각 하나에 보내는 묶음. entries 는 우선순위 순서."""

    slot_at: dt.datetime
    slot: SlotName
    entries: list[BatchEntry]


class PlanResult(BaseModel):
    """계획 엔진의 출력 전체."""

    plan_items: list[PlanItem]
    notice_items: list[NoticeItem]
    batches: list[NotificationBatch]
