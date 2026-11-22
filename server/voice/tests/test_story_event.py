"""I: 비 오는 날 스토리 이벤트 → AI 포스터 → 스토리 게시 → 알바생 할 일 (개선안 [2]-3 A3, instagram/story_event.py).

번호는 donna-voice/docs/test-scenarios-closed-loop.md 의 I장과 같다.
초옹장 11/17 (오후 2시부터 비), 인스타 연결(FakeGraph), 그림 엔진 mock(글자 없는 그림), 그리기는 뒤가 아니라 바로 (conftest).
I0: 밤사이 그려 둔 포스터를 브리핑에서 보여 주고 "응"이면 바로 올린다 (2026-11-22, Figma v0.2.1 H-06 · H-07).
    브리핑 차례는 요약 → 상세 브리핑 물음 → 스토리 이벤트(인스타 칸) → 리뷰 → 알바생 할 일. 이벤트가 있는 날은 인기 메뉴 피드를 묻지 않는다.
I1 ~ I8: 밤사이 그리기에 실패했을 때 (predraw_failed) 예전처럼 그릴지 묻고, 다 그리면 알림으로 묻는다.
"""

import pytest
from PIL import Image

from app.poster_ai import image_engine
from app.poster_ai.image_engine import PosterEngineError
from voice import repo, staff, staff_orders, width
from voice.instagram import media, story_event
from voice.tests.conftest import FakeGraph, hr_log, walk_to
from voice.tests.test_instagram import Choongjang, chj, connect, run_publish  # noqa: F401 (chj 는 fixture)

SE_ID = "se_s005_2026-11-17"
OFFER = "매장을 태그해 스토리에 올려 주시면 음료 1캔을 드려요"
TITLE = "[이벤트] 스토리 태그 손님 음료 1캔 드리기"


def to_story_step(chj: Choongjang) -> dict:
    """브리핑을 처음부터 듣고 스토리 이벤트 단계까지 (없으면 끝)."""
    return walk_to(chj, "story_event")


def record() -> dict:
    return repo.get("story_event", SE_ID)


def predraw_failed() -> None:
    """밤사이 미리 그리기에 실패한 것으로 둔다 (브리핑이 예전처럼 '그려서 올릴까요?'를 묻는다)."""
    repo.put("story_event", SE_ID, "s005", {**record(), "state": "failed", "error": "시험: 밤사이 그리기 실패", "drawn": 0,
                                             "image_url": None, "poster_url": None})


def ready(chj: Choongjang, ig_on, fake: FakeGraph | None = None) -> FakeGraph:
    """(밤사이 그리기 실패) 하린 가입 → 연결 → 브리핑에서 "응" → 포스터 다 그림 (알림이 쌓여 있다)."""
    chj.join("하린")  # s005 의 하린은 아직 안 들어온 상태다 (fixture). 알바생 할 일을 보려면 가입해 있어야 한다
    fake = ig_on(fake or FakeGraph())
    predraw_failed()
    connect(chj)
    to_story_step(chj)
    chj.turn("응, 좋아")
    assert record()["state"] == "ready"
    return fake


def open_story(chj: Choongjang) -> dict:
    found = [n for n in chj.notices() if n["kind"] == "story_event" and n["opens_turn"]]
    assert found, "포스터 알림이 없어요"
    return chj.turn(event="notice", notice_id=found[-1]["id"])


# ── I0 밤사이 그려 둔 포스터를 브리핑에서 보여 주고 바로 올리기 (2026-11-22) ──


def test_i0_predrawn_overnight(chj: Choongjang):
    """밤사이 준비가 포스터와 스토리 사진을 그려 둔다. 알리지 않는다 (브리핑에서 보여 준다)."""
    saved = record()
    assert saved["state"] == "ready" and saved["predrawn"] is True
    assert saved["poster_url"] == f"/media/{SE_ID}/poster_1.jpg" and saved["image_url"] == f"/media/{SE_ID}/story_1.jpg"
    poster = Image.open(media.MEDIA_DIR / SE_ID / "poster_1.jpg")
    story = Image.open(media.MEDIA_DIR / SE_ID / "story_1.jpg")
    assert (poster.format, poster.size) == ("JPEG", (1024, 1536)) and saved["poster_aspect"] == "1024:1536"  # 그린 그대로
    assert (story.format, story.size) == ("JPEG", (1080, 1920))  # 스토리 크기
    assert chj.client.get(f"/media/{SE_ID}/poster_1.jpg").status_code == 200  # 앱 미리보기
    assert [n for n in chj.notices() if n["kind"] == "story_event"] == []


def test_i0_briefing_shows_and_asks(chj: Choongjang, ig_on):
    ig_on(FakeGraph())
    connect(chj)
    asked = to_story_step(chj)
    assert asked["type"] == "ask" and asked["ask"] == {"key": "story_event"} and asked["expects_reply"] is True
    assert asked["briefing"] == {"step": 2, "total": 4, "step_key": "story_event"}
    assert asked["headline"] == "비 오는 날 이벤트를 올릴까요?"  # H-06: 스토리에 올라갈 모양 한 장만 보이고 묻는다
    assert [s["text"] for s in asked["say"]] == ["비 오는 날 이벤트 이미지를 만들었어요.", "인스타 스토리에 올릴까요?"]
    assert asked["cards"] == [{"type": "images", "id": "story_images", "items": [
        {"id": "story", "label": "스토리", "photo_url": f"/media/{SE_ID}/story_1.jpg", "aspect": "9:16"}]}]
    assert width.violations(asked) == []


def test_i0_yes_posts_right_away(chj: Choongjang, ig_on):
    chj.join("하린")
    fake = ig_on(FakeGraph())
    connect(chj)
    to_story_step(chj)
    done = chj.turn("응, 올려")
    # H-07: 올린 모양을 따로 보여 준다 (✓ 스토리에 올림). 게이지가 있어 가만히 있으면 다음 단계로
    assert done["intent"] == "instagram.post" and done["type"] == "answer" and done["headline"] == "스토리에 올렸어요"
    assert done["briefing"] == {"step": 2, "total": 4, "step_key": "story_event"} and done["expects_reply"] is False
    assert [s["text"] for s in done["say"]] == ["스토리에 올렸어요."]
    assert done["cards"] == [{"type": "images", "id": "story_images", "items": [
        {"id": "story", "label": "스토리에 올림", "photo_url": f"/media/{SE_ID}/story_1.jpg", "aspect": "9:16", "checked": True}]}]
    assert width.violations(done) == []
    assert record()["state"] == "approved" and hr_log() == [("story_poster", "approved")]
    after = chj.turn(event="auto_next")
    assert after["briefing"]["step_key"] == "reviews"  # 오늘은 다시 묻지 않고 리뷰 칸으로
    run_publish(chj)
    created = [params for method, path, params in fake.calls if method == "POST" and path.endswith("/media")]
    assert created == [{"media_type": "STORIES", "image_url": f"https://media.example.test/media/{SE_ID}/story_1.jpg"}]
    [card] = chj.staff_today("st_harin")["urgent"]
    assert card["title"] == TITLE and record()["state"] == "card_pinned"


def test_i0_owner_image_is_used_instead_of_drawing(chj: Choongjang, monkeypatch):
    """설정에 사장님이 준 이벤트 그림(story_event.image)이 있으면 그리지 않고 그 그림을 스토리 사진으로 둔다 (H '사장님이 준 것')."""
    def no_drawing(prompt, images):
        raise AssertionError("사장님 그림이 있으면 그리지 않아요")

    monkeypatch.setattr(image_engine, "generate", no_drawing)
    chj.client.post("/v1/dev/fixtures", json={"fixture": "s005_choongjang_h"})
    saved = record()
    assert saved["state"] == "ready" and saved["predrawn"] is True and saved["drawn"] == 1
    assert saved["image_url"] == saved["poster_url"] == f"/media/{SE_ID}/story_1.jpg" and saved["poster_aspect"] == "1080:1920"
    assert (media.MEDIA_DIR / SE_ID / "story_1.jpg").read_bytes() == media.source_path("/static/events/s005-rain-event.jpg").read_bytes()

    repo.put("story_event", SE_ID, "s005", {**saved, "state": "generating"})
    story_event.use_owner_image(SE_ID, "/static/events/none.jpg")  # 파일이 없으면 실패로 둔다 (브리핑은 그릴지부터 묻는다)
    assert record()["state"] == "failed"


def test_i0_later_does_not_post(chj: Choongjang, ig_on):
    ig_on(FakeGraph())
    connect(chj)
    to_story_step(chj)
    later = chj.turn("나중에")
    assert later["say"][0]["text"] == "네, 오늘은 스토리를 올리지 않을게요." and later["briefing"]["step_key"] == "reviews"
    assert record()["state"] == "declined" and chj.get("/v1/instagram")["posts"] == []
    assert hr_log() == [("story_poster", "rejected")]


# ── I1 브리핑에서 묻기 (밤사이 그리기에 실패했을 때) ──


def test_i1_rainy_day_asks(chj: Choongjang, ig_on):
    ig_on(FakeGraph())
    predraw_failed()
    connect(chj)
    asked = to_story_step(chj)
    assert asked["type"] == "ask" and asked["ask"] == {"key": "story_event"} and asked["expects_reply"] is True
    assert asked["briefing"] == {"step": 2, "total": 4, "step_key": "story_event"}
    assert asked["headline"] == "스토리 이벤트를 할까요?"
    assert [s["text"] for s in asked["say"]][-4:] == [
        "오늘은 오후 2시부터 비 소식이 있어요.",
        "비 오는 날 손님을 부르는 스토리 이벤트를 준비했어요.",
        f"{OFFER}.",
        "이벤트 포스터를 만들어 스토리에 올릴까요?",
    ]
    offer, todo = asked["cards"]
    assert offer == {"type": "quote", "id": "story_offer", "label": "비 오는 날 이벤트", "text": OFFER}
    assert todo["items"][0]["title"] == TITLE and todo["items"][0]["tone"] == "urgent"
    assert width.violations(asked) == []
    assert record()["state"] == "failed"  # 묻기만 했다


@pytest.mark.parametrize("case", ["not_connected", "no_preset", "sunny"])
def test_i1_no_step(chj: Choongjang, ig_on, case):
    if case != "not_connected":
        ig_on(FakeGraph())
        connect(chj)
    if case == "no_preset":
        chj.client.patch("/v1/settings", json={"store_id": "s005", "story_event": {"offer": None}})
        chj.client.post("/v1/dev/run", json={"store_id": "s005", "job": "prepare_briefing"})
    if case == "sunny":
        chj.clock("2026-11-18T09:02:00+09:00")  # 흐림, 비 30%
        chj.client.post("/v1/dev/run", json={"store_id": "s005", "job": "prepare_briefing"})
    assert to_story_step(chj)["briefing"]["step_key"] != "story_event"  # 끝이나 알바생 할 일 묻기로 넘어간다


def test_i1_settings_api(chj: Choongjang):
    shown = chj.get("/v1/settings")["story_event"]
    assert shown == {"headline": "비 오는 날 이벤트", "offer": OFFER, "staff_task": "스토리 태그 손님 음료 1캔 드리기"}
    bad = chj.client.patch("/v1/settings", json={"store_id": "s005", "story_event": {"offer": "[메뉴] 하나 서비스"}})
    assert bad.status_code == 400
    assert chj.client.patch("/v1/settings", json={"store_id": "s005", "story_event": {"price": "1000원"}}).status_code == 400


# ── I2 그리기 ──


def test_i2_yes_draws_and_notifies(chj: Choongjang, ig_on):
    ig_on(FakeGraph())
    predraw_failed()
    connect(chj)
    to_story_step(chj)
    drawn = []
    real = image_engine.generate

    def spy(prompt, images):
        drawn.append((prompt, [p.name for p in images]))
        return real(prompt, images)

    image_engine.generate, saved = spy, image_engine.generate
    try:
        done = chj.turn("응, 좋아")
    finally:
        image_engine.generate = saved
    assert done["intent"] == "instagram.post" and done["briefing"]["step_key"] == "reviews"  # 그리는 동안 리뷰 칸으로 이어 간다
    assert [s["text"] for s in done["say"]][:2] == ["네, 이벤트 포스터를 그릴게요.", "1~2분 걸려요. 다 되면 알려 드릴게요."]

    prompt, files = drawn[0]
    assert files == ["s005.png", "deulkkae-ongsimi-memil-kalguksu.png"]  # 로고 + 1등 메뉴
    assert f'Sub line: "{OFFER}"' in prompt and 'Headline (largest): "비 오는 날 이벤트"' in prompt
    assert "Rainy day" in prompt and "no prices" in prompt

    saved_record = record()
    assert saved_record["state"] == "ready" and saved_record["image_url"] == f"/media/{SE_ID}/story_1.jpg"
    assert saved_record["poster_url"] == f"/media/{SE_ID}/poster_1.jpg" and not saved_record.get("predrawn")
    image = Image.open(media.MEDIA_DIR / SE_ID / "story_1.jpg")
    assert image.format == "JPEG" and image.size == (1080, 1920)
    assert chj.client.get(f"/media/{SE_ID}/story_1.jpg").status_code == 200  # 앱 미리보기
    notices = [(n["kind"], n["opens_turn"], n["text"], n["alert_id"]) for n in chj.notices()]
    assert notices[-1] == ("story_event", True, "이벤트 포스터를 다 만들었어요", SE_ID)

    again = chj.turn("처음부터 다시")  # 오늘은 다시 묻지 않는다
    for _ in range(12):
        assert not (again["briefing"] and again["briefing"]["step_key"] == "story_event")
        if again["type"] == "end":
            break
        again = chj.turn("응") if again["briefing"]["step_key"] == "detail_ask" else chj.turn(event="auto_next")


# ── I3, I4 미리보기 → 올리기 → 알바생 할 일 ──


def test_i3_i4_preview_post_and_card(chj: Choongjang, ig_on):
    fake = ready(chj, ig_on)
    asked = open_story(chj)
    assert asked["type"] == "ask_action" and asked["expects_reply"] is True and asked["headline"] == "이벤트 포스터를 다 만들었어요"
    assert [s["text"] for s in asked["say"]] == ["이벤트 포스터를 다 만들었어요.", "화면에 띄웠어요.",
                                                f"스토리에 올리고, 알바생 할 일 맨 위에 {TITLE}를 넣을까요?"]
    preview, todo = asked["cards"]
    assert preview["type"] == "images" and [i["photo_url"] for i in preview["items"]] == [f"/media/{SE_ID}/poster_1.jpg", f"/media/{SE_ID}/story_1.jpg"]
    assert todo["items"][0]["title"] == TITLE
    assert width.violations(asked) == [] and "action" not in asked  # 앱의 action 은 아쉬운 리뷰(review_fix) 것

    done = chj.turn("응, 올려")
    assert done["intent"] == "action.approve" and done["headline"] == "이벤트 스토리를 올릴게요"
    assert [s["text"] for s in done["say"]] == ["네, 이벤트 스토리를 올릴게요.", f"올라가면 알바생 할 일 맨 위에 {TITLE}를 넣을게요."]
    assert record()["state"] == "approved"
    assert chj.staff_today("st_harin")["urgent"] == []  # 아직 안 올라갔다
    assert hr_log() == [("story_poster", "approved")]

    run_publish(chj)
    created = [params for method, path, params in fake.calls if method == "POST" and path.endswith("/media")]
    assert created == [{"media_type": "STORIES", "image_url": f"https://media.example.test/media/{SE_ID}/story_1.jpg"}]
    post = chj.get("/v1/instagram")["posts"][0]
    assert post["status"] == "published" and post["event_id"] == SE_ID
    assert not (media.MEDIA_DIR / post["id"]).exists()  # 그린 그림을 그대로 올린다 (다시 줄이지 않는다)

    [card] = chj.staff_today("st_harin")["urgent"]
    assert card["title"] == TITLE and card["detail"] == OFFER
    saved = record()
    assert saved["state"] == "card_pinned" and saved["task_id"] == card["id"]
    [pinned] = [t for t in staff.store_tasks("s005") if t["id"] == card["id"]]
    assert pinned["origin"] == "story_event"  # 리뷰에서 나온 일(review)로 적지 않는다
    assert card["id"] in [t["id"] for t in staff_orders._sent_today("s005")]  # "시킨 거 다 했대?"에는 들어간다
    told = chj.notices()
    assert [(n["text"], n["say"]) for n in told] == [("이벤트 스토리를 올렸어요", ["이벤트 스토리를 올렸어요.", f"알바생 할 일 맨 위에 {TITLE}를 넣었어요."])]

    twice = chj.turn("응")  # 이미 올렸다
    assert twice["headline"] == "스토리는 이미 올렸어요" and len(chj.get("/v1/instagram")["posts"]) == 1

    chj.staff_post(f"/tasks/{card['id']}/confirm", staff_id="st_harin")
    assert [n["kind"] for n in chj.notices()] == ["staff_checked"]


# ── I5 게시 실패 ──


def test_i5_publish_failure_no_card(chj: Choongjang, ig_on):
    ready(chj, ig_on, FakeGraph(fail={"media_publish": (100, "boom")}))
    open_story(chj)
    chj.turn("응, 올려")
    run_publish(chj)
    assert record()["state"] == "failed" and chj.staff_today("st_harin")["urgent"] == []
    assert [(n["text"], n["say"]) for n in chj.notices()] == [
        ("이벤트 스토리를 올리지 못했어요", ["이벤트 스토리를 올리지 못했어요.", "알바생 할 일에도 넣지 않았어요."])]


# ── I6 안 해, 다시 그려, 할 일 빼고 ──


def test_i6_cancel_then_redo(chj: Choongjang, ig_on):
    ready(chj, ig_on)
    open_story(chj)
    no = chj.turn("안 해")
    assert no["intent"] == "action.cancel" and no["headline"] == "올리지 않을게요" and record()["state"] == "declined"
    assert chj.get("/v1/instagram")["posts"] == []

    redo = chj.turn("다시 그려 줘")
    assert redo["intent"] == "action.redo" and redo["headline"] == "포스터를 다시 그릴게요"
    assert record()["state"] == "ready" and record()["image_url"] == f"/media/{SE_ID}/story_2.jpg"
    asked = open_story(chj)
    assert [i["photo_url"] for i in asked["cards"][0]["items"]] == [f"/media/{SE_ID}/poster_2.jpg", f"/media/{SE_ID}/story_2.jpg"]
    assert hr_log() == [("story_poster", "rejected")]  # 첫 포스터만 반려. 다시 그린 포스터는 따로 센다


def test_i6_story_only(chj: Choongjang, ig_on):
    ready(chj, ig_on)
    open_story(chj)
    edited = chj.turn("할 일은 넣지 마")
    assert edited["intent"] == "action.edit" and edited["type"] == "ask_action"
    assert edited["say"][-1]["text"] == "알바생 할 일은 빼고 스토리만 올릴까요?" and len(edited["cards"]) == 1
    done = chj.turn("응, 올려")
    assert done["say"] == [{"text": "네, 이벤트 스토리를 올릴게요.", "caption": None, "focus": []}]
    run_publish(chj)
    assert record()["state"] == "published" and chj.staff_today("st_harin")["urgent"] == []
    assert hr_log() == [("story_poster", "approved")]  # "할 일은 넣지 마"도 포스터는 그대로 승인 (9-0 m)


def test_i6_unclear_yes_asks_again(chj: Choongjang, ig_on):
    ready(chj, ig_on)
    open_story(chj)
    unsure = chj.turn("네")  # "도나야" 없이 "네"만: 손님에게 한 말일 수 있다
    assert unsure["intent"] == "action.unclear" and unsure["say"][0]["text"] == "올리시려면 '응, 올려'라고 말씀해 주세요."
    assert record()["state"] == "ready"


# ── I7 그림 실패 ──


def test_i7_engine_failure(chj: Choongjang, ig_on, monkeypatch):
    def broken(prompt, images):
        raise PosterEngineError("ChatGPT 사용량을 다 썼어요. 잠시 뒤 다시 해 주세요")

    real = image_engine.generate
    monkeypatch.setattr(image_engine, "generate", broken)
    ig_on(FakeGraph())
    predraw_failed()
    connect(chj)
    to_story_step(chj)
    chj.turn("응, 좋아")
    assert record()["state"] == "failed" and "사용량" in record()["error"]
    assert [(n["opens_turn"], n["text"]) for n in chj.notices()][-1] == (False, "이벤트 포스터를 그리지 못했어요")

    monkeypatch.setattr(image_engine, "generate", real)
    response = chj.client.post("/v1/dev/story_event", json={"store_id": "s005"}).json()  # /dev 에서 다시
    assert response["state"] == "ready"


# ── I8 아쉬운 리뷰 알림과 섞일 때 ──


def test_i8_review_and_story_do_not_mix(chj: Choongjang, ig_on):
    ready(chj, ig_on)
    open_story(chj)  # 스토리 포스터를 묻는 중에
    chj.settings(None)  # 묻는 가게 (바로 답하기를 켜면 답글은 묻지 않고 올린다)
    chj.clock("2026-11-17T15:40:00+09:00")
    rid = chj.demo_review("leak")  # 아쉬운 리뷰가 온다
    review_notice = [n for n in chj.notices() if n["kind"] == "negative_review"]
    asked = chj.turn(event="notice", notice_id=review_notice[-1]["id"])
    assert asked["headline"] == "아쉬운 리뷰가 왔어요"
    done = chj.turn("응, 진행해")
    assert done["headline"] == "답글 올리고 할 일 넣었어요" and repo.get("alert", f"al_{rid}")["state"] == "card_pinned"
    assert record()["state"] == "ready"  # 스토리는 그대로 기다린다
    assert chj.get("/v1/instagram")["posts"] == []
