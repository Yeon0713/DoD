"""가게별 계산 결과 보관.

한 가게를 계산하는 순서:
  1. DB 에서 now 까지 데이터를 꺼내 분석 입력으로 번역한다        (db_rows_to_analysis_inputs)
  2. 태성 분석을 돌린다: 하루 매출, 35일 달력, 손님 주문 주기, 리뷰 분류, 반복 불만
  3. 분석 결과를 계획 엔진 입력으로 바꿔 계획 엔진을 돌린다          (analysis_to_plan_inputs, make_plan)
     리뷰 답글은 지금 한 주(지난 토요일 11:00 ~ 이번 토요일 11:00) 몫만 남긴다  (keep_this_week_replies)
  4. 이번 한 주 리뷰 답글과 재주문 인사 초안을 CLOVA X 로 쓴다         (review_reply_writer)
  5. 화면에 보일 문장을 CLOVA X 로 다듬도록 뒤에서 맡긴다            (sentence_polish)

분석에 가게 하나당 몇 초가 걸리므로, 결과를 보관해 두고 SNAPSHOT_REFRESH_MINUTES(기본 10분)가 지나면 다시 계산한다.
사장님이 설정을 고치면 그 가게 결과를 지워 다음 요청에서 바로 다시 계산한다.
서버를 다시 켜면 보관한 결과와 고친 설정은 사라진다 (DB 저장은 다음 단계).
"""

import datetime as dt
import logging
import threading
from dataclasses import dataclass, field

from app.analysis.customer_cycle.order_cycle import build_customer_cycles
from app.analysis.input_shapes import AnalysisInputs
from app.analysis.pattern.sales_daily import build_sales_daily
from app.analysis.result_shapes import CustomerCycleRow, RiskSignalRow, SalesDailyRow
from app.analysis.review.label_reviews import attach_labels, label_reviews
from app.analysis.review.risk_signals import update_risk_signals
from app.analysis.store_calendar.calendar_day import CALENDAR_DAYS, build_calendar_days
from app.core.config import settings as app_settings
from app.core.error_response import ApiError
from app.core.seoul_time import at_time, now_seoul, to_seoul
from app.data_pipeline import registered_stores, read_store_db
from app.data_pipeline.analysis_to_plan_inputs import build_plan_inputs, build_store_settings, to_calendar_cell
from app.data_pipeline.db_rows_to_analysis_inputs import build_analysis_inputs
from app.planner.data_shapes import CalendarCell, PlanResult, Review, StoreSettings
from app.planner.priority_and_grouping import group_into_batches
from app.planner.rule_review_reply import current_reply_week_start
from app.planner.make_plan import make_plan
from app.planner.notification_time_helpers import KOREAN_WEEKDAYS
from app.review_reply_writer.write_reply_with_clova import write_drafts
from app.sentence_polish import polish_with_clova

logger = logging.getLogger(__name__)

# 문장 다듬기를 미리 맡길 기간: 오늘 기준 7일 전 ~ 35일 뒤 (1년치 지난 카드까지 다듬지 않도록)
POLISH_DAYS_BEFORE = 7
POLISH_DAYS_AFTER = 35


@dataclass
class StoreSnapshot:
    store_id: str
    computed_at: dt.datetime  # 이 시각까지의 데이터로 계산했다
    store: dict  # DB 가게 정보 한 줄
    inputs: AnalysisInputs  # 분석에 넣은 입력 (주문, 메뉴 등. 매출 화면도 같이 쓴다)
    sales_daily: list[SalesDailyRow]  # 태성: 하루 × 시간대 매출 (마감이 지난 날만)
    calendar_cells: list[CalendarCell]  # 태성: 오늘부터 35일 달력
    customer_cycles: list[CustomerCycleRow]  # 태성: 손님별 주문 주기 (NONE 포함)
    reviews: list[Review]  # 태성 리뷰 분류(label)가 붙은 리뷰
    risk_signals: list[RiskSignalRow]  # 태성: 반복 불만 신호
    settings: StoreSettings | None  # 계획 엔진 매장 설정. 만들 수 없는 가게면 None
    plan: PlanResult | None  # 계획 엔진 결과. 만들 수 없는 가게면 None
    plan_unavailable: ApiError | None = None  # plan 이 None 인 까닭
    ordered_at_by_order: dict[str, dt.datetime] = field(default_factory=dict)
    draft_texts: dict[str, str] = field(default_factory=dict)  # 할 일 id → CLOVA X 답글·재주문 인사 초안

    def require_plan(self) -> PlanResult:
        if self.plan is None:
            raise self.plan_unavailable or ApiError(500, "PLAN_UNAVAILABLE", "알림 계획을 만들지 못했어요.")
        return self.plan


_snapshots: dict[str, StoreSnapshot] = {}
_yesterday_cells: dict[str, tuple[dt.date, list[CalendarCell]]] = {}  # 가게별 어제 달력 칸 (하루에 한 번만 계산)
_settings_changes: dict[str, dict] = {}  # 가게별 사장님이 고친 설정 (서버 메모리)
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(store_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(store_id, threading.Lock())


def get_snapshot(store_id: str, now: dt.datetime | None = None) -> StoreSnapshot:
    """보관한 결과가 없거나 오래됐으면 다시 계산해서 돌려준다. now 는 테스트에서 시각을 고정할 때만 넣는다."""
    now = to_seoul(now) if now else now_seoul()
    refresh = dt.timedelta(minutes=app_settings.snapshot_refresh_minutes)
    with _lock_for(store_id):
        snapshot = _snapshots.get(store_id)
        if snapshot is None or now < snapshot.computed_at or now - snapshot.computed_at >= refresh:
            snapshot = _compute(store_id, now, previous=snapshot)
            _snapshots[store_id] = snapshot
        return snapshot


def _registered_base(store_id: str) -> dict:
    """사장님이 등록한 가게는 등록 때 네이버 지도에서 읽어 DB 에 저장한 요일별 영업시간과 브레이크 타임을 기본으로 쓴다.

    고친 설정은 서버 메모리에만 있어 서버를 다시 켜면 사라지므로, 그때도 실제 가게 시간이 나오게 한다.
    """
    info = registered_stores.place_info(store_id)
    if info is None or not any(info.weekly_hours.values()):
        return {}
    if any(h and h["close"] <= h["open"] for h in info.weekly_hours.values()):
        return {}  # 자정을 넘겨 여는 가게는 아직 계획을 못 만든다 (기본 대표 시간으로 둔다)
    return {"weekly_hours": info.weekly_hours, "break_time": info.break_time}


def get_settings_changes(store_id: str) -> dict:
    """그 가게 설정에 덮어쓸 값: 등록한 가게의 기본 시간 위에 사장님이 고친 값."""
    return {**_registered_base(store_id), **_settings_changes.get(store_id, {})}


def save_settings_changes(store_id: str, changes: dict) -> None:
    """사장님이 고친 설정을 기억하고, 그 가게 결과를 지워 다음 요청에서 새 설정으로 다시 계산하게 한다."""
    with _lock_for(store_id):
        _settings_changes[store_id] = {**_settings_changes.get(store_id, {}), **changes}
        _snapshots.pop(store_id, None)


def clear_all() -> None:
    """보관한 결과와 고친 설정을 모두 지운다 (테스트용)."""
    _snapshots.clear()
    _settings_changes.clear()
    _yesterday_cells.clear()


def _compute(store_id: str, now: dt.datetime, previous: StoreSnapshot | None) -> StoreSnapshot:
    started = now_seoul()
    store = read_store_db.read_store(store_id)
    inputs = build_analysis_inputs(store_id, now)

    # 태성 분석
    sales_daily = build_sales_daily(inputs, now).rows
    calendar_cells = [to_calendar_cell(row) for row in build_calendar_days(inputs, now)]
    customer_cycles = build_customer_cycles(inputs, now)
    labels = label_reviews(inputs.reviews, now, classifier=None)  # 키워드 규칙만 쓴다 (CLOVA 분류는 끔)
    reviews = attach_labels(inputs.reviews, labels)
    risk_signals = update_risk_signals(inputs.reviews, labels, previous.risk_signals if previous else [], now)

    # 계획 엔진
    settings, plan, unavailable = None, None, None
    try:
        settings = build_store_settings(store, get_settings_changes(store_id))
        plan_inputs = build_plan_inputs(
            settings,
            reviews,
            customer_cycles,
            calendar_for_planner(store_id, inputs, calendar_cells, now),
            risk_signals,
            inputs.events,
            inputs.games,
        )
        plan = drop_yesterday_only_items(make_plan(plan_inputs, now), now, settings)
        plan = keep_this_week_replies(plan, now, settings)
    except ApiError as error:
        unavailable = error

    # 답글 초안: 이번 한 주 답글과 가까운 재주문 인사만 (같은 리뷰는 한 번만 CLOVA 를 부른다)
    draft_texts = {}
    if plan is not None:
        today = now.date()
        first, last = today - dt.timedelta(days=POLISH_DAYS_BEFORE), today + dt.timedelta(days=POLISH_DAYS_AFTER)
        reply_items = [
            item
            for item in plan.plan_items
            if item.task_type == "REVISIT_REPLY"
            or (item.task_type == "REORDER_NUDGE" and first <= item.approval_request_at.date() <= last)
        ]
        draft_texts = write_drafts(
            reply_items, {review.review_id: review for review in reviews}, store, [menu.name for menu in inputs.menus]
        )

    snapshot = StoreSnapshot(
        store_id=store_id,
        computed_at=now,
        store=store,
        inputs=inputs,
        sales_daily=sales_daily,
        calendar_cells=calendar_cells,
        customer_cycles=customer_cycles,
        reviews=reviews,
        risk_signals=risk_signals,
        settings=settings,
        plan=plan,
        plan_unavailable=unavailable,
        ordered_at_by_order={order.order_id: order.ordered_at for order in inputs.orders},
        draft_texts=draft_texts,
    )
    _request_polish(snapshot)
    seconds = (now_seoul() - started).total_seconds()
    logger.info("%s 가게 분석과 계획을 %.1f초 만에 다시 계산했다", store_id, seconds)
    return snapshot


def first_known_at(day: dt.date) -> dt.datetime:
    """달력에서 day 를 처음 알게 된 시각: day 가 35일 달력 안으로 처음 들어온 날의 0시.

    달력은 서버가 10분마다 다시 계산하고 그때마다 computed_at 이 '지금'이 된다.
    계획 엔진은 computed_at 을 '근거를 알게 된 시각'으로 보고, 그보다 이른 승인 요청을 다음 알림 시각으로 미룬다.
    computed_at 을 그대로 넘기면 승인 요청 시각이 지날 때마다 다음 알림 시각으로 계속 밀려서
    앱에 승인 요청 카드가 한 번도 뜨지 않는다 (11/11 14:00 → 21:30 → 11/12 10:00 → ...).
    행사·경기·날씨는 DB 에 미리 들어 있으므로, 그 날짜가 달력에 처음 들어온 날에 이미 알았던 것으로 본다.
    """
    return at_time(day - dt.timedelta(days=CALENDAR_DAYS - 1), "00:00")


def calendar_for_planner(
    store_id: str, inputs: AnalysisInputs, calendar_cells: list[CalendarCell], now: dt.datetime
) -> list[CalendarCell]:
    """계획 엔진에 넘길 달력 칸. 화면에 보내는 달력(calendar_cells)과 두 가지가 다르다.

    1. computed_at 을 '처음 알게 된 시각'(first_known_at)으로 바꾼다. 승인 요청 시각이 밀리지 않게 한다.
    2. 어제 칸을 앞에 붙인다. 메뉴판 규칙은 전날과 태그가 달라야 할 일을 만드는데, 달력은 오늘부터라
       오늘 실행할 메뉴판 바꾸기(어제 14:00 승인 요청, 오늘 출근 후 실행)가 당일 아침에 사라졌다.
       어제 칸은 계산에 몇 초가 걸려서 가게마다 하루에 한 번만 계산해 기억한다.
    """
    yesterday = now.date() - dt.timedelta(days=1)
    remembered = _yesterday_cells.get(store_id)
    if remembered is None or remembered[0] != yesterday:
        # 어제가 쉬는 날이면 달력 칸이 없다. 메뉴판 규칙이 견줄 수 있게 그 앞의 여는 날까지 거슬러 간다 (길어야 일주일)
        cells_before: list[CalendarCell] = []
        for days_back in range(1, 8):
            day = now.date() - dt.timedelta(days=days_back)
            rows = build_calendar_days(inputs, now - dt.timedelta(days=days_back))
            cells_before = [to_calendar_cell(row) for row in rows if row.date == day]
            if cells_before:
                break
        remembered = (yesterday, cells_before)
        _yesterday_cells[store_id] = remembered
    cells = [*remembered[1], *calendar_cells]
    return [cell.model_copy(update={"computed_at": first_known_at(cell.date)}) for cell in cells]


def drop_yesterday_only_items(plan: PlanResult, now: dt.datetime, settings: StoreSettings) -> PlanResult:
    """어제 칸을 붙여서 새로 생긴 지난 일은 뺀다: 어제가 토요일일 때의 주말 포스터, 어제 아침의 주간 예고.

    어제 칸은 오늘 실행할 메뉴판 바꾸기를 남기려고 붙인 것이라, 그 밖의 어제 일은 만들지 않는다.
    """
    today = now.date()
    past_days = {today - dt.timedelta(days=days_back) for days_back in range(1, 8)}
    items = [
        item
        for item in plan.plan_items
        if not (item.task_type == "POSTER" and item.basis.kind == "CALENDAR_DAY" and item.target_date in past_days)
    ]
    notices = [
        notice
        for notice in plan.notice_items
        if not (notice.kind == "WEEKLY_PREVIEW" and to_seoul(notice.slot_at).date() < today)
    ]
    return PlanResult(plan_items=items, notice_items=notices, batches=group_into_batches(items, notices, settings))


def keep_this_week_replies(plan: PlanResult, now: dt.datetime, settings: StoreSettings) -> PlanResult:
    """리뷰 답글은 지금 한 주 몫만 남긴다. 답글을 올리는 시각이 이번 한 주 시작(지난 토요일 11:00)보다 뒤인 것만.

    예) 지금 11/19(목) → 11/14(토) 11:00 이후에 달려 11/21(토)에 올릴 답글만 남는다.
        1년 전 리뷰나 지난주에 이미 올렸어야 할 답글은 빠진다. 재주문 권유 등 다른 할 일은 그대로 둔다.
    알림 묶음(batches)도 남은 할 일로 다시 만든다.
    """
    week_start = current_reply_week_start(now)
    items = [
        item
        for item in plan.plan_items
        if item.task_type != "REVISIT_REPLY" or (item.execute_at is not None and item.execute_at > week_start)
    ]
    return PlanResult(
        plan_items=items,
        notice_items=plan.notice_items,
        batches=group_into_batches(items, plan.notice_items, settings),
    )


def _request_polish(snapshot: StoreSnapshot) -> None:
    """화면에 곧 보일 문장들을 CLOVA X 로 다듬도록 뒤에서 맡긴다. 기다리지 않는다."""
    store = snapshot.store
    today = snapshot.computed_at.date()
    first, last = today - dt.timedelta(days=POLISH_DAYS_BEFORE), today + dt.timedelta(days=POLISH_DAYS_AFTER)
    # 다듬어도 글자 그대로 남아야 하는 말: 행사·경기 이름, 요일
    names = [event.title for event in snapshot.inputs.events] + [game.title for game in snapshot.inputs.games]
    must_keep = [*names, *KOREAN_WEEKDAYS]
    cells = [cell.reason_text for cell in snapshot.calendar_cells]
    polish_with_clova.request_polish("calendar_reason", cells, store, must_keep)
    if snapshot.plan is None:
        return
    lines = [item.reason_line for item in snapshot.plan.plan_items if first <= item.approval_request_at.date() <= last]
    notices = [notice.text for notice in snapshot.plan.notice_items if first <= notice.slot_at.date() <= last]
    polish_with_clova.request_polish("plan_card", lines, store, must_keep)
    polish_with_clova.request_polish("notice", notices, store, must_keep)
