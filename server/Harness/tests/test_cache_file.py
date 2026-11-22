"""에이전트 결과 캐시의 파일 층 (Harness/cache.py, 2026-11-18): 서버를 다시 켜도(메모리를 비워도) 결과가 남는다."""

from Harness import cache
from Harness.spec import Proposal

KEY = ("voice_reply", "s005", "input-hash", "prompt-hash")


def proposal() -> Proposal:
    return Proposal("voice_reply", "rv_0401", {"text": "주문 또 해주셔서 감사합니다."}, "AGENT", "run_1", ["input"], ["검토 통과"])


def test_result_survives_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_PATH", tmp_path / "harness_cache.db")
    cache.put(KEY, proposal())
    cache.clear()  # 서버를 다시 켠 것과 같다 (메모리가 빈다)
    again = cache.get(KEY)
    assert isinstance(again, Proposal) and again == proposal()


def test_other_prompt_is_a_miss(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_PATH", tmp_path / "harness_cache.db")
    cache.put(KEY, proposal())
    cache.clear()
    assert cache.get(KEY[:3] + ("changed-prompt",)) is None  # 프롬프트를 고치면 새로 부른다


def test_clear_disk_removes_file_results(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_PATH", tmp_path / "harness_cache.db")
    cache.put(KEY, proposal())
    cache.clear_disk()
    assert cache.get(KEY) is None


def test_values_that_are_not_json_stay_in_memory_only(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_PATH", tmp_path / "harness_cache.db")
    cache.put(KEY, object())
    cache.clear()
    assert cache.get(KEY) is None


def test_no_file_when_path_is_none():
    assert cache.CACHE_PATH is None  # conftest: 다른 시험은 파일 층을 끈다
    cache.put(KEY, proposal())
    cache.clear()
    assert cache.get(KEY) is None


def test_nested_proposal_survives_restart(tmp_path, monkeypatch):
    """supervisor 처럼 content 안에 Proposal 을 품은 값도 그대로 돌아온다 (H1)."""
    monkeypatch.setattr(cache, "CACHE_PATH", tmp_path / "harness_cache.db")
    outer = Proposal("supervisor", "BATCH:x", {"headline": None, "revised": {"p1": proposal()}}, "AGENT", "run_2")
    cache.put(KEY, outer)
    cache.clear()
    again = cache.get(KEY)
    assert isinstance(again.content["revised"]["p1"], Proposal)
    assert again == outer


def test_legacy_nested_entry_is_a_miss(tmp_path, monkeypatch):
    """예전 모양(asdict)으로 저장된, 안쪽 Proposal 이 dict 가 된 항목은 빗나감으로 본다 (H1)."""
    import dataclasses
    import json

    monkeypatch.setattr(cache, "CACHE_PATH", tmp_path / "harness_cache.db")
    outer = Proposal("supervisor", "BATCH:x", {"headline": None, "revised": {"p1": proposal()}}, "AGENT", "run_2")
    text = json.dumps({"type": "proposal", "fields": dataclasses.asdict(outer)}, ensure_ascii=False)
    with cache._db() as conn:
        conn.execute("INSERT INTO results (agent, store_id, input_hash, prompt_hash, value) VALUES (?, ?, ?, ?, ?)", (*KEY, text))
    assert cache.get(KEY) is None
