"""오늘부터의 날씨: 단기예보 (getVilageFcst).

- 발표: 02, 05, 08, 11, 14, 17, 20, 23시. 발표 10분 뒤부터 API 에 올라온다 (단기예보 활용가이드).
  가장 최근 발표를 부르고, 아직 없으면 직전 발표로 다시 부른다.
- 한 번 발표에 항목이 수백 개라 여러 쪽(page)을 모두 모은다 (client.get_items).
- 쓰는 항목: SKY 하늘상태, PTY 강수형태, TMP 기온, TMN/TMX 최저·최고기온, POP 강수확률, PCP 강수량, SNO 적설.
- TMN·TMX 는 발표 시각에 따라 오늘 값이 없을 수 있다. 그때 시간별 기온으로 대신 계산하지 않고 null 로 둔다.
- PCP·SNO 는 "강수없음", "1mm 미만", "30.0~50.0mm", "50.0mm 이상" 같은 범주 글자다. 원문과 범주의 아래 끝을 함께 둔다.
- 실제 응답(2026-11-13)에서 본 것: 3일 뒤부터는 예보가 3시간 간격이고 PCP·SNO 가 단위 없는 숫자("0", "1")로 온다.
  "0" 은 없음으로 읽고, 그 밖의 단위 없는 숫자는 뜻(1시간·3시간 합계 등)이 문서에 없어 모름(None)으로 둔다.
  마지막 날은 00시 한 시각만 오기도 해서, 오늘이 아니고 최저·최고기온도 없이 MIN_HOURS 보다 적은 시각만 있는 날은 하루 요약을 만들지 않는다.
"""

import datetime as dt
import re
from collections import Counter, defaultdict

from app.core.seoul_time import SEOUL
from app.weather.client import KmaClient, KmaNoDataError
from app.weather.parsing import issue_times, number
from app.weather.schemas import DailyForecast, HourlyForecast, PrecipType, Sky

FORECAST_PATH = "/api/typ02/openApi/VilageFcstInfoService_2.0/getVilageFcst"
BASE_HOURS = (2, 5, 8, 11, 14, 17, 20, 23)
DELAY = dt.timedelta(minutes=10)
TRIES = 3
MIN_HOURS = 3  # 하루 요약을 만들 최소 시각 수 (오늘과 최저·최고기온이 있는 날은 상관없이 만든다)

# 단기예보 활용가이드 코드값
SKY_CODES: dict[int, Sky] = {1: "맑음", 3: "구름많음", 4: "흐림"}
PTY_CODES: dict[int, PrecipType] = {0: "없음", 1: "비", 2: "비/눈", 3: "눈", 4: "소나기"}
SKY_ORDER: list[Sky] = ["맑음", "구름많음", "흐림"]

_AMOUNT = r"(\d+(?:\.\d+)?)"


def amount_range(text: str | None, unit: str) -> tuple[float | None, float | None]:
    """범주 글자 → (아래 끝, 위 끝). 위 끝이 없으면("이상") None. 모르는 글자면 (None, None)."""
    if text is None:
        return None, None
    t = text.replace(" ", "")
    if t in ("강수없음", "적설없음") or t in ("0", "0.0"):
        return 0.0, 0.0
    if re.fullmatch(_AMOUNT, t):  # 단위 없는 0 아닌 숫자: 뜻이 문서에 없다
        return None, None
    if m := re.fullmatch(_AMOUNT + unit + "미만", t):
        return 0.0, float(m.group(1))
    if m := re.fullmatch(_AMOUNT + unit + "이상", t):
        return float(m.group(1)), None
    if m := re.fullmatch(_AMOUNT + "~" + _AMOUNT + unit, t):
        return float(m.group(1)), float(m.group(2))
    if m := re.fullmatch(_AMOUNT + unit, t):
        return float(m.group(1)), float(m.group(1))
    return None, None


def _code(value, codes: dict):
    n = number(value)
    return codes.get(int(n)) if n is not None else None


def daily_sky(skies: list[Sky | None]) -> Sky | None:
    """가장 많은 하늘상태. 같으면 더 흐린 쪽."""
    counts = Counter(s for s in skies if s)
    if not counts:
        return None
    return max(counts, key=lambda s: (counts[s], SKY_ORDER.index(s)))


def daily_precip_type(types: list[PrecipType | None]) -> PrecipType | None:
    """하루 강수형태. 비와 눈이 섞이면 비/눈, 눈만 → 눈, 비 → 비, 소나기만 → 소나기, 모두 없음 → 없음."""
    seen = {t for t in types if t}
    if not seen:
        return None
    rain, snow = bool(seen & {"비", "소나기"}), "눈" in seen
    if "비/눈" in seen or (rain and snow):
        return "비/눈"
    if snow:
        return "눈"
    if "비" in seen:
        return "비"
    if "소나기" in seen:
        return "소나기"
    return "없음"


def _at(day: str, hhmm: str) -> dt.datetime:
    return dt.datetime.strptime(day + hhmm, "%Y%m%d%H%M").replace(tzinfo=SEOUL)


def parse_short_forecast(items: list[dict], issued_at: dt.datetime) -> tuple[list[HourlyForecast], list[DailyForecast]]:
    by_time: dict[dt.datetime, dict] = defaultdict(dict)
    extremes: dict[dt.date, dict] = defaultdict(dict)
    for item in items:
        category, value = item.get("category"), item.get("fcstValue")
        at = _at(item["fcstDate"], item["fcstTime"])
        if category == "TMN":
            extremes[at.date()]["temperature_min"] = number(value)
        elif category == "TMX":
            extremes[at.date()]["temperature_max"] = number(value)
        else:
            by_time[at][category] = value

    hourly = [
        HourlyForecast(
            datetime=at,
            issued_at=issued_at,
            temperature=number(raw.get("TMP")),
            sky=_code(raw.get("SKY"), SKY_CODES),
            precipitation_type=_code(raw.get("PTY"), PTY_CODES),
            precipitation_probability=number(raw.get("POP")),
            precipitation_text=raw.get("PCP"),
            precipitation_mm_min=amount_range(raw.get("PCP"), "mm")[0],
            snow_text=raw.get("SNO"),
        )
        for at, raw in sorted(by_time.items())
    ]

    days: dict[dt.date, list[HourlyForecast]] = defaultdict(list)
    for h in hourly:
        days[h.datetime.date()].append(h)
    daily = []
    for day in sorted(set(days) | set(extremes)):
        hours = days.get(day, [])
        if day != issued_at.date() and day not in extremes and len(hours) < MIN_HOURS:
            continue  # 예보 끝의 00시 한 시각처럼 하루를 대표하지 못하는 날
        pops = [h.precipitation_probability for h in hours if h.precipitation_probability is not None]
        pcps = [h.precipitation_mm_min for h in hours]
        daily.append(
            DailyForecast(
                date=day,
                issued_at=issued_at,
                **extremes.get(day, {}),
                sky=daily_sky([h.sky for h in hours]),
                precipitation_type=daily_precip_type([h.precipitation_type for h in hours]),
                precipitation_mm_min=round(sum(pcps), 1) if hours and None not in pcps else None,
                precipitation_probability_max=max(pops) if pops else None,
                hours=len(hours),
            )
        )
    return hourly, daily


def fetch_short_forecast(client: KmaClient, nx: int, ny: int, now: dt.datetime) -> tuple[dt.datetime, list[HourlyForecast], list[DailyForecast]]:
    for base in issue_times(now, BASE_HOURS, DELAY, TRIES):
        try:
            items = client.get_items(FORECAST_PATH, {"base_date": base.strftime("%Y%m%d"), "base_time": base.strftime("%H%M"), "nx": nx, "ny": ny})
        except KmaNoDataError:
            continue
        if items:
            hourly, daily = parse_short_forecast(items, base)
            return base, hourly, daily
    raise KmaNoDataError("단기예보 자료가 아직 없어요")
