"""AI 포스터: 상황 모으기, CLOVA 멘트(와 대신 쓰는 문장), 프롬프트, Codex 결과 읽기, 스토리 크기, 일감 API."""

import datetime as dt
import io
import json
import subprocess
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core import naver_place
from app.core.config import settings
from app.core.seoul_time import SEOUL
from app.data_pipeline.store_snapshot_cache import get_snapshot
from app.main import create_app
from app.poster_ai import image_engine, jobs, ment, prompt, situation

PLAN = "POSTER:event_9002:2026-10-10"  # 초옹장 시험 주간: 10/10 남양 가을 축제 (docs/test-week.md)
NOW = dt.datetime(2026, 10, 7, 15, 5, tzinfo=SEOUL)


@pytest.fixture(scope="module")
def festival() -> situation.Situation:
    return situation.from_plan(get_snapshot("s005", NOW, wait_for_drafts=False, polish=False), PLAN)


def _jpg(color=(200, 150, 90), size=(600, 400)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "JPEG")
    return out.getvalue()


def test_situation_reads_event_weather_and_menus(festival):
    s = festival
    assert (s.kind, s.title, s.date) == ("EVENT", "남양 가을 축제", dt.date(2026, 10, 10))
    assert s.distance_km is not None and s.distance_km < 1
    assert "COLD" in s.weather_tags  # 시험 날씨: 10/10 최고 9.5도
    assert s.lines()[0] == "10월 10일(토) 남양 가을 축제, 가게에서 0.3km" and "쌀쌀해요" in s.lines()[1]
    assert s.menus
    with pytest.raises(ValueError):
        situation.from_plan(get_snapshot("s005", NOW, wait_for_drafts=False, polish=False), "MENU_ORDER:x:2026-10-10")


def test_weather_tags():
    assert situation._weather_tags(dt.date(2026, 8, 3), 33, 25, 0) == ["HOT"]
    assert situation._weather_tags(dt.date(2026, 7, 3), 27, 22, 30) == ["RAIN", "MONSOON"]
    assert situation._weather_tags(dt.date(2026, 1, 9), 0, -6, 5) == ["COLD", "SNOW"]


def test_clova_ments_are_parsed_and_checked(festival):
    answer = """여기 있어요
    [{"kind": "EVENT", "label": "축제 손님", "headline": "축제 가는 길에\\n한 그릇", "line": "구경 전후로 들러 주세요", "menu": "없는메뉴"},
     {"kind": "WEATHER", "label": "추운 날", "headline": "쌀쌀한 날엔", "line": "따끈한 국물 어떠세요?", "menu": "%s"},
     {"kind": "MENU", "label": "너무 긴 것", "headline": "%s", "line": "x"}]""" % (festival.menus[0], "가" * 40)
    ments = ment.parse(answer, festival.menus)
    assert [m.kind for m in ments] == ["EVENT", "WEATHER"]  # 너무 긴 큰 글자는 뺀다
    assert ments[0].headline == "축제 가는 길에\n한 그릇" and ments[0].menu == ""  # 목록에 없는 메뉴 이름은 지운다
    assert ments[1].menu == festival.menus[0]
    assert ment.parse("모르겠어요", festival.menus) == []


def test_basic_ments_when_clova_is_unavailable(festival, monkeypatch):
    monkeypatch.setattr(ment.clova, "ask", lambda *a, **k: None)
    ment._cache.clear()
    ments, source = ment.suggest(festival)
    assert source == "BASIC" and len(ments) == 3
    assert ments[0].kind == "EVENT" and "남양 가을 축제" in ments[0].headline
    assert ments[1].kind == "WEATHER" and ments[1].menu in festival.menus  # 쌀쌀한 날 국물 메뉴


def test_game_day_suggests_cheering_event():
    s = situation.Situation(store_id="s001", store_name="가게", category="치킨", address="서울", date=dt.date(2026, 11, 19), kind="GAME", title="저녁 야구 경기", menus=["후라이드"])
    assert "응원하는 팀을 리뷰에 남겨" in ment.fallback(s)[0].line


def test_prompt_keeps_text_verbatim_and_names_image_roles(festival):
    choice = prompt.PosterChoice(headline="축제 가는 길에\n한 그릇", line="구경 전후로 들러 주세요", extra="손목띠 보여 주시면 음료 드려요",
                                 style="FESTIVAL", menu="들깨옹심이", photo_labels=("들깨옹심이", "매장 사진"), has_logo=True)
    text = prompt.build(festival, choice)
    assert '"축제 가는 길에 / 한 그릇"' in text and '"구경 전후로 들러 주세요"' in text and '"손목띠 보여 주시면 음료 드려요"' in text
    assert "Attached image 1: the restaurant's LOGO" in text and 'Attached image 2: real photo of "들깨옹심이"' in text and "Attached image 3" in text
    assert "9:16" in text and "남양 가을 축제" in text and festival.address in text
    no_logo = prompt.build(festival, prompt.PosterChoice(headline="오늘은", line="", photo_labels=("매장 사진",)))
    assert "LOGO" not in no_logo and "Extra info" not in no_logo


def test_to_story_makes_instagram_story_size():
    for size in ((1024, 1536), (916, 1717), (1080, 1920)):
        out = Image.open(io.BytesIO(image_engine.to_story(_jpg(size=size))))
        assert out.size == (1080, 1920)


def test_openai_engine_sends_photos_and_counts_cost(tmp_path, monkeypatch):
    """openai: 첨부가 있으면 /v1/images/edits 에 image[] 로 보내고, b64 그림을 받고, usage 로 값을 센다. 실제 API 는 부르지 않는다."""
    import base64

    import httpx

    monkeypatch.setattr(settings, "poster_image_engine", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "poster_openai_model", "gpt-image-2")
    monkeypatch.setattr(settings, "poster_openai_quality", "medium")
    monkeypatch.setattr(settings, "poster_openai_size", "1024x1536")
    logo, food = tmp_path / "logo.png", tmp_path / "food.jpg"
    logo.write_bytes(b"logo")
    food.write_bytes(b"food")
    seen = {}

    def fake_post(url, headers=None, data=None, files=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, data=data, files=files)
        usage = {"input_tokens": 3600, "input_tokens_details": {"text_tokens": 600, "image_tokens": 3000}, "output_tokens": 1372}
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(b"PNGDATA").decode()}], "usage": usage})

    monkeypatch.setattr(image_engine, "post", fake_post)
    assert image_engine.engine_status()["ready"] is True
    text = prompt.build(situation.Situation("s005", "초옹장", "칼국수", "경기 화성시 남양읍", dt.date(2026, 11, 17), "RAIN", "비 오는 날"),
                        prompt.PosterChoice(headline="비 오는 날 이벤트", line="음료 1캔을 드려요", has_logo=True, photo_labels=("들깨옹심이",)))
    assert image_engine.generate(text, [logo, food]) == b"PNGDATA"
    assert seen["url"] == "https://api.openai.com/v1/images/edits" and seen["headers"]["Authorization"] == "Bearer sk-test"
    assert {k: seen["data"][k] for k in ("model", "size", "quality", "n")} == {"model": "gpt-image-2", "size": "1024x1536", "quality": "medium", "n": "1"}
    assert [(name, part[0], part[2]) for name, part in seen["files"]] == [("image[]", "logo.png", "image/png"), ("image[]", "food.jpg", "image/jpeg")]
    assert "Rainy day" in seen["data"]["prompt"] and image_engine.CODEX_ONLY not in seen["data"]["prompt"]  # Codex 에게만 하는 말은 뺀다
    # 600 × $5 + 3000 × $8 + 1372 × $30 (1백만 토큰당)
    assert image_engine.last_cost["usd"] == pytest.approx((600 * 5 + 3000 * 8 + 1372 * 30) / 1_000_000)

    for status, body, message in [(401, {"error": {"message": "bad key"}}, "키가 맞지 않아요"),
                                  (429, {"error": {"message": "rate"}}, "한도"),
                                  (400, {"error": {"code": "moderation_blocked", "message": "no"}}, "문구를 바꿔")]:
        monkeypatch.setattr(image_engine, "post", lambda *a, _s=status, _b=body, **k: httpx.Response(_s, json=_b))
        with pytest.raises(image_engine.PosterEngineError, match=message):
            image_engine.generate("그려 주세요", [logo])

    monkeypatch.setattr(settings, "openai_api_key", "")
    assert image_engine.engine_status() == {"engine": "openai", "ready": False, "note": "OPENAI_API_KEY 가 비어 있어요"}
    with pytest.raises(image_engine.PosterEngineError, match="OPENAI_API_KEY"):
        image_engine.generate("그려 주세요", [])


def test_codex_output_is_read_from_its_thread_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    monkeypatch.setattr(image_engine, "engine_status", lambda: {"engine": "codex", "ready": True, "note": ""})
    folder = tmp_path / "generated_images" / "thread-1"
    folder.mkdir(parents=True)
    seen = {}

    def fake_run(command, input, **kwargs):
        seen["command"], seen["prompt"] = command, input
        (folder / "exec-1.png").write_bytes(b"PNGDATA")
        stdout = "\n".join(json.dumps(e) for e in [{"type": "thread.started", "thread_id": "thread-1"}, {"type": "item.completed", "item": {"type": "agent_message", "text": "done"}}])
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(image_engine.subprocess, "run", fake_run)
    monkeypatch.setattr(settings, "poster_image_engine", "codex")
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"x")
    assert image_engine.generate("그려 주세요", [logo]) == b"PNGDATA"
    assert seen["command"][1:3] == ["exec", "--json"] and ["-i", str(logo)] == seen["command"][-3:-1] and seen["command"][-1] == "-"
    assert seen["prompt"] == "그려 주세요"  # 프롬프트는 표준 입력으로

    monkeypatch.setattr(image_engine.subprocess, "run", lambda command, input, **k: subprocess.CompletedProcess(command, 1, '{"type":"thread.started","thread_id":"none"}', "usage limit reached"))
    with pytest.raises(image_engine.PosterEngineError, match="사용량"):
        image_engine.generate("그려 주세요", [])


def test_poster_job_api_with_mock_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "poster_image_engine", "mock")
    monkeypatch.setattr(jobs, "POSTER_DIR", tmp_path / "posters")
    monkeypatch.setattr(naver_place, "_image", lambda url: _jpg() if "pstatic.net" in url else None)
    monkeypatch.setattr(ment.clova, "ask", lambda *a, **k: None)
    client = TestClient(create_app())
    assert client.get("/api/poster_ai/engine").json()["ready"] is True

    body = {"plan_id": PLAN, "photos": [{"label": "들깨옹심이", "url": "https://ldb-phinf.pstatic.net/a.jpg"}], "use_logo": True,
            "headline": "축제 가는 길에", "line": "들러 주세요", "extra": "", "style": "PHOTO", "menu": ""}
    started = client.post("/api/poster_ai/jobs", params={"store_id": "s005"}, json=body).json()
    assert started["status"] in ("RUNNING", "DONE")
    for _ in range(50):
        job = client.get(f"/api/poster_ai/jobs/{started['job_id']}").json()
        if job["status"] != "RUNNING":
            break
        time.sleep(0.1)
    assert job["status"] == "DONE" and job["image"] == f"/api/poster_ai/jobs/{started['job_id']}/image"
    assert "error" not in started and "error" not in job  # 앱은 응답에 "error" 칸이 있으면 실패로 본다
    res = client.get(job["image"])
    assert res.headers["content-type"] == "image/png" and Image.open(io.BytesIO(res.content)).size == (1080, 1920)

    bad = client.post("/api/poster_ai/jobs", params={"store_id": "s005"}, json={**body, "photos": [{"label": "x", "url": "https://evil.example.com/a.jpg"}]})
    assert bad.json()["error"]["code"] == "BAD_PHOTO"
    assert client.post("/api/poster_ai/jobs", params={"store_id": "s005"}, json={**body, "style": "WEIRD"}).json()["error"]["code"] == "INVALID_INPUT"
    assert client.get("/api/poster_ai/jobs/" + "0" * 32).json()["error"]["code"] == "NO_POSTER_JOB"
    assert client.get("/api/poster_ai/jobs/../../etc/image").status_code == 404


def test_broken_base64_photo_is_422_and_leaves_no_temp_dir(tmp_path, monkeypatch):
    import tempfile

    mkdtemp = tempfile.mkdtemp
    monkeypatch.setattr(jobs.tempfile, "mkdtemp", lambda prefix: mkdtemp(prefix=prefix, dir=tmp_path))
    monkeypatch.setattr(settings, "poster_image_engine", "mock")
    monkeypatch.setattr(jobs, "POSTER_DIR", tmp_path / "posters")
    monkeypatch.setattr(naver_place, "_image", lambda url: None)  # 네이버 사진 받기 실패
    monkeypatch.setattr(ment.clova, "ask", lambda *a, **k: None)
    client = TestClient(create_app())
    body = {"plan_id": PLAN, "photos": [{"label": "x", "url": "data:image/png;base64,abc"}], "use_logo": False,
            "headline": "축제 가는 길에", "line": "들러 주세요", "extra": "", "style": "PHOTO", "menu": ""}
    res = client.post("/api/poster_ai/jobs", params={"store_id": "s005"}, json=body)
    assert res.status_code == 422 and res.json()["error"]["code"] == "BAD_PHOTO"
    res = client.post("/api/poster_ai/jobs", params={"store_id": "s005"}, json={**body, "photos": [{"label": "x", "url": "https://ldb-phinf.pstatic.net/a.jpg"}]})
    assert res.status_code == 422 and res.json()["error"]["code"] == "BAD_PHOTO"
    assert list(tmp_path.glob("dona-poster-in-*")) == []  # 사진 준비에 실패하면 임시 폴더를 지운다


def test_calendar_api_sends_event_names_for_cards(monkeypatch):
    """포스터 카드 제목에 실제 행사 이름(예: 남양 가을 축제)을 쓰도록 달력 API 가 이름을 같이 보낸다"""
    from app.core.seoul_time import clock_shift, now_seoul, set_clock_shift
    from app.data_pipeline import store_snapshot_cache

    before = clock_shift()
    set_clock_shift(before + (NOW - now_seoul()))
    store_snapshot_cache.forget("s005")
    try:
        body = TestClient(create_app()).get("/api/calendar", params={"store_id": "s005"}).json()
    finally:
        set_clock_shift(before)
        store_snapshot_cache.forget("s005")
    refs = {r["ref_id"] for c in body["cells"] for r in c["reasons"] if r["tag"] in ("EVENT", "GAME")}
    assert body["names"].get("event_9002") == "남양 가을 축제"
    assert set(body["names"]) <= refs
