"""인스타 피드·스토리 올리기 (D-14, D-15). 실제 Graph API 대신 FakeGraph, 공개 주소는 https://media.example.test.

초옹장(s005)으로 브리핑 인스타 칸 '인스타에 올릴까요?' → 미리보기 넘기기 → "올려" → 게시 작업 → 올라감까지 본다.
v0.2.1 H: 비 오는 날 이벤트를 정해 둔 날은 스토리만 묻고 인기 메뉴 피드는 묻지 않는다. 피드를 보는 시험은 이벤트 없이 다시 넣는다 (no_story_event).
"""

import json

import httpx
import pytest
from PIL import Image

from app.core.config import settings
from voice import clock, config, repo, width
from voice.instagram import graph, media, posts
from voice.instagram.graph import InstagramError
from voice.jobs import queue
from voice.tests.conftest import FakeGraph, hr_log, no_morning_tasks, step_key, walk_to
from voice.tests.test_v021_choongjang import FIXTURE, Choongjang


@pytest.fixture
def chj(monkeypatch) -> Choongjang:
    monkeypatch.setattr(config, "DEMO_FIXTURE", "s005_choongjang")  # connect 를 {} 로 부르면 이 가게
    donna = Choongjang()
    donna.clock(json.loads(FIXTURE.read_text(encoding="utf-8"))["demo"]["now"])
    donna.client.post("/v1/dev/fixtures", json={"fixture": "s005_choongjang"})
    return donna


def connect(chj: Choongjang) -> dict:
    result = chj.client.post("/v1/instagram/connect", json={}).json()
    assert result["connected"] is True, result
    return result


def run_publish(chj: Choongjang) -> dict:
    return chj.client.post("/v1/dev/run", json={"store_id": "s005", "job": "instagram_publish"}).json()


def no_story_event(chj: Choongjang) -> None:
    """비 오는 날 이벤트를 정해 두지 않은 초옹장으로 다시 넣고 브리핑을 준비한다 (이벤트가 있는 날은 피드를 묻지 않는다, H)."""
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["settings"].pop("story_event")
    chj.client.post("/v1/dev/fixtures", json=payload)
    chj.client.post("/v1/dev/run", json={"store_id": "s005", "job": "prepare_briefing"})


def to_instagram_step(chj: Choongjang) -> dict:
    """브리핑을 처음부터 듣고 인스타 단계까지 간다 (묻는 단계는 대답하지 않고 넘긴다). 없으면 끝 응답."""
    return walk_to(chj, "instagram")


def to_end(chj: Choongjang, response: dict) -> dict:
    for _ in range(12):
        if response["type"] == "end":
            return response
        response = chj.turn(event="auto_next")
    raise AssertionError("브리핑 끝에 닿지 못했어요")


def test_not_connected_skips_instagram(chj: Choongjang):
    """토큰이 없으면 연결이 안 되고, 브리핑에 인스타 단계가 없다."""
    result = chj.client.post("/v1/instagram/connect", json={}).json()
    assert result["connected"] is False and "INSTAGRAM_ACCESS_TOKEN" in result["error"]
    assert "p_instagram" not in [r["id"] for r in chj.get("/v1/home")["cards"][0]["rows"]]
    assert to_instagram_step(chj)["type"] == "end"
    platforms = {p["key"]: p["connected"] for p in chj.get("/v1/settings")["platforms"]}
    assert platforms["instagram"] is False
    response = chj.client.post("/v1/instagram/posts", json={"store_id": "s005", "kind": "story"})
    assert response.status_code == 409


def test_briefing_feed_flow(chj: Choongjang, ig_on):
    fake = ig_on(FakeGraph())
    no_story_event(chj)
    assert connect(chj)["handle"] == "choongjang_namyang"
    assert chj.get("/v1/instagram")["connection"]["connected"] is True
    assert {p["key"]: p["connected"] for p in chj.get("/v1/settings")["platforms"]}["instagram"] is True
    # 연결하면 홈 줄을 H-01 차례로 다시 짠다 (일정 → 리뷰 → 인기 메뉴 피드 → …)
    assert chj.get("/v1/home")["cards"][0]["rows"][2] == {"id": "p_instagram", "kind": "instagram", "value": "인기 메뉴 피드 준비"}

    d14 = to_instagram_step(chj)
    assert d14["type"] == "ask" and d14["ask"] == {"key": "instagram_post"} and d14["expects_reply"] is True
    assert d14["briefing"] == {"step": 2, "total": 4, "step_key": "instagram"}
    assert d14["headline"] == "인스타에 올릴까요?"
    assert [s["text"] for s in d14["say"]] == [
        "이번 달 가장 많이 나간 메뉴는 들깨옹심이메밀칼국수, 멸치옹심이메밀칼국수, 들깨옹심이예요.",
        "손님 리뷰 “들깨 국물이 정말 고소해요”를 글에 넣었어요.",
        "인스타에 올릴까요?",
    ]
    menus, quote = d14["cards"]
    assert [(m["rank"], m["count_label"]) for m in menus["items"]] == [(1, "461그릇"), (2, "308그릇"), (3, "284그릇")]
    assert quote == {"type": "quote", "id": "insta_quote", "label": "글에 넣을 손님 리뷰", "text": "“들깨 국물이 정말 고소해요”"}
    assert width.violations(d14) == []

    d15 = chj.turn("화면에 보여 줘")
    card = d15["cards"][0]
    assert d15["type"] == "show_detail" and d15["headline"] == "이렇게 올라가요"
    assert (card["type"], card["slide"], card["slides"], card["top_label"]) == ("insta_post", 1, 4, "이번 달 1등")
    assert card["handle"] == "choongjang_namyang" and card["photo_url"] == "/static/menus/deulkkae-ongsimi-memil-kalguksu.png"
    slides = [chj.turn("다음 사진")["cards"][0] for _ in range(3)]
    assert [s["slide"] for s in slides] == [2, 3, 4]
    assert slides[-1]["photo_url"] is None and slides[-1]["title"] == "초옹장"  # 가게 소개 장

    posted = chj.turn("올려")
    assert posted["intent"] == "instagram.post" and posted["type"] == "answer"
    assert posted["briefing"]["step_key"] == "reviews"  # 인스타 다음은 리뷰 칸
    assert [s["text"] for s in posted["say"]][:2] == ["네, 인스타에 올릴게요.", "다 올라가면 알려 드릴게요."]
    assert hr_log() == [("instagram_post", "approved")]
    done = to_end(chj, posted)
    assert ("인스타에 인기 메뉴", "지금 올리고 있어요") in [(r["value"], r["sub"]) for r in done["cards"][0]["rows"]]
    post = chj.get("/v1/instagram")["posts"][0]
    assert post["status"] == "queued" and post["kind"] == "feed" and fake.paths("POST") == []  # 올리는 건 게시 작업에서

    run_publish(chj)
    post = chj.client.get(f"/v1/instagram/posts/{post['id']}").json()
    assert post["status"] == "published" and post["media_id"] == "media_1" and post["permalink"] == "https://www.instagram.com/p/TEST/"
    created = [params for method, path, params in fake.calls if method == "POST" and path.endswith("/media")]
    assert [c["image_url"] for c in created[:4]] == [f"https://media.example.test/media/{post['id']}/{n}.jpg" for n in range(1, 5)]
    assert all(c["is_carousel_item"] == "true" and "caption" not in c for c in created[:4])
    assert created[4]["media_type"] == "CAROUSEL" and created[4]["children"] == "child_1,child_2,child_3,child_4"
    assert created[4]["caption"].startswith("이번 달 가장 많이 나간 메뉴예요.\n1등 들깨옹심이메밀칼국수")
    assert "손님 한마디 “들깨 국물이 정말 고소해요”" in created[4]["caption"]
    assert created[4]["caption"].endswith("\n\n초옹장 · 경기 화성시 남양읍\n영업시간 10:30 ~ 20:30\n#초옹장")  # 가게 정보는 코드가 붙인다
    assert posts.hashtag("새뱅이 국수 (본점)") == "#새뱅이국수본점"
    assert ("POST", "17841400000000000/media_publish", {"creation_id": "carousel_1"}) in fake.calls

    image = Image.open(media.MEDIA_DIR / post["id"] / "1.jpg")
    assert image.format == "JPEG" and image.size == (1080, 1350)
    assert chj.client.get(f"/media/{post['id']}/1.jpg").status_code == 200  # base_url 모드: 인스타가 여기서 가져간다
    assert [n["text"] for n in chj.get("/v1/notices")["notices"]] == ["인스타에 인기 메뉴를 올렸어요"]
    assert chj.get("/v1/notices")["notices"] == []  # 한 번만

    again = chj.turn("처음부터 다시")
    for _ in range(12):
        assert step_key(again) != "instagram"  # 오늘은 다시 묻지 않는다
        if again["type"] == "end":
            break
        again = chj.turn("응") if step_key(again) == "detail_ask" else chj.turn(event="auto_next")
    assert ("인스타에 인기 메뉴", "피드에 올렸어요") in [(r["value"], r["sub"]) for r in again["cards"][0]["rows"]]


def test_rain_event_day_asks_story_not_feed(chj: Choongjang, ig_on):
    """비 오는 날 이벤트가 있는 날은 스토리만 묻는다 (H-06). 인기 메뉴 피드 단계와 홈 줄이 없다."""
    ig_on(FakeGraph())
    connect(chj)
    rows = [r["id"] for r in chj.get("/v1/home")["cards"][0]["rows"]]
    assert "p_story" in rows and "p_instagram" not in rows
    assert to_instagram_step(chj)["type"] == "end"


def test_later_does_not_post(chj: Choongjang, ig_on):
    ig_on(FakeGraph())
    no_story_event(chj)
    connect(chj)
    to_instagram_step(chj)
    later = chj.turn("나중에")
    assert later["intent"] == "instagram.later" and later["briefing"]["step_key"] == "reviews"
    assert later["say"][0]["text"] == "네, 내일 브리핑에서 다시 여쭤볼게요."
    assert chj.get("/v1/instagram")["posts"] == []
    assert hr_log() == []  # "나중에"는 세지 않는다 (9-0 n)


def test_story_outside_briefing(chj: Choongjang, ig_on):
    fake = ig_on(FakeGraph())
    connect(chj)
    no_morning_tasks()  # 아침에 못 물은 알바생 할 일이 있으면 그것부터 묻는다 (test_staff_tasks.py)
    said = chj.turn("인스타 스토리 올려 줘", addressed=True)
    assert said["intent"] == "instagram.story" and said["headline"] == "인스타에 스토리를 올릴게요"
    run_publish(chj)
    post = chj.get("/v1/instagram")["posts"][0]
    assert post["kind"] == "story" and post["status"] == "published"
    created = [params for method, path, params in fake.calls if method == "POST" and path.endswith("/media")]
    assert created == [{"media_type": "STORIES", "image_url": f"https://media.example.test/media/{post['id']}/1.jpg"}]
    assert Image.open(media.MEDIA_DIR / post["id"] / "1.jpg").size == (1080, 1920)


def test_expired_token_fails_and_disconnects(chj: Choongjang, ig_on):
    ig_on(FakeGraph(fail={"media_publish": (190, "Error validating access token")}))
    connect(chj)
    post = chj.client.post("/v1/instagram/posts", json={"store_id": "s005", "kind": "feed"}).json()
    run_publish(chj)
    post = chj.client.get(f"/v1/instagram/posts/{post['id']}").json()
    assert post["status"] == "failed" and "access token" in post["error"]
    assert chj.get("/v1/instagram")["connection"]["connected"] is False
    assert [n["text"] for n in chj.get("/v1/notices")["notices"]] == ["인스타에 인기 메뉴를 올리지 못했어요"]


def test_container_error_fails(chj: Choongjang, ig_on):
    ig_on(FakeGraph(status=["IN_PROGRESS", "ERROR"]))
    connect(chj)
    post = chj.client.post("/v1/instagram/posts", json={"store_id": "s005", "kind": "story"}).json()
    run_publish(chj)
    post = chj.client.get(f"/v1/instagram/posts/{post['id']}").json()
    assert post["status"] == "failed" and "ERROR" in post["error"]
    assert chj.get("/v1/instagram")["connection"]["connected"] is True  # 토큰 문제가 아니면 연결은 그대로


def test_scheduled_post_waits_for_its_time(chj: Choongjang, ig_on):
    fake = ig_on(FakeGraph())
    connect(chj)
    at = clock.iso(clock.now().replace(hour=11, minute=30))
    post = chj.client.post("/v1/instagram/posts", json={"store_id": "s005", "kind": "story", "post_at": at}).json()
    run_publish(chj)
    assert chj.client.get(f"/v1/instagram/posts/{post['id']}").json()["status"] == "queued" and fake.paths("POST") == []
    chj.clock(at)
    assert chj.client.get(f"/v1/instagram/posts/{post['id']}").json()["status"] == "published"


def test_public_url_modes(monkeypatch, tmp_path):
    path = media.MEDIA_DIR / "ig_0001" / "1.jpg"
    assert media.public_url(path) == "https://media.example.test/media/ig_0001/1.jpg"

    monkeypatch.setattr(settings, "public_media_base_url", "")
    with pytest.raises(InstagramError):
        media.public_url(path)

    uploads = []

    class FakeS3:
        def upload_file(self, filename, bucket, key, ExtraArgs=None):
            uploads.append((filename, bucket, key, ExtraArgs))

    monkeypatch.setattr(settings, "media_host", "object_storage")
    monkeypatch.setattr(settings, "ncp_object_storage_bucket", "donna-media")
    monkeypatch.setattr(media, "s3_client", lambda: FakeS3())
    assert media.public_url(path) == "https://kr.object.ncloudstorage.com/donna-media/instagram/ig_0001/1.jpg"
    assert uploads == [(str(path), "donna-media", "instagram/ig_0001/1.jpg", {"ACL": "public-read", "ContentType": "image/jpeg"})]


def test_public_url_litterbox(monkeypatch):
    path = media.MEDIA_DIR / "ig_0001" / "1.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"jpeg")
    sent = []

    def fake_post(url, data=None, files=None, timeout=None):
        sent.append((url, data, files["fileToUpload"][0]))
        if len(sent) == 1:
            raise httpx.ConnectTimeout("boom")
        return httpx.Response(200, text="https://litter.catbox.moe/abc123.jpg\n")

    monkeypatch.setattr(settings, "media_host", "litterbox")
    monkeypatch.setattr(media, "post", fake_post)
    monkeypatch.setattr(media.time, "sleep", lambda s: None)
    assert media.public_url(path) == "https://litter.catbox.moe/abc123.jpg"
    assert len(sent) == 2 and sent[-1][1] == {"reqtype": "fileupload", "time": "1h"} and sent[-1][2] == "1.jpg"

    monkeypatch.setattr(media, "post", lambda *a, **k: httpx.Response(412, text="error"))
    with pytest.raises(InstagramError, match="litterbox 412"):
        media.public_url(path)


def test_source_must_be_static():
    with pytest.raises(InstagramError):
        media.source_path("/etc/passwd")
    with pytest.raises(InstagramError):
        media.source_path("/static/../main.py")


def test_queue_ids_do_not_collide(chj: Choongjang):
    now = clock.now()
    first = queue.add("s005", "instagram_publish", now, {"post_id": "ig_0001"})
    second = queue.add("s005", "instagram_publish", now, {"post_id": "ig_0002"})
    assert first["id"] != second["id"]
    assert len([j for j in repo.all_of("job", "s005") if j["kind"] == "instagram_publish"]) == 2


def test_connect_failure_retries_but_read_timeout_does_not(ig_on, monkeypatch):
    fake = ig_on(FakeGraph())
    calls = []

    def flaky(error_type, fails):
        def post(url, data=None, timeout=None):
            calls.append(url)
            if len(calls) <= fails:
                raise error_type("boom")
            return fake.post(url, data, timeout)
        return post

    monkeypatch.setattr(graph, "post", flaky(httpx.ConnectTimeout, 2))
    assert graph.publish("container_1") == "media_1"
    assert len(calls) == 3

    calls.clear()
    monkeypatch.setattr(graph, "post", flaky(httpx.ConnectError, 3))
    with pytest.raises(InstagramError, match="닿지 못했어요"):
        graph.publish("container_1")
    assert len(calls) == graph.CONNECT_TRIES

    calls.clear()
    monkeypatch.setattr(graph, "post", flaky(httpx.ReadTimeout, 1))
    with pytest.raises(InstagramError, match="ReadTimeout"):
        graph.publish("container_1")
    assert len(calls) == 1


def test_graph_error_message(ig_on):
    ig_on(FakeGraph(fail={"17841400000000000": (100, "Unsupported get request")}))
    with pytest.raises(InstagramError) as raised:
        graph.account()
    assert raised.value.code == 100 and not raised.value.token_invalid
    assert posts.connection("s005")["connected"] is False


@pytest.mark.parametrize("text, instagram, expected", [
    ("인스타 스토리 올려 줘", False, "instagram.story"),
    ("인스타에 올려 줘", False, "instagram.feed"),
    ("인스타에 인기 메뉴 올려", False, "instagram.feed"),
    ("인스타에 올리지 마", False, None),
    ("인스타에 안 올려", False, None),
    ("인스타 올릴 수 있어?", False, None),
    ("인스타에 언제 올릴까", False, None),
    ("인스타에 올려도 돼?", False, None),
    ("스토리 올리지 마", False, None),
    ("인스타에 올리지 마", True, "instagram.later"),
    ("오늘은 올리지 말자", True, "instagram.later"),
    ("인스타에 올려", True, "instagram.post"),
])
def test_post_order_must_be_an_order(text, instagram, expected):
    """다시 묻지 않고 올리는 말이라, 하지 말라는 말이나 묻는 말은 게시로 가르지 않는다."""
    from voice.dialog import intent_rules

    found = intent_rules.match(text, None, addressed=True, instagram=instagram)
    assert (found.name if found else None) == expected


def test_do_not_post_in_briefing(chj: Choongjang, ig_on):
    ig_on(FakeGraph())
    no_story_event(chj)
    connect(chj)
    to_instagram_step(chj)
    said = chj.turn("인스타에 올리지 마")
    assert said["intent"] == "instagram.later"
    assert chj.get("/v1/instagram")["posts"] == []
    assert hr_log() == [("instagram_post", "rejected")]  # "올리지 마"는 반려 (9-0 n)


def test_unexpected_error_fails_instead_of_stuck(chj: Choongjang, ig_on, monkeypatch):
    """InstagramError 가 아닌 오류(사진 파일, boto3 업로드 등)도 failed 로 남기고 알린다. publishing 에 멈추지 않는다."""
    ig_on(FakeGraph())
    connect(chj)

    def broken(*args, **kwargs):
        raise OSError("cannot identify image file")

    monkeypatch.setattr(media, "prepare", broken)
    post = chj.client.post("/v1/instagram/posts", json={"store_id": "s005", "kind": "story"}).json()
    run_publish(chj)
    post = chj.client.get(f"/v1/instagram/posts/{post['id']}").json()
    assert post["status"] == "failed" and post["error"] == "OSError: cannot identify image file"
    assert chj.get("/v1/instagram")["connection"]["connected"] is True
    assert [n["text"] for n in chj.get("/v1/notices")["notices"]] == ["인스타에 스토리를 올리지 못했어요"]


def test_post_ids_differ_across_stores(chj: Choongjang):
    """번호는 가게마다 1 부터지만 repo 키와 사진 폴더는 가게를 가리지 않으므로, 가게가 달라도 id 가 겹치지 않아야 한다."""
    built = {"kind": "story", "slides": [{"src": "/static/x.png", "top_label": "1등", "title": "국수"}], "caption": None}
    first = posts.create("s005", built)
    other = posts.create("s999", built)
    assert first["id"] != other["id"]
    assert posts.get(first["id"])["store_id"] == "s005" and posts.get(other["id"])["store_id"] == "s999"
