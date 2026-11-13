"""목업 생성기: 가게 5곳의 2026년 1년치 데이터 (s001~s003 은 춘천 대학가 가상 가게, s004·s005 는 실제 가게 정보에 가상 주문).

server/ 폴더에서 실행:
    python -m db.mock.generate            # 기본 시드
    python -m db.mock.generate --seed 7   # 다른 시드

같은 시드면 항상 같은 데이터가 나온다. 실행하면 개발 DB 파일(db/data/*.db)을 새로 만들고,
같은 내용을 CSV 로도 저장한다.
- 매장 전용 테이블 → db/data/<매장>.db (s001.orders ...), db/mock/out/<매장>/<테이블>.csv
- 공통 테이블(events, games, weather_daily) → db/data/common.db, db/mock/out/common/<테이블>.csv

- 매장: s001 한림국수, s002 두리맥주(17시~다음 날 3시), s003 석사돈가스, s004 피플스클럽(돈가스·라멘, 주말은 점심만),
  s005 초옹장(화성 남양읍 옹심이·국수, 매일 영업).
  메뉴·영업시간·주문 패턴·알바·리뷰 문구가 매장마다 다르다.
- 매출·근무·날씨: 2026-01-01 ~ 12-31. 계절, 방학, 행사, 국가대표 경기, 비 효과를 넣었다.
- 리뷰: 11/10 까지 (s004·s005 는 11/13 까지 덧붙인다). 데모 주간 사건(11/16~22 행사·경기, 손님 c_w01·c_m01, 불만 리뷰, 매출 이상)은 v2(D4)에서 심는다.
"""

import argparse
import csv
import json
import math
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import insert
from sqlalchemy.schema import CreateIndex, CreateTable

from db import models
from db.session import DATA_DIR, engine, store_engine

SEED = 20260817
KST = ZoneInfo("Asia/Seoul")
OUT_DIR = Path(__file__).parent / "out"

# 기간
START = date(2026, 1, 1)  # 목
END = date(2026, 12, 31)
DEMO_WEEK = (date(2026, 11, 16), date(2026, 11, 22))  # 비 없음
REVIEW_END = date(2026, 11, 10)  # 11/11 부터 리뷰는 v2 에서 심는다

# ── 매장 ─────────────────────────────────────────────
# 메뉴: (이름, 분류, 가격). main_weight: 메인 메뉴 고르는 비중. seasonal: 월(1~12)별 비중이 바뀌는 메인 메뉴.
# slot_weight: 영업 시작부터 30분 단위 칸의 상대 주문 비중 (0 = 브레이크타임).
# shift_slots: 근무 칸 (출근, 퇴근). shift_template: 요일(0=월)별 {칸: 매장 안 알바 번호(1~5)}. 휴무 요일은 비운다.
STORES = [
    {
        "store": {
            "store_id": "s001",
            "name": "한림국수",
            "category": "국수",
            "address": "강원특별자치도 춘천시 효자동 (가상)",
            "lat": 37.8692,
            "lng": 127.7442,
            "open_time": time(10, 0),
            "close_time": time(22, 0),
            "closed_weekdays": [],
            "slots": ["10:00", "14:00", "21:30"],
        },
        "menu": [
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
        ],
        "main_weight": {"잔치국수": 20, "비빔국수": 15, "멸치국수": 10, "칼국수": 18, "들깨칼국수": 10, "장칼국수": 15},
        "seasonal": {"콩국수": [0, 0, 0, 1, 4, 10, 15, 14, 8, 3, 1, 0]},  # 여름 메뉴
        "side_p": {"hall": 0.4, "delivery": 0.6},
        "drink_p": {"hall": 0.25, "delivery": 0.2},
        "base_orders": 85,
        "hall_share": 0.6,
        "weekday_factor": [1.0, 1.0, 1.0, 1.05, 1.15, 0.95, 0.9],  # 월~일
        "hall_slot_weight": [0.3, 0.5, 1.5, 3.0, 4.0, 3.5, 2.0, 0.8, 0.5, 0.4, 0.4, 0.4,
                             0.5, 0.8, 1.5, 2.2, 3.0, 3.0, 2.5, 1.8, 1.2, 0.8, 0.5, 0.3],
        "delivery_slot_weight": [0.2, 0.3, 0.8, 1.5, 2.0, 1.8, 1.0, 0.6, 0.5, 0.5, 0.5, 0.5,
                                 0.6, 0.8, 1.2, 1.8, 2.5, 2.6, 2.4, 2.0, 1.6, 1.3, 1.0, 0.8],
        "customer_pool": 1200,
        "staff": [("김민준", 10320), ("이서연", 10320), ("박도윤", 10320), ("최하은", 10320), ("정우진", 10320)],
        # 영업 10:00~22:00 내내 동시 근무 2~3명. 교대는 15:30, 16:30 두 번에 나눈다.
        "shift_slots": {
            "open1": ((9, 30), (15, 30)),
            "open2": ((10, 0), (16, 30)),
            "close1": ((15, 30), (22, 30)),
            "close2": ((16, 30), (22, 0)),
            "lunch": ((11, 0), (14, 0)),  # 보조
            "dinner": ((17, 0), (21, 0)),  # 보조
        },
        # 1인 주 6일 (이서연만 주 5일). 3명은 가장 바쁜 금요일 점심·저녁만.
        "shift_template": {
            0: {"open1": 2, "open2": 3, "close1": 4, "close2": 5},  # 김민준 휴무
            1: {"open1": 3, "open2": 4, "close1": 5, "close2": 1},  # 이서연 휴무
            2: {"open1": 4, "open2": 5, "close1": 1, "close2": 2},  # 박도윤 휴무
            3: {"open1": 5, "open2": 1, "close1": 2, "close2": 3},  # 최하은 휴무
            4: {"open1": 1, "open2": 2, "close1": 3, "close2": 4, "lunch": 5, "dinner": 5},
            5: {"open1": 2, "open2": 3, "close1": 4, "close2": 1},  # 정우진 휴무
            6: {"open1": 4, "open2": 5, "close1": 1, "close2": 3},  # 이서연 휴무
        },
        "reviews": {"linked": 80, "linked_twice": 30, "unlinked": 220},
        "positive": [
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
            "추운 날 {menu} 먹으니까 몸이 녹네요.",
            "국물까지 다 마셨어요. {menu} 진짜 맛있어요.",
            "가격이 조금 올랐어도 이 정도 맛이면 만족해요.",
        ],
        "taste": [
            "{menu} 국물이 너무 짜요.",
            "면이 덜 익어서 딱딱했어요.",
            "예전보다 맛이 싱거워졌어요.",
            "{menu}에서 비린 맛이 났어요.",
            "양념이 너무 달아서 별로였어요.",
            "{menu} 면이 퍼져서 식감이 별로예요.",
        ],
        "mixed": [
            "{menu} 맛있는데 국물이 조금 짰어요.",
            "맛은 좋지만 면이 살짝 퍼져서 아쉬워요.",
            "{menu} 괜찮았어요. 다만 포장 용기가 좀 작아서 넘칠 뻔했어요.",
        ],
    },
    {
        "store": {
            "store_id": "s002",
            "name": "두리맥주",
            "category": "맥주",
            "address": "강원특별자치도 춘천시 효자동 강원대 후문 (가상)",
            "lat": 37.8721,
            "lng": 127.7468,
            "open_time": time(17, 0),
            "close_time": time(3, 0),  # 다음 날 새벽 3시
            "closed_weekdays": [],
            "slots": ["16:30", "18:00", "02:30"],
        },
        "menu": [
            ("후라이드치킨", "main", 18000),
            ("양념치킨", "main", 19000),
            ("골뱅이무침", "main", 17000),
            ("모둠소시지", "main", 15000),
            ("먹태구이", "main", 14000),
            ("나쵸", "main", 11000),
            ("어묵탕", "main", 15000),
            ("수박화채", "main", 13000),
            ("감자튀김", "side", 7000),
            ("치즈스틱", "side", 6000),
            ("마른안주", "side", 8000),
            ("생맥주(500cc)", "drink", 4500),
            ("병맥주", "drink", 5000),
            ("소주", "drink", 5000),
            ("하이볼", "drink", 7000),
        ],
        "main_weight": {"후라이드치킨": 22, "양념치킨": 18, "골뱅이무침": 12, "모둠소시지": 12, "먹태구이": 14, "나쵸": 8},
        "seasonal": {
            "어묵탕": [14, 12, 8, 4, 2, 1, 0, 0, 2, 5, 10, 14],  # 겨울 안주
            "수박화채": [0, 0, 0, 0, 2, 8, 12, 12, 4, 0, 0, 0],  # 여름 안주
        },
        # 술집은 손님이 여럿이 와서 안주를 나눠 먹고 술을 여러 잔 시킨다.
        "people": {"hall": ([2, 3, 4, 5, 6], [40, 25, 20, 10, 5]), "delivery": ([1, 2, 3, 4], [25, 45, 20, 10])},
        "mains_per_person": 0.5,
        "drinks_per_person": 2,
        "side_p": {"hall": 0.5, "delivery": 0.6},
        "drink_p": {"hall": 0.97, "delivery": 0.6},
        "base_orders": 45,
        "hall_share": 0.75,
        "weekday_factor": [0.7, 0.8, 0.9, 1.0, 1.4, 1.45, 0.75],  # 금·토 밤에 몰린다
        # 17:00~03:00, 20칸. 20~21시가 가장 붐비고 자정 넘어 줄어든다.
        "hall_slot_weight": [0.5, 0.8, 1.5, 2.2, 3.0, 3.5, 3.8, 3.8, 3.5, 3.2,
                             2.8, 2.5, 2.0, 1.6, 1.2, 0.9, 0.6, 0.4, 0.25, 0.1],
        "delivery_slot_weight": [0.3, 0.5, 0.8, 1.2, 1.6, 2.0, 2.2, 2.4, 2.5, 2.5,
                                 2.4, 2.3, 2.2, 2.0, 1.8, 1.5, 1.2, 0.9, 0.6, 0.3],
        "customer_pool": 800,
        "staff": [("배수현", 10320), ("유하람", 10320), ("문서준", 10320), ("장예은", 10320), ("송태민", 10320)],
        # 영업 17:00~03:00. 교대는 21:30~23:00 사이에 겹쳐서 한다. 금·토는 피크 보조 1명을 더 둔다.
        "shift_slots": {
            "open1": ((16, 30), (22, 30)),
            "open2": ((17, 0), (23, 0)),
            "close1": ((21, 30), (3, 30)),  # 다음 날 새벽에 퇴근
            "close2": ((22, 0), (3, 0)),
            "peak": ((19, 0), (1, 0)),  # 보조
        },
        # 1인 주 6일. 월~목·일에 한 명씩 쉬고 금·토는 전원 근무.
        "shift_template": {
            0: {"open1": 2, "open2": 3, "close1": 4, "close2": 5},  # 배수현 휴무
            1: {"open1": 3, "open2": 4, "close1": 5, "close2": 1},  # 유하람 휴무
            2: {"open1": 4, "open2": 5, "close1": 1, "close2": 2},  # 문서준 휴무
            3: {"open1": 5, "open2": 1, "close1": 2, "close2": 3},  # 장예은 휴무
            4: {"open1": 1, "open2": 2, "close1": 3, "close2": 4, "peak": 5},
            5: {"open1": 2, "open2": 3, "close1": 4, "close2": 5, "peak": 1},
            6: {"open1": 1, "open2": 2, "close1": 3, "close2": 4},  # 송태민 휴무
        },
        "reviews": {"linked": 70, "linked_twice": 25, "unlinked": 200},
        "positive": [
            "{menu} 바삭하고 맥주랑 찰떡이에요!",
            "생맥주가 시원하고 거품도 적당해요.",
            "친구들이랑 2차로 왔는데 분위기 좋아요.",
            "{menu} 양 많고 맛있어요. 또 올게요!",
            "새벽 3시까지 해서 시험 끝나고 오기 딱이에요.",
            "사장님 친절하시고 안주가 빨리 나와요.",
            "{menu} 처음 먹어봤는데 추천합니다.",
            "가격 대비 안주 구성이 좋아요.",
            "배달로 시켰는데 치킨이 눅눅하지 않았어요.",
            "하이볼이 진하고 맛있어요.",
            "새벽까지 하는 집 중에 여기가 제일 나아요.",
            "가격이 조금 올랐지만 그래도 만족해요.",
        ],
        "taste": [
            "{menu} 너무 짜요. 맥주만 계속 마셨네요.",
            "치킨 속이 덜 익은 것 같았어요.",
            "{menu} 기름이 너무 많고 맛이 별로예요.",
            "생맥주 맛이 이상해요. 김이 다 빠졌어요.",
            "{menu} 양념이 너무 달아서 별로였어요.",
            "먹태가 딱딱하고 비린 맛이 났어요.",
        ],
        "mixed": [
            "{menu} 맛있는데 조금 짰어요.",
            "분위기는 좋지만 자리가 좁아서 아쉬워요.",
            "{menu} 괜찮았어요. 다만 음악 소리가 커서 대화하기 힘들었어요.",
        ],
        "delay": [
            "주문하고 1시간 넘게 걸렸어요. 치킨이 다 식어서 왔네요.",
            "배달이 너무 늦어요. 예상 시간보다 40분 넘게 기다렸습니다.",
            "맛은 괜찮은데 배달이 늦어서 식어서 왔어요.",
            "새벽에 시켰는데 한 시간 가까이 걸렸어요.",
            "50분 넘게 걸렸네요. 배달이 자주 늦는 것 같아요.",
        ],
    },
    {
        "store": {
            "store_id": "s003",
            "name": "석사돈가스",
            "category": "돈가스",
            "address": "강원특별자치도 춘천시 석사동 (가상)",
            "lat": 37.8565,
            "lng": 127.7480,
            "open_time": time(11, 0),
            "close_time": time(21, 0),
            "closed_weekdays": ["MON"],  # 월요일 휴무
            "slots": ["10:30", "15:30", "20:30"],
        },
        "menu": [
            ("등심돈가스", "main", 9500),
            ("안심돈가스", "main", 10500),
            ("치즈돈가스", "main", 11000),
            ("카레돈가스", "main", 10500),
            ("생선가스", "main", 10000),
            ("냉모밀", "main", 8500),
            ("미니우동", "side", 3000),
            ("고구마치즈볼", "side", 4000),
            ("샐러드", "side", 3500),
            ("콜라", "drink", 2000),
            ("제로콜라", "drink", 2000),
        ],
        "main_weight": {"등심돈가스": 30, "안심돈가스": 15, "치즈돈가스": 20, "카레돈가스": 12, "생선가스": 8},
        "seasonal": {"냉모밀": [0, 0, 1, 3, 8, 14, 18, 16, 8, 2, 0, 0]},  # 여름 메뉴
        "side_p": {"hall": 0.35, "delivery": 0.5},
        "drink_p": {"hall": 0.3, "delivery": 0.25},
        "base_orders": 60,
        "hall_share": 0.7,
        "weekday_factor": [0.0, 0.95, 0.95, 1.0, 1.05, 1.2, 1.15],  # 월요일 휴무, 주말 가족 손님
        # 11:00~21:00, 20칸. 15:00~17:00 브레이크타임(주문 없음).
        "hall_slot_weight": [1.5, 3.0, 4.0, 4.0, 2.5, 1.5, 1.0, 0.6, 0.0, 0.0, 0.0, 0.0,
                             1.5, 2.5, 3.5, 3.5, 2.5, 1.5, 0.8, 0.3],
        "delivery_slot_weight": [0.8, 1.5, 2.0, 2.0, 1.5, 1.0, 0.8, 0.5, 0.0, 0.0, 0.0, 0.0,
                                 1.2, 2.0, 2.5, 2.5, 2.0, 1.5, 1.0, 0.5],
        "customer_pool": 700,
        "staff": [("오지훈", 10320), ("서다인", 10320), ("신재원", 10320), ("권나연", 10320), ("황준서", 10320)],
        # 영업 11:00~21:00, 브레이크 15:00~17:00. 점심조·저녁조로 나눈다. 금~일은 점심 보조 1명.
        "shift_slots": {
            "open1": ((10, 30), (15, 30)),
            "open2": ((11, 0), (15, 0)),
            "close1": ((16, 30), (21, 30)),
            "close2": ((17, 0), (21, 0)),
            "lunch": ((11, 30), (14, 0)),  # 보조
        },
        # 월요일 휴무. 1인 주 5일 안팎.
        "shift_template": {
            1: {"open1": 1, "open2": 2, "close1": 3, "close2": 4},  # 황준서 휴무
            2: {"open1": 2, "open2": 3, "close1": 4, "close2": 5},  # 오지훈 휴무
            3: {"open1": 3, "open2": 4, "close1": 5, "close2": 1},  # 서다인 휴무
            4: {"open1": 4, "open2": 5, "close1": 1, "close2": 2, "lunch": 3},
            5: {"open1": 5, "open2": 1, "close1": 2, "close2": 3, "lunch": 4},
            6: {"open1": 1, "open2": 2, "close1": 3, "close2": 4, "lunch": 5},
        },
        "reviews": {"linked": 50, "linked_twice": 20, "unlinked": 150},
        "positive": [
            "{menu} 튀김옷이 바삭하고 고기가 두꺼워요.",
            "{menu} 소스가 맛있어요. 또 시킬게요!",
            "가족이랑 주말에 왔는데 다들 만족했어요.",
            "양도 많고 가성비 좋아요.",
            "배달인데도 눅눅하지 않고 바삭했어요.",
            "치즈가 쭉 늘어나서 사진 찍기 좋아요. 맛도 최고!",
            "사장님 친절하시고 가게가 깔끔해요.",
            "{menu} 처음 먹어봤는데 추천합니다.",
            "점심에 든든하게 잘 먹었습니다.",
            "샐러드 드레싱까지 맛있어요.",
            "더운 날 냉모밀 시원하게 잘 먹었어요.",
            "가격이 만 원 넘지만 그 값 해요.",
        ],
        "taste": [
            "{menu} 고기가 질기고 맛이 별로예요.",
            "튀김옷이 너무 두껍고 맛없어요.",
            "{menu} 소스가 너무 짜요.",
            "속이 덜 익은 것 같았어요.",
            "{menu} 기름 냄새가 심하고 맛이 별로예요.",
            "예전보다 소스가 싱거워졌어요.",
        ],
        "mixed": [
            "{menu} 맛있는데 배달이라 조금 눅눅했어요.",
            "맛은 좋지만 소스가 조금 짰어요.",
            "{menu} 괜찮았어요. 다만 양배추가 좀 적어서 아쉬워요.",
        ],
    },
    {
        # 실제 가게. 주소·좌표·영업시간·메인 메뉴(이름·가격)는 네이버 지도 가게 화면(2026-11-13)을 따랐다.
        # 토핑(side)·음료(drink)는 네이버에 없어 넣은 가상 메뉴다. 주문·리뷰·알바는 모두 가상.
        "store": {
            "store_id": "s004",
            "name": "피플스클럽",
            "category": "돈가스",
            "address": "강원특별자치도 춘천시 우석로67번길 12 1층",
            "lat": 37.8653181,
            "lng": 127.7516618,
            "open_time": time(11, 0),  # 평일 11:00~20:30, 브레이크 14:30~17:00. 주말은 11:30~14:30 점심만
            "close_time": time(20, 30),
            "closed_weekdays": [],  # 휴무일은 네이버 소식·인스타로 따로 알린다
            "slots": ["10:30", "15:00", "20:00"],
        },
        "menu": [
            ("로스카츠", "main", 12500),
            ("히레카츠", "main", 14000),
            ("특로스카츠", "main", 17000),
            ("히레+치즈", "main", 14000),
            ("난축로스", "main", 15000),
            ("난축특로스카츠", "main", 18000),
            ("돈코츠라멘", "main", 11000),
            ("미소라멘", "main", 11000),
            ("마제멘", "main", 12000),
            ("돈코츠set", "main", 16000),
            ("미소 set", "main", 16000),
            ("마제 set", "main", 17000),
            ("아지타마고 추가", "side", 2000),
            ("차슈 추가", "side", 3000),
            ("콜라", "drink", 2000),
            ("사이다", "drink", 2000),
            ("제로콜라", "drink", 2000),
        ],
        "main_weight": {"로스카츠": 25, "히레카츠": 15, "특로스카츠": 8, "히레+치즈": 10, "난축로스": 6,
                        "난축특로스카츠": 4, "돈코츠set": 6, "미소 set": 4, "마제 set": 4},
        "seasonal": {
            "돈코츠라멘": [14, 13, 11, 9, 7, 5, 4, 4, 6, 9, 12, 14],  # 추울수록 국물 라멘
            "미소라멘": [10, 9, 8, 6, 4, 3, 2, 2, 4, 6, 8, 10],
            "마제멘": [5, 5, 6, 7, 9, 11, 12, 12, 9, 7, 6, 5],  # 국물 없는 라멘은 여름에 조금 더
        },
        "side_p": {"hall": 0.15, "delivery": 0.1},
        "drink_p": {"hall": 0.3, "delivery": 0.25},
        "base_orders": 55,
        "hall_share": 0.7,
        # 주말은 점심(3시간)만 여는데 점심 손님이 평일보다 40% 안팎 많다
        "weekday_factor": [0.95, 0.95, 1.0, 1.0, 1.1, 1.5, 1.45],
        # 11:00~20:30, 19칸. 14:30~17:00 브레이크타임(주문 없음).
        "hall_slot_weight": [1.5, 3.0, 4.5, 4.5, 3.0, 1.8, 0.8, 0.0, 0.0, 0.0, 0.0, 0.0,
                             1.2, 2.5, 3.5, 3.2, 2.2, 1.2, 0.4],
        "delivery_slot_weight": [0.8, 1.5, 2.2, 2.2, 1.6, 1.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0,
                                 1.0, 1.8, 2.4, 2.4, 2.0, 1.4, 0.6],
        "open_slots_by_weekday": {5: (1, 7), 6: (1, 7)},  # 토·일은 11:30~14:30 칸만
        "customer_pool": 600,
        "staff": [("한도현", 10320), ("윤채원", 10320), ("임시우", 10320), ("강민서", 10320), ("조은우", 10320)],
        # 평일은 점심조·저녁조, 주말은 점심 3명.
        "shift_slots": {
            "open1": ((10, 30), (15, 0)),
            "open2": ((11, 0), (14, 30)),
            "close1": ((16, 30), (21, 0)),
            "close2": ((17, 0), (20, 30)),
            "weekend1": ((11, 0), (15, 0)),
            "weekend2": ((11, 30), (14, 30)),
            "weekend_help": ((11, 30), (14, 30)),  # 보조
        },
        # 1인 주 5일 (조은우만 주 6일).
        "shift_template": {
            0: {"open1": 1, "open2": 2, "close1": 3, "close2": 4},  # 조은우 휴무
            1: {"open1": 2, "open2": 3, "close1": 4, "close2": 5},  # 한도현 휴무
            2: {"open1": 3, "open2": 4, "close1": 5, "close2": 1},  # 윤채원 휴무
            3: {"open1": 4, "open2": 5, "close1": 1, "close2": 2},  # 임시우 휴무
            4: {"open1": 5, "open2": 1, "close1": 2, "close2": 3},  # 강민서 휴무
            5: {"weekend1": 1, "weekend2": 4, "weekend_help": 5},
            6: {"weekend1": 2, "weekend2": 3, "weekend_help": 5},
        },
        "reviews": {"linked": 50, "linked_twice": 20, "unlinked": 160},
        "late_reviews": {"until": date(2026, 11, 13), "linked": 2, "unlinked": 4},  # 11/11~13 에 덧붙이는 리뷰 (하루 2건꼴)
        "positive": [
            "{menu} 튀김옷이 얇고 바삭해요. 고기도 부드러워요.",
            "{menu} 육즙이 살아 있어요. 또 올게요!",
            "라멘이랑 돈가스 둘 다 맛있는 집 찾기 힘든데 여기 최고예요.",
            "{menu} 처음 먹어봤는데 기대 이상이었어요.",
            "줄 서서 먹을 만해요. {menu} 추천합니다.",
            "가게가 깔끔하고 사장님이 친절하세요.",
            "주말 점심에 왔는데 웨이팅 있어도 금방 들어갔어요.",
            "{menu} 가격이 좀 있지만 그 값 해요.",
            "배달인데도 튀김이 눅눅하지 않았어요.",
            "국물이 진하고 차슈가 두툼해요.",
            "추운 날 라멘 한 그릇 하니까 몸이 녹네요.",
            "석사동에서 돈가스는 여기가 제일이에요.",
        ],
        "taste": [
            "{menu} 고기가 질기고 맛이 별로예요.",
            "{menu} 기름 냄새가 심했어요.",
            "라멘 국물이 너무 짜요.",
            "{menu} 속이 덜 익은 것 같았어요.",
            "면이 퍼져서 식감이 별로였어요.",
            "예전보다 튀김옷이 두꺼워진 것 같아요.",
        ],
        "mixed": [
            "{menu} 맛있는데 배달이라 조금 눅눅했어요.",
            "맛은 좋지만 라멘 국물이 조금 짰어요.",
            "{menu} 괜찮았어요. 다만 주말 웨이팅이 길어서 아쉬워요.",
        ],
    },
    {
        # 실제 가게. 주소·좌표·영업시간·메뉴(이름·가격)는 네이버 지도 가게 화면(2026-11-13, 가게 id 2004174048)을 따랐다.
        # 강릉초당두부는 네이버에 가격이 없어 가상 가격을 넣었다. 주문·리뷰·알바는 모두 가상.
        # 가게는 경기 화성시에 있지만 행사·경기·날씨는 다른 목업 가게와 같은 공통 데이터를 쓴다.
        "store": {
            "store_id": "s005",
            "name": "초옹장",
            "category": "한식",
            "address": "경기 화성시 만세구 남양읍 역골중앙로41번길 39 1층 101호",
            "lat": 37.2065963,
            "lng": 126.8272701,
            "open_time": time(10, 30),  # 매일 10:30~20:30 (라스트오더 20:20), 브레이크 없음
            "close_time": time(20, 30),
            "closed_weekdays": [],
            "slots": ["10:00", "15:00", "20:00"],
        },
        "menu": [
            ("초계국수(물)", "main", 11000),
            ("초계국수(비빔)", "main", 11000),
            ("들깨옹심이", "main", 12000),
            ("멸치옹심이", "main", 12000),
            ("들깨옹심이메밀칼국수", "main", 10000),
            ("멸치옹심이메밀칼국수", "main", 10000),
            ("새뱅이 장칼국수", "main", 9000),
            ("수도감세트(수육,도토리전병,감자전)", "main", 18000),
            ("수육(대)", "main", 28000),
            ("수육(소)", "main", 15000),
            ("강릉초당두부", "side", 8000),  # 네이버에 가격 없음 (가상)
            ("도토리전병", "side", 12000),
            ("감자전", "side", 7000),
            ("소주", "drink", 4000),
            ("맥주", "drink", 4000),
            ("양조장막걸리(한병)", "drink", 8000),
            ("양조장막걸리(한잔)", "drink", 3000),
            ("음료", "drink", 2000),
        ],
        "main_weight": {"들깨옹심이메밀칼국수": 18, "멸치옹심이메밀칼국수": 12, "새뱅이 장칼국수": 10,
                        "수도감세트(수육,도토리전병,감자전)": 5, "수육(대)": 2, "수육(소)": 4},
        "seasonal": {
            "초계국수(물)": [1, 1, 2, 4, 9, 15, 20, 19, 10, 3, 1, 1],  # 여름 메뉴
            "초계국수(비빔)": [2, 2, 3, 5, 7, 10, 12, 12, 7, 4, 2, 2],
            "들깨옹심이": [14, 13, 10, 8, 5, 3, 2, 2, 4, 8, 11, 14],  # 추울수록 따뜻한 옹심이
            "멸치옹심이": [10, 9, 8, 6, 4, 3, 2, 2, 3, 6, 8, 10],
        },
        "side_p": {"hall": 0.3, "delivery": 0.2},
        "drink_p": {"hall": 0.25, "delivery": 0.1},
        "base_orders": 60,
        "hall_share": 0.75,
        "weekday_factor": [0.9, 0.9, 0.95, 0.95, 1.05, 1.3, 1.25],  # 주말 가족 손님
        # 10:30~20:30, 20칸. 브레이크 없음. 점심이 저녁보다 많은 국수집.
        "hall_slot_weight": [0.6, 1.5, 3.5, 4.5, 4.0, 2.5, 1.5, 1.0, 0.8, 0.6,
                             0.6, 0.8, 1.5, 2.5, 3.0, 2.8, 2.0, 1.2, 0.6, 0.2],
        "delivery_slot_weight": [0.3, 0.8, 2.0, 2.5, 2.2, 1.5, 1.0, 0.8, 0.6, 0.6,
                                 0.6, 0.8, 1.2, 2.0, 2.4, 2.2, 1.8, 1.2, 0.6, 0.2],
        "customer_pool": 650,
        "staff": [("배수아", 10320), ("남궁현", 10320), ("문하린", 10320), ("양지성", 10320), ("백서윤", 10320)],
        # 매일 영업. 평일은 오픈·마감·점심 보조 3명, 주말은 4명.
        "shift_slots": {
            "open1": ((10, 0), (15, 0)),
            "open2": ((10, 30), (14, 30)),
            "close1": ((15, 0), (21, 0)),
            "close2": ((16, 30), (20, 30)),
            "lunch": ((11, 30), (14, 0)),  # 보조
        },
        # 1인 주 4~5일.
        "shift_template": {
            0: {"open1": 1, "close1": 2, "lunch": 3},
            1: {"open1": 2, "close1": 3, "lunch": 4},
            2: {"open1": 3, "close1": 4, "lunch": 5},
            3: {"open1": 4, "close1": 5, "lunch": 1},
            4: {"open1": 5, "close1": 1, "lunch": 2},
            5: {"open1": 1, "open2": 2, "close1": 3, "close2": 4},
            6: {"open1": 5, "open2": 1, "close1": 2, "close2": 3},
        },
        "reviews": {"linked": 50, "linked_twice": 20, "unlinked": 180},
        "late_reviews": {"until": date(2026, 11, 13), "linked": 2, "unlinked": 4},  # 11/11~13 에 덧붙이는 리뷰 (하루 2건꼴)
        "positive": [
            "{menu} 국물이 진하고 고소해요.",
            "옹심이가 쫀득쫀득해요. 또 올게요!",
            "{menu} 처음 먹어봤는데 기대 이상이었어요.",
            "메밀면이 부드럽고 들깨 국물이 정말 고소해요.",
            "수육이 야들야들하고 잡내가 없어요.",
            "{side} 바삭하고 맛있어요. 막걸리랑 잘 어울려요.",
            "가게가 깔끔하고 사장님이 친절하세요.",
            "더운 날 초계국수 시원하게 잘 먹었어요.",
            "부모님 모시고 왔는데 다들 만족하셨어요.",
            "양이 넉넉하고 가격도 괜찮아요.",
            "추운 날 옹심이 한 그릇 하니까 몸이 녹네요.",
            "{menu} 추천합니다. 남양읍 맛집이에요.",
        ],
        "taste": [
            "{menu} 국물이 너무 싱거웠어요.",
            "{menu} 간이 너무 세요.",
            "옹심이가 퍼져서 식감이 별로였어요.",
            "면이 불어서 왔어요.",
            "{side} 기름이 너무 많았어요.",
            "예전보다 들깨 국물이 묽어진 것 같아요.",
        ],
        "mixed": [
            "{menu} 맛있는데 배달이라 면이 조금 불었어요.",
            "맛은 좋지만 국물이 조금 짰어요.",
            "{menu} 괜찮았어요. 다만 점심엔 웨이팅이 길어서 아쉬워요.",
        ],
    },
]
# 처음 세 매장은 난수 하나를 같이 쓴다. 뒤에 더한 매장은 매장마다 따로 난수를 써서 앞 매장 데이터가 바뀌지 않게 한다.
SHARED_RNG_STORES = {"s001", "s002", "s003"}

# 매장 공통 불만 리뷰 문구
DELAY = [
    "주문하고 1시간 넘게 걸렸어요. 다 식어서 왔네요.",
    "배달이 너무 늦어요. 예상 시간보다 40분 넘게 기다렸습니다.",
    "맛은 괜찮은데 배달이 늦어서 식어서 왔어요.",
    "배달 시간 안내가 틀려서 점심시간을 놓쳤어요.",
    "늦게 와서 국물이 미지근했어요. 다음엔 빨리 부탁드려요.",
    "50분 넘게 걸렸네요. 배달이 자주 늦는 것 같아요.",
    "비 오는 날이라 그런지 한 시간 가까이 기다렸어요.",
]
PORTION = [
    "{menu} 양이 너무 적어요. 예전보다 확 줄었네요.",
    "가격 대비 양이 아쉬워요.",
    "양이 좀 적어서 배가 안 찼어요.",
    "기대했던 것보다 양이 너무 적어요.",
]
SERVICE = [
    "{side} 누락됐어요. 가게에 전화해도 안 받으시네요.",
    "주문한 {side} 안 왔어요. 누락 확인 부탁드려요.",
    "홀에서 먹었는데 직원 응대가 별로였어요.",
    "수저가 안 왔어요. 다음엔 꼭 챙겨주세요.",
]
HYGIENE = [
    "{menu}에서 머리카락이 나왔어요.",
    "음식에 이물질이 있었어요. 확인 부탁드립니다.",
]

# 주문 인원 (값, 비중). 매장 설정에 "people" 이 없으면 쓴다.
DEFAULT_PEOPLE = {"hall": ([1, 2, 3, 4], [45, 35, 12, 8]), "delivery": ([1, 2, 3], [50, 35, 15])}

# 리뷰 종류 비중. 배달 아닌 리뷰는 delay 대신 taste.
COMPLAINT_RATIO = 0.22
COMPLAINT_KIND_WEIGHT = {"delay": 45, "taste": 30, "portion": 12, "service": 10, "hygiene": 3}
MIXED_RATIO = 0.08  # 칭찬과 아쉬움이 섞인 리뷰
RATING = {
    "positive": ([4, 5], [30, 70]),
    "mixed": ([3, 4], [50, 50]),
    "delay": ([2, 3], [50, 50]),
    "taste": ([1, 2, 3], [30, 40, 30]),
    "portion": ([2, 3], [60, 40]),
    "service": ([1, 2], [50, 50]),
    "hygiene": ([1], [1]),
}

# ── 행사·경기 (모두 가상) ────────────────────────────
# 행사 기간에는 모든 매장의 주문이 +30% 안팎. distance_km 는 s001 기준.
EVENTS = [
    ("춘천 봄꽃 축제", "local_festival", datetime(2026, 4, 11, 10), datetime(2026, 4, 12, 20), 37.8750, 127.7350, 1.2),
    ("강원대 봄 대동제", "univ_festival", datetime(2026, 5, 20, 10), datetime(2026, 5, 22, 23), 37.8690, 127.7460, 0.5),
    ("강원대 대동제", "univ_festival", datetime(2026, 9, 23, 10), datetime(2026, 9, 25, 23), 37.8690, 127.7460, 0.5),
    ("춘천 가을 지역 축제", "local_festival", datetime(2026, 10, 10, 10), datetime(2026, 10, 11, 21), 37.8800, 127.7300, 1.6),
    ("효자동 연말 플리마켓", "other", datetime(2026, 12, 5, 11), datetime(2026, 12, 6, 18), 37.8710, 127.7420, 0.6),
    ("춘천 겨울 빛 축제", "local_festival", datetime(2026, 12, 12, 17), datetime(2026, 12, 14, 22), 37.8810, 127.7290, 2.1),
]
FESTIVAL_DATES = {d for _, _, s, e, *_ in EVENTS for d in (s.date() + timedelta(days=i) for i in range((e.date() - s.date()).days + 1))}

GAMES = [
    # (종목, 수준, 제목, 시작). 국가대표 경기 날만 18시 이후 배달 +25%, 야구는 효과 없음.
    ("soccer", "national", "대한민국 vs 콜롬비아 (친선)", datetime(2026, 3, 27, 20, 0)),
    ("soccer", "national", "대한민국 vs 가나 (친선)", datetime(2026, 6, 2, 20, 0)),
    ("soccer", "national", "대한민국 vs 파라과이 (친선)", datetime(2026, 10, 14, 20, 0)),
    ("soccer", "national", "대한민국 vs 우즈베키스탄 (친선)", datetime(2026, 12, 9, 20, 0)),
    ("baseball", "pro", "프로야구 개막전", datetime(2026, 3, 28, 14, 0)),
    ("baseball", "pro", "프로야구 정규시즌", datetime(2026, 5, 12, 18, 30)),
    ("baseball", "pro", "프로야구 정규시즌", datetime(2026, 7, 7, 18, 30)),
    ("baseball", "pro", "프로야구 정규시즌", datetime(2026, 8, 26, 18, 30)),
    ("baseball", "pro", "프로야구 정규시즌", datetime(2026, 9, 9, 18, 30)),
    ("baseball", "pro", "프로야구 정규시즌", datetime(2026, 9, 16, 18, 30)),
    ("baseball", "pro", "프로야구 정규시즌", datetime(2026, 9, 30, 18, 30)),
    ("baseball", "pro", "프로야구 포스트시즌", datetime(2026, 10, 20, 18, 30)),
    ("baseball", "pro", "프로야구 한국시리즈", datetime(2026, 10, 28, 18, 30)),
]
NATIONAL_GAME_DATES = {g[3].date() for g in GAMES if g[1] == "national"}

# ── 효과 크기 ────────────────────────────────────────
FESTIVAL_LIFT = (1.25, 1.35)  # 행사 날 영업시간 내내, 홀·배달 모두
GAME_DELIVERY_LIFT = 1.25  # 국가대표 경기 날 GAME_FROM_HOUR 이후 배달
GAME_FROM_HOUR = 18
RAIN_DELIVERY_LIFT = 1.15  # 비 오는 날 배달 (하루 종일)
RAIN_MM = 5.0  # 이 이상이면 '비 오는 날'
# 대학가라 방학(1·2·7·8월)에 손님이 준다. 3월 개강 직후는 조금 많다.
MONTH_FACTOR = [0.8, 0.85, 1.05, 1.0, 1.0, 0.95, 0.85, 0.9, 1.0, 1.0, 1.0, 0.9]
RAIN_PROB = [0.10, 0.10, 0.15, 0.20, 0.20, 0.30, 0.45, 0.35, 0.25, 0.15, 0.12, 0.10]  # 월별 (겨울엔 눈 포함)

OVERTIME_PROB = 0.15  # 근무는 30분 단위. 가끔 퇴근이 30분 늦어진다 (연장)


WEEKDAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]  # closed_weekdays 에 쓰는 요일 코드 (플래너와 같다)


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


def open_minutes(store: dict) -> int:
    return store["open_time"].hour * 60 + store["open_time"].minute


# ── 생성 ─────────────────────────────────────────────
def gen_weather(rng: random.Random) -> list[dict]:
    rows = []
    for d in days(START, END):
        doy = d.timetuple().tm_yday
        temp_max = 15.5 + 14.5 * math.cos(2 * math.pi * (doy - 210) / 365) + rng.uniform(-2.5, 2.5)  # 1월 1도, 8월 초 30도
        temp_min = temp_max - rng.uniform(7, 11)
        rainy = rng.random() < RAIN_PROB[d.month - 1] and not (DEMO_WEEK[0] <= d <= DEMO_WEEK[1])
        precip = round(rng.uniform(RAIN_MM, 60 if d.month in (7, 8) else 30), 1) if rainy else 0.0
        rows.append({"date": d, "temp_max": round(temp_max, 1), "temp_min": round(temp_min, 1), "precip_mm": precip})
    return rows


def pick_items(rng: random.Random, cfg: dict, d: date, channel: str) -> list[tuple[str, int]]:
    weights = dict(cfg["main_weight"], **{name: w[d.month - 1] for name, w in cfg["seasonal"].items()})
    mains, mw = list(weights), list(weights.values())
    sides = [n for n, c, _ in cfg["menu"] if c == "side"]
    drinks = [n for n, c, _ in cfg["menu"] if c == "drink"]
    people = rng.choices(*cfg.get("people", DEFAULT_PEOPLE)[channel])[0]
    n_main = max(1, round(people * cfg.get("mains_per_person", 1)))
    counts: dict[str, int] = {}
    for name in rng.choices(mains, mw, k=n_main):
        counts[name] = counts.get(name, 0) + 1
    if rng.random() < cfg["side_p"][channel]:
        side = rng.choice(sides)
        counts[side] = counts.get(side, 0) + 1
    if rng.random() < cfg["drink_p"][channel]:
        counts[rng.choice(drinks)] = rng.randint(1, people * cfg.get("drinks_per_person", 1))
    return list(counts.items())


def gen_store_orders(rng: random.Random, cfg: dict, weather: dict[date, dict]) -> list[dict]:
    """한 매장의 주문 (id 없이). 손님 키는 매장마다 따로: c1_0001, c2_0001 ..."""
    store = cfg["store"]
    prices = {name: price for name, _, price in cfg["menu"]}
    prefix = f"c{int(store['store_id'][1:])}_"
    pool = cfg["customer_pool"]
    customers = [f"{prefix}{i:04d}" for i in range(1, pool + 1)]
    cust_w = [1 / (i ** 0.8) for i in range(1, pool + 1)]  # 단골일수록 자주 시킴
    hall_w = [w / sum(cfg["hall_slot_weight"]) for w in cfg["hall_slot_weight"]]
    deliv_w = [w / sum(cfg["delivery_slot_weight"]) for w in cfg["delivery_slot_weight"]]
    base_min = open_minutes(store)

    orders = []
    for d in days(START, END):
        if WEEKDAYS[d.weekday()] in store["closed_weekdays"]:
            continue
        total = cfg["base_orders"] * cfg["weekday_factor"][d.weekday()] * MONTH_FACTOR[d.month - 1]
        festival = rng.uniform(*FESTIVAL_LIFT) if d in FESTIVAL_DATES else 1.0
        rainy = weather[d]["precip_mm"] >= RAIN_MM
        game = d in NATIONAL_GAME_DATES
        first, last = cfg.get("open_slots_by_weekday", {}).get(d.weekday(), (0, len(hall_w)))

        for slot in range(first, last):
            evening = base_min + slot * 30 >= GAME_FROM_HOUR * 60  # 자정 넘은 새벽도 포함
            for channel, share, w in (("hall", cfg["hall_share"], hall_w), ("delivery", 1 - cfg["hall_share"], deliv_w)):
                lam = total * share * w[slot]
                lam *= festival
                if channel == "delivery":
                    if rainy:
                        lam *= RAIN_DELIVERY_LIFT
                    if game and evening:
                        lam *= GAME_DELIVERY_LIFT
                for _ in range(poisson(rng, lam)):
                    minute = base_min + slot * 30 + rng.randint(0, 29)  # 자정을 넘으면 24*60 이상
                    at = kst(d, 0) + timedelta(minutes=minute, seconds=rng.randint(0, 59))
                    cust = rng.choices(customers, cust_w)[0] if channel == "delivery" else None
                    picked = pick_items(rng, cfg, d, channel)
                    orders.append({"ordered_at": at, "channel": channel,
                                   "customer_key": cust, "_items": picked,
                                   "_amount": sum(prices[n] * q for n, q in picked)})
    return orders


def gen_orders(rng: random.Random, cfg: dict, weather: dict[date, dict]):
    """한 매장의 주문과 주문 품목. id 는 매장마다 1부터."""
    menu_ids = {name: i for i, (name, _, _) in enumerate(cfg["menu"], start=1)}
    prices = {name: price for name, _, price in cfg["menu"]}
    orders = sorted(gen_store_orders(rng, cfg, weather), key=lambda o: o["ordered_at"])
    rows, items = [], []
    for oid, o in enumerate(orders, start=1):
        o["order_id"] = oid
        rows.append({"order_id": oid, "ordered_at": o["ordered_at"], "channel": o["channel"],
                     "customer_key": o["customer_key"], "total_amount": o["_amount"]})
        for name, qty in o["_items"]:
            items.append({"order_id": oid, "menu_id": menu_ids[name], "quantity": qty, "unit_price": prices[name]})
    return rows, items, orders


def review_pools(cfg: dict) -> dict[str, list[str]]:
    """리뷰 종류별 문장 목록. {menu}, {side} 자리에 그 매장 메뉴가 들어간다."""
    return {"positive": cfg["positive"], "mixed": cfg["mixed"], "taste": cfg["taste"],
            "delay": cfg.get("delay", DELAY), "portion": PORTION, "service": SERVICE, "hygiene": HYGIENE}


def review_text(rng: random.Random, cfg: dict, kind: str) -> str:
    mains = [n for n, c, _ in cfg["menu"] if c == "main"]
    sides = [n for n, c, _ in cfg["menu"] if c == "side"]
    return rng.choice(review_pools(cfg)[kind]).format(menu=rng.choice(mains), side=rng.choice(sides))


def gen_reviews(rng: random.Random, cfg: dict, orders: list[dict]) -> list[dict]:
    """한 매장의 리뷰. id 는 매장마다 1부터."""
    n = cfg["reviews"]
    review_cut = kst(REVIEW_END, 12)  # 리뷰 작성이 11/10 안에 끝나도록 주문은 그 전까지만
    by_cust: dict[str, list[dict]] = {}
    for o in orders:
        if o["customer_key"] and o["ordered_at"] < review_cut:
            by_cust.setdefault(o["customer_key"], []).append(o)
    candidates = sorted(c for c, os in by_cust.items() if len(os) >= 2)
    linked = rng.sample(candidates, n["linked"])
    twice = set(rng.sample(linked, n["linked_twice"]))

    drafts = []
    for c in linked:
        for o in rng.sample(by_cust[c], 2 if c in twice else 1):
            at = o["ordered_at"] + timedelta(minutes=rng.randint(40, 600))
            drafts.append({"order": o, "customer_key": c, "written_at": at, "delivery": True})
    for _ in range(n["unlinked"]):
        d = START + timedelta(days=rng.randint(0, (REVIEW_END - START).days))
        at = kst(d, rng.randint(11, 23), rng.randint(0, 59), rng.randint(0, 59))
        drafts.append({"order": None, "customer_key": None, "written_at": at, "delivery": rng.random() < 0.5})

    rows = review_rows(rng, cfg, drafts)
    rows.sort(key=lambda r: r["written_at"])
    for rid, r in enumerate(rows, start=1):
        r["review_id"] = rid
    return rows


def gen_late_reviews(rng: random.Random, cfg: dict, orders: list[dict], first_id: int) -> list[dict]:
    """REVIEW_END 다음 날부터 late_reviews["until"] 까지 덧붙이는 리뷰. 앞 리뷰는 그대로 두고 id 는 first_id 부터."""
    late = cfg["late_reviews"]
    start, end = REVIEW_END + timedelta(days=1), late["until"]
    end_at = kst(end, 23, 59, 59)
    deliveries = [o for o in orders if o["customer_key"] and kst(start, 0) <= o["ordered_at"] < kst(end, 12)]
    drafts = []
    for o in rng.sample(deliveries, late["linked"]):
        at = min(o["ordered_at"] + timedelta(minutes=rng.randint(40, 600)), end_at)
        drafts.append({"order": o, "customer_key": o["customer_key"], "written_at": at, "delivery": True})
    for i in range(late["unlinked"]):
        d = start + timedelta(days=i % ((end - start).days + 1))  # 날마다 돌아가며 넣어 마지막 날에도 리뷰가 있게 한다
        at = kst(d, rng.randint(11, 23), rng.randint(0, 59), rng.randint(0, 59))
        drafts.append({"order": None, "customer_key": None, "written_at": at, "delivery": rng.random() < 0.5})
    rows = review_rows(rng, cfg, drafts)
    rows.sort(key=lambda r: r["written_at"])
    for rid, r in enumerate(rows, start=first_id):
        r["review_id"] = rid
    return rows


def review_rows(rng: random.Random, cfg: dict, drafts: list[dict]) -> list[dict]:
    """리뷰 초안(주문, 손님, 쓴 때, 배달 여부)에 종류·별점·글을 붙인다."""
    kinds_c, kinds_w = list(COMPLAINT_KIND_WEIGHT), list(COMPLAINT_KIND_WEIGHT.values())
    rows = []
    for r in drafts:
        x = rng.random()
        if x < COMPLAINT_RATIO:
            kind = rng.choices(kinds_c, kinds_w)[0]
            if kind == "delay" and not r["delivery"]:
                kind = "taste"
        elif x < COMPLAINT_RATIO + MIXED_RATIO:
            kind = "mixed"
        else:
            kind = "positive"
        ratings, rw = RATING[kind]
        rows.append({"order_id": r["order"]["order_id"] if r["order"] else None,
                     "customer_key": r["customer_key"], "written_at": r["written_at"],
                     "rating": rng.choices(ratings, rw)[0], "content": review_text(rng, cfg, kind),
                     "complaint_type": None})
    return rows


def gen_shifts(rng: random.Random, cfg: dict) -> list[dict]:
    """한 매장의 실제 출퇴근 기록. 30분 단위로, 출근은 예정 시각 그대로, 퇴근은 가끔 30분 연장된다.
    staff_id 는 매장 안 알바 번호(1~5) 그대로."""
    rows = []
    for d in days(START, END):
        for slot, staff_id in cfg["shift_template"].get(d.weekday(), {}).items():
            (h1, m1), (h2, m2) = cfg["shift_slots"][slot]
            start = kst(d, h1, m1)
            overnight = (h2, m2) < (h1, m1)  # 자정 넘어 다음 날 퇴근
            end = kst(d, h2, m2) + timedelta(days=overnight, minutes=30 if rng.random() < OVERTIME_PROB else 0)
            rows.append((staff_id, start, end))
    rows.sort(key=lambda r: (r[1], r[0]))
    return [{"shift_id": i, "staff_id": s, "starts_at": a, "ends_at": b} for i, (s, a, b) in enumerate(rows, start=1)]


def build(seed: int) -> dict[str, dict[str, list[dict]]]:
    """{"common": {테이블: 행}, "s001": {테이블: 행}, ...}. 매장 키는 DB 스키마 이름과 같다."""
    rng = random.Random(seed)
    weather = gen_weather(rng)
    by_date = {w["date"]: w for w in weather}
    data: dict[str, dict[str, list[dict]]] = {
        "common": {
            "events": [{"event_id": i, "name": n, "kind": k, "starts_at": s.replace(tzinfo=KST),
                        "ends_at": e.replace(tzinfo=KST), "lat": la, "lng": ln, "distance_km": km}
                       for i, (n, k, s, e, la, ln, km) in enumerate(EVENTS, start=1)],
            "games": [{"game_id": i, "sport": s, "level": lv, "title": t, "starts_at": at.replace(tzinfo=KST)}
                      for i, (s, lv, t, at) in enumerate(GAMES, start=1)],
            "weather_daily": weather,
        },
    }
    rngs = {cfg["store"]["store_id"]: rng if cfg["store"]["store_id"] in SHARED_RNG_STORES
            else random.Random(f"{seed}:{cfg['store']['store_id']}") for cfg in STORES}
    raw_orders = {}
    for cfg in STORES:
        sid = cfg["store"]["store_id"]
        orders, items, raw_orders[sid] = gen_orders(rngs[sid], cfg, by_date)
        data[sid] = {
            "store": [cfg["store"]],
            "menu": [{"menu_id": i, "name": n, "category": c, "price": p}
                     for i, (n, c, p) in enumerate(cfg["menu"], start=1)],
            "staff": [{"staff_id": i, "name": n, "hourly_wage": w} for i, (n, w) in enumerate(cfg["staff"], start=1)],
            "orders": orders,
            "order_items": items,
        }
    for cfg in STORES:
        sid = cfg["store"]["store_id"]
        data[sid]["reviews"] = gen_reviews(rngs[sid], cfg, raw_orders[sid])
        if "late_reviews" in cfg:  # 따로 난수를 써서 앞 리뷰와 근무 데이터는 바뀌지 않는다
            late_rng = random.Random(f"{seed}:{sid}:late_reviews")
            data[sid]["reviews"] += gen_late_reviews(late_rng, cfg, raw_orders[sid], len(data[sid]["reviews"]) + 1)
    for cfg in STORES:
        sid = cfg["store"]["store_id"]
        data[sid]["shifts"] = gen_shifts(rngs[sid], cfg)
    return data


# ── 저장 ─────────────────────────────────────────────
TABLES = {
    "store": models.Store, "menu": models.Menu, "staff": models.Staff, "shifts": models.Shift,
    "orders": models.Order, "order_items": models.OrderItem, "reviews": models.Review,
    "events": models.Event, "games": models.Game, "weather_daily": models.WeatherDaily,
}


def to_csv_value(v):
    if v is None:
        return ""
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    return v


def table_rows(name: str, rows: list[dict]) -> list[dict]:
    """모델에 있는 열만 남긴다."""
    cols = [c.name for c in TABLES[name].__table__.columns]
    return [{c: r[c] for c in cols} for r in rows]


def write_csv(data: dict[str, dict[str, list[dict]]]) -> None:
    """out/common/<테이블>.csv, out/<매장>/<테이블>.csv"""
    for group, tables in data.items():
        (OUT_DIR / group).mkdir(parents=True, exist_ok=True)
        for name, rows in tables.items():
            cols = [c.name for c in TABLES[name].__table__.columns]
            with open(OUT_DIR / group / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(cols)
                for r in rows:
                    w.writerow([to_csv_value(r[c]) for c in cols])


def create_tables(conn, tables) -> None:
    """테이블과 인덱스를 만든다. 인덱스는 이름 순서로 만들어 DB 파일이 실행마다 똑같이 나오게 한다
    (create_all 은 인덱스 순서가 실행마다 달라질 수 있다)."""
    for table in tables:
        conn.execute(CreateTable(table))
        for index in sorted(table.indexes, key=lambda i: i.name):
            conn.execute(CreateIndex(index))


def load_db(data: dict[str, dict[str, list[dict]]]) -> None:
    """db/data/*.db 를 지우고 새로 만든다. 공통 테이블은 common.db, 매장 테이블은 매장 파일(s001.db ...)."""
    engine.dispose()  # 열려 있는 연결이 옛 파일을 붙잡고 있지 않게
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for path in DATA_DIR.glob("*.db"):
        path.unlink()
    store_ids = [cfg["store"]["store_id"] for cfg in STORES]
    for sid in store_ids:
        (DATA_DIR / f"{sid}.db").touch()  # 빈 파일도 SQLite DB 다. 접속할 때 붙는다.

    common = [TABLES[name].__table__ for name in models.COMMON_TABLES]
    per_store = [TABLES[name].__table__ for name in models.STORE_TABLES]
    with engine.begin() as conn:
        create_tables(conn, common)
        for name in models.COMMON_TABLES:
            conn.execute(insert(TABLES[name]), table_rows(name, data["common"][name]))
    for sid in store_ids:
        with store_engine(sid).begin() as conn:
            create_tables(conn, per_store)
            for name in models.STORE_TABLES:  # 부모 테이블부터
                conn.execute(insert(TABLES[name]), table_rows(name, data[sid][name]))
    engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="목업 데이터 생성")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    data = build(args.seed)
    load_db(data)
    write_csv(data)

    print(f"seed={args.seed}")
    print("  공통: " + ", ".join(f"{name} {len(rows)}행" for name, rows in data["common"].items()))
    for cfg in STORES:
        sid = cfg["store"]["store_id"]
        mine = data[sid]["orders"]
        per_day: dict[date, int] = {}
        for o in mine:
            per_day[o["ordered_at"].date()] = per_day.get(o["ordered_at"].date(), 0) + 1
        deliv = sum(o["channel"] == "delivery" for o in mine)
        sales = sum(o["total_amount"] for o in mine)
        print(f"  {sid} {cfg['store']['name']}: " + ", ".join(f"{name} {len(rows)}행" for name, rows in data[sid].items()))
        print(f"       하루 주문 {min(per_day.values())}~{max(per_day.values())}건, 배달 {deliv / len(mine):.0%}, 매출 {sales:,}원")
    print(f"  CSV → {OUT_DIR}")


if __name__ == "__main__":
    main()
