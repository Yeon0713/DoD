"""label 스위트(Harness/evals/label_eval.py): 분류기 rule·hcx·voice 채점. 3행짜리 가짜 정답지와 가짜 CLOVA 로만 본다.

가짜 정답지 (fake_gold.py)
  c0001 "국수가 맛있어요 010-…"  긍정            balanced   → rule 긍정 (맞음)
  c0002 "면이 불어서 왔어요"      부정 [TASTE, DELIVERY_DELAY] balanced → rule 부정 [DELIVERY_DELAY] (유형 하나 놓침)
  c0003 "양은 적은데 맛은 좋아요" 혼합 [PORTION]  full_only  → rule 긍정 (놓침)
"""

import json

import httpx
import pytest

from app.core.config import settings
from Harness.evals import cli, gold, label_eval, report
from Harness.tests.fake_gold import write_gold

pytest.importorskip("openpyxl")


@pytest.fixture
def fake_gold(tmp_path):
    return write_gold(tmp_path / "gold.xlsx")


@pytest.fixture
def cases(fake_gold):
    return gold.load_gold(*fake_gold)


def by(rows, id, system, set_name):
    return next(row for row in rows if row["id"] == id and row["system"] == system and row["set"] == set_name)


def hcx_answer(content: str) -> httpx.Response:
    return httpx.Response(200, json={"result": {"message": {"content": content}, "usage": {"promptTokens": 50, "completionTokens": 9}}})


class FakeHcx:
    """리뷰 글로 답을 고른다. 글이 ANSWERS 에 없으면 500 (답 없음)."""

    ANSWERS = {
        "면이 불어서 왔어요": '{"sentiment": "NEGATIVE", "complaint_types": ["DELIVERY_DELAY", "TASTE"]}',
        "양은 적은데 맛은 좋아요": '```json\n{"sentiment": "MIXED", "complaint_types": ["PORTION"]}\n```',
    }

    def __init__(self):
        self.sent: list[str] = []

    def __call__(self, url, headers=None, json=None, timeout=None):
        text = json["messages"][1]["content"][0]["text"]
        self.sent.append(text)
        answer = self.ANSWERS.get(text)
        return hcx_answer(answer) if answer else httpx.Response(500, json={})


def test_rule_scores_on_balanced_and_full(cases):
    result = label_eval.evaluate(cases, ["rule"])
    rows = result["metrics"]
    assert by(rows, "negative_recall", "rule", "balanced")["value"] == 1.0
    full_recall = by(rows, "negative_recall", "rule", "full")
    assert (full_recall["numerator"], full_recall["denominator"]) == (1, 2)  # 혼합 c0003 을 놓침
    assert by(rows, "negative_precision", "rule", "full")["value"] == 1.0
    type_f1 = by(rows, "complaint_type_f1", "rule", "full")
    assert type_f1["value"] == pytest.approx(0.5) and "tp 1, fp 0, fn 2" in type_f1["note"] and "초안" in type_f1["note"]
    assert not any(row["id"].startswith("complaint_type_f1:") for row in rows)  # 유형별 정답이 5건 미만
    assert not any(row["id"] == "hcx_failed" for row in rows)
    assert result["confusion"]["full"]["rule"] == {"POSITIVE": {"POSITIVE": 1}, "NEGATIVE": {"NEGATIVE": 1}, "MIXED": {"POSITIVE": 1}}


def test_only_wrong_cases_are_kept_with_reasons_and_sets(cases):
    wrong = {row["case_id"]: row for row in label_eval.evaluate(cases, ["rule"])["cases"]}
    assert set(wrong) == {"c0002", "c0003"}
    assert wrong["c0002"]["wrong"] == ["types"] and wrong["c0002"]["sets"] == ["balanced", "full"]
    assert wrong["c0003"]["wrong"] == ["sentiment", "types", "negative"] and wrong["c0003"]["sets"] == ["full"]
    assert wrong["c0003"]["text"] == "양은 적은데 맛은 좋아요" and wrong["c0003"]["fit"] is False


def test_voice_uses_two_way_sentiment_and_low_rating(cases):
    result = label_eval.evaluate(cases, ["voice"])
    rows = result["metrics"]
    macro = by(rows, "sentiment_macro_f1", "voice", "full")
    assert macro["note"].startswith("2종")
    # c0002 는 별점이 없어(0) 글과 상관없이 negative, 주제 하나(delivery)만 유형으로 센다
    assert result["confusion"]["full"]["voice"]["NEGATIVE"] == {"negative": 1}
    assert result["confusion"]["full"]["voice"]["MIXED"] == {"positive": 1}
    assert "음성은 주제 하나만" in by(rows, "complaint_type_f1", "voice", "full")["note"]
    assert {row["case_id"] for row in result["cases"]} == {"c0002", "c0003"}  # c0002 는 유형만 틀림


def test_hcx_counts_calls_failures_and_masks_phone(cases):
    fake = FakeHcx()
    result = label_eval.evaluate(cases, ["hcx"], post=fake)
    rows = result["metrics"]
    failed = by(rows, "hcx_failed", "hcx", "full")
    assert (failed["numerator"], failed["denominator"]) == (1, 3) and failed["higher_is_better"] is False
    assert by(rows, "negative_recall", "hcx", "full")["value"] == 1.0
    assert by(rows, "complaint_type_f1", "hcx", "full")["value"] == 1.0
    assert by(rows, "negative_precision", "hcx", "balanced")["value"] == 1.0
    (missing,) = result["cases"]  # 틀린 것은 답을 못 받은 c0001 하나
    assert missing["case_id"] == "c0001" and missing["wrong"] == ["failed"] and missing["output"] == "답 없음"
    assert missing["calls"] == 2  # 처음 한 번 + 다시 한 번
    assert result["confusion"]["balanced"]["hcx"]["POSITIVE"] == {"답 없음": 1}
    assert all("010-1234-5678" not in text for text in fake.sent)  # 전화번호는 가리고 보낸다


def test_scope_balanced_skips_full(cases):
    fake = FakeHcx()
    result = label_eval.evaluate(cases, ["hcx"], scope="balanced", post=fake)
    assert {row["set"] for row in result["metrics"]} == {"balanced"}
    assert len(fake.sent) == 1 + 2  # c0002 한 번, c0001 은 두 번 (c0003 은 부르지 않는다)
    assert set(result["sets"]) == {"label_balanced"}


def test_suite_runs_rule_and_voice_without_clova_key(fake_gold, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "")
    monkeypatch.setattr(report, "OUT_ROOT", tmp_path / "harness_eval")
    path, sha = fake_gold
    cli.main(["label", "--gold", str(path), "--gold-sha", sha])
    (out,) = (tmp_path / "harness_eval").glob("label-*/result.json")
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["schema"] == 1 and body["suite"] == "label" and body["systems"] == ["rule", "voice"]
    assert body["config"]["gold_verified"] is False and body["config"]["model"] is None
    assert body["config"]["gold"]["file"] == "gold.xlsx" and set(body["config"]["gold"]["sets"]) == {"label_balanced", "label_full"}
    assert set(body["tables"]["confusion"]) == {"balanced", "full"}
    assert (out.parent / "sets" / "label_full.json").exists()
    assert {row["set"] for row in body["metrics"]} == {"balanced", "full"}


def test_suite_needs_key_only_for_hcx_and_rejects_unknown(fake_gold, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "")
    path, sha = fake_gold
    with pytest.raises(SystemExit, match="CLOVA_STUDIO_API_KEY"):
        cli.main(["label", "--systems", "rule,hcx", "--gold", str(path), "--gold-sha", sha])
    with pytest.raises(SystemExit, match="rule, hcx, voice"):
        cli.main(["label", "--systems", "rule,gpt", "--gold", str(path), "--gold-sha", sha])
    with pytest.raises(SystemExit, match="sha256 이 달라요"):
        cli.main(["label", "--gold", str(path), "--gold-sha", "0" * 64])


def test_hcx_timeout_only_inside_eval(fake_gold, tmp_path, monkeypatch):
    """--hcx-timeout 은 평가 실행 안에서만 hcx_classifier.TIMEOUT_SECONDS 를 바꾸고 끝나면 되돌린다."""
    from app.analysis.review import hcx_classifier

    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    monkeypatch.setattr(report, "OUT_ROOT", tmp_path / "harness_eval")
    seen = []

    def classify(text, post=None):  # 밖으로 부르지 않고, 부른 때의 제한 시간만 본다
        seen.append(hcx_classifier.TIMEOUT_SECONDS)
        return "POSITIVE", []

    monkeypatch.setattr(hcx_classifier, "classify_with_hcx", classify)
    before = hcx_classifier.TIMEOUT_SECONDS
    path, sha = fake_gold
    cli.main(["label", "--systems", "hcx", "--scope", "balanced", "--hcx-timeout", "33", "--gold", str(path), "--gold-sha", sha])
    assert seen and set(seen) == {33} and hcx_classifier.TIMEOUT_SECONDS == before
    (out,) = (tmp_path / "harness_eval").glob("label-*/result.json")
    assert json.loads(out.read_text(encoding="utf-8"))["config"]["hcx_timeout_seconds"] == 33
