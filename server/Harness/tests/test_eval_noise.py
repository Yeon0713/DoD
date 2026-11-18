"""noise 스위트(Harness/evals/noise_eval.py): 모의 받아쓰기 오류와 강도별 채점. CLOVA 는 가짜로만 본다."""

import json
import random

import pytest

from app.core.config import settings
from Harness.evals import cli, intent_eval, noise_eval, report
from Harness.tests.test_eval_intent import IntentClova


def no_clova(*args, **kwargs):
    raise AssertionError("rule 은 CLOVA 를 부르면 안 돼요")


CTX = {"briefing_step": 1, "donna_was_speaking": False, "last_type": "answer"}


# ── 오류 넣기 ──


def test_levels_are_deterministic_nested_and_never_revisit():
    first = noise_eval.corrupt_levels("오늘 일정 브리핑해 줘", "doc:1")
    assert first == noise_eval.corrupt_levels("오늘 일정 브리핑해 줘", "doc:1")  # 같은 사례·seed 면 늘 같다
    assert first[0] == ("오늘 일정 브리핑해 줘", [])
    texts = [text for text, _ in first]
    assert len(set(texts)) == len(texts) == 4  # 앞 강도로 되돌아가지 않는다
    assert [len(kinds) for _, kinds in first] == [0, 1, 2, 3]
    assert first[2][1][:1] == first[1][1]  # 강도 2 는 강도 1 에 오류 하나를 더한 것
    assert set(kind for _, kinds in first for kind in kinds) <= set(noise_eval.KINDS)


def test_each_kind_changes_text_the_expected_way():
    rng = random.Random(0)
    assert noise_eval._sound("브리핑", rng) in noise_eval.SOUND_ALIKE["브리핑"]
    assert noise_eval._sound("도나야", rng) in ("돈아야", "또나야", "토나야")  # 호출어 변형
    assert noise_eval._sound("면 삶아", rng) is None
    assert noise_eval._ending("보여 줘요", rng) == "보여 줘"
    assert noise_eval._ending("응", rng) is None  # 한 글자 낱말은 그대로
    spaced = noise_eval._spacing("다시 말해", rng)
    assert spaced.replace(" ", "") == "다시말해" and spaced != "다시 말해"
    changed = noise_eval._jamo("브리핑", rng)
    assert len(changed) == 3 and changed != "브리핑"
    assert noise_eval._jamo("123", rng) is None


def test_jamo_choices_stay_close():
    choices = noise_eval._jamo_choices("반")  # ㅂ+ㅏ+ㄴ
    assert {"빤", "판", "바", "방"} <= set(choices)
    assert all("가" <= ch <= "힣" for ch in choices)


def test_noisy_cases_keep_ids_and_clean_text():
    cases = [{"id": "a", "text": "다음으로 넘어가 줘", "addressed": False, "context": CTX, "expected_intent": "briefing.next"}]
    (noisy,) = noise_eval.noisy_cases(cases, 2)
    assert noisy["id"] == "a" and noisy["clean_text"] == "다음으로 넘어가 줘" and noisy["noise"] == 2
    assert noisy["text"] != noisy["clean_text"] and len(noisy["noise_kinds"]) == 2
    assert noise_eval.noisy_cases(cases, 0)[0]["text"] == "다음으로 넘어가 줘"


def test_parse_levels():
    assert noise_eval.parse_levels("3,0,1") == [0, 1, 3]
    for bad in ("", "4", "a"):
        with pytest.raises(SystemExit):
            noise_eval.parse_levels(bad)


# ── 채점 ──


def test_level_zero_matches_intent_suite_and_rows_are_tagged():
    _, cases = intent_eval.load_cases()
    result = noise_eval.evaluate(cases, ["rule"], [0, 3], post=no_clova)
    assert len(result["cases"]) == 2 * len(cases) and result["calls"] == 0
    clean = {m["id"]: m["numerator"] for m in intent_eval.evaluate(cases, ["rule"], post=no_clova)["metrics"]}
    level0 = {m["id"]: m["numerator"] for m in result["metrics"] if m["noise"] == 0}
    assert level0 == clean
    level3 = {m["id"]: m for m in result["metrics"] if m["noise"] == 3}
    assert "강도 3" in level3["intent_accuracy"]["name"]
    assert level3["intent_accuracy"]["numerator"] < level0["intent_accuracy"]  # 오류가 많으면 덜 맞힌다
    assert all(row["noise"] in (0, 3) and "clean_text" in row for row in result["cases"])


def test_judge_called_only_for_unmatched_noisy_text(monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    cases = [{"id": "a", "text": "다음", "addressed": False, "context": CTX, "expected_intent": "briefing.next"},
             {"id": "b", "text": "면 삶아", "addressed": False, "context": CTX, "expected_intent": "not_for_donna"}]
    post = IntentClova({})
    result = noise_eval.evaluate(cases, ["rule+judge"], [0, 1], post=post)
    plan = noise_eval.planned_calls(cases, ["rule+judge"], [0, 1], 1)
    assert result["calls"] == len(post.requests) == sum(p["rule+judge"]["typical"] for p in plan.values())


def test_cli_noise_rule_runs_without_key_and_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "")
    monkeypatch.setattr(report, "OUT_ROOT", tmp_path / "harness_eval")
    monkeypatch.setattr(intent_eval.httpx, "post", no_clova)
    cli.main(["noise", "--dry-run"])  # rule+judge 가 기본이어도 dry-run 은 키 없이 된다
    assert not (tmp_path / "harness_eval").exists()
    cli.main(["noise", "--systems", "rule", "--levels", "0,2"])
    (out,) = (tmp_path / "harness_eval").glob("noise-*/result.json")
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["suite"] == "noise" and body["config"]["levels"] == [0, 2]
    assert "모의" in body["config"]["label"] and {m["noise"] for m in body["metrics"]} == {0, 2}
    with pytest.raises(SystemExit):
        cli.main(["noise", "--systems", "rule+judge"])  # 실제로 돌릴 때는 키가 필요하다
