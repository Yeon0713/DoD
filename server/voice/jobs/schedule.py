"""F6 좋은 리뷰 답글 올릴 때와 이유 정하기 (규칙). 답글 본문은 voice_reply 에이전트가 쓴다.

2026-11-18 팀 개선안 (donna-voice/docs/test-scenarios-closed-loop.md P): 올리는 때는 외식을 고민하는 때로 고정한다.
  weekday_to_weekend  월~목에 쓴 리뷰 → 그 주 토요일, 주말 첫 식사 피크 한 시간 전 (10:30 ~ 11:30 안으로).
                      토요일에 쉬면 일요일. 그때가 이미 지났으면 지금 뒤의 첫 식사 피크 한 시간 전.
  weekend_next_peak   금~일에 쓴 리뷰 → 쓴 뒤 24 ~ 48시간 안의 첫 식사 피크 한 시간 전.
                      그 안에 없으면 (지났거나 쉬는 날) max(지금, 쓴 뒤 24시간) 뒤의 첫 식사 피크 한 시간 전.
식사 피크는 가게의 store.peak_hours {"lunch", "dinner"} (포스 주문 시간대로 정한 값), 없으면 점심 12시 · 저녁 6시.
날씨·행사·경기·추위는 시각을 바꾸지 않는다. 올리는 날의 것을 답글 글(context)에만 넣는다.
같은 때에 올리는 답글은 한 줄로 묶는다 (예약 카드는 3줄까지).
"""

import datetime as dt

from app.core.seoul_time import at_time
from voice import hours, speech, width
from voice.clock import parse

RAIN_CHANCE = 0.6
COLD_MAX = 5
MAX_ROWS = 3
DEFAULT_PEAKS = {"lunch": "12:00", "dinner": "18:00"}
WEEKEND_EARLIEST, WEEKEND_LATEST = "10:30", "11:30"  # 토요일 아침 발송 창 (사장님 인터뷰 루틴)
MEAL_NAMES = {"lunch": "점심", "dinner": "저녁"}


def peaks(store: dict) -> dict[str, str]:
    return {**DEFAULT_PEAKS, **(store.get("peak_hours") or {})}


def _minus_hour(hhmm: str) -> str:
    return hours.hhmm(hours.minutes(hhmm) - 60)


def slots(store: dict, start: dt.date, days: int = 10) -> list[tuple[dt.datetime, str]]:
    """start 날부터 문 여는 날마다 (식사 피크 한 시간 전, 'lunch' | 'dinner')."""
    found = []
    for n in range(days):
        day = start + dt.timedelta(days=n)
        if hours.on(store, day) is None:
            continue
        for meal, peak in sorted(peaks(store).items(), key=lambda kv: kv[1]):
            found.append((at_time(day, _minus_hour(peak)), meal))
    return found


def _weekend_morning(store: dict, written: dt.datetime) -> dt.datetime | None:
    """그 주 토요일(쉬면 일요일)의 첫 식사 피크 한 시간 전, 10:30 ~ 11:30 안으로 맞춘 시각."""
    saturday = written.date() + dt.timedelta(days=(5 - written.weekday()) % 7)
    for day in (saturday, saturday + dt.timedelta(days=1)):
        if hours.on(store, day) is None:
            continue
        first = min(peaks(store).values())
        moment = min(max(_minus_hour(first), WEEKEND_EARLIEST), WEEKEND_LATEST)
        return at_time(day, moment)
    return None


def post_time(review: dict, store: dict, now: dt.datetime) -> dict:
    """{kind, label, meal, post_at(datetime)} 이 리뷰의 답글을 올릴 때."""
    written = parse(review["written_at"])
    if written.weekday() <= 3:  # 월~목
        moment = _weekend_morning(store, written)
        if moment and moment > now:
            return {"kind": "weekday_to_weekend", "label": "주말 점심 전", "meal": "lunch", "post_at": moment}
    else:  # 금~일
        early, late = written + dt.timedelta(hours=24), written + dt.timedelta(hours=48)
        for moment, meal in slots(store, early.date(), 4):
            if early <= moment <= late and moment > now:
                return {"kind": "weekend_next_peak", "label": f"{MEAL_NAMES[meal]} 한 시간 전", "meal": meal, "post_at": moment}
    after = max(now, written + dt.timedelta(hours=24)) if written.weekday() >= 4 else now
    moment, meal = next((m, meal) for m, meal in slots(store, after.date(), 14) if m > after)
    kind = "weekday_to_weekend" if written.weekday() <= 3 else "weekend_next_peak"
    return {"kind": kind, "label": f"{MEAL_NAMES[meal]} 한 시간 전", "meal": meal, "post_at": moment}


def context_for(data: dict[str, list[dict]], day: dt.date, store: dict | None = None) -> dict:
    """올리는 날의 날씨·행사·경기. 답글 글에만 쓴다 (시각은 바꾸지 않는다)."""
    weather = next((w for w in data.get("weather", []) if w["date"] == day.isoformat()), None) or {}
    event = next((e for e in sorted(data.get("event", []), key=lambda e: e["starts_at"]) if parse(e["starts_at"]).date() == day), None)
    game = next((g for g in sorted(data.get("game", []), key=lambda g: g["starts_at"]) if parse(g["starts_at"]).date() == day), None)
    rain = weather.get("rain_chance", 0) >= RAIN_CHANCE
    return {
        "rain": rain,
        "cold": not rain and weather.get("temp_max", 99) <= COLD_MAX,
        "event": event["name"] if event else None,
        "game": game["name"] if game else None,
        "rain_menu": (store or {}).get("rain_menu"),
    }


def template_key(reason: dict) -> str:
    """답글 템플릿 고르기 (voice_reply.POSITIVE_TEMPLATES). 그날의 일이 먼저, 없으면 올리는 때."""
    context = reason.get("context") or {}
    if context.get("rain"):
        return "weather"
    if context.get("event"):
        return "event"
    if context.get("game"):
        return "game"
    if context.get("cold"):
        return "season"
    if reason.get("kind") == "weekend_next_peak":
        return "dinner" if reason.get("meal") == "dinner" else "lunch"
    return "weekend"


def explanation(reason: dict, post_at: dt.datetime) -> str:
    """말할 때 쓰는 한 문장 (마침표 없이). 예약 카드에는 넣지 않는다."""
    when = f"{speech.weekday(post_at.date())}요일 {speech.clock_label(post_at)}"
    if reason["kind"] == "weekday_to_weekend":
        return f"평일에 오신 손님 리뷰는 주말 외식을 고민하는 {when}에 올려요"
    return f"주말에 오신 손님 리뷰는 {MEAL_NAMES.get(reason.get('meal'), '식사')} 한 시간 전인 {when}에 올려요"


def context_line(reason: dict) -> str | None:
    """그날의 일로 글을 바꿨으면 한 문장 (마침표 없이)."""
    context = reason.get("context") or {}
    menu = context.get("rain_menu") or "국물 요리"
    if context.get("rain"):
        return f"그날 비 소식이 있어서 {speech.josa(menu, '을', '를')} 권하는 답글로 썼어요"
    if context.get("event"):
        return f"그날 {context['event']} 가시는 길에 들르시라는 답글로 썼어요"
    if context.get("game"):
        return f"그날 {context['game']} 보기 전에 들르시라는 답글로 썼어요"
    if context.get("cold"):
        return "그날 날이 추워서 국물 메뉴를 권하는 답글로 썼어요"
    return None


def occasion_for(review: dict, data: dict[str, list[dict]], store: dict, now: dt.datetime) -> dict:
    """voice_reply 에 넘기는 때와 이유: {kind, label, meal, post_at(datetime), context, template, explanation}."""
    timing = post_time(review, store, now)
    reason = {**timing, "context": context_for(data, timing["post_at"].date(), store)}
    return {**reason, "template": template_key(reason), "explanation": explanation(reason, timing["post_at"])}


def card_text(reason: dict, menus: list[dict], rain_menu: str | None = None) -> str:
    """scheduled[].text (폭 13 안). 그날의 일이 있으면 그것을, 없으면 올리는 때를."""
    from voice.jobs.strengths import SOUP_RE

    key = template_key(reason)
    if key == "weather":
        soup = next((m["name"] for m in menus if SOUP_RE.search(m["name"])), "")
        short = rain_menu or ("전골" if "전골" in soup else "탕" if "탕" in soup else "국물")
        return width.fit("scheduled.text", f"비 오는 날 {short} 권하기", "비 오는 날 국물 권하기")
    return {
        "game": "경기 보기 전에 들르시게",
        "event": "행사 가기 전에 들르시게",
        "season": "추운 날 국물 권하기",
        "weekend": "주말에 리뷰를 많이 봐요",
        "lunch": "점심 메뉴 고를 때 보시게",
        "dinner": "저녁 메뉴 고를 때 보시게",
    }[key]


def rows(scheduled: list[dict], menus: list[dict], now: dt.datetime, rain_menu: str | None = None) -> list[dict]:
    """예약한 답글(reply_status == scheduled, 앞으로 올릴 것) → scheduled 카드 줄. 같은 때는 한 줄로, 최대 3줄."""
    groups: dict[str, list[dict]] = {}
    for review in sorted(scheduled, key=lambda r: r["reply_post_at"]):
        if parse(review["reply_post_at"]) > now:
            groups.setdefault(review["reply_post_at"], []).append(review)
    result = []
    for number, (post_at_text, members) in enumerate(list(groups.items())[:MAX_ROWS], 1):
        post_at = parse(post_at_text)
        reason = members[0]["reply_reason"]
        said = reason.get("explanation") or ""
        extra = context_line(reason)
        result.append({
            "id": f"sr_{number}", "day_label": speech.weekday(post_at.date()), "time_label": speech.clock_label(post_at),
            "post_at": post_at.isoformat(timespec="seconds"), "reason": {"kind": reason["kind"], "label": reason["label"]},
            "text": card_text(reason, menus, rain_menu), "review_ids": [m["id"] for m in members],
            "explanation": said,  # 말할 때 쓴다. 카드에는 앱이 쓰지 않는 칸
            "context_line": extra,
        })
    return result
