"""guards 스위트의 끊겨도 이어 돌리기(cases.jsonl, --resume)와 CLOVA 호출 상한(GuardedPost). 실제 CLOVA 를 부르지 않는다."""

import json

import httpx
import pytest

from app.core.config import settings
from Harness.evals import cli, derive, guards_eval, report
from Harness.tests.fake_gold import write_gold

pytest.importorskip("openpyxl")


def ok_post(url, **kwargs):
    return httpx.Response(200, json={}, request=httpx.Request("POST", url))


def test_guarded_post_caps_timeout_and_counts():
    seen = {}

    def post(url, **kwargs):
        seen.update(kwargs)
        return ok_post(url)

    guarded = guards_eval.GuardedPost(post, call_timeout=60)
    guarded("http://x", json={}, timeout=600)
    assert seen["timeout"] == 60 and guarded.calls == 1


def test_guarded_post_turns_connection_error_into_abort_with_reason():
    def down(url, **kwargs):
        raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")

    with pytest.raises(guards_eval.CaseAborted, match="연결 실패: ConnectError"):
        guards_eval.GuardedPost(down)("http://x", json={})

    def slow(url, **kwargs):
        raise httpx.ReadTimeout("read")

    with pytest.raises(guards_eval.CaseAborted, match="연결 실패: 호출 제한 시간 60초"):
        guards_eval.GuardedPost(slow)("http://x", json={})


def test_guarded_post_stops_after_call_cap_and_deadline():
    guarded = guards_eval.GuardedPost(ok_post, max_calls=2)
    guarded("http://x")
    guarded("http://x")
    with pytest.raises(guards_eval.CaseAborted, match="호출 상한 2번"):
        guarded("http://x")
    now = [0.0]
    late = guards_eval.GuardedPost(ok_post, deadline=10, clock=lambda: now[0])
    late("http://x")
    now[0] = 11
    with pytest.raises(guards_eval.CaseAborted, match="사례 제한 시간 10초"):
        late("http://x")


def test_connection_failure_becomes_unknown_and_next_case_goes_on(monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")

    def down(url, **kwargs):
        raise httpx.ConnectError("getaddrinfo failed")

    cases = guards_eval.critic_cases()[:2]
    stores = {"t001": guards_eval.critic_store()}
    result = guards_eval.evaluate(cases, stores, ["critic"], post=down)
    rows = result["cases"]
    assert [row["outcome"] for row in rows] == ["unknown", "unknown"]
    assert all(row["error"].startswith("연결 실패") and row["calls"] == 1 for row in rows)


def test_resumable_drops_connection_failures_and_keeps_last_row():
    rows = [
        {"system": "critic", "run": 1, "case_id": "a", "error": None, "outcome": "pass"},
        {"system": "critic", "run": 1, "case_id": "b", "error": "연결 실패: ConnectError", "outcome": "unknown"},
        {"system": "critic", "run": 1, "case_id": "c", "error": "사례 제한 시간 300초를 넘김", "outcome": "unknown"},
        {"system": "critic", "run": 2, "case_id": "a", "error": None, "outcome": "pass"},
    ]
    kept = {(row["run"], row["case_id"]) for row in guards_eval.resumable(rows)}
    assert kept == {(1, "a"), (2, "a")}  # 연결 실패와 사례 제한 시간 초과는 다시 판정한다


def test_evaluate_skips_done_rows():
    cases = guards_eval.critic_cases()[:3]
    stores = {"t001": guards_eval.critic_store()}
    first = guards_eval.evaluate(cases[:2], stores, ["regex"])["cases"]
    seen = []
    result = guards_eval.evaluate(cases, stores, ["regex"], done=first, on_case=lambda name, run, row: seen.append(row["case_id"]))
    assert seen == [cases[2]["case_id"]]  # 끝난 두 건은 다시 판정하지 않는다
    assert len(result["cases"]) == 3


def test_jsonl_written_per_case_and_resume_fills_the_rest(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "")
    monkeypatch.setattr(report, "OUT_ROOT", tmp_path / "harness_eval")
    path, sha = write_gold(tmp_path / "gold.xlsx")
    args = ["guards", "--gold", str(path), "--gold-sha", sha]
    cli.main(args)
    (out,) = (tmp_path / "harness_eval").glob("guards-*")
    lines = (out / guards_eval.CASES_JSONL).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 45
    # 끊긴 것처럼: 뒤 5줄을 지우고 반쯤 쓴 줄을 남긴다
    (out / guards_eval.CASES_JSONL).write_text("\n".join(lines[:40]) + "\n{\"case_id\": ", encoding="utf-8")
    cli.main([*args, "--resume", str(out)])
    body = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert len(body["cases"]) == 45 and body["config"]["resumed"] == 1
    assert len(guards_eval.read_jsonl(out / guards_eval.CASES_JSONL)) == 45
    assert len(list((tmp_path / "harness_eval").glob("guards-*"))) == 1  # 새 폴더를 만들지 않는다


def test_resume_refuses_when_sets_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "")
    monkeypatch.setattr(report, "OUT_ROOT", tmp_path / "harness_eval")
    path, sha = write_gold(tmp_path / "gold.xlsx")
    cli.main(["guards", "--gold", str(path), "--gold-sha", sha])
    (out,) = (tmp_path / "harness_eval").glob("guards-*")
    body = json.loads((out / "result.json").read_text(encoding="utf-8"))
    body["config"]["gold"]["sets"]["normal"] = "0" * 64
    (out / "result.json").write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(SystemExit, match="세트가 바뀌어"):
        cli.main(["guards", "--gold", str(path), "--gold-sha", sha, "--resume", str(out)])


def test_normal_set_skips_replies_over_300_chars(tmp_path):
    from Harness.evals import gold

    cases = gold.load_gold(*write_gold(tmp_path / "gold.xlsx"))
    long_reply = "국수 맛있게 드셨다니 기뻐요. " * 30
    changed = [{**cases[0], "gold": {**cases[0]["gold"], "reply": long_reply}}, *cases[1:]]
    assert len(long_reply) > derive.NORMAL_MAX_CHARS
    assert [row["source_case_id"] for row in derive.normal_set(changed)] == ["c0003"]
