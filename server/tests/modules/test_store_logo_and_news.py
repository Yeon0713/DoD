"""네이버 소식 카드 읽기, 소식 사진에서 로고 찾기, 로고 바탕 지우기·여백 자르기."""

import io
import json

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.core import logo_image, naver_place
from app.data_pipeline import store_logo
from app.main import create_app


def _png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def _photo_like() -> bytes:
    """테두리 색이 섞이고 화면을 채운 그림 (음식 사진·안내 포스터처럼)"""
    image = Image.new("RGB", (300, 300))
    draw = ImageDraw.Draw(image)
    for x in range(0, 300, 10):
        draw.rectangle((x, 0, x + 10, 300), fill=((x * 7) % 256, (x * 3) % 256, (x * 5) % 256))
    return _png(image)


def _notice_like() -> bytes:
    """흰 바탕이지만 글이 화면 대부분을 채운 안내문"""
    image = Image.new("RGB", (300, 300), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    for y in range(20, 280, 16):
        for x in range(20, 280, 12):
            draw.rectangle((x, y, x + 8, y + 10), fill=((x * 5) % 200, (y * 3) % 200, 90))
    return _png(image)


def test_logo_is_told_apart_from_photos_and_notices(logo_png):
    assert logo_image.logo_score(logo_png) is not None
    assert logo_image.logo_score(_photo_like()) is None
    assert logo_image.logo_score(_notice_like()) is None
    assert logo_image.logo_score(b"not an image") is None


def test_cut_out_removes_background_and_trims_margin(logo_png):
    out = Image.open(io.BytesIO(logo_image.cut_out(logo_png)))
    assert out.mode == "RGBA"
    w, h = out.size
    assert w < 140 and h < 170  # 400 × 300 의 흰 여백이 잘렸다 (그림은 100 × 140)
    assert out.getpixel((0, 0))[3] == 0  # 바탕은 투명
    assert out.getpixel((w // 2, h - h // 4))[3] == 255  # 그림은 그대로
    assert out.getpixel((w // 2, h - h // 4))[:3] == (72, 52, 44)


def test_cut_out_keeps_photo_background():
    """바탕이 한 가지 색이 아니면(사진) 지우지 않는다"""
    out = Image.open(io.BytesIO(logo_image.cut_out(_photo_like())))
    assert out.getpixel((0, 0))[3] == 255


def _feed_html(feeds: dict) -> str:
    refs = [{"__ref": k} for k in feeds]
    state = {**feeds, "ROOT_QUERY": {'feeds({"businessId":"1"})': {"__typename": "FeedsResult", "feeds": refs}}}
    return f"<script>window.__APOLLO_STATE__ = {json.dumps(state, ensure_ascii=False)};window.__X = 1</script>"


def test_news_cards_are_read_in_order():
    html = _feed_html({
        "Feed:1_2": {"__typename": "Feed", "feedId": 2, "title": "10월 휴무 없습니다", "desc": "정상영업", "category": "알림",
                     "period": "2026.10.01. ~ 2026.10.09.", "createdString": "20261001",
                     "media": [{"mediaType": "IMAGE", "thumbnail": "https://ldb-phinf.pstatic.net/a.jpg"}]},
        "Feed:1_1": {"__typename": "Feed", "feedId": 1, "title": "오픈 안내", "desc": "", "category": "알림", "createdString": "20260319",
                     "media": [{"mediaType": "VIDEO", "thumbnail": "https://ldb-phinf.pstatic.net/v.jpg"}, {"mediaType": "IMAGE", "thumbnail": "https://ldb-phinf.pstatic.net/logo.png"}]},
        "Feed:1_0": {"__typename": "Feed", "feedId": 0, "title": "지운 소식", "isDeleted": True, "media": []},
    })
    news = naver_place.parse_news(html)
    assert [(n.news_id, n.title, n.created) for n in news] == [("2", "10월 휴무 없습니다", "2026-10-01"), ("1", "오픈 안내", "2026-03-19")]
    assert news[0].period == "2026.10.01. ~ 2026.10.09." and news[1].photos == ["https://ldb-phinf.pstatic.net/logo.png"]
    info = naver_place.PlaceInfo(place_id="1", name="가게", category="", road_address="", address="", lat=0, lng=0, weekly_hours={}, break_time=None, news=news)
    assert naver_place.PlaceInfo.from_dict(info.to_dict()).news == news  # 저장했다 다시 읽어도 같다


def test_logo_is_found_among_news_photos(monkeypatch, logo_png):
    images = {"https://ldb-phinf.pstatic.net/food.jpg": _photo_like(), "https://ldb-phinf.pstatic.net/notice.png": _notice_like(),
              "https://ldb-phinf.pstatic.net/logo.png": logo_png}
    monkeypatch.setattr(naver_place, "_image", images.get)
    news = [naver_place.PlaceNews(news_id=str(i), title="", body="", category="", period=None, created=None, photos=[url]) for i, url in enumerate(images)]
    assert naver_place.find_logo(news) == "https://ldb-phinf.pstatic.net/logo.png"
    assert naver_place.find_logo(news[:2]) is None


def test_naver_logo_is_kept_cut_out_and_owner_logo_comes_first(monkeypatch, logo_png):
    monkeypatch.setattr(naver_place, "_image", lambda url: logo_png)
    url = "https://ldb-phinf.pstatic.net/logo.png"
    assert store_logo.url_of("s005", url).startswith("/api/stores/s005/logo?v=")
    assert store_logo.source_of("s005") == "NAVER"
    kept = Image.open(store_logo.path_of("s005"))
    assert kept.getpixel((0, 0))[3] == 0  # 받아 둔 네이버 로고도 바탕을 지웠다
    monkeypatch.setattr(naver_place, "_image", lambda url: (_ for _ in ()).throw(AssertionError("다시 받지 않는다")))
    store_logo.url_of("s005", url)
    store_logo.save("s005", "data:image/png;base64," + __import__("base64").b64encode(logo_png).decode())
    assert store_logo.source_of("s005") == "OWNER"
    client = TestClient(create_app())
    assert client.delete("/api/stores/s005/logo").json()["removed"] is True
    assert store_logo.source_of("s005") == "NAVER"  # 올린 로고를 지우면 네이버 로고로 돌아간다


def test_place_api_returns_news_and_logo_source(monkeypatch, logo_png):
    from app.data_pipeline import registered_stores

    monkeypatch.setattr(naver_place, "_image", lambda url: logo_png)
    news = [naver_place.PlaceNews(news_id="9", title="가격은 그대로", body="옹심이가 더 많아졌어요", category="알림", period=None, created="2026-10-29", photos=[])]
    info = naver_place.PlaceInfo(place_id="2004174048", name="초옹장", category="한식", road_address="경기 화성시", address="", lat=37.2, lng=126.8,
                                 weekly_hours={d: {"open": "10:30", "close": "20:30"} for d in ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")},
                                 break_time=None, logo="https://ldb-phinf.pstatic.net/logo.png", news=news)
    store_id = registered_stores.register(info)
    place = TestClient(create_app()).get("/api/naver/place", params={"store_id": store_id}).json()["place"]
    assert place["logo_source"] == "NAVER" and place["logo"].startswith(f"/api/stores/{store_id}/logo?v=")
    assert [n["title"] for n in place["news"]] == ["가격은 그대로"]
