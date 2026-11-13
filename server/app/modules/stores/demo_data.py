"""등록한 가게에 넣는 우리 전용 목업 데이터 (주문, 주문 메뉴, 알바, 근무).

팀 목업 생성기(db/mock/generate.py)와 따로다. 기존 가게 파일(s001~s003)은 건드리지 않고, 사장님이 등록한 가게 파일(s101 ...)에만 넣는다.
그 가게의 실제 요일별 영업시간, 브레이크 타임, 메뉴(이름·가격)를 따라 만든다.

- 기간: 오늘 70일 전 ~ 21일 뒤. 서버는 "지금" 이전 주문만 쓰므로(read_store_db) 하루가 지날 때마다 그날 매출이 쌓인다.
- 점심(문 연 뒤 ~ 브레이크 시작), 저녁(브레이크 끝 ~ 마감 30분 전)에 주문이 몰린다. 주말처럼 점심만 여는 날은 점심만.
- 홀 / 배달. 배달 주문의 손님 번호로 단골을 찾는다: 매주 오는 단골 6명(같은 요일), 매달 오는 단골 10명(4주 간격).
- 추운 날(최고 기온 10도 아래, 공통 날씨 표)은 주문이 조금 늘고 라멘 같은 따뜻한 메뉴가 더 팔린다.
- 같은 가게는 늘 같은 데이터가 나온다 (난수 씨앗 = 가게 id).
"""

import datetime as dt
import random

from sqlalchemy import func, insert, select

from app.core.seoul_time import SEOUL, now_seoul
from app.data_pipeline import read_store_db
from db import models
from db.session import store_engine

DAYS_BEFORE, DAYS_AFTER = 70, 21
DAY_CODES = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
WARM_WORDS = ("라멘", "멘", "우동", "국", "탕", "전골", "짬뽕")
STAFF = [("김하늘", 10320), ("이준호", 10320), ("박서연", 10320)]


def _minutes(hhmm: str) -> int:
    hour, minute = map(int, hhmm.split(":"))
    return hour * 60 + minute


def _at(day: dt.date, minutes: int) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(0, 0), SEOUL) + dt.timedelta(minutes=minutes)


def has_orders(store_id: str) -> bool:
    with store_engine(store_id).connect() as conn:
        return bool(conn.execute(select(func.count()).select_from(models.Order)).scalar())


def fill(store_id: str, weekly_hours: dict, break_time: dict | None) -> dict:
    """주문, 주문 메뉴, 알바, 근무를 넣는다. 이미 주문이 있으면 넣지 않는다. 넣은 건수를 돌려준다."""
    if has_orders(store_id):
        return {"orders": 0, "skipped": True}
    rng = random.Random(f"demo:{store_id}")
    menus = read_store_db.read_menus(store_id) or [{"menu_id": None, "name": "대표 메뉴", "price": 12000}]
    weather = {row["date"]: float(row["temp_max"]) for row in read_store_db.read_weather(store_id) if row["temp_max"] is not None}
    today = now_seoul().date()

    weekly_regulars = [(f"c_w{i:02d}", rng.randrange(7), rng.choice(["lunch", "dinner"])) for i in range(1, 7)]
    monthly_regulars = [(f"c_m{i:02d}", rng.randrange(28)) for i in range(1, 11)]
    new_customer = 0

    orders, items, shifts = [], [], []
    order_id = shift_id = 0
    for offset in range(-DAYS_BEFORE, DAYS_AFTER + 1):
        day = today + dt.timedelta(days=offset)
        hours = weekly_hours.get(DAY_CODES[day.weekday()])
        if not hours:
            continue
        open_m, close_m = _minutes(hours["open"]), _minutes(hours["close"])
        weekend = day.weekday() >= 5
        cold = weather.get(day, 15.0) < 10
        # 점심과 저녁 시간대 (브레이크가 영업시간 안에 있으면 그 앞뒤로 나눈다)
        if break_time and open_m < _minutes(break_time["start"]) < close_m:
            windows = [("lunch", open_m, _minutes(break_time["start"]) - 15)]
            if _minutes(break_time["end"]) < close_m - 30:
                windows.append(("dinner", _minutes(break_time["end"]), close_m - 30))
        else:
            middle = open_m + (close_m - open_m) // 2
            windows = [("lunch", open_m, middle), ("dinner", middle, close_m - 30)]

        for part, start, end in windows:
            if end <= start:
                continue
            base = (34 if weekend else 26) if part == "lunch" else 17
            count = max(4, round(rng.gauss(base * (1.08 if cold else 1.0), base * 0.12)))
            peak = start + (end - start) * (0.45 if part == "lunch" else 0.4)
            delivery_share = 0.35 if part == "lunch" else 0.45
            for _ in range(count):
                minute = int(rng.triangular(start, end, peak))
                channel = "delivery" if rng.random() < delivery_share else "hall"
                customer = None
                if channel == "delivery":
                    new_customer += 1
                    customer = f"c_new{new_customer:05d}"
                order_id += 1
                orders.append(_order(rng, order_id, _at(day, minute), channel, customer, menus, cold, items))
            # 단골: 매주 단골은 정한 요일·시간대, 매달 단골은 4주 간격
            for key, weekday, regular_part in weekly_regulars:
                if day.weekday() == weekday and regular_part == part and rng.random() < 0.85:
                    order_id += 1
                    orders.append(_order(rng, order_id, _at(day, int(rng.uniform(start, end))), "delivery", key, menus, cold, items))
            for key, phase in monthly_regulars:
                if part == "lunch" and (day.toordinal() - phase) % 28 == 0:
                    order_id += 1
                    orders.append(_order(rng, order_id, _at(day, int(rng.uniform(start, end))), "delivery", key, menus, cold, items))

        # 근무: 1번 알바는 여는 시간 ~ 브레이크, 2번은 브레이크 뒤 ~ 마감, 주말은 3번이 점심을 돕는다
        for staff_number, (part, start, end) in enumerate(windows, start=1):
            shift_id += 1
            shifts.append({"shift_id": shift_id, "staff_id": staff_number, "starts_at": _at(day, start - 30), "ends_at": _at(day, end + 30)})
        if weekend:
            shift_id += 1
            shifts.append({"shift_id": shift_id, "staff_id": 3, "starts_at": _at(day, open_m), "ends_at": _at(day, close_m)})

    with store_engine(store_id).begin() as conn:
        conn.execute(insert(models.Staff), [{"staff_id": i, "name": name, "hourly_wage": wage} for i, (name, wage) in enumerate(STAFF, start=1)])
        conn.execute(insert(models.Order), orders)
        if items:
            conn.execute(insert(models.OrderItem), items)
        conn.execute(insert(models.Shift), shifts)
    return {"orders": len(orders), "order_items": len(items), "shifts": len(shifts), "skipped": False}


def _order(rng, order_id, at, channel, customer, menus, cold, items) -> dict:
    weights = [(2.2 if cold and any(w in m["name"] for w in WARM_WORDS) else 1.0) for m in menus]
    chosen: dict = {}
    for _ in range(rng.choices([1, 2, 3], [0.55, 0.35, 0.10])[0]):
        menu = rng.choices(menus, weights)[0]
        chosen[menu["menu_id"]] = (menu, chosen.get(menu["menu_id"], (menu, 0))[1] + 1)
    total = 0
    for menu_id, (menu, quantity) in chosen.items():
        price = menu["price"] or 12000
        total += price * quantity
        if menu_id is not None:
            items.append({"order_id": order_id, "menu_id": menu_id, "quantity": quantity, "unit_price": price})
    return {"order_id": order_id, "ordered_at": at, "channel": channel, "customer_key": customer, "total_amount": total}
