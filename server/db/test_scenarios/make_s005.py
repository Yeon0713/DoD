"""초옹장(s005) 시험 주간 데이터를 만든다: 2026-10-05(월) ~ 10-11(일).

팀 목업 파일(db/data/s005.db, common.db)은 고치지 않는다. 여기서 만든 s005.json 을 서버가 겹쳐 읽는다
(app/data_pipeline/test_scenario.py). 다시 만들려면 server 폴더에서:  python db/test_scenarios/make_s005.py

그 주에 할 일이 고루 나오게 넣는 것 (모두 시험용으로 지은 값)
- 날씨: 10/6 비, 10/7부터 추워져 10/8~10/11 최고기온 10도 아래 → 10/8부터 겨울 (계절 바뀜 → 메뉴판 바꾸기),
        10/12부터 다시 따뜻해져(팀 목업 날씨) 겨울이 끝남 → 메뉴판 되돌리기
- 행사: 가게 근처(약 0.3km) "남양 가을 축제" 10/10(토)~10/11(일) → 포스터, 메뉴판.
        행사 효과를 배우도록 9/19(토)~9/20(일)에 같은 곳 "남양 성지 음악회"와 그날 늘어난 주문을 넣는다
- 매출: 9/19~20, 10/10~11 점심·저녁에 주문을 더 넣어 행사 날 매출이 오른다
- 예약: 네이버 예약에서 동기화한 것처럼 (목업). 10/6 점심 4명 확정, 10/8 저녁 단체 15명 문의(사장님이 받으면 그날 저녁이 바빠짐),
        10/9 점심 단체 포장 20인분 확정, 11/20 저녁 12명 문의 (실제 오늘 기준 주에도 하나)
- 리뷰: 10/5~10/6 맛 불만 3건(7일 안 같은 불만 3건 → 반복 불만 개선) + 각 불만 빠른 답글,
        매달 오는 단골(c5_0104)의 9/6 리뷰 → 9/12 답글 → 4주 뒤 10/10 재주문 권유
"""

import datetime as dt
import json
import random
from pathlib import Path

OUT = Path(__file__).with_name("s005.json")
KST = dt.timezone(dt.timedelta(hours=9))
NEAR = {"lat": 37.2088, "lng": 126.8296}  # 초옹장(37.2066, 126.8273)에서 약 0.3km

# 메뉴 (db/data/s005.db menu 표): id → 가격
MAINS = {1: 11000, 2: 11000, 3: 12000, 4: 12000, 5: 10000, 6: 10000, 7: 9000, 8: 18000, 10: 15000}
SIDES = {11: 8000, 12: 12000, 13: 7000}
DRINKS = {14: 4000, 15: 4000, 16: 8000, 18: 2000}


def at(day: str, hh: int, mm: int, ss: int = 0) -> str:
    y, m, d = map(int, day.split("-"))
    return dt.datetime(y, m, d, hh, mm, ss, tzinfo=KST).isoformat()


def weather() -> list[dict]:
    rows = [
        ("2026-10-06", 17.0, 11.0, 18.0),  # 비
        ("2026-10-07", 12.5, 6.0, 0.0),
        ("2026-10-08", 9.0, 2.5, 0.0),  # 여기부터 3일 연속 10도 아래 → 10/8 부터 겨울
        ("2026-10-09", 8.0, 1.0, 0.0),
        ("2026-10-10", 9.5, 2.0, 0.0),
        ("2026-10-11", 9.0, 3.0, 2.0),
    ]
    return [{"date": d, "temp_max": hi, "temp_min": lo, "precip_mm": rain} for d, hi, lo, rain in rows]


def events() -> list[dict]:
    return [
        {"event_id": 9001, "name": "남양 성지 음악회", "kind": "local_festival", "starts_at": at("2026-09-19", 11, 0), "ends_at": at("2026-09-20", 20, 0), **NEAR, "distance_km": 0.3},
        {"event_id": 9002, "name": "남양 가을 축제", "kind": "local_festival", "starts_at": at("2026-10-10", 11, 0), "ends_at": at("2026-10-11", 20, 0), **NEAR, "distance_km": 0.3},
    ]


def orders(rng: random.Random) -> list[dict]:
    """행사 날 늘어난 주문. 점심(11:00~14:00) 20건, 저녁(17:00~20:00) 17건씩."""
    rows, order_id = [], 9_000_001
    for day in ("2026-09-19", "2026-09-20", "2026-10-10", "2026-10-11"):
        for start, end, count in ((11 * 60, 14 * 60, 20), (17 * 60, 20 * 60, 17)):
            for _ in range(count):
                minute = rng.randint(start, end - 1)
                items = [{"menu_id": m, "quantity": rng.choice([1, 1, 2]), "unit_price": MAINS[m]} for m in rng.sample(sorted(MAINS), rng.choice([1, 2]))]
                if rng.random() < 0.4:
                    s = rng.choice(sorted(SIDES))
                    items.append({"menu_id": s, "quantity": 1, "unit_price": SIDES[s]})
                if rng.random() < 0.3:
                    d = rng.choice(sorted(DRINKS))
                    items.append({"menu_id": d, "quantity": rng.choice([1, 2]), "unit_price": DRINKS[d]})
                channel = "delivery" if rng.random() < 0.3 else "hall"
                rows.append({
                    "order_id": order_id,
                    "ordered_at": at(day, minute // 60, minute % 60, rng.randint(0, 59)),
                    "channel": channel,
                    "customer_key": f"cx_{order_id % 100000:05d}" if channel == "delivery" else None,
                    "total_amount": sum(i["quantity"] * i["unit_price"] for i in items),
                    "items": items,
                })
                order_id += 1
    return sorted(rows, key=lambda r: r["ordered_at"])


def reviews() -> list[dict]:
    return [
        # 매달 오는 단골 c5_0104 의 9/6 배달 주문(14853)에 단 리뷰 → 9/12(토) 답글 → 10/10(토) 재주문 권유
        {"review_id": 900001, "order_id": 14853, "customer_key": "c5_0104", "written_at": at("2026-09-06", 19, 40), "rating": 5,
         "content": "들깨옹심이 늘 먹던 그 맛이에요. 다음 달에도 또 시킬게요!", "complaint_type": None},
        # 맛 불만 3건 (7일 안) → 반복 불만 개선. 각각 빠른 답글도 나온다
        {"review_id": 900002, "order_id": None, "customer_key": None, "written_at": at("2026-10-05", 19, 10), "rating": 2,
         "content": "국물이 너무 짜요. 예전 맛이 아니네요.", "complaint_type": "taste"},
        {"review_id": 900003, "order_id": None, "customer_key": None, "written_at": at("2026-10-06", 12, 40), "rating": 2,
         "content": "칼국수 면이 다 퍼졌어요. 맛이 변했어요.", "complaint_type": "taste"},
        {"review_id": 900004, "order_id": None, "customer_key": None, "written_at": at("2026-10-06", 18, 30), "rating": 1,
         "content": "옹심이가 덜 익었고 국물도 싱거워요.", "complaint_type": "taste"},
    ]


def reservations() -> list[dict]:
    """네이버 예약에서 받아 온 것처럼 넣는 예약 (이름은 가린 꼴, 모두 지어낸 값)"""
    return [
        {"external_id": "naver-1001", "kind": "RESERVATION", "at": at("2026-10-06", 12, 0), "people": 4, "name": "김*진", "memo": "창가 자리 부탁드려요", "status": "CONFIRMED"},
        {"external_id": "naver-1002", "kind": "RESERVATION", "at": at("2026-10-08", 18, 30), "people": 15, "name": "이*호", "memo": "부서 회식이에요. 수육 미리 준비 부탁드려요", "status": "REQUESTED"},
        {"external_id": "naver-1003", "kind": "GROUP_ORDER", "at": at("2026-10-09", 11, 30), "people": 20, "name": "박*연", "memo": "포장 단체 주문 (초계국수 10, 장칼국수 10)", "status": "CONFIRMED"},
        {"external_id": "naver-1004", "kind": "RESERVATION", "at": at("2026-11-20", 18, 0), "people": 12, "name": "최*아", "memo": "동창 모임이에요", "status": "REQUESTED"},
    ]


def main() -> None:
    rng = random.Random("s005-oct-week2")
    doc = {
        "_설명": "초옹장(s005) 시험 주간 2026-10-05(월)~10-11(일). 팀 목업 파일을 고치지 않고 서버가 겹쳐 읽는다. 만드는 법과 넣은 것은 make_s005.py, docs/test-week.md",
        "store_id": "s005",
        "week": {"start": "2026-10-05", "end": "2026-10-11"},
        "weather": weather(),
        "events": events(),
        "orders": orders(rng),
        "reviews": reviews(),
        "reservations": reservations(),
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{OUT.name}: 주문 {len(doc['orders'])}건, 리뷰 {len(doc['reviews'])}건, 행사 {len(doc['events'])}개, 날씨 {len(doc['weather'])}일, 예약 {len(doc['reservations'])}건")


if __name__ == "__main__":
    main()
