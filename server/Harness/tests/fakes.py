"""테스트용 가짜 가게 스냅샷과 가짜 CLOVA.

가게 t001 '테스트국수' (11:00~21:00), 지금은 2026-11-15(일) 15:00.
- 메뉴: m1 잔치국수, m2 비빔국수, m3 만두, m4 콜라
- 지난 35일: 매일 12시 주문 2건, 19시 주문 1건. 최근 7일(11/8~11/14)은 19시에 3건 더 (저녁 몰림)
- 맛 불만 리뷰 r1~r3: 11/12~11/14 19시 잔치국수 주문에 달림 → 위험 신호 risk_001 (TASTE)
- 좋은 리뷰 r4: 매주 단골 c1 의 비빔국수 주문
- 근무: 불만 리뷰 날마다 11~15시 1명, 17~21시 1명 (19시 근무 1명)
- 행사 e1 춘천 겨울 빛 축제(11/21, 1.2km), 경기 g1 국가대표 축구 경기(11/19 20시)
- 할 일: 답글 r1(QUICK), 답글 r4(WEEKLY), 재주문 인사 c1, 반복 불만 risk_001, 메뉴판 11/21, 포스터 e1
"""

import copy
import datetime as dt

import httpx

from app.analysis.input_shapes import AnalysisInputs, Menu, Order, OrderItem, Shift, StoreInfo, WeatherDay
from app.analysis.result_shapes import CustomerCycleRow
from app.core.seoul_time import SEOUL
from app.data_pipeline.store_snapshot_cache import StoreSnapshot
from app.planner.data_shapes import (
    Basis, CalendarCell, CalendarReason, Event, Game, PlanItem, PlanResult, Review, ReviewLabel, RiskSignal,
)

NOW = dt.datetime(2026, 11, 15, 15, 0, tzinfo=SEOUL)


def at(day: dt.date, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=SEOUL)


def label(sentiment: str, types: list[str]) -> ReviewLabel:
    groups = sorted({"DELIVERY" if t == "DELIVERY_DELAY" else "SERVICE" if t == "SERVICE" else "FOOD" for t in types})
    return ReviewLabel(sentiment=sentiment, complaint_types=types, complaint_groups=groups, is_quick=bool(types),
                       labeler="RULE", labeled_at=NOW - dt.timedelta(hours=1))


def make_snapshot() -> StoreSnapshot:
    menus = [
        Menu(menu_id="m1", name="잔치국수", category="MAIN", price=7000),
        Menu(menu_id="m2", name="비빔국수", category="MAIN", price=8000),
        Menu(menu_id="m3", name="만두", category="SIDE", price=5000),
        Menu(menu_id="m4", name="콜라", category="DRINK", price=2000),
    ]
    orders, items = [], []

    def order(oid: str, when: dt.datetime, menu: str, customer: str | None = None, channel: str = "BAEMIN") -> None:
        orders.append(Order(order_id=oid, ordered_at=when, channel=channel, customer_key=customer, total_amount=7000))
        items.append(OrderItem(order_id=oid, menu_id=menu, quantity=1, unit_price=7000))

    first = NOW.date() - dt.timedelta(days=35)
    for offset in range(35):
        day = first + dt.timedelta(days=offset)
        order(f"o{day:%m%d}a", at(day, 12, 10), "m1", channel="HALL")
        order(f"o{day:%m%d}b", at(day, 12, 30), "m2", channel="HALL")
        order(f"o{day:%m%d}c", at(day, 19, 10), "m3")
        if day >= NOW.date() - dt.timedelta(days=7):
            for n in range(3):
                order(f"o{day:%m%d}busy{n}", at(day, 19, 20 + n), "m1")
    for week in range(4):  # 단골 c1: 매주 토요일 12시 비빔국수
        order(f"oc1_{week}", at(dt.date(2026, 11, 14) - dt.timedelta(weeks=week), 12, 40), "m2", customer="c1")
    for n, day in enumerate([dt.date(2026, 11, 12), dt.date(2026, 11, 13), dt.date(2026, 11, 14)], 1):
        order(f"ocomp{n}", at(day, 19, 40), "m1", customer=f"cx{n}")

    reviews = [
        Review(review_id="r1", platform="BAEMIN", written_at=at(dt.date(2026, 11, 12), 21), rating=2,
               text="국물이 너무 싱거웠어요. 잔치국수 맛이 예전 같지 않네요", customer_key="cx1", order_id="ocomp1",
               label=label("NEGATIVE", ["TASTE"])),
        Review(review_id="r2", platform="BAEMIN", written_at=at(dt.date(2026, 11, 13), 21), rating=2,
               text="면이 퍼져서 왔고 맛이 밍밍했어요 010-1234-5678", customer_key="cx2", order_id="ocomp2",
               label=label("NEGATIVE", ["TASTE"])),
        Review(review_id="r3", platform="NAVER", written_at=at(dt.date(2026, 11, 14), 21), rating=3,
               text="양은 괜찮은데 국물 맛이 좀 약해요", customer_key="cx3", order_id="ocomp3",
               label=label("MIXED", ["TASTE"])),
        Review(review_id="r4", platform="NAVER", written_at=at(dt.date(2026, 11, 14), 14), rating=5,
               text="비빔국수 양념이 새콤달콤 맛있어요! 또 시킬게요", customer_key="c1", order_id="oc1_0",
               label=label("POSITIVE", [])),
    ]
    shifts = []
    for day in (dt.date(2026, 11, 12), dt.date(2026, 11, 13), dt.date(2026, 11, 14)):
        shifts.append(Shift(shift_id=f"s{day:%d}a", staff_key="staffA", starts_at=at(day, 11), ends_at=at(day, 15), hourly_wage=10030))
        shifts.append(Shift(shift_id=f"s{day:%d}b", staff_key="staffB", starts_at=at(day, 17), ends_at=at(day, 21), hourly_wage=10030))
    events = [Event(event_id="e1", kind="LOCAL_FESTIVAL", title="춘천 겨울 빛 축제",
                    start_at=at(dt.date(2026, 11, 21), 17), end_at=at(dt.date(2026, 11, 22), 22), distance_km=1.2)]
    games = [Game(game_id="g1", kind="NATIONAL_TEAM", title="국가대표 축구 경기", start_at=at(dt.date(2026, 11, 19), 20))]
    inputs = AnalysisInputs(
        store=StoreInfo(store_id="t001", name="테스트국수", lat=37.88, lng=127.73,
                        open_time=dt.time(11), close_time=dt.time(21)),
        orders=orders, order_items=items, menus=menus, shifts=shifts, events=events, games=games, reviews=reviews,
        weather=[WeatherDay(date=dt.date(2026, 11, 21), temp_max=4.0, temp_min=-3.0, rain_mm=0.0)],
    )
    calendar = [
        CalendarCell(date=dt.date(2026, 11, 21), daypart="DINNER", signal="HIGH", baseline_sales=300000,
                     expected_sales=390000, ratio=1.3, reasons=[CalendarReason(tag="EVENT", ref_id="e1", effect=0.3)],
                     reason_text="춘천 겨울 빛 축제로 저녁 손님이 늘 거예요", computed_at=NOW - dt.timedelta(hours=1)),
    ]
    risk = RiskSignal(risk_id="risk_001", complaint_type="TASTE", review_ids=["r1", "r2", "r3"],
                      first_at=reviews[0].written_at, last_at=reviews[2].written_at,
                      detected_at=reviews[2].written_at, status="OPEN")
    cycles = [CustomerCycleRow(customer_key="c1", cycle="WEEKLY", intervals_days=[7, 7, 7],
                               computed_at=NOW - dt.timedelta(hours=1))]

    def item(plan_id: str, task_type: str, basis: Basis, day: dt.date, **extra) -> PlanItem:
        return PlanItem(plan_id=plan_id, task_type=task_type, basis=basis, target_date=day,
                        approval_request_at=at(NOW.date(), 14), reason_line="이유", planned_at=NOW - dt.timedelta(hours=2), **extra)

    plan_items = [
        item("REVISIT_REPLY:r1:2026-11-15", "REVISIT_REPLY", Basis(kind="REVIEW", ref_id="r1"), NOW.date(), revisit_class="QUICK"),
        item("REVISIT_REPLY:r4:2026-11-15", "REVISIT_REPLY", Basis(kind="REVIEW", ref_id="r4"), NOW.date(), revisit_class="WEEKLY"),
        item("REORDER_NUDGE:c1:2026-11-15", "REORDER_NUDGE", Basis(kind="CUSTOMER", ref_id="c1"), NOW.date()),
        item("REVIEW_FIX:risk_001:2026-11-15", "REVIEW_FIX", Basis(kind="RISK_SIGNAL", ref_id="risk_001"), NOW.date()),
        item("MENU_ORDER:2026-11-21:2026-11-21", "MENU_ORDER", Basis(kind="CALENDAR_DAY", ref_id="2026-11-21"), dt.date(2026, 11, 21)),
        item("POSTER:e1:2026-11-21", "POSTER", Basis(kind="EVENT", ref_id="e1"), dt.date(2026, 11, 21)),
    ]
    return StoreSnapshot(
        store_id="t001", computed_at=NOW, store={"name": "테스트국수", "category": "국수", "address": "춘천시 (가상)"},
        inputs=inputs, sales_daily=[], calendar_cells=calendar, customer_cycles=cycles, reviews=reviews,
        risk_signals=[risk], settings=None, plan=PlanResult(plan_items=plan_items, notice_items=[], batches=[]),
    )


# ── 가짜 CLOVA ──


def call(name: str, arguments: dict) -> tuple[str, dict]:
    """도구 호출 하나."""
    return (name, arguments)


class FakeClova:
    """미리 적은 차례대로 답한다. 차례 하나는
    - [call(...), ...]: 도구 호출들 (finishReason tool_calls)
    - str: 도구 없이 글만
    - int: 그 HTTP 상태로 실패
    받은 요청 바디는 requests 에 쌓인다. 차례가 모자라면 테스트가 실패한다.
    """

    def __init__(self, *turns):
        self.turns = list(turns)
        self.requests: list[dict] = []
        self._ids = 0

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.requests.append(copy.deepcopy(json))  # 실행기가 뒤에 대화를 덧붙여도 그때 보낸 모양 그대로 남긴다
        assert self.turns, f"CLOVA 를 예상보다 많이 불렀어요. 마지막 요청: {json['messages'][-1]}"
        turn = self.turns.pop(0)
        request = httpx.Request("POST", url)
        if isinstance(turn, int):
            return httpx.Response(turn, json={"status": {"code": str(turn)}}, request=request)
        if isinstance(turn, str):
            message, finish = {"role": "assistant", "content": turn}, "stop"
        else:
            calls = []
            for name, arguments in turn:
                self._ids += 1
                calls.append({"id": f"call_{self._ids}", "type": "function", "function": {"name": name, "arguments": arguments}})
            message, finish = {"role": "assistant", "content": "", "toolCalls": calls}, "tool_calls"
        body = {"status": {"code": "20000"}, "result": {"message": message, "finishReason": finish,
                                                          "usage": {"promptTokens": 100, "completionTokens": 20, "totalTokens": 120}}}
        return httpx.Response(200, json=body, request=request)

    def tool_messages(self, request_index: int) -> list[str]:
        """그 요청에 담긴 tool 메시지들의 내용."""
        return [m["content"] for m in self.requests[request_index]["messages"] if m["role"] == "tool"]

    def done(self) -> bool:
        return not self.turns
