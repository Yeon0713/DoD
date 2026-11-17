"""all 스위트(run_all)와 보고서(report_md). 스위트 실행은 가짜로 바꿔 CLOVA 를 부르지 않는다."""

import dataclasses
import datetime as dt
import json

import pytest

from app.core.config import settings
from Harness.evals import cli, metrics, report, report_md, run_all


def fake_suites(tmp_path, fail: tuple[str, ...] = (), seen: list | None = None):
    def runner(name):
        def run(args):
            if seen is not None:
                seen.append((name, list(args.system_names)))
            if name in fail:
                raise RuntimeError(f"{name} 망가짐")
            out = report.start(name, config={}, systems=args.system_names, swap_logs=False)
            return out.finish()
        return run

    return {name: dataclasses.replace(suite, run=runner(name)) if name in run_all.ORDER else suite
            for name, suite in cli.SUITES.items()}


def test_all_runs_in_order_and_continues_after_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    monkeypatch.setattr(report, "OUT_ROOT", tmp_path)
    seen = []
    args = cli.build_parser().parse_args(["all", "--baseline"])
    outcomes = run_all.run_all(args, fake_suites(tmp_path, fail=("guards",), seen=seen))
    assert [name for name, _ in seen] == list(run_all.ORDER)
    assert dict(seen)["reply"] == ["A", "B"] and dict(seen)["intent"] == ["rule", "rule+judge"]  # 스위트마다 기본 시스템
    status = {row["suite"]: row["status"] for row in outcomes}
    assert status == {"label": "완료", "guards": "실패", "reply": "완료", "batch": "완료", "intent": "완료"}
    for row in outcomes:
        if row["out"]:
            body = json.loads((tmp_path / row["out"] / "result.json").read_text(encoding="utf-8"))
            assert body["config"]["baseline"] is True
    assert report.BASELINE is False  # 끝나면 되돌린다
    assert "== 결과 폴더 ==" in capsys.readouterr().out


def test_all_skips_suites_needing_key(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "")
    monkeypatch.setattr(report, "OUT_ROOT", tmp_path)
    outcomes = run_all.run_all(cli.build_parser().parse_args(["all"]), fake_suites(tmp_path))
    status = {row["suite"]: row["status"] for row in outcomes}
    assert status["reply"] == "안 돌림" and status["label"] == "완료"  # label 기본(rule,voice)은 키가 필요 없다


def write_result(root, suite, systems, rows, cases, config=None):
    run = report.start(suite, config=config or {}, systems=systems, root=root, swap_logs=False)
    run.metrics, run.cases = rows, cases
    return run.finish().parent


def test_report_lists_metrics_failures_and_not_run(tmp_path):
    reply = write_result(tmp_path, "reply", ["A", "B"], [
        metrics.metric("reply_fit_rate", "답글 적합률", question=2, system="A", numerator=3, denominator=4),
        metrics.metric("reply_fit_rate", "답글 적합률", question=2, system="B", numerator=1, denominator=4),
        metrics.value_metric("prep_seconds", "답글 준비 시간 중앙값", question=5, system="B", value=None, unit="seconds"),
    ], [
        {"case_id": "c0002", "system": "B", "fit": False, "conditions": {"fact": True, "format": False},
         "format_failures": ["빈칸"], "rejections": ["메뉴 목록에 없는 메뉴", "메뉴 목록에 없는 메뉴"], "error": None},
    ], config={"gold": {"file": "review_gold_v1.xlsx", "sha256": "abcdef1234567890"}, "baseline": True})
    intent = write_result(tmp_path, "intent", ["rule"], [
        metrics.metric("wrong_answer_rate", "잘못 답한 비율", question=4, system="rule", numerator=0, denominator=30,
                       higher_is_better=False),
    ], [{"case_id": "unknown:1", "system": "rule", "correct": False, "expected_intent": "unknown", "intent": "stop"}])
    text = report_md.build(report_md.load([reply, intent]), today=dt.date(2026, 11, 18))
    assert text.index("## 계획 문서와 다른 점") < text.index("## 실행")
    assert "안 돌림: label, guards, batch" in text and "reply B `prep_seconds`" in text
    assert "| 답글 적합률 `reply_fit_rate` | 3/4 (75.0%) | 1/4 (25.0%) |" in text
    assert "(낮을수록 좋음)" in text and "review_gold_v1.xlsx abcdef123456" in text
    assert "reply B: 메뉴 목록에 없는 메뉴 (2)" in text
    assert "reply B `c0002`: 부적합: format (형식: 빈칸)" in text and "정답 unknown → stop" in text
    assert "## 질문 1. 리뷰를 바르게 가르는가\n\n안 돌림" in text
    assert "안 돌림 (guards 의 judge_* 결과 없음)" in text


def test_report_cli_picks_latest_and_writes_out(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "OUT_ROOT", tmp_path / "results")
    write_result(tmp_path / "results", "intent", ["rule"], [], [])
    out = tmp_path / "report.md"
    cli.main(["report", "--out", str(out)])
    assert out.read_text(encoding="utf-8").startswith("# 도나 신뢰성 평가 보고")
    assert set(report_md.latest_folders(tmp_path / "results")) == {"intent"}
    assert report_md.latest_folders(tmp_path / "results", baseline=True) == {}
