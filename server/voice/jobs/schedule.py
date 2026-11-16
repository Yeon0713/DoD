"""F6 좋은 리뷰 답글 올릴 때와 이유 정하기 (규칙). 답글 본문은 voice_reply 에이전트가 쓴다.

내일부터 7일 안의 '좋은 때'를 우선순위대로 찾는다.
  weather  비 소식(rain_chance ≥ 0.6)이 있는 첫날 아침 8시
  game     첫 경기 시작 1시간 30분 전 (정시로 내림)
  event    첫 행사 전날 오전 11시
  season   (비 소식이 없을 때) 최고 기온 5도 이하인 첫날 아침 8시
  weekend  다음 토요일 오전 11시
  lunch    (점심을 말한 리뷰가 있을 때) 앞의 때 다음 평일, 문 여는 시각. 점심 메뉴를 고를 때 보시게
답글 기다리는 좋은 리뷰는 먼저 말이 맞는 때(비 오는 날 → weather, 점심 → lunch, 주말 → weekend)에 하나씩 붙이고,
나머지를 오래된 것부터 앞의 때부터 붙인다. 남는 리뷰는 마지막 때에 함께 올린다 (같은 때는 한 줄).
"""

import datetime as dt
import re

from app.core.seoul_time import SEOUL, at_time
from voice import speech, width
from voice.clock import parse

RAIN_CHANCE = 0.6
COLD_MAX = 5
MAX_ROWS = 3
AFFINITY = {"weather": re.compile(r"비\s?(오는|올|와|올때)"), "lunch": re.compile(r"점심"), "weekend": re.compile(r"주말")}


def _at(day: dt.date, hour: int) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, hour, tzinfo=SEOUL)


def _short(name: str, fallback: str) -> str:
    return name if width.fits(name, "reason.label") else fallback


def occasions(data: dict[str, list[dict]], today: dt.date, reviews: list[dict] | None = None, store: dict | None = None) -> list[dict]:
    """{kind, label, explanation, post_at(datetime)} 를 우선순위 순서로."""
    days = [today + dt.timedelta(days=n) for n in range(1, 8)]
    rain_menu = (store or {}).get("rain_menu")
    weather = {w["date"]: w for w in data.get("weather", [])}
    found: list[dict] = []

    rainy = next((d for d in days if (weather.get(d.isoformat()) or {}).get("rain_chance", 0) >= RAIN_CHANCE), None)
    if rainy:
        found.append({"kind": "weather", "label": "비 소식", "post_at": _at(rainy, 8),
                      "explanation": f"{speech.weekday(rainy)}요일엔 비가 와서, 그날 아침에 비 오는 날 {rain_menu or '메뉴'}를 권하는 답글을 올려요"})
    games = sorted((g for g in data.get("game", []) if parse(g["starts_at"]).date() in days), key=lambda g: g["starts_at"])
    if games:
        start = parse(games[0]["starts_at"])
        post_at = (start - dt.timedelta(minutes=90)).replace(minute=0)
        found.append({"kind": "game", "label": _short(games[0]["name"], "경기"), "post_at": post_at,
                      "explanation": f"{speech.weekday(start.date())}요일 {games[0]['name']} 전에, 경기 보기 전에 들르시게 해요"})
    events = sorted((e for e in data.get("event", []) if parse(e["starts_at"]).date() in days), key=lambda e: e["starts_at"])
    if events:
        start = parse(events[0]["starts_at"])
        eve = start.date() - dt.timedelta(days=1)
        found.append({"kind": "event", "label": _short(events[0]["name"], "행사"), "post_at": _at(max(eve, days[0]), 11),
                      "explanation": f"{events[0]['name']} 전날에 미리 올려 답글을 보고 방문하시게 해요"})
    cold = next((d for d in days if (weather.get(d.isoformat()) or {}).get("temp_max", 99) <= COLD_MAX), None)
    if cold and not rainy:
        found.append({"kind": "season", "label": "추위", "post_at": _at(cold, 8),
                      "explanation": "날이 추워져서 국물 메뉴를 권하는 답글을 올려요"})
    saturday = next(d for d in days if d.weekday() == 5)
    found.append({"kind": "weekend", "label": "주말", "post_at": _at(saturday, 11),
                  "explanation": "리뷰를 많이 보는 토요일 오전에 모아서 올려요"})
    opens = (store or {}).get("open_time")
    if reviews and opens and any(AFFINITY["lunch"].search(r["text"]) for r in reviews) and opens < "12:00":
        used = {o["post_at"].date() for o in found}
        after = min(used)
        lunch_day = next((d for d in days if d > after and d.weekday() < 5 and d not in used), None)
        if lunch_day:
            found.append({"kind": "lunch", "label": "점심 손님", "post_at": at_time(lunch_day, opens),
                          "explanation": f"{speech.weekday(lunch_day)}요일은 점심 메뉴를 고를 때 보시게 오전에 올려요"})
    return found


def card_text(kind: str, menus: list[dict], rain_menu: str | None = None) -> str:
    """scheduled[].text (폭 13 안)."""
    from voice.jobs.strengths import SOUP_RE

    if kind == "weather":
        soup = next((m["name"] for m in menus if SOUP_RE.search(m["name"])), "")
        short = rain_menu or ("전골" if "전골" in soup else "탕" if "탕" in soup else "국물")
        return width.fit("scheduled.text", f"비 오는 날 {short} 권하기", "비 오는 날 국물 권하기")
    return {
        "game": "경기 보기 전에 들르시게",
        "event": "행사 가기 전에 들르시게",
        "season": "추운 날 국물 권하기",
        "weekend": "주말에 리뷰를 많이 봐요",
        "lunch": "점심 메뉴 고를 때 보시게",
    }[kind]


def assign(reviews: list[dict], found: list[dict]) -> list[tuple[dict, dict]]:
    """(리뷰, 때) 짝. 말이 맞는 때에 먼저 하나씩 붙이고, 나머지는 오래된 것부터 아직 빈 때에 앞에서부터 붙인다.
    때는 MAX_ROWS 개까지 쓰고, 남는 리뷰는 마지막 때에 함께 붙인다."""
    slots = found[:MAX_ROWS]
    ordered = sorted(reviews, key=lambda r: r["written_at"])
    pairs: list[tuple[dict, dict]] = []
    taken: set[int] = set()
    left = []
    for review in ordered:
        match = next((n for n, slot in enumerate(slots) if n not in taken and slot["kind"] in AFFINITY
                      and AFFINITY[slot["kind"]].search(review["text"])), None)
        if match is None:
            left.append(review)
        else:
            taken.add(match)
            pairs.append((review, slots[match]))
    free = [n for n in range(len(slots)) if n not in taken]
    for number, review in enumerate(left):
        slot = free[number] if number < len(free) else len(slots) - 1
        pairs.append((review, slots[slot]))
    return pairs


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
        result.append({
            "id": f"sr_{number}", "day_label": speech.weekday(post_at.date()), "time_label": speech.clock_label(post_at),
            "post_at": post_at.isoformat(timespec="seconds"), "reason": {"kind": reason["kind"], "label": reason["label"]},
            "text": card_text(reason["kind"], menus, rain_menu), "review_ids": [m["id"] for m in members],
            "explanation": reason["explanation"],  # 말할 때 쓴다. 카드에는 앱이 쓰지 않는 칸
        })
    return result
