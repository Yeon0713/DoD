"""응답 읽기: ASOS 일자료, 단기예보, 그리고 API 호출 오류 구분·재시도·여러 쪽 모으기."""

import datetime as dt
import pathlib

import httpx
import pytest

from app.core.seoul_time import SEOUL
from app.weather.client import (
    KmaAuthError,
    KmaClient,
    KmaInvalidRequestError,
    KmaNoDataError,
    KmaRateLimitError,
    KmaResponseError,
    KmaTimeoutError,
)
from app.weather.observations import parse_daily, precip_type_observed, sky_from_cloud
from app.weather.parsing import number, typ01_rows
from app.weather.short_forecast import amount_range, daily_precip_type, daily_sky, parse_short_forecast
from kma_samples import daily_row, daily_text, short_items

DAY = dt.date(2026, 11, 12)


# ── ASOS 일자료 ──


def test_parse_daily_reads_columns_by_help_numbers():
    text = daily_text([daily_row(DAY, 101, ta_avg=5.2, ta_max=11.0, ta_min=-10.4, cloud=7.2, rn=3.5), daily_row(DAY, 108)])
    day = parse_daily(text, 101, DAY)
    assert (day.temperature_avg, day.temperature_max, day.temperature_min) == (5.2, 11.0, -10.4)  # 영하 10도는 결측이 아니다
    assert (day.precipitation_mm, day.cloud_cover, day.new_snow_cm) == (3.5, 7.2, None)  # 신적설 -9 는 결측
    assert (day.sky, day.precipitation_type) == ("구름많음", "비")
    assert parse_daily(text, 101, DAY - dt.timedelta(days=1)) is None


def test_parse_daily_keeps_missing_as_null_not_zero():
    day = parse_daily(daily_text([daily_row(DAY, 101, ta_avg=-99.0, ta_max=-99.0, ta_min=-99.0, cloud=-9.0, rn=-9.0)]), 101, DAY)
    assert day.temperature_avg is None and day.temperature_min is None and day.precipitation_mm is None
    assert day.sky is None and day.precipitation_type is None  # 모르면 맑음·없음으로 정하지 않는다
    zero = parse_daily(daily_text([daily_row(DAY, 101, rn=0.0)]), 101, DAY)
    assert (zero.precipitation_mm, zero.precipitation_type) == (0.0, "없음")


@pytest.mark.parametrize(("cloud", "sky"), [(0, "맑음"), (5.4, "맑음"), (5.5, "구름많음"), (8.4, "구름많음"), (8.5, "흐림"), (10, "흐림"), (None, None)])
def test_observed_sky_uses_short_forecast_cloud_bands(cloud, sky):
    assert sky_from_cloud(cloud) == sky  # 전운량 0~5 맑음, 6~8 구름많음, 9~10 흐림


def test_observed_precip_type():
    assert precip_type_observed(4.0, 3.2, True) == "눈"
    assert precip_type_observed(4.0, None, True) == "비"
    assert precip_type_observed(0.0, None, True) == "없음"  # 아주 약한 비(0.1mm 미만)
    assert precip_type_observed(None, None, True) == "없음"  # -9: 관측은 됐고 비가 안 온 날
    assert precip_type_observed(None, None, False) is None  # 관측 자체가 빠진 날


def test_parse_real_asos_daily_response():
    """실제 kma_sfcdd.php 응답 (춘천 101, 2026-11-12, 맑고 비 없는 날: 일강수량 -9)."""
    text = (pathlib.Path(__file__).parent / "samples" / "kma_sfcdd_101_20261112.txt").read_text(encoding="utf-8")
    day = parse_daily(text, 101, dt.date(2026, 11, 12))
    assert (day.temperature_avg, day.temperature_min, day.temperature_max, day.cloud_cover) == (5.9, 0.8, 14.4, 4.8)
    assert (day.precipitation_mm, day.new_snow_cm, day.sky, day.precipitation_type) == (None, None, "맑음", "없음")


def test_typ01_reads_header_line_when_no_numbered_help_and_fails_without_names():
    text = "# TM STN TA_AVG\n20261112 101 3.0\n"
    assert typ01_rows(text, ["TM", "STN", "TA_AVG"]) == [{"TM": "20261112", "STN": "101", "TA_AVG": "3.0"}]
    with pytest.raises(KmaResponseError):
        typ01_rows("20261112 101 3.0\n", ["TM", "STN", "TA_AVG"])
    with pytest.raises(KmaResponseError):  # 칸 수가 다르면 짐작하지 않는다
        typ01_rows("# TM STN TA_AVG\n20261112 101\n", ["TM", "STN", "TA_AVG"])


# ── 단기예보 ──


@pytest.mark.parametrize(
    ("text", "expected"),
    [("강수없음", (0.0, 0.0)), ("1mm 미만", (0.0, 1.0)), ("1.0mm 미만", (0.0, 1.0)), ("2.0mm", (2.0, 2.0)),
     ("30.0~50.0mm", (30.0, 50.0)), ("50.0mm 이상", (50.0, None)), ("이상한 값", (None, None)), (None, (None, None))],
)
def test_pcp_categories(text, expected):
    assert amount_range(text, "mm") == expected


def test_snow_categories():
    assert amount_range("적설없음", "cm") == (0.0, 0.0)
    assert amount_range("0.5cm 미만", "cm") == (0.0, 0.5)
    assert amount_range("5.0cm 이상", "cm") == (5.0, None)


def test_number_treats_900_as_missing():
    assert number("-999") is None and number("900") is None and number("") is None and number("-12.5") == -12.5


def test_parse_short_forecast_builds_hourly_and_daily():
    base = dt.datetime(2026, 11, 13, 8, 0, tzinfo=SEOUL)
    hourly, daily = parse_short_forecast(short_items(base.replace(tzinfo=None)), base)
    assert hourly[0].datetime == dt.datetime(2026, 11, 13, 9, 0, tzinfo=SEOUL)
    assert hourly[-1].datetime == dt.datetime(2026, 11, 16, 23, 0, tzinfo=SEOUL)  # API 가 준 마지막 시각까지
    assert all(h.issued_at == base and h.type == "forecast" for h in hourly)
    rainy = next(h for h in hourly if h.datetime.date() == dt.date(2026, 11, 14))
    assert (rainy.sky, rainy.precipitation_type, rainy.precipitation_text, rainy.precipitation_mm_min) == ("흐림", "비", "2.0mm", 2.0)

    by_day = {d.date: d for d in daily}
    today = by_day[dt.date(2026, 11, 13)]
    assert (today.sky, today.precipitation_type, today.temperature_min, today.hours) == ("맑음", "없음", None, 15)  # 오늘 TMN 은 만들지 않는다
    tomorrow = by_day[dt.date(2026, 11, 14)]
    assert (tomorrow.sky, tomorrow.precipitation_type, tomorrow.temperature_min, tomorrow.temperature_max) == ("흐림", "비", 1.0, 12.0)
    assert (tomorrow.precipitation_mm_min, tomorrow.precipitation_probability_max, tomorrow.hours) == (48.0, 70, 24)
    mixed = by_day[dt.date(2026, 11, 15)]  # 오전 눈, 오후 비
    assert (mixed.sky, mixed.precipitation_type, mixed.precipitation_mm_min) == ("구름많음", "비/눈", 0.0)


def test_daily_sky_and_precip_type_rules():
    assert daily_sky(["맑음", "맑음", "흐림"]) == "맑음"
    assert daily_sky(["맑음", "흐림"]) == "흐림"  # 같으면 더 흐린 쪽
    assert daily_sky([None]) is None
    assert daily_precip_type(["없음", "소나기"]) == "소나기"
    assert daily_precip_type(["소나기", "비"]) == "비"
    assert daily_precip_type(["눈", "없음"]) == "눈"
    assert daily_precip_type(["눈", "소나기"]) == "비/눈"
    assert daily_precip_type(["없음", "없음"]) == "없음"
    assert daily_precip_type([None]) is None


# ── API 호출 ──

KEY = "SECRET-KEY-123"


def _client(handler, **kwargs) -> KmaClient:
    return KmaClient(KEY, http=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None, **kwargs)


def _typ02(code="00", items=None, total=None):
    return {"response": {"header": {"resultCode": code, "resultMsg": "X"},
                         "body": {"items": {"item": items} if items is not None else "", "totalCount": total if total is not None else len(items or [])}}}


def test_auth_error_from_api_hub_hides_key():
    client = _client(lambda req: httpx.Response(401, json={"result": {"status": 401, "message": "유효한 인증키가 아닙니다."}}))
    with pytest.raises(KmaAuthError) as info:
        client.get_text("/api/typ01/url/stn_inf.php", {"inf": "SFC"})
    assert KEY not in str(info.value)


def test_missing_key_is_auth_error():
    with pytest.raises(KmaAuthError):
        KmaClient("")


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ("<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg><returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>", KmaAuthError),
        ("<response><header><resultCode>03</resultCode><resultMsg>NO_DATA</resultMsg></header></response>", KmaNoDataError),
        ("<response><header><resultCode>22</resultCode></header></response>", KmaRateLimitError),
        ("<html>점검 중</html>", KmaResponseError),
        ("not json", KmaResponseError),
    ],
)
def test_typ02_xml_and_text_errors(body, error):
    client = _client(lambda req: httpx.Response(200, text=body))
    with pytest.raises(error):
        client.get_items("/api/typ02/openApi/x", {})


def test_typ02_result_codes():
    for code, error in (("03", KmaNoDataError), ("10", KmaInvalidRequestError), ("20", KmaAuthError), ("99", KmaResponseError)):
        client = _client(lambda req, code=code: httpx.Response(200, json=_typ02(code)))
        with pytest.raises(error):
            client.get_items("/api/typ02/openApi/x", {})


def test_rate_limit_status_is_not_retried():
    calls = []
    client = _client(lambda req: calls.append(1) or httpx.Response(429, text="too many"))
    with pytest.raises(KmaRateLimitError):
        client.get_text("/x", {})
    assert len(calls) == 1


def test_timeouts_and_server_errors_retry_a_limited_number_of_times():
    calls = []

    def flaky(req):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow", request=req)
        if len(calls) == 2:
            return httpx.Response(503)
        return httpx.Response(200, text="# TM STN TA_AVG\n")

    assert _client(flaky).get_text("/x", {}).startswith("#")
    assert len(calls) == 3

    always_slow = _client(lambda req: (_ for _ in ()).throw(httpx.ConnectTimeout("slow", request=req)), retries=2)
    with pytest.raises(KmaTimeoutError):
        always_slow.get_text("/x", {})


def test_get_items_collects_every_page_and_sends_key_and_json():
    seen = []

    def pages(req):
        seen.append(dict(req.url.params))
        page = int(req.url.params["pageNo"])
        items = [{"n": 1}, {"n": 2}] if page == 1 else [{"n": 3}]
        return httpx.Response(200, json=_typ02(items=items, total=3))

    assert [i["n"] for i in _client(pages).get_items("/api/typ02/openApi/x", {"nx": 60}, page_size=2)] == [1, 2, 3]
    assert [p["pageNo"] for p in seen] == ["1", "2"]
    assert seen[0]["authKey"] == KEY and seen[0]["dataType"] == "JSON" and seen[0]["nx"] == "60"


def test_get_items_empty_body_is_empty_list():
    assert _client(lambda req: httpx.Response(200, json=_typ02(items=None, total=0))).get_items("/x", {}) == []


def test_get_text_reads_cp949():
    client = _client(lambda req: httpx.Response(200, content="# STN_ID LON LAT STN_KO\n101 127.7 37.9 춘천\n".encode("cp949")))
    assert "춘천" in client.get_text("/x", {})


def test_typ01_joins_two_line_header_and_keeps_spaces_in_last_column():
    """실제 지점정보 응답 모양: 칸 이름이 두 줄(STN / ID)로 나뉘고, 마지막 칸 주소에 빈칸이 있다."""
    text = "# STN   LON  LAT STN STN_KO LAW_ADDR\n#  ID degee degree  AD ---- ----\n  101 127.7 37.9 101 춘천 강원특별자치도 춘천시 우두동\n"
    rows = typ01_rows(text, ["STN_ID", "LON", "LAT"], rest_in_last=True)
    assert rows == [{"STN_ID": "101", "LON": "127.7", "LAT": "37.9", "STN_AD": "101", "STN_KO": "춘천", "LAW_ADDR": "강원특별자치도 춘천시 우두동"}]


def test_parse_real_short_forecast_response():
    """실제 getVilageFcst 응답 (춘천 격자 73,134, 2026-11-13 17시 발표). 3일 뒤부터 3시간 간격, PCP 가 단위 없는 숫자."""
    import json

    items = json.loads((pathlib.Path(__file__).parent / "samples" / "getVilageFcst_73_134_202611131700.json").read_text(encoding="utf-8"))
    issued = dt.datetime(2026, 11, 13, 17, tzinfo=SEOUL)
    hourly, daily = parse_short_forecast(items, issued)
    assert hourly[-1].datetime == dt.datetime(2026, 11, 18, 0, tzinfo=SEOUL)  # API 가 준 마지막 시각
    summary = {d.date.day: (d.sky, d.precipitation_type, d.temperature_min, d.temperature_max, d.hours) for d in daily}
    assert summary == {
        13: ("구름많음", "없음", None, None, 6),  # 오늘은 18시부터, 최저·최고는 없음
        14: ("흐림", "비", 8.0, 14.0, 24),
        15: ("맑음", "없음", 8.0, 18.0, 24),
        16: ("흐림", "없음", 7.0, 15.0, 24),
        17: ("흐림", "비", 7.0, 14.0, 8),  # 3시간 간격
    }  # 18일은 00시 한 시각뿐이라 하루 요약을 만들지 않는다
    assert {d.date.day: d.precipitation_mm_min for d in daily}[17] is None  # 단위 없는 "1" 은 모름
    assert amount_range("1", "mm") == (None, None) and amount_range("0", "mm") == (0.0, 0.0)
