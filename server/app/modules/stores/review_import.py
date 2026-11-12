"""리뷰 불러오기 (배민, 네이버, 쿠팡이츠).

진짜로는 각 플랫폼 사장님 화면에서 리뷰를 크롤링해 온다 (아직 없음).
지금은 시험용 목업 리뷰를 만든다: 가게 메뉴 이름을 넣은 글, 최근 60일에 흩어진 날짜, 이번 주 좋은 리뷰,
그리고 불러온 날 새벽의 불만 리뷰를 넣어 그날 바로 할 일(사과 답글, 반복 불만 점검)이 생기게 한다.
같은 가게·같은 플랫폼은 늘 같은 리뷰가 나온다 (난수 씨앗을 가게 id 와 플랫폼으로 정한다).
"""

import datetime as dt
import random

from app.core.seoul_time import now_seoul

PLATFORMS = ("BAEMIN", "NAVER", "COUPANG")
PLATFORM_NAMES = {"BAEMIN": "배민", "NAVER": "네이버", "COUPANG": "쿠팡이츠"}
HOW_MANY = {"BAEMIN": 24, "NAVER": 18, "COUPANG": 12}

GOOD = [
    "{menu} 정말 맛있어요. 또 시킬게요!",
    "{menu} 바삭하고 촉촉해요. 양도 넉넉해요.",
    "포장이 꼼꼼해서 하나도 안 식었어요. {menu} 최고예요.",
    "사장님 친절하시고 {menu} 맛있게 잘 먹었습니다.",
    "{menu} 먹으러 일부러 왔어요. 만족합니다.",
    "깔끔하고 맛있게 잘 먹었습니다.",
    "{menu} 소스가 진하고 좋아요. 추천합니다.",
]
DELIVERY_LATE = [
    "배달이 50분 넘게 걸려서 {menu}가 다 식었어요.",
    "주문하고 한 시간 가까이 기다렸어요. 맛은 괜찮은데 너무 늦어요.",
]
TASTE_BAD = [
    "{menu}가 너무 짜요. 예전 맛이 아니네요.",
    "{menu} 튀김이 덜 익은 느낌이었어요.",
]


def make_reviews(store_id: str, platform: str, menus: list[str], open_hour: int, close_hour: int, regulars: list[str] | None = None) -> list[dict]:
    """그 플랫폼 목업 리뷰. 칸: written_at, rating, content, complaint_type (DB 규칙: none, delivery_delay, taste)"""
    rng = random.Random(f"{store_id}:{platform}")
    now = now_seoul()
    menus = menus or ["대표 메뉴"]
    delivery = platform != "NAVER"  # 네이버 리뷰는 매장 손님, 배민·쿠팡이츠는 배달 손님
    rows = []

    def at(days_ago: int) -> dt.datetime:
        day = now - dt.timedelta(days=days_ago)
        hour = rng.randint(open_hour, max(open_hour, close_hour - 1))
        return day.replace(hour=hour, minute=rng.randint(0, 59), second=0, microsecond=0)

    def add(written_at: dt.datetime, kind: str, customer_key: str | None = None) -> None:
        if written_at > now:
            written_at = now - dt.timedelta(minutes=rng.randint(10, 90))
        menu = rng.choice(menus)
        if kind == "late":
            rows.append({"written_at": written_at, "rating": 2, "content": rng.choice(DELIVERY_LATE).format(menu=menu), "complaint_type": "delivery_delay"})
        elif kind == "taste":
            rows.append({"written_at": written_at, "rating": 2, "content": rng.choice(TASTE_BAD).format(menu=menu), "complaint_type": "taste"})
        else:
            rows.append({"written_at": written_at, "rating": rng.choice([5, 5, 5, 4]), "content": rng.choice(GOOD).format(menu=menu), "complaint_type": "none"})
        if customer_key:
            rows[-1]["customer_key"] = customer_key

    def this_morning(hour: int, minute: int) -> dt.datetime:
        """오늘 새벽 (문 열기 전). 아직 그 시각 전이면 조금 전으로."""
        return min(now.replace(hour=hour, minute=minute, second=0, microsecond=0), now - dt.timedelta(minutes=10))

    total = HOW_MANY[platform]
    # 오늘 할 일이 되는 리뷰: 오늘 새벽 불만 1건 (문 열기 전 알림에 바로 사과 답글)
    #   배민·쿠팡이츠는 배달 지연, 네이버는 맛 불만. 배달 지연이 7일 안에 3건이 되어 오늘 오후 개선 점검도 생긴다
    if platform == "BAEMIN":
        add(this_morning(0, 40), "late")
        add(at(3), "late")
    elif platform == "COUPANG":
        add(this_morning(1, 10), "late")
    else:
        add(this_morning(0, 20), "taste")
    # 이번 주 좋은 리뷰 2건 (토요일 답글 묶음). 배달 플랫폼은 그중 1건을 단골 손님이 쓴 것으로 (단골 답글·재주문 인사 일)
    regular = rng.choice(regulars) if delivery and regulars else None
    add(at(rng.randint(1, 3)), "good", regular)
    add(at(rng.randint(1, 3)), "good")
    # 지난 60일: 대부분 좋은 리뷰, 가끔 불만 (최근 7일 밖)
    for _ in range(total - len(rows)):
        roll = rng.random()
        kind = "late" if delivery and roll < 0.12 else "taste" if roll < 0.18 else "good"
        add(at(rng.randint(8, 60)), kind)
    rows.sort(key=lambda r: r["written_at"])
    return rows
