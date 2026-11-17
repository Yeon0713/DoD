"""batch 스위트(Harness/evals/batch_eval.py): 진단 d1~d4 와 묶음 조율. 가짜 CLOVA 와 가짜 3행 정답지로만 본다."""

import json
import re

import httpx
import pytest

from app.core.config import settings
from Harness.evals import batch_eval, cli, gold, judge, report, scenarios
from Harness.tests.fake_gold import write_gold
from Harness.tests.test_eval_guards import RouterClova

pytest.importorskip("openpyxl")

HYPOTHESIS = "저녁 주문이 몰릴 때 근무가 혼자라 조리가 밀려요"
CHECKLIST = ["저녁 근무 인원 확인", "국물 간 확인", "조리 순서 점검"]
TIP = "금요일 저녁엔 국물 간을 한 번 더 보세요"
AGENT_SUBMITS = {"submit_diagnosis", "submit_tip", "submit_voice_all", "submit_batch", "submit_batch_all"}
FIRST_TOOLS = ("get_risk_reviews", "get_review_counts")  # 제출 전에 한 번 부를 도구 (근거)


@pytest.fixture(autouse=True)
def fresh_judge_errors():
    judge.reset_model_errors()
    yield
    judge.reset_model_errors()


def diagnosis(confidence="high", text=HYPOTHESIS):
    return {"hypotheses": [{"text": text, "evidence": ["get_risk_reviews"]}], "checklist": list(CHECKLIST), "confidence": confidence}


class ScriptClova(RouterClova):
    """에이전트 요청은 도구를 보고 답한다: 근거 도구를 아직 안 불렀으면 부르고, 불렀으면 제출. 심판·검토기 질문은 RouterClova."""

    def __init__(self, confidence="high", **kwargs):
        super().__init__(**kwargs)
        self.confidence = confidence

    def __call__(self, url, headers=None, json=None, timeout=None):
        names = [tool["function"]["name"] for tool in (json or {}).get("tools") or []]
        submit = next((n for n in names if n in AGENT_SUBMITS), None)
        if submit is None:
            return super().__call__(url, headers=headers, json=json, timeout=timeout)
        self.requests.append(json)
        called = any(m["role"] == "tool" for m in json["messages"])
        first = next((n for n in FIRST_TOOLS if n in names), None)
        if first and not called:
            return self._tool(url, first, {})
        return self._tool(url, submit, self._submit(submit, json))

    def _submit(self, name: str, body: dict) -> dict:
        if name == "submit_diagnosis":
            return diagnosis(self.confidence)
        if name == "submit_tip":
            return {"tip": TIP, "evidence": ["get_review_counts"]}
        if name == "submit_voice_all":
            return {"replies": [], "tip": {"tip": TIP, "evidence": ["get_review_counts"]}}
        if name == "submit_batch":  # 묶음 안 할 일마다 메모 하나 (경고 메모만 붙이고 다시 쓰게 하지 않는다)
            user = "".join(m["content"] if isinstance(m["content"], str) else "" for m in body["messages"] if m["role"] == "user")
            plan_ids = dict.fromkeys(re.findall(r"(?:REVISIT_REPLY|REORDER_NUDGE|REVIEW_FIX|POSTER):\w+:\d{4}-\d{2}-\d{2}", user))
            return {"headline": "맛 불만 정리가 먼저예요", "accepted": [],
                    "item_notes": [{"plan_id": pid, "note": "함께 보고 확인해 주세요"} for pid in plan_ids]}
        if name == "submit_batch_all":
            user = "".join(m["content"] if isinstance(m["content"], str) else "" for m in body["messages"] if m["role"] == "user")
            replies = []
            if "REVISIT_REPLY:r1" in user:
                replies.append({"plan_id": "REVISIT_REPLY:r1:2026-11-15", "text": "국물이 싱거우셨다니 죄송합니다. 저녁 근무를 늘려 간을 다시 보겠습니다.",
                                "quoted_review_words": ["국물이 너무 싱거웠어요"], "menus_mentioned": [], "facts_used": []})
            if "REVISIT_REPLY:r4" in user:
                replies.append({"plan_id": "REVISIT_REPLY:r4:2026-11-15", "text": "비빔국수 양념을 좋게 봐 주셔서 감사해요. 또 들러 주세요.",
                                "quoted_review_words": ["비빔국수 양념이 새콤달콤 맛있어요"], "menus_mentioned": ["비빔국수"], "facts_used": []})
            args = {"replies": replies}
            if "REVIEW_FIX" in user:
                args["diagnosis"] = diagnosis(self.confidence)
            return args
        raise AssertionError(name)

    def _tool(self, url, name, arguments):
        message = {"role": "assistant", "content": "", "toolCalls": [
            {"id": f"call_{len(self.requests)}", "type": "function", "function": {"name": name, "arguments": arguments}}]}
        payload = {"status": {"code": "20000"}, "result": {"message": message, "finishReason": "tool_calls",
                                                             "usage": {"promptTokens": 50, "completionTokens": 10}}}
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))


@pytest.fixture
def clova(monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")


# ── 사례 가게 ──


def test_scenarios_plant_causes():
    d1, d2, d3 = (scenarios.snapshot(c) for c in ("d1", "d2", "d3"))
    hours = lambda snap: sorted(o.ordered_at.hour for o in snap.inputs.orders if o.order_id.startswith("ocomp"))
    assert hours(d1) == [19, 19, 19] and hours(d2) == [12, 15, 20] and hours(d3) == [19, 19, 19]
    assert d3.risk_signals[0].complaint_type == "DELIVERY_DELAY" and all(w.rain_mm > 0 for w in d3.inputs.weather[1:])
    assert {r.review_id: r.label.complaint_types for r in d3.reviews if r.review_id in ("r1", "r2", "r3")} == {
        "r1": ["DELIVERY_DELAY"], "r2": ["DELIVERY_DELAY"], "r3": ["DELIVERY_DELAY"]}
    assert len(scenarios.fixed_proposals()) == 5  # fakes.make_snapshot 은 그대로 (d1 은 바뀌지 않음)


def test_cause_found():
    assert batch_eval.cause_found(HYPOTHESIS, scenarios.EXPECT["d1"], "high")
    assert not batch_eval.cause_found("국물 간이 흔들렸어요", scenarios.EXPECT["d1"], "high")
    assert batch_eval.cause_found("", scenarios.EXPECT["d2"], "low") and not batch_eval.cause_found("x", scenarios.EXPECT["d2"], "high")


# ── 진단 ──


@pytest.mark.parametrize("system", ["A", "B"])
def test_diagnosis_rows(system, clova):
    result = batch_eval.evaluate([system], post=ScriptClova(), diagnosis_ids=("d1", "d2"), batch_ids=())
    d1, d2 = result["cases"]
    assert d1["source"] == "AGENT" and d1["cause_found"] is True and d1["grounded"] is True and d1["run_id"]
    assert d1["checklist"] == CHECKLIST and d1["calls"] == 2
    assert d2["cause_found"] is False  # 공통점이 없는데 high 로 단정했다
    low = batch_eval.evaluate([system], post=ScriptClova("low"), diagnosis_ids=("d2",), batch_ids=())["cases"][0]
    assert low["cause_found"] is True


def test_d4_voice_tip_from_gold(clova, tmp_path):
    rows = gold.load_gold(*write_gold(tmp_path / "gold.xlsx"))
    reviews, topic = scenarios.voice_reviews(rows, batch_eval.voice_view(rows)[1])
    assert topic == "taste" and [r["id"] for r in reviews] == ["c0002"] and "19:30" in reviews[0]["written_at"]
    for system in ("A", "B"):
        (row,) = batch_eval.evaluate([system], post=ScriptClova(), gold_rows=rows, diagnosis_ids=("d4",), batch_ids=())["cases"]
        assert row["output"] == TIP and row["source"] == "AGENT" and row["cause_found"] is True, system


# ── 묶음 조율 ──


def test_b_batch_conflicts_left_and_no_extra_calls(clova):
    judge_post = RouterClova(verdicts={"어긋나지": ("아니오", ["간을 다시 보겠습니다"])})
    rows = batch_eval.evaluate(["B"], post=ScriptClova(), judge_post=judge_post, diagnosis_ids=(),
                               batch_ids=("b_mismatch", "b_same", "b_clean1"))["cases"]
    mismatch, same, clean = rows
    assert mismatch["source"] == "AGENT" and mismatch["left"] == ["REPLY_VS_DIAGNOSIS"]
    assert mismatch["consistency"]["REVISIT_REPLY:r1:2026-11-15"]["ok"] is False
    assert mismatch["rework"] == {"per_item": {}, "total": 0, "ok": True}
    assert set(mismatch["fit_before"]) == {"REVISIT_REPLY:r1:2026-11-15"}  # 조율 전 고정 초안도 채점
    assert same["left"] == ["SAME_CUSTOMER_TWICE"]  # 규칙은 두 할 일이 함께 있으면 남은 것으로 본다
    assert clean["source"] == "NONE" and clean["calls"] == 0 and clean["left"] == []
    metrics = {m["id"]: m for m in batch_eval.score("B", rows)}
    assert metrics["conflicts_left"]["note"] == "심은 충돌 2개 중 2개 남음"
    assert metrics["no_conflict_calls"]["note"] == "B 1건 중 1건"


def test_a_batch_writes_whole_batch_and_skips_poster(clova):
    rows = batch_eval.evaluate(["A"], post=ScriptClova(), judge_post=RouterClova(), diagnosis_ids=(),
                               batch_ids=("b_menu", "b_mismatch"))["cases"]
    (mismatch,) = rows  # b_menu(포스터)는 A 가 맡지 않아 뺀다
    assert mismatch["source"] == "AGENT" and mismatch["left"] == [] and mismatch["fit_before"] == {}
    assert mismatch["output"]["REVISIT_REPLY:r1:2026-11-15"]["text"].startswith("국물이 싱거우셨다니")
    assert mismatch["rework"] is None


def test_suite_writes_counts(tmp_path, monkeypatch, clova):
    monkeypatch.setattr(report, "OUT_ROOT", tmp_path / "harness_eval")
    path, sha = write_gold(tmp_path / "gold.xlsx")
    fake = ScriptClova()
    original = batch_eval.evaluate
    monkeypatch.setattr(batch_eval, "evaluate", lambda *a, **k: original(*a, post=fake, judge_post=fake, **k))
    cli.main(["batch", "--systems", "A,B", "--gold", str(path), "--gold-sha", sha])
    (out,) = (tmp_path / "harness_eval").glob("batch-*/result.json")
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["config"]["judge_mode"] == "tools" and body["systems"] == ["A", "B"]
    found = {(m["id"], m["system"]): m for m in body["metrics"]}
    assert found[("diagnosis_cause_found", "B")]["note"].startswith("B 4건 중")
    assert ("no_conflict_calls", "A") not in found and found[("no_conflict_calls", "B")]["value"] == 2
    assert len(body["cases"]) == 4 * 2 + 5 + 4  # 진단 4 × 2, 묶음 B 5 + A 4
