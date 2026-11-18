"""tts 스위트(Harness/evals/tts_eval.py): 첫 소리·전체 합성 시간. 가짜 합성기·가짜 시계로만 본다 (모델을 올리지 않는다)."""

import json

import pytest

from Harness.evals import cli, report, tts_eval


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def fake_synth(clock: Clock, first: float = 0.4, rest: float = 0.6, chunks: int = 3, fail: str | None = None):
    calls = []

    def synth(text):
        calls.append(text)
        if text == fail:
            raise RuntimeError("합성 실패")
        for k in range(chunks):
            clock.now += first if k == 0 else rest / (chunks - 1)
            yield b"audio"

    synth.calls = calls
    return synth


def test_measure_first_and_total_with_warm_up(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(tts_eval, "timer", clock)
    synth = fake_synth(clock)
    rows = tts_eval.measure(synth, ["가", "나"], runs=2)
    assert synth.calls[0] == "가" and len(synth.calls) == 5  # 데우기 1번 + 2문장 × 2회
    assert [(r["case_id"], r["run"]) for r in rows] == [("tts:1", 1), ("tts:2", 1), ("tts:1", 2), ("tts:2", 2)]
    assert all(r["first_seconds"] == pytest.approx(0.4) and r["total_seconds"] == pytest.approx(1.0) for r in rows)
    m = {x["id"]: x for x in tts_eval.score(rows)}
    assert m["tts_first_p50"]["value"] == pytest.approx(0.4) and m["tts_total_p95"]["value"] == pytest.approx(1.0)
    assert (m["tts_error_rate"]["numerator"], m["tts_error_rate"]["denominator"]) == (0, 4)


def test_failed_sentence_is_counted_and_others_continue(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(tts_eval, "timer", clock)
    rows = tts_eval.measure(fake_synth(clock, fail="나"), ["가", "나", "다"], warm_up=False)
    bad = rows[1]
    assert bad["error"].startswith("RuntimeError") and bad["first_seconds"] is None and bad["total_seconds"] is None
    assert rows[2]["total_seconds"] == pytest.approx(1.0)
    m = {x["id"]: x for x in tts_eval.score(rows)}
    assert m["tts_error_rate"]["numerator"] == 1


def test_sentences_are_twenty_short_lines():
    assert len(tts_eval.SENTENCES) == 20 == len(set(tts_eval.SENTENCES))


def test_not_run_when_tts_unavailable_writes_nothing(tmp_path, monkeypatch, capsys):
    from voice import tts

    monkeypatch.setattr(report, "OUT_ROOT", tmp_path / "harness_eval")
    monkeypatch.setattr(tts, "ENABLED", False)
    cli.main(["tts"])
    assert "안 돌림" in capsys.readouterr().out and not (tmp_path / "harness_eval").exists()
    monkeypatch.setattr(tts, "ENABLED", True)
    monkeypatch.setattr(tts, "available", lambda: False)
    assert tts_eval.unavailable_reason()


def test_run_with_given_synth_writes_result(tmp_path, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(tts_eval, "timer", clock)
    monkeypatch.setattr(report, "OUT_ROOT", tmp_path / "harness_eval")
    args = cli.build_parser().parse_args(["tts"])
    path = tts_eval.run(args, synth=fake_synth(clock))
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["suite"] == "tts" and len(body["cases"]) == 20 and body["systems"] == ["tts"]
    assert body["config"]["cache"].startswith("쓰지 않음")
