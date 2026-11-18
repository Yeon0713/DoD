"""포스터 할 일 하나의 상황: 그날 행사·경기, 날씨(덥다·춥다·비·눈·장마), 계절, 가게 메뉴.

CLOVA 가 멘트를 고르고(ment.py) 그림 프롬프트를 만들 때(prompt.py) 이 값을 쓴다.
"""

import datetime as dt
from dataclasses import dataclass, field

from app.data_pipeline import registered_stores
from app.data_pipeline.store_snapshot_cache import StoreSnapshot

KOREAN_WEEKDAYS = "월화수목금토일"
HOT = 30.0  # 낮 최고 이 도 이상이면 덥다
COLD = 10.0  # 낮 최고 이 도 아래면 춥다
RAIN = 1.0  # 이 mm 이상이면 비
MONSOON = ((6, 19), (7, 27))  # 장마철 (중부 평년 6월 하순 ~ 7월 하순)


@dataclass
class Situation:
    store_id: str
    store_name: str
    category: str
    address: str
    date: dt.date
    kind: str  # EVENT, GAME, WEEKEND (행사·경기가 없는 주말), RAIN (음성 앱 비 오는 날 스토리 이벤트)
    title: str  # 행사·경기 이름. 주말이면 "이번 주말"
    start_at: dt.datetime | None = None
    distance_km: float | None = None
    temp_max: float | None = None
    temp_min: float | None = None
    rain_mm: float | None = None
    weather_tags: list[str] = field(default_factory=list)  # HOT, COLD, RAIN, SNOW, MONSOON
    season: str | None = None  # 달력이 그날을 계절 날로 본다: "WINTER", "SUMMER" (season_winter 같은 근거)
    menus: list[str] = field(default_factory=list)  # 메인 메뉴 이름

    @property
    def date_ko(self) -> str:
        return f"{self.date.month}월 {self.date.day}일({KOREAN_WEEKDAYS[self.date.weekday()]})"

    def lines(self) -> list[str]:
        """사장님께 보일 상황 몇 줄"""
        out = []
        if self.kind == "EVENT":
            where = f", 가게에서 {self.distance_km:.1f}km" if self.distance_km is not None else ""
            out.append(f"{self.date_ko} {self.title}{where}")
        elif self.kind == "GAME":
            when = f" {self.start_at:%H:%M}" if self.start_at else ""
            out.append(f"{self.date_ko}{when} {self.title}")
        else:
            out.append(f"{self.date_ko} 주말")
        weather = self.weather_line()
        if weather:
            out.append(weather)
        return out

    def weather_line(self) -> str | None:
        parts = []
        if self.temp_max is not None:
            parts.append(f"낮 {round(self.temp_max, 1):g}도")
        words = {"HOT": "더워요", "COLD": "쌀쌀해요", "RAIN": "비 소식이 있어요", "SNOW": "눈 소식이 있어요", "MONSOON": "장마철이에요"}
        parts += [words[t] for t in self.weather_tags]
        if self.season == "WINTER" and "COLD" not in self.weather_tags:
            parts.append("추운 날씨예요")
        elif self.season == "SUMMER" and "HOT" not in self.weather_tags:
            parts.append("더운 날씨예요")
        return ", ".join(parts) if parts else None


def _weather_tags(day: dt.date, temp_max: float | None, temp_min: float | None, rain: float | None) -> list[str]:
    tags = []
    if temp_max is not None and temp_max >= HOT:
        tags.append("HOT")
    if temp_max is not None and temp_max < COLD:
        tags.append("COLD")
    if rain is not None and rain >= RAIN:
        cold_enough = temp_max is not None and temp_max <= 1 or temp_min is not None and temp_min <= -2
        tags.append("SNOW" if cold_enough else "RAIN")
    if MONSOON[0] <= (day.month, day.day) <= MONSOON[1]:
        tags.append("MONSOON")
    return tags


def from_plan(snapshot: StoreSnapshot, plan_id: str) -> Situation:
    """포스터 할 일 id(POSTER:{근거 id}:{날짜})로 상황을 모은다. 계획에 없어도 id 로 날짜와 근거를 읽는다."""
    parts = plan_id.split(":")
    if len(parts) != 3 or parts[0] != "POSTER":
        raise ValueError("포스터 할 일 id 가 아니에요")
    ref_id, day = parts[1], dt.date.fromisoformat(parts[2])
    inputs = snapshot.inputs
    store = snapshot.store
    event = next((e for e in inputs.events if e.event_id == ref_id), None)
    game = next((g for g in inputs.games if g.game_id == ref_id), None)
    weather = next((w for w in inputs.weather if w.date == day), None)
    season = None
    for cell in snapshot.calendar_cells:
        if cell.date == day:
            for reason in cell.reasons:
                if reason.tag == "SEASON":
                    season = reason.ref_id.removeprefix("season_").upper()
    info = registered_stores.place_info(snapshot.store_id)
    menus = [m.name for m in info.menus] if info and info.menus else [m.name for m in inputs.menus if m.category == "MAIN"]
    situation = Situation(
        store_id=snapshot.store_id,
        store_name=(info.name if info else store["name"]),
        category=(info.category if info and info.category else store.get("category", "")),
        address=(info.road_address or info.address) if info else store.get("address", "").replace("(가상)", "").strip(),
        date=day,
        kind="EVENT" if event else "GAME" if game else "WEEKEND",
        title=event.title if event else game.title if game else "이번 주말",
        start_at=event.start_at if event else game.start_at if game else None,
        distance_km=event.distance_km if event else None,
        temp_max=weather.temp_max if weather else None,
        temp_min=weather.temp_min if weather else None,
        rain_mm=weather.rain_mm if weather else None,
        season=season,
        menus=menus[:20],
    )
    if weather:
        situation.weather_tags = _weather_tags(day, weather.temp_max, weather.temp_min, weather.rain_mm)
    return situation
