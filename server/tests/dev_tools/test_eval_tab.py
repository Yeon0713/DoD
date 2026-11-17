"""개발자 대시보드 '평가' 탭 API (app/modules/dev_tools/eval_reader.py). 임시 결과 폴더만 읽는다."""

import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app
from app.modules.dev_tools import eval_reader
from Harness import trace


def metric(id, system, numerator, denominator, question=2, **extra):
    return {"id": id, "question": question, "name": id, "system": system, "value": numerator / denominator,
            "numerator": numerator, "denominator": denominator, "unit": "ratio", "higher_is_better": True, "note": "", **extra}


def write(root, name, body):
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "result.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return folder


def reply_body(started, fit_b):
    case = {"text": "면이 불었어요", "complaint_types": ["TASTE"], "checks": {"length_ok": True}, "rejections": []}
    return {
        "schema": 1, "suite": "reply", "started_at": started, "finished_at": started, "git": {"commit": "abc1234", "dirty": False},
        "config": {"baseline": True}, "systems": ["A", "B"],
        "metrics": [metric("reply_fit_rate", "A", 1, 2), metric("reply_fit_rate", "B", fit_b, 2),
                    metric("agent_fit_rate", "B", 0, 2)],
        "cases": [
            {**case, "case_id": "c1", "system": "A", "run": 1, "run_id": "ra1", "source": "AGENT", "output": "A 답글", "fit": True,
             "conditions": {"fact": True, "format": True}, "verdicts": {"fact": {"vote": [True, True, True], "ok": True}}},
            {**case, "case_id": "c1", "system": "B", "run": 1, "run_id": "rb1", "source": "FALLBACK", "output": "B 답글", "fit": False,
             "conditions": {"fact": False, "format": False}, "format_failures": ["빈칸"],
             "verdicts": {"fact": {"vote": [False, False, None], "ok": False, "quote": "무료로 드릴게요"}}},
        ],
        "validation": {},
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "dev_tools_enabled", True)
    monkeypatch.setattr(eval_reader, "EVAL_ROOT", tmp_path / "harness_eval")
    root = tmp_path / "harness_eval"
    write(root, "reply-20261117-100000", reply_body("2026-11-17T10:00:00+09:00", 0))
    new = write(root, "reply-20261118-100000", reply_body("2026-11-18T10:00:00+09:00", 1))
    write(root, "critic-20261110-090000", {"summary": {"runs": 3, "missed": 2, "label": "예전"}, "rows": [{"id": "k1", "ok": False}]})
    write(root, "guards-20261117-120000", {
        "schema": 1, "suite": "guards", "started_at": "2026-11-17T12:00:00+09:00", "git": {}, "config": {}, "systems": ["judge_tools"],
        "metrics": [metric("missed_rate", "judge_tools", 1, 10, question=3, set="gold"),
                    metric("missed_rate", "judge_tools", 0, 5, question=3, set="critic_cases")],
        "cases": [], "validation": {"critic_target": {"gold": {"missed": 1, "pass": False}}}})
    monkeypatch.setattr(trace, "TRACE_PATH", new / "harness_trace.db")  # 그 폴더에 실행 기록을 쓴다 (평가 실행과 같게)
    trace.record(run_id="rb1", parent_run_id=None, agent="reply_agent", store_id="t001", step=0, kind="start", name="REVISIT_REPLY:c1")
    trace.record(run_id="w1", parent_run_id="rb1", agent="reply_critic", store_id="t001", step=0, kind="llm", name="HCX-005")
    trace.record(run_id="other", parent_run_id=None, agent="reply_agent", store_id="t001", step=0, kind="start", name="x")
    return TestClient(create_app())


def test_list_runs_newest_first_with_headline_and_legacy(client):
    runs = client.get("/api/dev_tools/evals").json()["runs"]
    assert [r["id"] for r in runs][:2] == ["reply-20261118-100000", "guards-20261117-120000"]
    newest = runs[0]
    assert newest["suite"] == "reply" and newest["commit"] == "abc1234" and newest["baseline"] is True
    assert [(m["id"], m["system"]) for m in newest["headline"]] == [("reply_fit_rate", "A"), ("reply_fit_rate", "B"), ("agent_fit_rate", "B")]
    legacy = next(r for r in runs if r["id"].startswith("critic"))
    assert legacy["legacy"] is True and legacy["suite"] == "critic" and {m["id"] for m in legacy["headline"]} <= {"runs", "missed"}


def test_run_detail_normalizes_cases_and_pairs(client):
    body = client.get("/api/dev_tools/evals/run", params={"id": "reply-20261118-100000"}).json()
    assert body["cases_total"] == 2 and body["legacy"] is False
    b = next(c for c in body["cases"] if c["system"] == "B")
    assert b["ok"] is False and b["input"] == "면이 불었어요" and b["output"] == "B 답글"
    assert b["verdicts"]["fact"]["vote"] == [False, False, None]
    assert "형식: 빈칸" in b["problems"] and "fact 문제 문구: 무료로 드릴게요" in b["problems"]
    (pair,) = body["pairs"]
    assert pair["A"]["output"] == "A 답글" and pair["B"]["output"] == "B 답글" and pair["only"] == "A"
    failed = client.get("/api/dev_tools/evals/run", params={"id": "reply-20261118-100000", "failed_only": True}).json()
    assert [c["system"] for c in failed["cases"]] == ["B"] and failed["cases_all"] == 2
    only_a = client.get("/api/dev_tools/evals/run", params={"id": "reply-20261118-100000", "system": "A", "limit": 1}).json()
    assert [c["system"] for c in only_a["cases"]] == ["A"] and body["judge_check"] is None


def test_guards_metrics_keep_set_and_judge_check(client):
    body = client.get("/api/dev_tools/evals/run", params={"id": "guards-20261117-120000"}).json()
    assert {m["key"] for m in body["metrics"]} == {"missed_rate [gold]", "missed_rate [critic_cases]"}
    assert body["judge_check"]["validation"]["critic_target"]["gold"]["missed"] == 1


def test_legacy_run_detail(client):
    body = client.get("/api/dev_tools/evals/run", params={"id": "critic-20261110-090000"}).json()
    assert body["legacy"] is True and body["summary"]["label"] == "예전"
    assert {m["key"]: m["value"] for m in body["metrics"]} == {"runs": 3, "missed": 2}
    assert body["cases"][0]["case_id"] == "k1" and body["cases"][0]["ok"] is False


def test_trend_per_run_and_system(client):
    body = client.get("/api/dev_tools/evals/trend", params={"suite": "reply", "metric": "reply_fit_rate"}).json()
    b = [(p["id"], p["value"]) for p in body["points"] if p["system"] == "B"]
    assert b == [("reply-20261117-100000", 0.0), ("reply-20261118-100000", 0.5)] and body["higher_is_better"] is True
    guards = client.get("/api/dev_tools/evals/trend", params={"suite": "guards", "metric": "missed_rate [gold]"}).json()
    assert [p["value"] for p in guards["points"]] == [0.1]


def test_trace_reads_folder_db_like_steps_of(client):
    body = client.get("/api/dev_tools/evals/trace", params={"id": "reply-20261118-100000", "run_id": "rb1"}).json()
    assert body["steps"] == trace.steps_of("rb1")  # TRACE_PATH 가 그 폴더를 가리킬 때 trace 와 같은 모양
    assert [(s["run_id"], s["kind"]) for s in body["steps"]] == [("rb1", "start"), ("w1", "llm")]
    empty = client.get("/api/dev_tools/evals/trace", params={"id": "reply-20261117-100000", "run_id": "rb1"}).json()
    assert empty["steps"] == []  # 실행 기록 파일이 없는 폴더


@pytest.mark.parametrize("bad", ["../secret", "..", "a/b", "reply-20261118-100000/../x", "", "%2e%2e"])
def test_bad_ids_are_rejected(client, bad):
    for path in ("/api/dev_tools/evals/run", "/api/dev_tools/evals/trace"):
        response = client.get(path, params={"id": bad, "run_id": "rb1"})
        assert response.status_code in (400, 404, 422), (path, bad)


def test_missing_run_is_404(client):
    assert client.get("/api/dev_tools/evals/run", params={"id": "reply-20991231-000000"}).status_code == 404


def test_agent_names_include_comparison_agents():
    from app.modules.dev_tools.data_provider import AGENT_NAMES

    assert AGENT_NAMES["single_agent"] == "단일 에이전트(비교용)" and AGENT_NAMES["voice_single_agent"].startswith("음성")


def test_run_charts_and_summary(client):
    """그래프용 집계(charts)와 질문별 요약 카드(summary), 사례 하나 열기(case)."""
    body = client.get("/api/dev_tools/evals/run", params={"id": "reply-20261118-100000"}).json()
    c = body["charts"]
    assert c["q2"]["conditions"]["systems"]["B"]["fact"] == {"pass": 0, "fail": 1, "unknown": 0, "total": 1, "rate": 0.0}
    assert c["q4"]["pass_distribution"] == {"runs": 1, "systems": {"A": [0, 1], "B": [1, 0]}}
    grid = c["cases_grid"]
    assert grid["conditions"] == ["fact", "format"] and grid["rows"][0]["system"] == "B"  # 실패한 사례 먼저
    one = client.get("/api/dev_tools/evals/run", params={"id": "reply-20261118-100000", "case": grid["rows"][0]["index"]}).json()
    assert [(x["system"], x["case_id"]) for x in one["cases"]] == [("B", "c1")]
    guards = client.get("/api/dev_tools/evals/run", params={"id": "guards-20261117-120000"}).json()["charts"]["q3"]["scatter"]
    assert guards is None  # false_reject_rate 가 없는 세트는 점을 찍지 않는다
    summary = {card["question"]: card for card in client.get("/api/dev_tools/evals").json()["summary"]}
    q2 = summary[2]
    assert q2["run"] == "reply-20261118-100000" and q2["values"]["B"]["value"] == 0.5 and q2["diff"] == 0.0
    assert q2["goal"] is True and summary[1]["run"] is None


def test_outcome_mix_splits_success_by_fit_and_failures_by_cause(client):
    """결과 구성: 생성 성공은 적합 여부로, 실패는 원인으로. fail_cause 가 없는 예전 줄은 그 폴더의 실행 기록으로 가른다."""
    mix = client.get("/api/dev_tools/evals/run", params={"id": "reply-20261118-100000"}).json()["charts"]["q2"]["outcome_mix"]
    assert mix["systems"] == {"A": {"success_fit": 1}, "B": {"no_submit": 1}}  # B 실행 rb1 은 제출 없이 끝난 기록
    assert [o["key"] for o in mix["order"]][:3] == ["success_fit", "success_unfit", "transport"]
