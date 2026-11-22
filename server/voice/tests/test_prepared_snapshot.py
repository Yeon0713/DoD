"""밤사이 준비 결과 저장본 (voice/prepared_snapshot.py, 2026-11-18): '처음부터'가 준비(CLOVA)를 다시 하지 않고 바로 브리핑할 수 있다."""

import pytest

from voice import prepared_snapshot
from voice.jobs import briefing
from voice.tests.conftest import Choongjang

NAME = "s005_choongjang"


@pytest.fixture
def snapshot_on(tmp_path, monkeypatch):
    monkeypatch.setattr(prepared_snapshot, "ENABLED", True)
    monkeypatch.setattr(prepared_snapshot, "FOLDER", tmp_path)
    return tmp_path


def fresh(donna: Choongjang) -> dict:
    response = donna.client.post("/v1/dev/fixtures", json={"fixture": NAME})
    assert response.status_code == 200, response.text
    return response.json()


def test_restart_uses_saved_preparation(snapshot_on, monkeypatch):
    donna = Choongjang()
    assert fresh(donna).get("prepared") is None  # 저장본이 없으면 예전처럼 준비한다
    prepared_before = donna.turn("오늘 일정 브리핑해 줘")
    prepared_snapshot.save(NAME, "s005")

    def no_prepare(store_id):
        raise AssertionError("저장본이 있으면 다시 준비하지 않아야 해요")

    monkeypatch.setattr(briefing, "prepare", no_prepare)
    again = Choongjang()
    assert fresh(again)["prepared"] == "snapshot"
    after = again.turn("오늘 일정 브리핑해 줘")
    assert after["headline"] == prepared_before["headline"] and after["say"] == prepared_before["say"]
    # 알바생 표는 시나리오 파일에서 새로: 하린은 아직 안 들어왔다
    assert again.get("/v1/settings")["staff_count"] == 4


def test_changed_scenario_is_prepared_again(snapshot_on, monkeypatch):
    donna = Choongjang()
    fresh(donna)
    prepared_snapshot.save(NAME, "s005")
    monkeypatch.setattr(prepared_snapshot, "fixture_sha", lambda name: "changed")  # 시나리오 파일을 고친 것과 같다
    assert prepared_snapshot.load(NAME) is None
    assert fresh(Choongjang()).get("prepared") is None


def test_tests_do_not_use_the_real_snapshot():
    assert prepared_snapshot.ENABLED is False  # conftest


def test_snapshot_carries_predrawn_poster(snapshot_on):
    """밤사이 그려 둔 이벤트 포스터와 스토리 사진도 저장본 옆에 두고, '처음부터'에 MEDIA_DIR 로 되돌린다 (2026-11-22)."""
    from voice.instagram import media

    donna = Choongjang()
    fresh(donna)
    files = ["se_s005_2026-11-17/poster_1.jpg", "se_s005_2026-11-17/story_1.jpg"]
    assert all((media.MEDIA_DIR / f).exists() for f in files)
    prepared_snapshot.save(NAME, "s005")
    assert all((prepared_snapshot.media_folder(NAME) / f).exists() for f in files)

    for f in files:
        (media.MEDIA_DIR / f).unlink()  # 다른 컴퓨터에서 처음 켠 것과 같다
    again = Choongjang()
    assert fresh(again)["prepared"] == "snapshot"
    assert all((media.MEDIA_DIR / f).exists() for f in files)
    assert again.client.get("/media/se_s005_2026-11-17/story_1.jpg").status_code == 200
