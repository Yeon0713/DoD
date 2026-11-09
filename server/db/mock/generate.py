"""목업 생성기 v1: 춘천 대학가 국수집(가상).

server/ 폴더에서 실행:
    python -m db.mock.generate            # 기본 시드
    python -m db.mock.generate --seed 7   # 다른 시드

같은 시드면 항상 같은 데이터가 나온다. 실행하면 DB 의 C1 테이블을 비우고 다시 채운 뒤,
같은 내용을 db/mock/out/<테이블>.csv 로도 저장한다.

v1 범위 (D2): 기본 매출 패턴과 과거 효과(축제, 국가대표 경기, 비).
데모 주간 사건(11/16~22 행사·경기, 손님 c_w01·c_m01, 불만 리뷰, 매출 이상)은 v2(D4)에서 심는다.
"""

import argparse
import csv
import json
import math
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import insert, text

from db import models
from db.session import engine

SEED = 20260817
KST = ZoneInfo("Asia/Seoul")
OUT_DIR = Path(__file__).parent / "out"

# 기간
START = date(2026, 8, 17)  # 월
END = date(2026, 11, 22)  # 일, 14주
WEATHER_END = date(2026, 11, 30)
DEMO_WEEK = (date(2026, 11, 16), date(2026, 11, 22))  # 비 없음
REVIEW_END = date(2026, 11, 10)  # 11/11 부터 리뷰는 v2 에서 심는다

STORE_ID = "s001"

# ── 매장 ─────────────────────────────────────────────
DAYPARTS = [
    {"key": "lunch", "start": "11:00", "end": "13:30"},
    {"key": "dinner", "start": "17:00", "end": "21:00"},
    {"key": "night", "start": "21:00", "end": "22:00"},
]
STORE = {
    "store_id": STORE_ID,
    "name": "한림국수",
    "category": "국수",
    "address": "강원특별자치도 춘천시 효자동 (가상)",
    "lat": 37.8692,
    "lng": 127.7442,
    "open_time": time(10, 0),
    "close_time": time(22, 0),
    "closed_weekdays": [],
    "dayparts": DAYPARTS,
    "busy_dayparts": ["lunch", "dinner"],
    "slots": ["10:00", "14:00", "21:30"],
}

# (이름, 분류, 가격)
MENU = [
    ("잔치국수", "main", 7000),
    ("비빔국수", "main", 8000),
    ("멸치국수", "main", 7500),
    ("칼국수", "main", 8500),
    ("들깨칼국수", "main", 9500),
    ("콩국수", "main", 9000),
    ("장칼국수", "main", 9000),
    ("김밥", "side", 4000),
    ("만두(5개)", "side", 5000),
    ("주먹밥", "side", 3500),
    ("콜라", "drink", 2000),
    ("사이다", "drink", 2000),
]
MAIN_WEIGHT = {"잔치국수": 20, "비빔국수": 15, "멸치국수": 10, "칼국수": 18, "들깨칼국수": 10, "장칼국수": 15}
KONGGUKSU_BY_MONTH = {8: 14, 9: 8, 10: 3, 11: 1}  # 콩국수는 여름 메뉴

STAFF = [("알바A", 10320), ("알바B", 10320), ("알바C", 10320)]

# ── 행사·경기 (모두 가상) ────────────────────────────
EVENTS = [
    # 과거 효과: 점심·저녁 +30% 안팎
    ("강원대 대동제", "univ_festival", datetime(2026, 9, 23, 10), datetime(2026, 9, 25, 23), 37.8690, 127.7460, 0.5),
    ("춘천 가을 지역 축제", "local_festival", datetime(2026, 10, 10, 10), datetime(2026, 10, 11, 21), 37.8800, 127.7300, 1.6),
    # 앞날 일정
    ("효자동 연말 플리마켓", "other", datetime(2026, 12, 5, 11), datetime(2026, 12, 6, 18), 37.8710, 127.7420, 0.6),
    ("춘천 겨울 빛 축제", "local_festival", datetime(2026, 12, 12, 17), datetime(2026, 12, 14, 22), 37.8810, 127.7290, 2.1),
]
FESTIVAL_DATES = {date(2026, 9, 23), date(2026, 9, 24), date(2026, 9, 25), date(2026, 10, 10), date(2026, 10, 11)}

GAMES = [
    # (종목, 수준, 제목, 시작)
    ("soccer", "national", "대한민국 vs 파라과이 (친선)", datetime(2026, 10, 14, 20, 0)),  # 저녁·야간 배달 +25%
    ("baseball", "pro", "프로야구 정규시즌", datetime(2026, 8, 26, 18, 30)),  # 이하 야구: 효과 없음
    ("baseball", "pro", "프로야구 정규시즌", datetime(2026, 9, 9, 18, 30)),
    ("baseball", "pro", "프로야구 정규시즌", datetime(2026, 9, 16, 18, 30)),
    ("baseball", "pro", "프로야구 정규시즌", datetime(2026, 9, 30, 18, 30)),
    ("baseball", "pro", "프로야구 포스트시즌", datetime(2026, 10, 20, 18, 30)),
    ("baseball", "pro", "프로야구 한국시리즈", datetime(2026, 10, 28, 18, 30)),
    ("soccer", "national", "대한민국 vs 우즈베키스탄 (친선)", datetime(2026, 12, 9, 20, 0)),  # 앞날
]
NATIONAL_GAME_DATES = {g[3].date() for g in GAMES if g[1] == "national"}

# ── 효과 크기 ────────────────────────────────────────
FESTIVAL_LIFT = (1.25, 1.35)  # 점심·저녁, 홀·배달 모두
GAME_DELIVERY_LIFT = 1.25  # 국가대표 경기 날 저녁·야간 배달
RAIN_DELIVERY_LIFT = 1.15  # 비 오는 날 배달 (하루 종일)
RAIN_MM = 5.0  # 이 이상이면 '비 오는 날'

# ── 주문량 ───────────────────────────────────────────
BASE_ORDERS_PER_DAY = 85
HALL_SHARE = 0.6
WEEKDAY_FACTOR = [1.0, 1.0, 1.0, 1.05, 1.15, 0.95, 0.9]  # 월~일
VACATION_FACTOR = 0.9  # 8월은 방학
# 10:00 부터 30분 단위 24칸의 상대 비중
HALL_SLOT_WEIGHT = [0.3, 0.5, 1.5, 3.0, 4.0, 3.5, 2.0, 0.8, 0.5, 0.4, 0.4, 0.4,
                    0.5, 0.8, 1.5, 2.2, 3.0, 3.0, 2.5, 1.8, 1.2, 0.8, 0.5, 0.3]
DELIVERY_SLOT_WEIGHT = [0.2, 0.3, 0.8, 1.5, 2.0, 1.8, 1.0, 0.6, 0.5, 0.5, 0.5, 0.5,
                        0.6, 0.8, 1.2, 1.8, 2.5, 2.6, 2.4, 2.0, 1.6, 1.3, 1.0, 0.8]
CUSTOMER_POOL = 500

# ── 리뷰 ─────────────────────────────────────────────
LINKED_CUSTOMERS = 30  # 주문 이력과 이어지는 리뷰 손님
LINKED_TWICE = 10  # 그중 리뷰를 2번 쓴 손님
UNLINKED_REVIEWS = 80
COMPLAINT_RATIO = 0.2

POSITIVE = [
    "{menu} 국물이 진하고 맛있어요. 또 시킬게요!",
    "면이 쫄깃해서 좋아요. {menu} 추천합니다.",
    "양도 많고 가성비 최고입니다.",
    "학교 근처에서 제일 자주 먹는 집이에요.",
    "사장님 친절하세요. {menu} 맛있게 먹었습니다.",
    "깔끔하고 맛있게 잘 먹었습니다.",
    "{menu} 처음 먹어봤는데 기대 이상이었어요.",
    "늘 먹던 맛 그대로라 좋아요.",
    "포장 꼼꼼하게 해주셔서 하나도 안 샜어요.",
    "김밥이랑 같이 먹으니 딱 좋네요.",
    "시험기간에 든든하게 잘 먹었어요.",
    "{menu} 간이 딱 맞아요. 단골 될 것 같아요.",
]
DELAY = [
    "주문하고 1시간 넘게 걸렸어요. 면이 다 불어서 왔네요.",
    "배달이 너무 늦어요. 예상 시간보다 40분 넘게 기다렸습니다.",
    "맛은 괜찮은데 배달이 늦어서 식어서 왔어요.",
    "배달 시간 안내가 틀려서 점심시간을 놓쳤어요.",
    "늦게 와서 국물이 미지근했어요. 다음엔 빨리 부탁드려요.",
    "50분 넘게 걸렸네요. 배달이 자주 늦는 것 같아요.",
]
TASTE = [
    "{menu} 국물이 너무 짜요.",
    "면이 덜 익어서 딱딱했어요.",
    "예전보다 맛이 싱거워졌어요.",
    "{menu}에서 비린 맛이 났어요.",
    "양념이 너무 달아서 별로였어요.",
    "{menu} 면이 퍼져서 식감이 별로예요.",
]


def kst(d: date, hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hour, minute, second, tzinfo=KST)


def days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def poisson(rng: random.Random, lam: float) -> int:
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def slot_daypart(slot: int) -> str | None:
    """slot 0 = 10:00~10:30. 30분 칸이 속한 시간대."""
    minutes = 10 * 60 + slot * 30
    for dp in DAYPARTS:
        h1, m1 = map(int, dp["start"].split(":"))
        h2, m2 = map(int, dp["end"].split(":"))
        if h1 * 60 + m1 <= minutes < h2 * 60 + m2:
            return dp["key"]
    return None


# ── 생성 ─────────────────────────────────────────────
def gen_weather(rng: random.Random) -> list[dict]:
    rain_prob = {8: 0.35, 9: 0.25, 10: 0.15, 11: 0.12}
    total = (WEATHER_END - START).days
    rows = []
    for d in days(START, WEATHER_END):
        t = (d - START).days / total
        temp_max = 31 - 22 * t + rng.uniform(-2.5, 2.5)  # 8월 중순 31도 → 11월 말 9도
        temp_min = temp_max - rng.uniform(7, 11)
        rainy = rng.random() < rain_prob[d.month] and not (DEMO_WEEK[0] <= d <= DEMO_WEEK[1])
        precip = round(rng.uniform(RAIN_MM, 40), 1) if rainy else 0.0
        rows.append({"date": d, "temp_max": round(temp_max, 1), "temp_min": round(temp_min, 1), "precip_mm": precip})
    return rows


def pick_items(rng: random.Random, d: date, channel: str, menu_ids: dict) -> list[tuple[str, int]]:
    weights = dict(MAIN_WEIGHT, 콩국수=KONGGUKSU_BY_MONTH[d.month])
    mains, mw = list(weights), list(weights.values())
    if channel == "hall":
        people = rng.choices([1, 2, 3, 4], [45, 35, 12, 8])[0]
        side_p, drink_p = 0.4, 0.25
    else:
        people = rng.choices([1, 2, 3], [50, 35, 15])[0]
        side_p, drink_p = 0.6, 0.2
    counts: dict[str, int] = {}
    for name in rng.choices(mains, mw, k=people):
        counts[name] = counts.get(name, 0) + 1
    if rng.random() < side_p:
        side = rng.choice(["김밥", "만두(5개)", "주먹밥"])
        counts[side] = counts.get(side, 0) + 1
    if rng.random() < drink_p:
        counts[rng.choice(["콜라", "사이다"])] = rng.randint(1, people)
    return list(counts.items())


def gen_orders(rng: random.Random, weather: dict[date, dict]):
    menu_ids = {name: i + 1 for i, (name, _, _) in enumerate(MENU)}
    prices = {name: price for name, _, price in MENU}
    customers = [f"c_{i:04d}" for i in range(1, CUSTOMER_POOL + 1)]
    cust_w = [1 / (i ** 0.8) for i in range(1, CUSTOMER_POOL + 1)]  # 단골일수록 자주 시킴
    hall_w = [w / sum(HALL_SLOT_WEIGHT) for w in HALL_SLOT_WEIGHT]
    deliv_w = [w / sum(DELIVERY_SLOT_WEIGHT) for w in DELIVERY_SLOT_WEIGHT]

    orders, items = [], []
    for d in days(START, END):
        total = BASE_ORDERS_PER_DAY * WEEKDAY_FACTOR[d.weekday()] * (VACATION_FACTOR if d.month == 8 else 1.0)
        festival = rng.uniform(*FESTIVAL_LIFT) if d in FESTIVAL_DATES else 1.0
        rainy = weather[d]["precip_mm"] >= RAIN_MM
        game = d in NATIONAL_GAME_DATES

        for slot in range(24):
            dp = slot_daypart(slot)
            for channel, share, w in (("hall", HALL_SHARE, hall_w), ("delivery", 1 - HALL_SHARE, deliv_w)):
                lam = total * share * w[slot]
                if dp in ("lunch", "dinner"):
                    lam *= festival
                if channel == "delivery":
                    if rainy:
                        lam *= RAIN_DELIVERY_LIFT
                    if game and dp in ("dinner", "night"):
                        lam *= GAME_DELIVERY_LIFT
                for _ in range(poisson(rng, lam)):
                    minute = slot * 30 + rng.randint(0, 29)
                    at = kst(d, 10 + minute // 60, minute % 60, rng.randint(0, 59))
                    cust = rng.choices(customers, cust_w)[0] if channel == "delivery" else None
                    picked = pick_items(rng, d, channel, menu_ids)
                    orders.append({"ordered_at": at, "channel": channel, "customer_key": cust,
                                   "_items": picked, "_amount": sum(prices[n] * q for n, q in picked)})

    orders.sort(key=lambda o: o["ordered_at"])
    rows = []
    for oid, o in enumerate(orders, start=1):
        rows.append({"order_id": oid, "store_id": STORE_ID, "ordered_at": o["ordered_at"],
                     "channel": o["channel"], "customer_key": o["customer_key"], "total_amount": o["_amount"]})
        for name, qty in o["_items"]:
            items.append({"order_id": oid, "menu_id": menu_ids[name], "quantity": qty, "unit_price": prices[name]})
        o["order_id"] = oid
    return rows, items, orders


def gen_reviews(rng: random.Random, orders: list[dict]) -> list[dict]:
    review_cut = kst(REVIEW_END, 12)  # 리뷰 작성이 11/10 안에 끝나도록 주문은 그 전까지만
    by_cust: dict[str, list[dict]] = {}
    for o in orders:
        if o["customer_key"] and o["ordered_at"] < review_cut:
            by_cust.setdefault(o["customer_key"], []).append(o)
    candidates = sorted(c for c, os in by_cust.items() if len(os) >= 2)
    linked = rng.sample(candidates, LINKED_CUSTOMERS)
    twice = set(rng.sample(linked, LINKED_TWICE))

    drafts = []
    for c in linked:
        for o in rng.sample(by_cust[c], 2 if c in twice else 1):
            at = o["ordered_at"] + timedelta(minutes=rng.randint(40, 600))
            drafts.append({"order": o, "customer_key": c, "written_at": at, "delivery": True})
    for _ in range(UNLINKED_REVIEWS):
        d = START + timedelta(days=rng.randint(0, (REVIEW_END - START).days))
        at = kst(d, rng.randint(11, 23), rng.randint(0, 59), rng.randint(0, 59))
        drafts.append({"order": None, "customer_key": None, "written_at": at, "delivery": rng.random() < 0.5})

    n_complaint = round(len(drafts) * COMPLAINT_RATIO)
    complaint_idx = rng.sample(range(len(drafts)), n_complaint)
    kinds = {i: ("delay" if j < n_complaint * 0.6 and drafts[i]["delivery"] else "taste")
             for j, i in enumerate(complaint_idx)}

    mains = [name for name, cat, _ in MENU if cat == "main"]
    rows = []
    for i, r in enumerate(drafts):
        menu = rng.choice(mains)
        kind = kinds.get(i, "positive")
        if kind == "positive":
            content, rating = rng.choice(POSITIVE), rng.choices([4, 5], [30, 70])[0]
        elif kind == "delay":
            content, rating = rng.choice(DELAY), rng.choice([2, 3])
        else:
            content, rating = rng.choice(TASTE), rng.choice([1, 2, 3])
        rows.append({"store_id": STORE_ID, "order_id": r["order"]["order_id"] if r["order"] else None,
                     "customer_key": r["customer_key"], "written_at": r["written_at"],
                     "rating": rating, "content": content.format(menu=menu), "complaint_type": None})
    rows.sort(key=lambda r: r["written_at"])
    for rid, r in enumerate(rows, start=1):
        r["review_id"] = rid
    return rows


def gen_shifts() -> list[dict]:
    # 요일별(월~일) 점심 담당, 저녁 담당. 금·토 저녁은 한 명 더.
    lunch = [1, 2, 3, 1, 2, 3, 1]
    dinner = [2, 3, 1, 2, 3, 1, 2]
    extra = {4: 3, 5: 2}
    rows = []
    for d in days(START, END):
        wd = d.weekday()
        rows.append((lunch[wd], kst(d, 10, 30), kst(d, 14)))
        rows.append((dinner[wd], kst(d, 16, 30), kst(d, 22)))
        if wd in extra:
            rows.append((extra[wd], kst(d, 17, 30), kst(d, 21, 30)))
    return [{"shift_id": i, "staff_id": s, "starts_at": a, "ends_at": b} for i, (s, a, b) in enumerate(rows, start=1)]


def build(seed: int) -> dict[str, list[dict]]:
    rng = random.Random(seed)
    weather = gen_weather(rng)
    orders, items, raw = gen_orders(rng, {w["date"]: w for w in weather})
    reviews = gen_reviews(rng, raw)
    return {
        "store": [STORE],
        "menu": [{"menu_id": i, "store_id": STORE_ID, "name": n, "category": c, "price": p}
                 for i, (n, c, p) in enumerate(MENU, start=1)],
        "staff": [{"staff_id": i, "store_id": STORE_ID, "name": n, "hourly_wage": w}
                  for i, (n, w) in enumerate(STAFF, start=1)],
        "shifts": gen_shifts(),
        "events": [{"event_id": i, "name": n, "kind": k, "starts_at": s.replace(tzinfo=KST),
                    "ends_at": e.replace(tzinfo=KST), "lat": la, "lng": ln, "distance_km": km}
                   for i, (n, k, s, e, la, ln, km) in enumerate(EVENTS, start=1)],
        "games": [{"game_id": i, "sport": s, "level": lv, "title": t, "starts_at": at.replace(tzinfo=KST)}
                  for i, (s, lv, t, at) in enumerate(GAMES, start=1)],
        "weather_daily": weather,
        "orders": orders,
        "order_items": items,
        "reviews": reviews,
    }


# ── 저장 ─────────────────────────────────────────────
TABLES = {
    "store": models.Store, "menu": models.Menu, "staff": models.Staff, "shifts": models.Shift,
    "events": models.Event, "games": models.Game, "weather_daily": models.WeatherDaily,
    "orders": models.Order, "order_items": models.OrderItem, "reviews": models.Review,
}


def to_csv_value(v):
    if v is None:
        return ""
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    return v


def write_csv(data: dict[str, list[dict]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, rows in data.items():
        cols = [c.name for c in TABLES[name].__table__.columns]
        with open(OUT_DIR / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for r in rows:
                w.writerow([to_csv_value(r[c]) for c in cols])


def load_db(data: dict[str, list[dict]]) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(TABLES) + " RESTART IDENTITY CASCADE"))
        for name, rows in data.items():  # 부모 테이블부터 넣도록 TABLES 순서와 같다
            conn.execute(insert(TABLES[name]), rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="목업 데이터 생성")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    data = build(args.seed)
    load_db(data)
    write_csv(data)

    per_day: dict[date, int] = {}
    for o in data["orders"]:
        d = o["ordered_at"].date()
        per_day[d] = per_day.get(d, 0) + 1
    deliv = sum(o["channel"] == "delivery" for o in data["orders"])
    print(f"seed={args.seed}")
    for name, rows in data.items():
        print(f"  {name:14s} {len(rows):6d}행")
    print(f"  하루 주문 {min(per_day.values())}~{max(per_day.values())}건, 배달 비중 {deliv / len(data['orders']):.0%}")
    print(f"  CSV → {OUT_DIR}")


if __name__ == "__main__":
    main()
