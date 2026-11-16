"""목업 데이터와 메모리 저장소.

Figma `v0.2.1 : 디자인개선`의 하루 시나리오(D-01 ~ D-33, F-01 ~ F-09)에 그려진 내용과 같은 기준 데이터다.
가게는 초옹장(s005, 김호찬 사장님)이다. 숫자, 메뉴, 리뷰, 알바생 이름은 Figma와 같다.
나중에 에이전트가 붙으면 이 파일의 값이 실제 수집 결과로 바뀐다.

시나리오 (POST /v1/dev/fixtures {"scenario": ...})
  setup      처음 한 번 하는 날 (인스타 연결 전, 알바생과 매뉴얼 없음): D-01 ~ D-06
  first_day  설정을 마친 다음 날 아침. 아쉬운 리뷰에 바로 답해도 될지 아직 안 물음: D-07 ~ D-16 (기본)
  next_day   허락했고, 밤사이 아쉬운 리뷰 하나에 도나가 12분 만에 답함
"""
from __future__ import annotations

import copy
import datetime as dt

KST = dt.timezone(dt.timedelta(hours=9))
DEMO_NOW = dt.datetime(2026, 11, 17, 9, 2, tzinfo=KST)
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


def at(day: int, hour: int, minute: int = 0) -> str:
    return dt.datetime(2026, 11, day, hour, minute, tzinfo=KST).isoformat()


def _menu(i: str, name: str, count: int, photo: str) -> dict:
    return {"id": i, "name": name, "month_count": count, "photo_url": f"/static/menus/{photo}.png"}


def _staff(i: str, name: str, call: str, joined: bool = True, in_at: str | None = None) -> dict:
    return {"id": i, "name": name, "call": call, "joined": joined, "in_at": in_at, "out_at": None}


def _task(i: str, title: str, phase: str, repeat: str = "daily", must_confirm: bool = False, sent_at: str | None = None,
          owner_words: str | None = None, to: str = "all", kind: str = "do", short: str | None = None) -> dict:
    """알바생 할 일 하나.
    phase: before_open(오픈 전) / open(영업 중) / closing(마감)
    repeat: daily(매뉴얼, 매일) / today(오늘만)
    kind: do(할 것) / dont(오늘 하지 말 것)
    """
    return {"id": i, "title": title, "short": short or title, "phase": phase, "repeat": repeat, "must_confirm": must_confirm, "kind": kind,
            "sent_at": sent_at, "owner_words": owner_words, "to": to, "done": {}, "confirmed": {}, "canceled": False}


def _base() -> dict:
    return {
        "now": DEMO_NOW,
        "store": {
            "id": "s005",
            "name": "초옹장",
            "category": "칼국수",
            "open_time": "10:30",
            "close_time": "20:30",
            "closed_weekdays": [],
            "address": "경기 화성시 남양읍",
            "logo_url": "/static/logos/s005.png",
            "menus": ["들깨옹심이메밀칼국수", "멸치옹심이메밀칼국수", "들깨옹심이", "새뱅이 장칼국수"],
            "timezone": "Asia/Seoul",
        },
        "settings": {"negative_review_auto_reply": None},
        "events": [],
        "games": [],
        "reservations": [
            {"id": "rs_0031", "starts_at": at(17, 12), "party_size": 12, "kind": "group", "name": None},
            {"id": "rs_0032", "starts_at": at(17, 18), "party_size": 4, "kind": "general", "name": None},
            {"id": "rs_0033", "starts_at": at(17, 19), "party_size": 2, "kind": "general", "name": None},
            {"id": "rs_0034", "starts_at": at(18, 18), "party_size": 3, "kind": "general", "name": None},
            {"id": "rs_0035", "starts_at": at(18, 19), "party_size": 2, "kind": "general", "name": None},
        ],
        "weather": [
            {"date": "2026-11-17", "rain_chance": 0.7, "rain_from": 14, "temp_min": 3, "temp_max": 11, "label": "비"},
            {"date": "2026-11-18", "rain_chance": 0.3, "temp_min": 2, "temp_max": 10, "label": "흐림"},
            {"date": "2026-11-19", "rain_chance": 0.8, "temp_min": 3, "temp_max": 9, "label": "비"},
            {"date": "2026-11-20", "rain_chance": 0.2, "temp_min": 0, "temp_max": 8, "label": "구름"},
            {"date": "2026-11-21", "rain_chance": 0.1, "temp_min": -1, "temp_max": 7, "label": "맑음"},
            {"date": "2026-11-22", "rain_chance": 0.1, "temp_min": -2, "temp_max": 6, "label": "맑음"},
        ],
        # 답글을 기다리는 리뷰 5개: 좋은 리뷰 3개, 아쉬운 리뷰 2개 (D-09)
        "reviews": [
            {
                "id": "rv_0412", "platform": "baemin", "rating": 2, "order_channel": "delivery",
                "text": "면이 불어서 왔어요.", "written_at": at(16, 21, 40), "sentiment": "negative", "topic": "delivery",
                "summary": "면이 불어서 왔대요", "reply_status": "none",
                "reply_text": None, "reply_summary": None, "reply_posted_at": None, "replied_in_minutes": None,
            },
            {
                "id": "rv_0410", "platform": "naver", "rating": 2, "order_channel": "hall",
                "text": "옹심이가 조금 퍼져 있었어요.", "written_at": at(16, 13, 10), "sentiment": "negative", "topic": "taste",
                "summary": "옹심이가 퍼졌대요", "reply_status": "none",
                "reply_text": None, "reply_summary": None, "reply_posted_at": None, "replied_in_minutes": None,
            },
            {
                "id": "rv_0401", "platform": "naver", "rating": 5, "order_channel": "hall",
                "text": "들깨 국물이 정말 고소해요. 비 오는 날 또 올게요.", "written_at": at(15, 20, 5), "sentiment": "positive",
                "topic": "taste", "summary": "들깨 국물이 고소하대요", "reply_status": "scheduled",
                "reply_text": "비 오는 날엔 따끈한 들깨옹심이가 더 맛있어요. 오늘 같은 날 또 들러 주세요.", "reply_post_at": at(19, 8),
            },
            {
                "id": "rv_0405", "platform": "naver", "rating": 5, "order_channel": "hall",
                "text": "점심에 먹기 딱 좋아요. 옹심이가 쫀득해요.", "written_at": at(15, 12, 30), "sentiment": "positive",
                "topic": "taste", "summary": "옹심이가 쫀득하대요", "reply_status": "scheduled",
                "reply_text": "점심 한 그릇으로 든든하시죠. 쫀득한 옹심이 그대로 준비해 둘게요.", "reply_post_at": at(20, 10, 30),
            },
            {
                "id": "rv_0409", "platform": "baemin", "rating": 4, "order_channel": "delivery",
                "text": "양이 넉넉해서 든든했어요.", "written_at": at(16, 19, 45), "sentiment": "positive",
                "topic": "portion", "summary": "양이 넉넉하대요", "reply_status": "scheduled",
                "reply_text": "든든하게 드셨다니 기뻐요. 주말에도 넉넉하게 준비해 둘게요.", "reply_post_at": at(21, 11),
            },
        ],
        # 최근 7일 좋은 리뷰 14개에서 찾은 것 (F5의 결과, D-12)
        "strengths": {
            "positive_count": 14,
            "items": [
                {"id": "b_1", "label": "고소한 들깨 국물", "count": 9},
                {"id": "b_2", "label": "쫀득한 옹심이", "count": 6},
                {"id": "b_3", "label": "넉넉한 양", "count": 4},
            ],
            "keep": "들깨는 지금처럼 그날 아침에 갈아 주세요",
        },
        # F6의 결과: 언제, 왜 (D-13)
        "scheduled": [
            {
                "id": "sr_1", "day_label": "목", "time_label": "아침 8시", "post_at": at(19, 8),
                "reason": {"kind": "weather", "label": "비 소식"}, "text": "비 오는 날 옹심이 권하기", "review_ids": ["rv_0401"],
                "say": "목요일엔 비가 와서 비 오는 날 옹심이를 권하는 답글을 올릴게요.",
            },
            {
                "id": "sr_2", "day_label": "금", "time_label": "오전 10시 반", "post_at": at(20, 10, 30),
                "reason": {"kind": "lunch", "label": "점심 손님"}, "text": "점심 메뉴 고를 때 보시게", "review_ids": ["rv_0405"],
                "say": "금요일은 점심 메뉴를 고를 때 보시게 오전에 올릴게요.",
            },
            {
                "id": "sr_3", "day_label": "토", "time_label": "오전 11시", "post_at": at(21, 11),
                "reason": {"kind": "weekend", "label": "주말"}, "text": "주말에 리뷰를 많이 봐요", "review_ids": ["rv_0409"],
                "say": "나머지는 리뷰를 많이 보는 토요일 오전에 올릴게요.",
            },
        ],
        # 이번 달 가장 많이 나간 메뉴 (포스 매출, D-03, D-14)
        "top_menus": [
            _menu("m_1", "들깨옹심이메밀칼국수", 461, "deulkkae-ongsimi-memil-kalguksu"),
            _menu("m_2", "멸치옹심이메밀칼국수", 308, "myeolchi-ongsimi-memil-kalguksu"),
            _menu("m_3", "들깨옹심이", 284, "deulkkae-ongsimi"),
            _menu("m_4", "새뱅이 장칼국수", 258, "saebaengi-jangkalguksu"),
        ],
        "instagram": {
            "connected": True,
            "handle": "choongjang_namyang",
            "quote": "들깨 국물이 정말 고소해요",
            "caption": "이번 달 가장 많이 나간 메뉴 1, 2, 3이에요. 손님 한마디: \"들깨 국물이 정말 고소해요\"",
            "slides": 4,
            "posted_at": None,
            "likes": 42,
            "story_mentions": [],
        },
        # 알바생. in_at 은 그날 처음 알바생 화면을 연 시각 (= 출근). 정우는 초대만 받고 아직 안 들어왔다 (D-31).
        "staff": [
            _staff("st_namgung", "남궁현", "현", in_at=at(17, 10)),
            _staff("st_yang", "양지성", "지성", in_at=at(17, 11, 30)),
            _staff("st_harin", "문하린", "하린", in_at=at(17, 14, 58)),
            _staff("st_bae", "배수아", "수아"),
            _staff("st_baek", "백서윤", "서윤"),
            {**_staff("st_jungwoo", "정우", "정우", joined=False), "invited_at": at(16, 15, 40)},
        ],
        "invites": {"482017": "st_harin"},
        # 매뉴얼 세 묶음 (D-06). 알바생 화면에는 그날 할 일로 올라간다 (F-06).
        "manual": {
            "before_open": ["바닥과 테이블 청소", "수저 채우기"],
            "open": ["빈 테이블 정리", "품절 안내"],
            "closing": ["바닥 청소", "냉장고 온도 적기"],
        },
        "tasks": [
            {**_task("tk_floor", "오픈 전 바닥 닦기", "before_open", short="바닥 닦기"), "done": {"st_namgung": at(17, 10, 50)}},
            _task("tk_fridge", "마감 때 냉장고 온도 적기", "closing", short="냉장고 온도"),
        ],
        "notices": [],
        # 오늘 한 것. 도나가 한 일은 미리 적혀 있고, 사장님이 한 일은 일어날 때 더해진다.
        "activity": [
            {"id": "a_read", "actor": "donna", "text": "밤사이 리뷰 5개를 읽고 나눴어요", "at": at(17, 8, 40)},
            {"id": "a_sched", "actor": "donna", "text": "좋은 리뷰 답글 3개를 예약했어요", "at": at(17, 8, 50)},
            {"id": "a_brief", "actor": "donna", "text": "오늘 일정 브리핑을 준비했어요", "at": at(17, 9, 0)},
        ],
        # 브리핑 동안 한 것 (D-16의 "오늘 아침에 한 것")
        "morning_done": [],
        "past": [
            {"label": "어제", "date_label": "11월 16일 월요일", "items": [
                {"id": "y_1", "actor": "donna", "text": "리뷰 7개를 읽고 나눴어요"},
                {"id": "y_2", "actor": "donna", "text": "좋은 리뷰 2개에 답글을 올렸어요"},
                {"id": "y_3", "actor": "owner", "text": "오늘 일정 브리핑을 들었어요"},
            ]},
            {"label": "지난주", "date_label": "11월 9일 ~ 15일", "items": [
                {"id": "w_1", "actor": "donna", "text": "답글 11개를 올렸어요"},
                {"id": "w_2", "actor": "owner", "text": "브리핑을 다섯 번 들었어요"},
            ]},
        ],
        "sessions": {},
        "requests": {},
        "turn_seq": 141,
        "seq": 0,
    }


STATE: dict = _base()


def reset(scenario: str = "first_day") -> None:
    STATE.clear()
    STATE.update(copy.deepcopy(_base()))
    if scenario == "setup":
        STATE["instagram"]["connected"] = False
        STATE["staff"] = [{**s, "joined": False, "in_at": None} for s in STATE["staff"] if s["id"] == "st_harin"]
        STATE["invites"] = {}
        STATE["manual"] = {}
        STATE["tasks"] = []
        STATE["now"] = dt.datetime(2026, 11, 16, 15, 2, tzinfo=KST)
    elif scenario == "next_day":
        STATE["settings"]["negative_review_auto_reply"] = True
        rv = STATE["reviews"][0]
        rv.update(
            reply_status="posted",
            reply_text="불어서 드시게 해 정말 죄송합니다. 다음부터 배달은 면과 국물을 따로 담아 보내 드릴게요. 다시 찾아 주시면 제대로 된 한 그릇으로 보답하겠습니다.",
            reply_summary="사과하고, 다음엔 면을 따로 담겠다고 답했어요",
            reply_posted_at=at(16, 21, 52),
            replied_in_minutes=12,
        )


def now() -> dt.datetime:
    return STATE["now"]


def new_id(prefix: str) -> str:
    STATE["seq"] += 1
    return f"{prefix}_{STATE['seq']:04d}"


def log(actor: str, text: str, key: str) -> None:
    """오늘 한 것에 한 줄 더한다. 같은 일은 한 번만 적는다."""
    if any(a["id"] == key for a in STATE["activity"]):
        return
    STATE["activity"].append({"id": key, "actor": actor, "text": text, "at": now().isoformat()})


def date_label(d: dt.date) -> str:
    return f"{d.month}월 {d.day}일 {WEEKDAYS[d.weekday()]}요일"


def hm(text: str) -> dt.time:
    h, m = text.split(":")
    return dt.time(int(h), int(m))


def clock_label(t: dt.time | dt.datetime) -> str:
    """오전 10시 30분, 저녁 8시 30분 (화면 글)."""
    h, m = t.hour, t.minute
    part = "오전" if h < 12 else "낮" if h == 12 else "오후" if h < 17 else "저녁" if h < 21 else "밤"
    h12 = h if h <= 12 else h - 12
    return f"{part} {h12}시" + (f" {m}분" if m else "")


def store_status() -> dict:
    """가게 상태 줄 (v0.2.1). 영업시간에서 바로 나온다."""
    s = STATE["store"]
    t = now().timetz().replace(tzinfo=None)
    open_t, close_t = hm(s["open_time"]), hm(s["close_time"])
    if t < open_t:
        return {"state": "before_open", "label": "영업 전", "detail": f"{clock_label(open_t)}에 열어요"}
    if t < close_t:
        return {"state": "open", "label": "영업 중", "detail": f"{clock_label(close_t)}에 닫아요"}
    return {"state": "closed", "label": "영업 끝", "detail": f"내일 {clock_label(open_t)}에 열어요"}


def staff_by_call(word: str) -> dict | None:
    for s in STATE["staff"]:
        if word and (word.startswith(s["call"]) or word.startswith(s["name"]) or s["name"].endswith(word)):
            return s
    return None


def present_staff() -> list[dict]:
    """오늘 나온 사람: 오늘 알바생 화면을 연 사람."""
    t = now()
    return [s for s in STATE["staff"] if s["joined"] and s["in_at"] and dt.datetime.fromisoformat(s["in_at"]) <= t and not s["out_at"]]
