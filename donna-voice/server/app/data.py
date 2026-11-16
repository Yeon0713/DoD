"""목업 데이터와 메모리 저장소.

Figma v0.2.0 화면에 그려진 내용과 같은 기준 데이터다 (docs/v0.2.0-voice-agent-handoff.md 13장).
나중에 에이전트가 붙으면 이 파일의 값이 실제 수집 결과로 바뀐다.
"""
from __future__ import annotations

import copy
import datetime as dt

KST = dt.timezone(dt.timedelta(hours=9))
DEMO_NOW = dt.datetime(2026, 11, 17, 9, 2, tzinfo=KST)
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


def at(day: int, hour: int, minute: int = 0) -> str:
    return dt.datetime(2026, 11, day, hour, minute, tzinfo=KST).isoformat()


def _base() -> dict:
    return {
        "now": DEMO_NOW,
        "store": {
            "id": "s001",
            "name": "도나네 곱창 역삼점",
            "category": "곱창",
            "open_time": "10:00",
            "close_time": "22:00",
            "closed_weekdays": [],
            "menus": ["곱창전골", "소곱창 구이", "대창 구이", "볶음밥"],
            "timezone": "Asia/Seoul",
        },
        "settings": {"negative_review_auto_reply": None},
        "events": [{"id": "ev_0007", "name": "강남 페스티벌", "starts_at": at(17, 18)}],
        "games": [
            {"id": "gm_0012", "name": "한국시리즈", "starts_at": at(17, 18, 30), "sport": "baseball"},
            {"id": "gm_0013", "name": "한국시리즈", "starts_at": at(20, 18, 30), "sport": "baseball"},
        ],
        "reservations": [
            {"id": "rs_0027", "starts_at": at(17, 18), "party_size": 2, "kind": "general"},
            {"id": "rs_0028", "starts_at": at(17, 18, 30), "party_size": 4, "kind": "general"},
            {"id": "rs_0029", "starts_at": at(17, 19, 30), "party_size": 3, "kind": "general"},
            {"id": "rs_0030", "starts_at": at(17, 20), "party_size": 2, "kind": "general"},
            {"id": "rs_0031", "starts_at": at(17, 19), "party_size": 12, "kind": "group"},
        ],
        "weather": [
            {"date": "2026-11-17", "rain_chance": 0.1, "temp_min": 2, "temp_max": 12, "label": "맑음"},
            {"date": "2026-11-18", "rain_chance": 0.2, "temp_min": 1, "temp_max": 11, "label": "구름"},
            {"date": "2026-11-19", "rain_chance": 0.8, "temp_min": 3, "temp_max": 9, "label": "비"},
            {"date": "2026-11-20", "rain_chance": 0.2, "temp_min": 0, "temp_max": 8, "label": "구름"},
            {"date": "2026-11-21", "rain_chance": 0.1, "temp_min": -1, "temp_max": 7, "label": "맑음"},
            {"date": "2026-11-22", "rain_chance": 0.1, "temp_min": -2, "temp_max": 6, "label": "맑음"},
        ],
        # 답글을 기다리는 리뷰 5개: 좋은 리뷰 3개, 아쉬운 리뷰 2개
        "reviews": [
            {
                "id": "rv_0412", "platform": "baemin", "rating": 1, "order_channel": "delivery",
                "text": "배달이 너무 늦어서 다 식어서 왔어요. 곱창은 맛있는데 아쉽네요.",
                "written_at": at(16, 21, 40), "sentiment": "negative", "topic": "delivery",
                "summary": "배달이 늦어 음식이 식었대요", "reply_status": "none",
                "reply_text": None, "reply_summary": None, "reply_posted_at": None, "replied_in_minutes": None,
            },
            {
                "id": "rv_0410", "platform": "naver", "rating": 2, "order_channel": "hall",
                "text": "맛은 괜찮은데 양이 생각보다 적었어요.",
                "written_at": at(16, 13, 10), "sentiment": "negative", "topic": "portion",
                "summary": "양이 생각보다 적었대요", "reply_status": "none",
                "reply_text": None, "reply_summary": None, "reply_posted_at": None, "replied_in_minutes": None,
            },
            {
                "id": "rv_0401", "platform": "naver", "rating": 5, "order_channel": "hall",
                "text": "곱창전골 국물이 진하고 깊어요. 추운 날 또 올게요.",
                "written_at": at(15, 20, 5), "sentiment": "positive", "topic": "taste",
                "summary": "전골 국물이 진하대요", "reply_status": "scheduled",
                "reply_text": "비 오는 날엔 뜨끈한 곱창전골이 더 맛있어요. 오늘 같은 날 또 들러 주세요.",
                "reply_post_at": at(19, 8),
            },
            {
                "id": "rv_0405", "platform": "naver", "rating": 5, "order_channel": "hall",
                "text": "사장님이 친절하시고 볶음밥이 최고예요.",
                "written_at": at(15, 21, 30), "sentiment": "positive", "topic": "service",
                "summary": "친절하고 볶음밥이 좋대요", "reply_status": "scheduled",
                "reply_text": "경기 보기 전에 든든하게 드시고 가세요. 볶음밥도 넉넉히 볶아 드릴게요.",
                "reply_post_at": at(20, 17),
            },
            {
                "id": "rv_0409", "platform": "baemin", "rating": 4, "order_channel": "delivery",
                "text": "양이 넉넉해서 둘이 먹고도 남았어요.",
                "written_at": at(16, 19, 45), "sentiment": "positive", "topic": "portion",
                "summary": "양이 넉넉하대요", "reply_status": "scheduled",
                "reply_text": "넉넉하게 드셨다니 기뻐요. 주말에도 푸짐하게 준비해 둘게요.",
                "reply_post_at": at(21, 11),
            },
        ],
        # 최근 7일 좋은 리뷰 14개에서 찾은 것 (F5의 결과)
        "strengths": {
            "positive_count": 14,
            "items": [
                {"id": "b_1", "label": "곱창전골 국물", "count": 9},
                {"id": "b_2", "label": "친절한 응대", "count": 6},
                {"id": "b_3", "label": "넉넉한 양", "count": 4},
            ],
            "keep": "육수는 지금처럼 매일 아침 끓여 주세요",
            "keep_say": "육수를 지금처럼 매일 아침 끓이시면 이 반응이 이어질 거예요.",
        },
        "improve": {
            "tip": "금요일 저녁엔 배달 시간을 10분 넉넉히 안내해 보세요",
            "say": "금요일 저녁에 배달이 자주 늦으니, 배달 시간을 10분 넉넉히 안내해 보세요.",
            "caption": "배달 시간을 넉넉히 안내해 보세요.",
        },
        # F6의 결과: 언제, 왜
        "scheduled": [
            {
                "id": "sr_1", "day_label": "목", "time_label": "아침 8시", "post_at": at(19, 8),
                "reason": {"kind": "weather", "label": "비 소식"}, "text": "비 오는 날 전골 권하기", "review_ids": ["rv_0401"],
                "say": "목요일엔 비가 와서, 그날 아침에 비 오는 날 전골을 권하는 답글을 올릴게요.",
                "caption": "비 오는 목요일 아침에 올릴게요.",
            },
            {
                "id": "sr_2", "day_label": "금", "time_label": "오후 5시", "post_at": at(20, 17),
                "reason": {"kind": "game", "label": "한국시리즈"}, "text": "경기 보기 전에 들르시게", "review_ids": ["rv_0405"],
                "say": "금요일은 한국시리즈 전에, 경기 보기 전에 들르시게 올릴게요.",
                "caption": "금요일은 경기 전에 올릴게요.",
            },
            {
                "id": "sr_3", "day_label": "토", "time_label": "오전 11시", "post_at": at(21, 11),
                "reason": {"kind": "weekend", "label": "주말"}, "text": "주말에 리뷰를 많이 봐요", "review_ids": ["rv_0409"],
                "say": "나머지는 리뷰를 많이 보는 토요일 오전에 올릴게요.",
                "caption": "나머지는 토요일 오전에 올릴게요.",
            },
        ],
        # 오늘 한 것. 도나가 한 일은 미리 적혀 있고, 사장님이 한 일(브리핑 듣기, 허락)은 일어날 때 더해진다.
        "activity": [
            {"id": "a_read", "actor": "donna", "text": "밤사이 리뷰 5개를 읽고 나눴어요", "at": at(17, 8, 40)},
            {"id": "a_sched", "actor": "donna", "text": "좋은 리뷰 답글 3개를 예약했어요", "at": at(17, 8, 50)},
            {"id": "a_brief", "actor": "donna", "text": "오늘 일정 브리핑을 준비했어요", "at": at(17, 9, 0)},
        ],
        # 지난 일 (목업). "브리핑을 듣고 한 일"은 사장님이 알려 줘야 적을 수 있다 (docs/open-features.md).
        "past": [
            {"label": "어제", "date_label": "11월 16일 월요일", "items": [
                {"id": "y_1", "actor": "donna", "text": "리뷰 7개를 읽고 나눴어요"},
                {"id": "y_2", "actor": "donna", "text": "좋은 리뷰 2개에 답글을 올렸어요"},
                {"id": "y_3", "actor": "owner", "text": "오늘 일정 브리핑을 들었어요"},
                {"id": "y_4", "actor": "owner", "text": "배달 안내 시간을 10분 늘렸어요", "after_briefing": True},
            ]},
            {"label": "지난주", "date_label": "11월 9일 ~ 15일", "items": [
                {"id": "w_1", "actor": "donna", "text": "답글 11개를 올렸어요"},
                {"id": "w_2", "actor": "donna", "text": "아쉬운 리뷰 3개를 알려 드렸어요"},
                {"id": "w_3", "actor": "owner", "text": "브리핑을 다섯 번 들었어요"},
            ]},
        ],
        "sessions": {},
        "requests": {},
        "turn_seq": 141,
    }


STATE: dict = _base()


def reset(scenario: str = "first_day") -> None:
    """first_day: 허락을 아직 안 물음. next_day: 허락했고, 밤사이 아쉬운 리뷰 하나에 도나가 12분 만에 답함."""
    STATE.clear()
    STATE.update(copy.deepcopy(_base()))
    if scenario == "next_day":
        STATE["settings"]["negative_review_auto_reply"] = True
        STATE["past"][0]["items"].insert(2, {"id": "y_auto", "actor": "donna", "text": "아쉬운 리뷰에 12분 만에 답했어요"})
        rv = STATE["reviews"][0]
        rv.update(
            reply_status="posted",
            reply_text="늦은 배달로 불편을 드려 죄송합니다. 다음 주문은 더 빨리, 따뜻하게 보내 드릴게요.",
            reply_summary="사과하고, 다음엔 더 빨리 보낸다고 답했어요",
            reply_posted_at=at(16, 21, 52),
            replied_in_minutes=12,
        )


def now() -> dt.datetime:
    return STATE["now"]


def log(actor: str, text: str, key: str) -> None:
    """오늘 한 것에 한 줄 더한다. 같은 일은 한 번만 적는다."""
    if any(a["id"] == key for a in STATE["activity"]):
        return
    STATE["activity"].append({"id": key, "actor": actor, "text": text, "at": now().isoformat()})


def date_label(d: dt.date) -> str:
    return f"{d.month}월 {d.day}일 {WEEKDAYS[d.weekday()]}요일"
