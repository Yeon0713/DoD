"""매출 탭 6개 계산.

데이터가 오는 길
- 이번 주(weeks), 시간대(times), 달별(months): DB → 태성 분석(하루 × 시간대 매출 sales_daily, 35일 달력) → 여기서 묶음
  · 태성의 sales_daily 는 마감이 지난 날만 만들므로, 오늘 '지금까지' 부분은 DB 주문으로 더한다
- 오늘 실시간(live), 메뉴별(menus), 어디서·누가(channels): DB 주문을 여기서 바로 더한다
  · 태성 분석에 시간별·메뉴별·주문 방식별 매출이 없어서다. 단골 판정만 태성 분석(customer_cycle)을 쓴다

날짜는 모두 영업일이다. 새벽 3시에 닫는 가게의 01시 주문은 전날 매출이다 (태성의 daypart_time 규칙).
"""

import datetime as dt
from collections import defaultdict

from app.analysis.pattern.daypart_time import at_business_time, business_date, daypart_at, dayparts_of
from app.core.seoul_time import now_seoul
from app.data_pipeline import read_store_db
from app.data_pipeline.store_snapshot_cache import StoreSnapshot, get_snapshot
from app.modules.sales.dashboard_response_format import (
    ChannelAmount,
    CustomerSplit,
    DaypartAmount,
    HourAmount,
    MenuAmount,
    MonthAmount,
    PeopleAmount,
    SalesChannels,
    SalesLive,
    SalesMenus,
    SalesMonths,
    SalesPeriod,
    SalesTimes,
    SalesWeeks,
    WeekDay,
    WeekdayDaypartAverage,
)

DAYPART_LABELS = {"LUNCH": "점심", "DINNER": "저녁", "NIGHT": "밤"}
REASON_NAMES = {"GAME": "경기", "EVENT": "축제", "WEATHER": "날씨"}
SEASON_NAMES = {"season_winter": "추워져요", "season_summer": "더워져요"}
CHANNEL_LABELS = {"HALL": "가게 손님", "DELIVERY": "배달"}
USUAL_WEEKS = 4  # '평소'는 지난 4주 같은 요일 평균


class _Store:
    """한 가게의 영업일 계산 도우미."""

    def __init__(self, snapshot: StoreSnapshot):
        self.snapshot = snapshot
        self.info = snapshot.inputs.store
        self.ranges = dayparts_of(self.info)

    def day_of(self, t: dt.datetime) -> dt.date:
        return business_date(t, self.info)

    def day_start(self, day: dt.date) -> dt.datetime:
        return at_business_time(day, self.info.open_time, self.info)

    def daypart_of(self, t: dt.datetime) -> str | None:
        return daypart_at(t, self.ranges)

    def open_hours(self) -> list[int]:
        """영업하는 시(時) 목록. 예) 10~22시 영업 → [10, 11, ..., 21], 17~03시 → [17, ..., 23, 0, 1, 2]"""
        start, end = self.info.open_time.hour, self.info.close_time.hour + (1 if self.info.close_time.minute else 0)
        length = (end - start) % 24 or 24
        return [(start + i) % 24 for i in range(length)]


def _orders_since(store_id: str, since: dt.datetime, now: dt.datetime) -> list[dict]:
    """DB 에서 since ~ now 주문을 바로 읽는다 (계산 보관본보다 최신)."""
    return read_store_db.read_orders(store_id, now, since=since)


def _actual_by_day(snapshot: StoreSnapshot) -> dict[dt.date, int]:
    """태성 sales_daily: 영업일별 실제 매출 (마감이 지난 날만)."""
    totals: dict[dt.date, int] = defaultdict(int)
    for row in snapshot.sales_daily:
        totals[row.date] += row.sales_amount
    return totals


def _forecast_by_day(snapshot: StoreSnapshot) -> dict[dt.date, int]:
    """태성 calendar_day: 영업일별 예상 매출."""
    totals: dict[dt.date, int] = defaultdict(int)
    for cell in snapshot.calendar_cells:
        totals[cell.date] += cell.expected_sales
    return totals


def _reason_names(snapshot: StoreSnapshot, day: dt.date) -> list[str]:
    names = []
    for cell in snapshot.calendar_cells:
        if cell.date != day:
            continue
        for reason in cell.reasons:
            name = SEASON_NAMES.get(reason.ref_id, "계절") if reason.tag == "SEASON" else REASON_NAMES[reason.tag]
            if name not in names:
                names.append(name)
    return names


def _period_range(store: _Store, period: SalesPeriod, now: dt.datetime) -> tuple[dt.date, dt.datetime, dt.datetime, dt.datetime]:
    """(시작 영업일, 시작 시각, 앞 기간 시작 시각, 앞 기간 끝 시각). 앞 기간은 같은 길이의 바로 앞 기간이다."""
    today = store.day_of(now)
    first = {
        "today": today,
        "week": today - dt.timedelta(days=today.weekday()),
        "4w": today - dt.timedelta(days=27),
        "month": today.replace(day=1),
    }[period]
    start = store.day_start(first)
    if period == "month":
        prev_first = (first - dt.timedelta(days=1)).replace(day=1)
    else:
        prev_first = first - dt.timedelta(days={"today": 1, "week": 7, "4w": 28}[period])
    prev_start = store.day_start(prev_first)
    return first, start, prev_start, prev_start + (now - start)


# ── 오늘 실시간 (DB) ──


def get_live(store_id: str) -> SalesLive:
    store = _Store(get_snapshot(store_id))
    now = now_seoul()
    today = store.day_of(now)
    start = store.day_start(today)
    elapsed = now - start
    orders = _orders_since(store_id, store.day_start(today - dt.timedelta(weeks=USUAL_WEEKS)), now)

    def total(rows, since, until):
        return sum(o["total_amount"] for o in rows if since <= o["ordered_at"] <= until)

    todays = [o for o in orders if o["ordered_at"] >= start]
    amount = sum(o["total_amount"] for o in todays)
    yesterday = store.day_start(today - dt.timedelta(days=1))
    usual_starts = [store.day_start(today - dt.timedelta(weeks=w)) for w in range(1, USUAL_WEEKS + 1)]
    usual_ends = [store.day_start(d.date() + dt.timedelta(days=1)) for d in usual_starts]

    hourly = []
    now_hour = now.hour
    hours = store.open_hours()
    for hour in hours:
        usual = sum(
            o["total_amount"]
            for s, e in zip(usual_starts, usual_ends)
            for o in orders
            if s <= o["ordered_at"] < e and o["ordered_at"].hour == hour
        )
        position, now_position = hours.index(hour), hours.index(now_hour) if now_hour in hours else None
        if now_position is None:
            state = "past" if now >= store.day_start(today) + dt.timedelta(hours=len(hours)) else "future"
        else:
            state = "past" if position < now_position else "now" if position == now_position else "future"
        hourly.append(
            HourAmount(
                hour=hour,
                amount=sum(o["total_amount"] for o in todays if o["ordered_at"].hour == hour),
                usual=round(usual / USUAL_WEEKS),
                state=state,
            )
        )
    return SalesLive(
        is_example=False,
        now=now,
        date=today,
        amount=amount,
        orders=len(todays),
        avg=round(amount / len(todays)) if todays else 0,
        yesterdaySame=total(orders, yesterday, yesterday + elapsed),
        usualDay=round(sum(total(orders, s, e - dt.timedelta(microseconds=1)) for s, e in zip(usual_starts, usual_ends)) / USUAL_WEEKS),
        usualSame=round(sum(total(orders, s, s + elapsed) for s in usual_starts) / USUAL_WEEKS),
        hourly=hourly,
    )


# ── 이번 주와 지난주 (태성 분석 + 오늘은 DB) ──


def get_weeks(store_id: str) -> SalesWeeks:
    snapshot = get_snapshot(store_id)
    store = _Store(snapshot)
    now = now_seoul()
    today = store.day_of(now)
    monday = today - dt.timedelta(days=today.weekday())
    actual, forecast = _actual_by_day(snapshot), _forecast_by_day(snapshot)
    today_amount = sum(o["total_amount"] for o in _orders_since(store_id, store.day_start(today), now))
    usual_today = round(sum(actual.get(today - dt.timedelta(weeks=w), 0) for w in range(1, USUAL_WEEKS + 1)) / USUAL_WEEKS)

    days = []
    for i in range(7):
        day = monday + dt.timedelta(days=i)
        last = actual.get(day - dt.timedelta(days=7), 0)
        reasons = _reason_names(snapshot, day)
        if day < today:
            days.append(WeekDay(date=day, amount=actual.get(day, 0), last=last, state="actual", reasons=reasons))
        elif day == today:
            days.append(WeekDay(date=day, amount=today_amount, last=last, state="now", reasons=reasons, usual=usual_today))
        else:
            days.append(WeekDay(date=day, amount=forecast.get(day, 0), last=last, state="forecast", reasons=reasons))

    last_monday = monday - dt.timedelta(days=7)
    last_same_day = today - dt.timedelta(days=7)
    last_same_start = store.day_start(last_same_day)
    last_same_part = sum(
        o["total_amount"]
        for o in _orders_since(store_id, last_same_start, last_same_start + (now - store.day_start(today)))
    )
    last_same_period = sum(actual.get(last_monday + dt.timedelta(days=i), 0) for i in range(today.weekday())) + last_same_part
    to_date = sum(d.amount for d in days if d.state != "forecast")
    today_rest = max(0, usual_today - today_amount)
    return SalesWeeks(
        is_example=False,
        weekStart=monday,
        days=days,
        toDate=to_date,
        lastSamePeriod=last_same_period,
        lastTotal=sum(d.last for d in days),
        forecastTotal=sum(d.amount for d in days) + today_rest,
    )


# ── 메뉴별 (DB) ──


def get_menus(store_id: str, period: SalesPeriod) -> SalesMenus:
    store = _Store(get_snapshot(store_id))
    now = now_seoul()
    first, start, prev_start, prev_end = _period_range(store, period, now)
    names = {row["menu_id"]: row["name"] for row in read_store_db.read_menus(store_id)}
    orders = read_store_db.read_orders(store_id, now, since=prev_start)
    in_current = {o["order_id"] for o in orders if o["ordered_at"] >= start}
    in_previous = {o["order_id"] for o in orders if prev_start <= o["ordered_at"] <= prev_end}

    totals: dict[str, dict[str, int]] = {}
    for item in read_store_db.read_order_items(store_id, now, since=prev_start):
        current, previous = item["order_id"] in in_current, item["order_id"] in in_previous
        if not (current or previous):
            continue
        name = names.get(item["menu_id"], f"메뉴 {item['menu_id']}")
        row = totals.setdefault(name, {"qty": 0, "amount": 0, "prevQty": 0, "prevAmount": 0})
        amount = item["quantity"] * item["unit_price"]
        if current:
            row["qty"] += item["quantity"]
            row["amount"] += amount
        else:
            row["prevQty"] += item["quantity"]
            row["prevAmount"] += amount
    items = [MenuAmount(name=name, **row) for name, row in totals.items() if row["qty"] > 0]
    items.sort(key=lambda m: m.amount, reverse=True)
    return SalesMenus(is_example=False, period=period, from_=first, to=store.day_of(now), items=items)


# ── 시간대와 요일 (태성 분석 + 오늘은 DB) ──


def get_times(store_id: str, period: SalesPeriod) -> SalesTimes:
    snapshot = get_snapshot(store_id)
    store = _Store(snapshot)
    now = now_seoul()
    today = store.day_of(now)
    first, _, _, _ = _period_range(store, period, now)

    amounts: dict[str, int] = defaultdict(int)
    for row in snapshot.sales_daily:  # 마감이 지난 날 (태성 분석)
        if first <= row.date < today:
            amounts[row.daypart] += row.sales_amount
    for order in _orders_since(store_id, store.day_start(today), now):  # 오늘 지금까지 (DB)
        daypart = store.daypart_of(order["ordered_at"])
        if daypart:
            amounts[daypart] += order["total_amount"]

    ranges = {r.daypart: r for r in store.ranges}
    dayparts = [
        DaypartAmount(
            key=key,
            label=label,
            range=f"{ranges[key].start.hour}시 ~ {ranges[key].end.hour}시" if key in ranges else "",
            amount=amounts.get(key, 0),
        )
        for key, label in DAYPART_LABELS.items()
    ]

    grid_totals: dict[tuple[int, str], int] = defaultdict(int)
    grid_first = today - dt.timedelta(weeks=USUAL_WEEKS)
    for row in snapshot.sales_daily:  # 지난 4주 (태성 분석)
        if grid_first <= row.date < today:
            grid_totals[(row.date.weekday(), row.daypart)] += row.sales_amount
    grid = [
        WeekdayDaypartAverage(weekday=weekday, daypart=key, avg=round(grid_totals[(weekday, key)] / USUAL_WEEKS))
        for weekday in range(7)
        for key in DAYPART_LABELS
    ]
    return SalesTimes(is_example=False, period=period, from_=first, to=today, dayparts=dayparts, grid=grid)


# ── 어디서, 누가 (DB + 단골 판정은 태성 분석) ──


def get_channels(store_id: str, period: SalesPeriod) -> SalesChannels:
    snapshot = get_snapshot(store_id)
    store = _Store(snapshot)
    now = now_seoul()
    first, start, _, _ = _period_range(store, period, now)
    orders = _orders_since(store_id, start, now)

    channels = []
    for key in ("DELIVERY", "HALL"):
        rows = [o for o in orders if o["channel"].upper() == key]
        channels.append(ChannelAmount(key=key, label=CHANNEL_LABELS[key], amount=sum(o["total_amount"] for o in rows), orders=len(rows)))

    regulars = {c.customer_key for c in snapshot.customer_cycles if c.cycle in ("WEEKLY", "MONTHLY")}
    first_order: dict[str, dt.datetime] = {}
    for order in snapshot.inputs.orders:  # 손님별 첫 주문 시각 (분석에 넣은 전체 기록)
        if order.customer_key and order.customer_key not in first_order:
            first_order[order.customer_key] = order.ordered_at
    groups: dict[str, dict[str, int]] = {"regular": defaultdict(int), "fresh": defaultdict(int), "other": defaultdict(int)}
    unknown = [o for o in orders if not o["customer_key"]]
    for order in orders:
        key = order["customer_key"]
        if not key:
            continue
        group = "regular" if key in regulars else "fresh" if first_order.get(key, order["ordered_at"]) >= start else "other"
        groups[group][key] += order["total_amount"]

    def pack(group: dict[str, int]) -> PeopleAmount:
        return PeopleAmount(people=len(group), amount=sum(group.values()))

    return SalesChannels(
        is_example=False,
        period=period,
        from_=first,
        to=store.day_of(now),
        channels=channels,
        platformsSimulated=False,
        customers=CustomerSplit(
            regular=pack(groups["regular"]),
            fresh=pack(groups["fresh"]),
            other=pack(groups["other"]),
            unknownOrders=len(unknown),
            unknownAmount=sum(o["total_amount"] for o in unknown),
        ),
    )


# ── 달별 (태성 분석 + 오늘은 DB) ──


def get_months(store_id: str) -> SalesMonths:
    snapshot = get_snapshot(store_id)
    store = _Store(snapshot)
    now = now_seoul()
    today = store.day_of(now)
    this_month = today.strftime("%Y-%m")

    amounts: dict[str, int] = defaultdict(int)
    days: dict[str, set[dt.date]] = defaultdict(set)
    for row in snapshot.sales_daily:  # 마감이 지난 날 (태성 분석)
        if row.date < today:
            month = row.date.strftime("%Y-%m")
            amounts[month] += row.sales_amount
            days[month].add(row.date)
    order_counts: dict[str, int] = defaultdict(int)
    for order in snapshot.inputs.orders:  # 주문 수는 sales_daily 에 없어서 DB 주문으로 센다
        day = store.day_of(order.ordered_at)
        if day < today:
            order_counts[day.strftime("%Y-%m")] += 1
    todays = _orders_since(store_id, store.day_start(today), now)  # 오늘 지금까지 (DB)
    if todays:
        amounts[this_month] += sum(o["total_amount"] for o in todays)
        order_counts[this_month] += len(todays)
        days[this_month].add(today)

    last_28 = [today - dt.timedelta(days=i) for i in range(1, 29)]
    actual = _actual_by_day(snapshot)
    avg_daily = round(sum(actual.get(day, 0) for day in last_28) / 28)
    orders_28 = sum(1 for o in snapshot.inputs.orders if last_28[-1] <= store.day_of(o.ordered_at) <= last_28[0])
    next_month = (today.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    remaining_days = (next_month - today).days - 1

    months = []
    for month in sorted(amounts):
        partial = month == this_month or min(days[month]).day != 1
        months.append(
            MonthAmount(
                month=month,
                amount=amounts[month],
                orders=order_counts.get(month, 0),
                days=len(days[month]),
                partial=partial,
                forecast=amounts[month] + avg_daily * remaining_days if month == this_month else None,
            )
        )
    return SalesMonths(
        is_example=False,
        months=months,
        avgDaily=avg_daily,
        avgOrder=round(sum(actual.get(day, 0) for day in last_28) / orders_28) if orders_28 else 0,
    )
