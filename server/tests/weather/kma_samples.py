"""기상청 API 가짜 응답. 인증키 없이 날씨 모듈을 시험한다.

typ01 글자 응답은 API허브 문서의 칸 이름을 쓰고, 칸 순서는 응답 안 번호 설명 줄로 정한다 (실제 응답처럼 help=1).
"""

import datetime as dt

from app.weather.client import KmaNoDataError

# 실제 지점정보 응답(2026-11-13)에서 세 관측소 줄만 남긴 것. 칸 이름이 두 줄(STN / ID)로 나뉘고 마지막 칸(주소)에 빈칸이 있다.
# 마지막 999 줄은 잘린 줄 (건너뛰어야 한다)
STATIONS_TEXT = """#START7777
#--------------------------------------------------------------------------------------------------
#   STN_ID : 지점번호
#      LON : 경도(degree) / LAT : 위도(degree)
#   STN_SP : 지점 특성코드
#       HT : 노장 해발고도 (m)
#    HT_PA : 기압계 해발고도 (m)
#    HT_TA : 온도계 지상높이 (m)
#    HT_WD : 풍향/풍속계 지상높이 (m)
#    HT_RN : 우량계 지상높이 (m)
#   STN_KO : 지점명(한글)
#   STN_EN : 지점명(영문)
#   STN_AD : 관리관서번호
#   FCT_ID : 예보구역코드
#   LAW_ID : 법정동코드
#    BASIN : 수계코드
# LAW_ADDR : 법정동주소
#--------------------------------------------------------------------------------------------------
# STN           LON           LAT STN_SP          HT     HT_PA     HT_TA     HT_WD     HT_RN STN STN_KO               STN_EN               FCT_ID   LAW_ID    BASIN LAW_ADDR
#  ID         degee        degree --------         m         m         m         m         m  AD -------------------- -------------------- -------- ---------- ---- ----------------------------------------------------------
  101  127.73570000   37.90262000 31210        75.82     77.05      1.50     10.00      1.40 101 춘천                 Chuncheon            11D10301 5111011800 ---- 강원특별자치도 춘천시 우두동                                
  108  126.96580000   37.57142000 11101        85.67     86.67      1.50     10.00      0.50 108 서울                 Seoul                11B10101 1111017800 ---- 서울특별시 종로구 송월동                                    
  211  128.16811000   38.05991000 32100       202.00    203.00      1.50     10.00      0.50 105 인제                 Inje                 11D10201 5181025022 ---- 강원특별자치도 인제군 인제읍 남북리                         
  999  127.70000000
#7777END
"""

DAILY_COLUMNS = ["TM", "STN", "WS_AVG", "TA_AVG", "TA_MAX", "TA_MIN", "CA_TOT", "RN_DAY", "SD_NEW"]


def daily_text(rows: list[list]) -> str:
    help_lines = [f"#  {i}. {name:<10}: 설명" for i, name in enumerate(DAILY_COLUMNS, start=1)]
    data = [",".join(str(v) for v in row) + "," for row in rows]
    return "\n".join(["#START7777", "#  기상청 지상관측 일자료", *help_lines, "#----", *data, "#7777END"]) + "\n"


def daily_row(day: dt.date, stn: int, ta_avg=5.2, ta_max=11.0, ta_min=-1.3, cloud=2.0, rn=0.0, snow=-9.0) -> list:
    return [day.strftime("%Y%m%d"), stn, 1.8, ta_avg, ta_max, ta_min, cloud, rn, snow]


def short_items(base: dt.datetime) -> list[dict]:
    """base 발표 단기예보: 그날 09시부터 3일 뒤 23시까지 시간별 + 다음 날부터 TMN/TMX.
    다음 날은 하루 종일 흐리고 비, 그다음 날은 오전 눈 오후 비, 나머지는 맑음."""
    items = []
    t = base.replace(hour=9)
    while t.date() <= base.date() + dt.timedelta(days=3):
        d, h = t.strftime("%Y%m%d"), t.strftime("%H%M")
        offset = (t.date() - base.date()).days
        if offset == 1:
            sky, pty, pcp = "4", "1", "2.0mm"
        elif offset == 2:
            sky, pty, pcp = "3", "3" if t.hour < 12 else "1", "1mm 미만"
        else:
            sky, pty, pcp = "1", "0", "강수없음"
        for cat, val in (("TMP", "8"), ("POP", "70" if pty != "0" else "20"), ("PTY", pty), ("PCP", pcp), ("SNO", "적설없음"), ("SKY", sky), ("REH", "60")):
            items.append({"baseDate": base.strftime("%Y%m%d"), "baseTime": base.strftime("%H%M"), "category": cat, "fcstDate": d, "fcstTime": h, "fcstValue": val})
        if h == "0600" and offset > 0:
            items.append({"category": "TMN", "fcstDate": d, "fcstTime": h, "fcstValue": "1.0"})
        if h == "1500" and offset > 0:
            items.append({"category": "TMX", "fcstDate": d, "fcstTime": h, "fcstValue": "12.0"})
        t += dt.timedelta(hours=1)
    return items


class FakeKma:
    """KmaClient 대신. 주소(path)로 가짜 응답을 고른다. calls 에 부른 기록을 남긴다.

    missing_day: 이 날은 관측소가 결측(-99, -9)을 준다.
    short_no_data_bases: 이 발표 시각(HHMM)은 아직 자료가 없다.
    errors: path 일부 → 그 주소에서 낼 오류.
    """

    def __init__(self, missing_day=None, short_no_data_bases=("1100",), errors=None):
        self.missing_day = missing_day
        self.short_no_data_bases = set(short_no_data_bases)
        self.errors = errors or {}
        self.calls: list[tuple[str, dict]] = []

    def _maybe_fail(self, path):
        for part, error in self.errors.items():
            if part in path:
                raise error

    def get_text(self, path: str, params: dict) -> str:
        self.calls.append((path, params))
        self._maybe_fail(path)
        if path.endswith("stn_inf.php"):
            return STATIONS_TEXT
        if path.endswith("kma_sfcdd.php"):
            day = dt.datetime.strptime(params["tm"], "%Y%m%d").date()
            if day == self.missing_day:
                return daily_text([daily_row(day, params["stn"], ta_avg=-99.0, ta_max=-99.0, ta_min=-99.0, cloud=9.6, rn=-9.0)])
            if day.day % 7 == 0:  # 7일, 14일 … 은 흐리고 비 12.5mm
                return daily_text([daily_row(day, params["stn"], cloud=9.4, rn=12.5)])
            return daily_text([daily_row(day, params["stn"])])
        raise AssertionError(path)

    def get_items(self, path: str, params: dict, page_size: int = 1000) -> list[dict]:
        self.calls.append((path, params))
        self._maybe_fail(path)
        if path.endswith("getVilageFcst"):
            if params["base_time"] in self.short_no_data_bases:
                raise KmaNoDataError("아직 없음")
            base = dt.datetime.strptime(params["base_date"] + params["base_time"], "%Y%m%d%H%M")
            return short_items(base)
        raise AssertionError(path)
