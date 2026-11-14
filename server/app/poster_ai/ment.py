"""포스터 멘트 추천: 상황(행사·경기·날씨·계절·메뉴)을 CLOVA 에 주고 멘트 3개를 받는다.

- 행사가 있는 날: 그 행사와 이어지는 멘트 (예: "축제 구경 전후로 들러 주세요")
- 경기가 있는 날: 응원 이벤트 멘트 (예: "응원하는 팀을 리뷰에 남겨 주시면 다음 방문 쿠폰을 문자로 보내 드려요")
- 덥다·춥다·비·눈·장마: "오늘은 이 메뉴 어떠세요?" (가게 메뉴 중에서 고른다)
CLOVA 키가 없거나 답이 이상하면 정해 둔 문장으로 만든다. 같은 상황은 서버 메모리에 기억해 다시 묻지 않는다.
"""

import json
import re
from dataclasses import asdict, dataclass

from app.core import clova
from app.poster_ai.situation import Situation

HEADLINE_MAX = 18  # 큰 글자 (줄바꿈 빼고)
LINE_MAX = 45  # 작은 글자

SYSTEM = """너는 동네 식당 사장님의 인스타 스토리 포스터 문구를 쓰는 사람이다.
주어진 상황과 메뉴만 보고 포스터 문구 3개를 JSON 배열로만 답한다. 다른 말은 쓰지 않는다.
각 항목: {"kind": "EVENT|GAME|WEATHER|MENU", "label": "사장님이 고를 때 볼 짧은 이름(10자 안)", "headline": "포스터 큰 글자(18자 안, 줄을 나누려면 \\n)", "line": "작은 글자 한 문장(45자 안)", "menu": "추천 메뉴 이름(메뉴 목록에 있는 이름 그대로, 없으면 빈 글자)"}
규칙:
- 행사가 있으면 1개는 그 행사 이름을 넣어 행사 손님을 부르는 문구.
- 경기가 있으면 1개는 응원 이벤트 문구(예: 응원하는 팀을 리뷰에 남겨 주시면 다음 방문 쿠폰을 문자로 보내 드려요).
- 날씨나 계절이 있으면 1개는 "오늘은 이 메뉴 어떠세요?" 처럼 날씨에 맞는 메뉴를 권하는 문구.
- 메뉴 이름은 목록에 있는 것만 쓴다. 가격, 할인율, 없는 혜택은 지어내지 않는다 (쿠폰·서비스는 사장님이 고칠 수 있게 문장만).
- 존댓말, 짧고 따뜻하게. 이모지와 해시태그는 쓰지 않는다."""

_cache: dict[tuple, list["Ment"]] = {}


@dataclass
class Ment:
    kind: str
    label: str
    headline: str
    line: str
    menu: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _user_text(s: Situation) -> str:
    rows = [f"가게: {s.store_name} ({s.category})", f"날짜: {s.date_ko}"]
    if s.kind == "EVENT":
        rows.append(f"근처 행사: {s.title}" + (f" (가게에서 {s.distance_km:.1f}km)" if s.distance_km is not None else ""))
    elif s.kind == "GAME":
        rows.append(f"경기: {s.title}" + (f" {s.start_at:%H:%M} 시작" if s.start_at else ""))
    else:
        rows.append("행사·경기 없는 주말")
    weather = s.weather_line()
    rows.append(f"날씨: {weather}" if weather else "날씨: 모름")
    rows.append("메뉴: " + ", ".join(s.menus[:15]))
    return "\n".join(rows)


def _pick_menu(s: Situation, words: tuple[str, ...]) -> str:
    for word in words:
        for menu in s.menus:
            if word in menu:
                return menu
    return s.menus[0] if s.menus else ""


def fallback(s: Situation) -> list[Ment]:
    """CLOVA 를 못 쓸 때의 기본 멘트"""
    out = []
    if s.kind == "EVENT":
        out.append(Ment("EVENT", "행사 손님 맞이", f"{s.title}\n가는 길에", f"구경 전후로 {s.store_name}에 들러 든든하게 드세요"))
    elif s.kind == "GAME":
        out.append(Ment("GAME", "응원 이벤트", "오늘은\n함께 응원해요", "응원하는 팀을 리뷰에 남겨 주시면 다음 방문 쿠폰을 문자로 보내 드려요"))
    tags = set(s.weather_tags) | ({"COLD"} if s.season == "WINTER" else set()) | ({"HOT"} if s.season == "SUMMER" else set())
    if tags & {"COLD", "SNOW"}:
        menu = _pick_menu(s, ("옹심이", "국밥", "탕", "찌개", "칼국수", "국"))
        out.append(Ment("WEATHER", "추운 날 메뉴", f"쌀쌀한 날엔\n{menu}", f"따끈한 {menu} 한 그릇 어떠세요?", menu))
    elif tags & {"RAIN", "MONSOON"}:
        menu = _pick_menu(s, ("전", "칼국수", "수제비", "국물"))
        out.append(Ment("WEATHER", "비 오는 날 메뉴", f"비 오는 날엔\n{menu}", f"빗소리 들으며 {menu} 어떠세요?", menu))
    elif "HOT" in tags:
        menu = _pick_menu(s, ("냉", "초계", "막국수", "콩국수", "물"))
        out.append(Ment("WEATHER", "더운 날 메뉴", f"더운 날엔\n시원한 {menu}", f"시원한 {menu}로 더위를 식혀 가세요", menu))
    menu = s.menus[0] if s.menus else s.category
    out.append(Ment("MENU", "대표 메뉴", f"오늘은\n{menu} 한 그릇", f"{s.store_name}에서 정성껏 준비해 기다릴게요", menu))
    if len(out) < 3:
        out.append(Ment("MENU", "주말 인사", "이번 주말도\n든든하게", f"{s.store_name}에서 따뜻한 한 끼 하고 가세요", menu))
    return out[:3]


def _clean(raw: dict, menus: list[str]) -> Ment | None:
    try:
        headline = str(raw["headline"]).replace("\\n", "\n").strip()
        line = str(raw["line"]).strip()
    except (KeyError, TypeError):
        return None
    if not headline or not line or len(headline.replace("\n", "")) > HEADLINE_MAX + 4 or len(line) > LINE_MAX + 15:
        return None
    menu = str(raw.get("menu") or "")
    kind = str(raw.get("kind") or "MENU").upper()
    return Ment(
        kind=kind if kind in ("EVENT", "GAME", "WEATHER", "MENU") else "MENU",
        label=str(raw.get("label") or "추천 문구")[:12],
        headline=headline,
        line=line,
        menu=menu if menu in menus else "",
    )


def parse(answer: str | None, menus: list[str]) -> list[Ment]:
    if not answer:
        return []
    match = re.search(r"\[.*\]", answer, re.S)
    if not match:
        return []
    try:
        rows = json.loads(match.group(0))
    except ValueError:
        return []
    ments = [m for m in (_clean(r, menus) for r in rows if isinstance(r, dict)) if m]
    return ments[:3]


def suggest(s: Situation) -> tuple[list[Ment], str]:
    """(멘트 3개, 어디서 왔나 "CLOVA" | "BASIC")"""
    key = (s.store_id, s.date, s.kind, s.title, tuple(s.weather_tags), s.season, tuple(s.menus))
    if key in _cache:
        return _cache[key], "CLOVA"
    ments = parse(clova.ask(SYSTEM, _user_text(s), max_tokens=700, temperature=0.7, timeout=20, feature="poster_ment", store_id=s.store_id), s.menus)
    if len(ments) >= 2:
        _cache[key] = ments
        return ments, "CLOVA"
    return fallback(s), "BASIC"
