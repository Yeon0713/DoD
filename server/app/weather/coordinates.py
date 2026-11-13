"""위치 계산. API 를 부르지 않는 순수 함수만 둔다.

- to_grid: WGS84 위도·경도 → 단기예보 격자 (nx, ny). 기상청 단기예보 활용가이드의 람베르트 정각원추도법(LCC) 변환
- distance_km: 두 지점 사이 거리 (관측소 고르기)
"""

import math

# 단기예보 활용가이드의 격자 변환 값 (지도 반경, 격자 간격, 표준위도 1·2, 기준점 경도·위도, 기준점 격자 X·Y)
RE_KM = 6371.00877
GRID_KM = 5.0
SLAT1, SLAT2 = 30.0, 60.0
OLON, OLAT = 126.0, 38.0
XO, YO = 43, 136


def to_grid(latitude: float, longitude: float) -> tuple[int, int]:
    deg = math.pi / 180.0
    re = RE_KM / GRID_KM
    slat1, slat2, olon, olat = SLAT1 * deg, SLAT2 * deg, OLON * deg, OLAT * deg

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = sf**sn * math.cos(slat1) / sn
    ro = re * sf / math.tan(math.pi * 0.25 + olat * 0.5) ** sn

    ra = re * sf / math.tan(math.pi * 0.25 + latitude * deg * 0.5) ** sn
    theta = longitude * deg - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn
    nx = math.floor(ra * math.sin(theta) + XO + 0.5)
    ny = math.floor(ro - ra * math.cos(theta) + YO + 0.5)
    return nx, ny


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """대원 거리 (하버사인)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))

