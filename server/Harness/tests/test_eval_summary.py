"""summary(Harness/evals/summary.py): 질문 1~5 순서의 마크다운 표 하나 (scorecard 와 같은 계산). CLOVA 없음."""

import json

import pytest

from Harness.evals import cli, metrics, report, scorecard, summary


def metric(id, system, numerator, denominator, **keys):
    return {**metrics.metric(id, id, question=4, system=system, numerator=numerator, denominator=denominator), **keys}


def write(root, name, suite, systems, rows, cases=None, *, started="2026-11-18T10:00:00+09:00", dirty=False, config=None):
    folder = root / name
    folder.mkdir(parents=True)
    body = {"schema": 1, "suite": suite, "started_at": started, "git": {"commit": "abc1234", "branch": "b", "dirty": dirty},
            "config": config or {}, "systems": systems, "metrics": rows, "cases": cases or [], "validation": {}}
    (folder / "result.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return folder


def lines_for(text: str, label: str, system: str) -> list[str]:
    return [line for line in text.splitlines() if f" · {label} | {system} |" in line]


def render(*folders):
    return summary.render(scorecard.scorecard([summary.load(folder) for folder in folders]), report.real_now())


def test_wilson_interval():
    assert metrics.wilson_interval(0, 0) is None
    low, high = metrics.wilson_interval(0, 10)
    assert low == 0.0 and high == pytest.approx(0.2775, abs=1e-4)
    low, high = metrics.wilson_interval(5, 10)
    assert (low, high) == (pytest.approx(0.2366, abs=1e-4), pytest.approx(0.7634, abs=1e-4))
    assert metrics.wilson_interval(10, 10)[1] == 1.0


def test_one_table_in_question_order_with_status_words(tmp_path):
    root = tmp_path / "harness_eval"
    intent = write(root, "intent-20261118-100000", "intent", ["rule"], [
        metric("false_activation_rate", "rule", 3, 39), metric("missed_command_rate_addressed", "rule", 0, 5)])
    guards = write(root, "guards-20261118-110000", "guards", ["critic"],
                   [metric("missed_rate:compensation", "critic", 0, 42, set="all")], dirty=True)
    text = render(intent, guards)
    assert text.count("| 질문 | 세부 지표 |") == 1 and text.startswith("# 평가 지표 요약")
    titles = [title for title in scorecard.QUESTIONS.values() if f"| {title} |" in text]
    assert titles == list(scorecard.QUESTIONS.values())  # 질문 1~5 모두, 이 순서로
    positions = [text.index(f"| {title} |") for title in titles]
    assert positions == sorted(positions)
    (row,) = lines_for(text, "주방 대화 오작동률", "rule")
    assert "| 3/39 | 7.7% | 2.7% ~ 20.3% |" in row and "intent-20261118-100000 | abc1234 |" in row
    (row,) = lines_for(text, "\"도나야\"로 부른 명령 놓침률", "rule")
    assert "| 0/5 | 표본 부족 | - | 0 | - |" in row
    (row,) = lines_for(text, "주방 대화 오작동률", "rule+judge")
    assert f"| - | {summary.NOT_RUN} | - |" in row
    (row,) = lines_for(text, "보상 약속 놓침률", "critic")
    assert "| 0/42 | 0.0% |" in row and "| 0 | 통과 |" in row and "abc1234+수정" in row
    (row,) = lines_for(text, "사람 표본: 그대로 올림 비율", "B")
    assert "사람 표본 없음" in row


def test_latency_rows_say_server_time_and_case_level_note(tmp_path):
    root = tmp_path / "harness_eval"
    turns = [{"case_id": f"turn:{i}", "system": "rule+judge", "run": r, "kind": "briefing", "seconds": 0.05, "error": None}
             for i in range(6) for r in (1, 2)]
    voice = write(root, "voice-20261118-120000", "voice", ["rule+judge"], [], turns)
    text = render(voice)
    (row,) = lines_for(text, "/v1/turn 브리핑 단계", "rule+judge")
    assert "| n=12 | p50 0.05초 · p95 0.05초 |" in row and "서버 처리 시간(네트워크·TTS 제외)" in row and "| 통과 |" in row
    (row,) = lines_for(text, "/v1/turn 5초 초과·오류율", "rule+judge")
    assert "| 0/6 | 표본 부족 |" in row and "회차 합 0/12" in row  # 사례 6개 (회차 2 → 사례별 다수결)


def test_cli_summary_with_results_and_all(tmp_path, monkeypatch):
    root = tmp_path / "harness_eval"
    monkeypatch.setattr(report, "OUT_ROOT", root)
    write(root, "intent-20261118-100000", "intent", ["rule"], [metric("false_activation_rate", "rule", 0, 39)],
          started="2026-11-18T10:00:00+09:00")
    write(root, "intent-20261118-130000", "intent", ["rule"], [metric("false_activation_rate", "rule", 2, 39)],
          started="2026-11-18T13:00:00+09:00")
    out = tmp_path / "docs" / "평가지표-요약.md"
    cli.main(["summary", "--results", "intent-20261118-100000", "--out", str(out)])
    assert "| 0/39 |" in out.read_text(encoding="utf-8")  # 준 폴더만 쓴다
    cli.main(["summary", "--out", str(out)])  # 비우면 모든 결과에서 지표마다 최근
    assert "| 2/39 |" in out.read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main(["summary", "--results", "없는-폴더", "--out", str(out)])
