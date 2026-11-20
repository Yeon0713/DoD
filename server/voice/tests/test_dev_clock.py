"""시계를 멈춘 동안의 작업 큐와 server/.env 읽기 (2026-11-21).

시계(dev/clock)는 서버에 하나다. 시연 PC 에 앱으로 들어온 실제 가게가 같이 있으면, 시계를 옮길 때 그 가게 리뷰 답글까지
가짜 시각으로 써서 5분 넘게 멈췄다. 이제 시계를 멈춘 동안에는 fixtures 로 넣은 가게만 돈다.
"""

import datetime as dt

from voice import clock, config, repo
from voice.jobs import queue
from voice.tests.conftest import choongjang


def real_store() -> str:
    """앱 가입으로 들어온 것 같은 가게 (fixture 표시 없음)."""
    store = {k: v for k, v in repo.store("s005").items() if k != "fixture"}
    repo.put("store", "s777", "s777", {**store, "id": "s777", "name": "실제 가게"})
    return "s777"


def test_fixture_stores_are_marked():
    choongjang(at=None)
    assert repo.store("s005")["fixture"] is True


def test_fixed_clock_runs_only_fixture_stores():
    choongjang(at=None)
    real = real_store()
    due = clock.now() - dt.timedelta(minutes=1)
    real_job = queue.add(real, "post_scheduled", due)["id"]
    demo_job = queue.add("s005", "post_scheduled", due)["id"]
    ran = queue.run_due()
    assert demo_job in ran and real_job not in ran
    clock.set_now(None)  # 실제 시각으로 돌아오면 실제 가게 작업도 돈다
    assert real_job in queue.run_due()


def test_dotenv_switch_turns_an_agent_off(monkeypatch, clova_on):  # clova_on: CLOVA 키가 있는 상태
    monkeypatch.delenv("VOICE_AGENT_FIXCARD", raising=False)
    assert config.agent_on("fixcard") is True
    monkeypatch.setattr(config, "_DOTENV", {"VOICE_AGENT_FIXCARD": "false"})  # server/.env 에 적은 것
    assert config.agent_on("fixcard") is False
    monkeypatch.setenv("VOICE_AGENT_FIXCARD", "true")  # 셸에서 준 값이 먼저다
    assert config.agent_on("fixcard") is True
