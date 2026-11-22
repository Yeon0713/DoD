"""확정한 예약·단체 주문을 이번 주 달력(화면에 보내는 칸)의 예상 매출에 더한다.

더하는 매출 = 인원 × 1인 평균 금액
  1인 평균 금액: 최근 8주 주문에서 "주문 금액 ÷ 그 주문의 메인 메뉴 그릇 수"의 평균 (메인 메뉴 한 그릇을 한 사람으로 본다).
  주문 기록이 없으면 메뉴 메인 가격의 평균.
그 시간대(점심·저녁·밤)는 예약 시각으로 정한다. 영업시간 밖이면 가장 가까운 시간대에 넣는다.
더한 뒤 비율(예상 ÷ 기준선)로 신호를 다시 정한다 (1.15 이상이면 많음, store_calendar.calendar_day 와 같은 기준).
이유에 RESERVATION 을 붙이고 이유 글 끝에 "단체 예약 12명" 처럼 덧붙인다.

계획 엔진이 쓰는 달력(메뉴판·포스터 규칙)에는 넣지 않는다. 예약 때문에 메뉴판을 바꾸지는 않는다.
"""

import datetime as dt
from collections import defaultdict

from app.analysis.input_shapes import AnalysisInputs
from app.analysis.pattern.daypart_time import business_date, dayparts_of
from app.analysis.store_calendar.calendar_day import HIGH_RATIO, LOW_RATIO
from app.core.seoul_time import to_seoul
from app.planner.data_shapes import CalendarCell, CalendarReason

LOOKBACK = dt.timedelta(weeks=8)
KIND_WORD = {"RESERVATION": "예약", "GROUP_ORDER": "단체 주문"}


def per_person_amount(inputs: AnalysisInputs, now: dt.datetime) -> int:
    mains = {m.menu_id for m in inputs.menus if m.category.upper() == "MAIN"}
    since = now - LOOKBACK
    bowls: dict[str, int] = defaultdict(int)
    for item in inputs.order_items:
        if item.menu_id in mains:
            bowls[item.order_id] += item.quantity
    amounts = [o.total_amount / bowls[o.order_id] for o in inputs.orders if since <= o.ordered_at <= now and bowls.get(o.order_id)]
    if amounts:
        return round(sum(amounts) / len(amounts))
    prices = [m.price for m in inputs.menus if m.menu_id in mains and m.price]
    return round(sum(prices) / len(prices)) if prices else 12000


def _daypart_of(at: dt.datetime, inputs: AnalysisInputs) -> str | None:
    """예약 시각의 시간대. 영업시간 밖이면 가장 가까운 시간대 (시작·끝까지 분 차이가 가장 작은 곳)."""
    ranges = dayparts_of(inputs.store)
    if not ranges:
        return None
    t = to_seoul(at).time()
    minutes = t.hour * 60 + t.minute
    best, gap = None, None
    for r in ranges:
        start, end = r.start.hour * 60 + r.start.minute, r.end.hour * 60 + r.end.minute
        inside = start <= minutes < end if start < end else (minutes >= start or minutes < end)
        if inside:
            return r.daypart
        d = min(abs(minutes - start), abs(minutes - end))
        if gap is None or d < gap:
            best, gap = r.daypart, d
    return best


def _signal(ratio: float) -> str:
    return "HIGH" if ratio >= HIGH_RATIO else "LOW" if ratio <= LOW_RATIO else "NORMAL"


def apply_reservations(cells: list[CalendarCell], reservations: list[dict], inputs: AnalysisInputs, now: dt.datetime) -> list[CalendarCell]:
    """확정 예약을 칸에 더한 새 칸 목록. 예약이 없는 칸은 그대로."""
    confirmed = [r for r in reservations if r["status"] == "CONFIRMED"]
    if not confirmed:
        return cells
    person = per_person_amount(inputs, now)
    by_cell: dict[tuple[dt.date, str], list[dict]] = defaultdict(list)
    for r in confirmed:
        daypart = _daypart_of(r["at"], inputs)
        if daypart:
            by_cell[(business_date(r["at"], inputs.store), daypart)].append(r)  # 칸 날짜는 영업일 (자정 넘는 가게의 새벽은 전날)
    out = []
    for cell in cells:
        found = by_cell.get((cell.date, cell.daypart))
        if not found:
            out.append(cell)
            continue
        extra = sum(r["people"] for r in found) * person
        expected = cell.expected_sales + extra
        base = cell.baseline_sales
        ratio = round(expected / base, 2) if base else cell.ratio
        reasons = list(cell.reasons) + [
            CalendarReason(tag="RESERVATION", ref_id=f"reservation_{r['reservation_id']}", effect=round(r["people"] * person / base, 2) if base else 0.0)
            for r in found
        ]
        words = ", ".join(f"{'단체 ' if r['people'] >= 8 or r['kind'] == 'GROUP_ORDER' else ''}{KIND_WORD[r['kind']]} {r['people']}{'인분' if r['kind'] == 'GROUP_ORDER' else '명'}" for r in found)
        text = f"{cell.reason_text}, {words}" if cell.reason_text else f"{words}이 있어요"
        out.append(cell.model_copy(update={"expected_sales": expected, "ratio": ratio, "signal": _signal(ratio) if base else "HIGH", "reasons": reasons, "reason_text": text}))
    return out
