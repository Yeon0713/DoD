"""ASOS 관측소 찾기. 기상청 지점정보(stn_inf.php, inf=SFC)를 받아 가게에서 가까운 순으로 고른다.

관측소 번호와 위치를 짐작해 적어 두지 않고 공식 지점정보에서 읽는다 (지난 관측을 받을 관측소를 고르는 데만 쓴다).
지점정보는 자주 바뀌지 않으므로 하루 동안 메모리에 보관한다.
"""

import datetime as dt

from app.weather.client import KmaClient, KmaResponseError
from app.weather.coordinates import distance_km
from app.weather.parsing import typ01_rows
from app.weather.schemas import Station

STATION_PATH = "/api/typ01/url/stn_inf.php"
KEEP = dt.timedelta(hours=24)

_cache: tuple[dt.datetime, list[Station]] | None = None


def parse_stations(text: str) -> list[Station]:
    stations = []
    for row in typ01_rows(text, ["STN_ID", "LON", "LAT"], skip_mismatched=True, rest_in_last=True):
        try:
            station_id, lon, lat = int(row["STN_ID"]), float(row["LON"]), float(row["LAT"])
        except ValueError:
            continue
        if not (32 <= lat <= 39.5 and 124 <= lon <= 132):  # 칸이 밀려 읽힌 줄은 버린다
            continue
        stations.append(Station(station_id=station_id, name=row.get("STN_KO"), latitude=lat, longitude=lon))
    if not stations:
        raise KmaResponseError("지점정보에서 관측소를 읽지 못했어요")
    return stations


def fetch_stations(client: KmaClient, now: dt.datetime) -> list[Station]:
    """지금 운영 중인 ASOS(지상) 관측소 목록. tm 을 주면 그때 있던 지점만 온다."""
    global _cache
    if _cache and now - _cache[0] < KEEP:
        return _cache[1]
    text = client.get_text(STATION_PATH, {"inf": "SFC", "stn": "", "tm": now.strftime("%Y%m%d%H%M"), "help": "1"})
    stations = parse_stations(text)
    _cache = (now, stations)
    return stations


def clear_cache() -> None:
    global _cache
    _cache = None


def nearest_stations(stations: list[Station], latitude: float, longitude: float, limit: int = 5) -> list[Station]:
    """가까운 순 limit 개. distance_km 를 채운다."""
    measured = [s.model_copy(update={"distance_km": round(distance_km(latitude, longitude, s.latitude, s.longitude), 2)}) for s in stations]
    return sorted(measured, key=lambda s: s.distance_km)[:limit]
