"""StoreSnapshot 을 읽는 공용 도구 (읽기 전용, DB 에 쓰지 않는다).

시각은 "19시(오후 7시)"처럼 두 표기를 함께 돌려준다. 모델이 어느 쪽으로 써도 근거 대조를 통과하게 하려는 것이다.
"""

import datetime as dt

from app.core.seoul_time import to_seoul
from app.menu_board.menu_candidates import KIND_NAMES
from app.planner.notification_time_helpers import KOREAN_WEEKDAYS
from Harness.spec import RunContext, Tool
from Harness.tools import NO_ARGS, obj, string

DAYPART_NAMES = {"LUNCH": "점심", "DINNER": "저녁", "NIGHT": "야간"}
SIGNAL_NAMES = {"HIGH": "많음", "NORMAL": "보통", "LOW": "적음"}


def hour_label(hour: int) -> str:
    if hour == 0:
        spoken = "밤 12시"
    elif hour < 12:
        spoken = f"오전 {hour}시"
    elif hour == 12:
        spoken = "낮 12시"
    else:
        spoken = f"오후 {hour - 12}시"
    return f"{hour}시({spoken})"


def day_label(day: dt.date) -> str:
    return f"{day.month}월 {day.day}일({KOREAN_WEEKDAYS[day.weekday()]})"


def parse_date(text: object) -> dt.date:
    try:
        return dt.date.fromisoformat(str(text).strip()[:10])
    except ValueError:
        raise ValueError(f"날짜는 YYYY-MM-DD 로 적어 주세요 (받은 값: {text!r})") from None


def menu_list(ctx: RunContext, task: dict, args: dict) -> list[dict]:
    return [
        {"menu_id": m.menu_id, "name": m.name, "category": m.category, "price": m.price}
        for m in ctx.snapshot.inputs.menus
    ]


def store_facts(ctx: RunContext, task: dict, args: dict) -> dict:
    if not ctx.store_facts:
        return {"facts": [], "note": "등록된 가게 사실이 없어요. 가게 사정(재료, 조리법, 직원 등)은 쓰지 마세요."}
    return {"facts": ctx.store_facts, "note": "이 목록에 있는 사실만 글자 그대로 쓸 수 있어요."}


def day_context(ctx: RunContext, task: dict, args: dict) -> dict:
    try:
        day = parse_date(args.get("date"))
    except ValueError as error:
        return {"error": str(error)}
    inputs = ctx.snapshot.inputs
    weather = next((w for w in inputs.weather if w.date == day), None)
    events = [
        {"title": e.title, "kind": KIND_NAMES.get(e.kind, e.kind), "distance_km": round(e.distance_km, 1),
         "starts": f"{to_seoul(e.start_at):%m-%d %H:%M}", "ends": f"{to_seoul(e.end_at):%m-%d %H:%M}"}
        for e in inputs.events
        if to_seoul(e.start_at).date() <= day <= to_seoul(e.end_at).date()
    ]
    games = [
        {"title": g.title, "kind": KIND_NAMES.get(g.kind, g.kind), "starts": hour_label(to_seoul(g.start_at).hour)}
        for g in inputs.games
        if to_seoul(g.start_at).date() == day
    ]
    calendar = [
        {"daypart": DAYPART_NAMES.get(c.daypart, c.daypart), "signal": SIGNAL_NAMES.get(c.signal, c.signal),
         "ratio": round(c.ratio, 2), "reason": c.reason_text}
        for c in ctx.snapshot.calendar_cells
        if c.date == day
    ]
    return {
        "date": day_label(day),
        "weather": None if weather is None else {
            "temp_max": weather.temp_max, "temp_min": weather.temp_min, "rain_mm": weather.rain_mm,
        },
        "events": events,
        "games": games,
        "calendar": calendar,
    }


MENU_LIST = Tool("get_menu_list", "우리 가게 메뉴 목록 (menu_id, 이름, 종류 MAIN/SIDE/DRINK, 가격)", NO_ARGS, menu_list)
STORE_FACTS = Tool(
    "get_store_facts",
    "가게가 직접 등록한 사실 메모 (재료, 조리 방법 등). 여기 있는 사실만 글에 쓸 수 있다",
    NO_ARGS,
    store_facts,
)
DAY_CONTEXT = Tool(
    "get_day_context",
    "그날의 날씨, 근처 행사, 경기, 우리 가게 달력(시간대별 예상 수요)",
    obj({"date": string("날짜 YYYY-MM-DD")}),
    day_context,
)
