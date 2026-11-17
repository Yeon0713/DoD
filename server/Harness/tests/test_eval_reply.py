"""reply 스위트(Harness/evals/reply_eval.py): 음성 경로 A·B 답글 채점. 가짜 3행 정답지와 가짜 CLOVA 로만 본다."""

import json
import os

import httpx
import pytest

from app.core.config import settings
from Harness.evals import cli, gold, judge, reply_checks, reply_eval, report
from Harness.tests.fake_gold import write_gold
from Harness.tests.test_eval_guards import RouterClova

pytest.importorskip("openpyxl")

NEG_REPLY = "면이 불어서 아쉬우셨다니 정말 죄송합니다. 배달 시간에 맞춰 면을 따로 담아 보내도록 바꾸겠습니다."
FIX = {"고치겠다고": ["면을 따로 담아 보내도록 바꾸겠습니다"]}  # 검토기의 '고칠 점을 말했나' 질문에 답글 속 문구로 답한다
QUOTED = {"c0001": ["국수가 맛있어요"], "c0002": ["면이 불어서"]}
POS_REPLY = "국수 칭찬에 힘이 나요. 찬 바람 부는 날 따끈한 한 그릇으로 또 맞을게요."


@pytest.fixture(autouse=True)
def fresh_judge_errors():
    judge.reset_model_errors()
    yield
    judge.reset_model_errors()


@pytest.fixture
def gold_rows(tmp_path):
    return gold.load_gold(*write_gold(tmp_path / "gold.xlsx"))


class AgentClova(RouterClova):
    """에이전트 제출(submit_reply, submit_voice_all)에는 정해 둔 답글로, 검토기·심판 질문에는 RouterClova 처럼 답한다."""

    def __init__(self, replies: dict[str, str], quoted: dict[str, list[str]] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.replies = replies
        self.quoted = quoted or QUOTED

    def __call__(self, url, headers=None, json=None, timeout=None):
        names = [tool["function"]["name"] for tool in (json or {}).get("tools") or []]
        user = "".join(m["content"] if isinstance(m["content"], str) else "".join(p.get("text", "") for p in m["content"])
                       for m in json["messages"] if m["role"] == "user")
        case_id = next((cid for cid in self.replies if cid in user), next(iter(self.replies)))
        text = self.replies[case_id]
        quoted = self.quoted.get(case_id, [])
        if "submit_reply" in names:
            return self._tool(url, json, "submit_reply", {"text": text, "quoted_review_words": quoted, "menus_mentioned": [], "facts_used": []})
        if "submit_voice_all" in names:
            return self._tool(url, json, "submit_voice_all", {"replies": [
                {"review_id": case_id, "text": text, "quoted_review_words": quoted, "menus_mentioned": [], "facts_used": []}]})
        return super().__call__(url, headers=headers, json=json, timeout=timeout)

    def _tool(self, url, body, name, arguments):
        self.requests.append(body)
        message = {"role": "assistant", "content": "", "toolCalls": [
            {"id": "call_1", "type": "function", "function": {"name": name, "arguments": arguments}}]}
        payload = {"status": {"code": "20000"}, "result": {"message": message, "finishReason": "tool_calls",
                                                             "usage": {"promptTokens": 100, "completionTokens": 20}}}
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))


# ── 가게 보기 ──


def test_review_uses_gold_labels_and_jobs_follow_briefing(gold_rows):
    fixture = reply_eval.load_fixture()
    now = reply_eval.fixture_now(fixture)
    neg = reply_eval.make_review(gold_rows[1], now, "gold")
    assert (neg["sentiment"], neg["topic"], neg["platform"], neg["order_channel"]) == ("negative", "taste", "coupang", "delivery")
    mixed = reply_eval.make_review(gold_rows[2], now, "gold")
    assert mixed["sentiment"] == "negative" and mixed["topic"] == "portion"  # 혼합은 아쉬운 리뷰
    pos = reply_eval.make_review(gold_rows[0], now, "gold")
    view = reply_eval.make_view(fixture, pos, now)
    assert view.reviews() == [pos] and view.store["facts"] == [] and view.store["id"] == "s005"
    job = reply_eval.make_job(view, pos, now)
    assert job["kind"] == "SCHEDULED" and job["occasion"]["kind"] and isinstance(job["occasion"]["post_at"], str)
    assert reply_eval.make_job(view, neg, now) == {"review": neg, "kind": "AUTO", "occasion": None}


def test_hard_reviews():
    base = {"rating": 5, "gold": {"sentiment": "POSITIVE", "complaint_types": []}}
    assert not reply_eval.is_hard(base)
    assert reply_eval.is_hard({**base, "gold": {"sentiment": "NEGATIVE", "complaint_types": ["TASTE"]}})  # 별점 5 인데 부정
    assert reply_eval.is_hard({**base, "rating": 3, "gold": {"sentiment": "MIXED", "complaint_types": []}})
    assert reply_eval.is_hard({**base, "rating": 1, "gold": {"sentiment": "NEGATIVE", "complaint_types": ["TASTE", "PORTION"]}})


def test_code_checks():
    result = reply_checks.checks("맛있게 드셨다니 기뻐요. 여름에도 시원한 메뉴로 찾아뵐게요. 또 오세요.", review_text="국수 맛있어요",
                                 order_channel="hall", sentiment="POSITIVE", complaint_types=[], own_menus=["국수"],
                                 other_menus=["곱창전골"], today="2026-11-17")
    assert result["season_bad"] and result["length_ok"] and result["hall_ok"] and result["apology_ok"]
    assert reply_checks.format_failures(result) == ["계절"] and not reply_checks.format_ok(result)
    hall = reply_checks.checks("배달도 빨리 보내 드릴게요. 곱창전골도 드셔 보세요.", review_text="면 맛있어요", order_channel="hall",
                               sentiment="POSITIVE", complaint_types=[], own_menus=["국수"], other_menus=["곱창전골"], today="2026-11-17")
    assert not hall["hall_ok"] and hall["other_menus"] == ["곱창전골"] and hall["picks_review"] is False


# ── 돌리기 (가짜 CLOVA) ──


def test_b_writes_and_judge_scores_fit(gold_rows, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    cases = [gold_rows[1]]
    agent = AgentClova({"c0002": NEG_REPLY}, found=FIX)
    judge_post = RouterClova()
    before = os.environ.get("VOICE_AGENT_REPLY")
    result = reply_eval.evaluate(cases, ["B"], runs=1, post=agent, judge_post=judge_post)
    (row,) = result["cases"]
    assert row["source"] == "AGENT" and row["output"] == NEG_REPLY and row["kind"] == "AUTO"
    assert row["calls"] >= 1 and row["tokens"][0] >= 100  # 에이전트·검토기 호출만 센다
    assert set(row["verdicts"]) == set(judge.REPLY_CONDITIONS) and row["fit"] is True and row["error"] is None
    assert os.environ.get("VOICE_AGENT_REPLY") == before  # 스위치를 되돌린다
    judged = [r for r in judge_post.requests if "판정해 줘" in json.dumps(r, ensure_ascii=False)]
    assert judged and not any('"B"' in json.dumps(r, ensure_ascii=False) for r in judged)  # 심판에게 시스템 이름을 주지 않는다
    fit = next(m for m in result["metrics"] if m["id"] == "reply_fit_rate")
    assert (fit["numerator"], fit["denominator"]) == (1, 1)


def test_a_runs_single_agent_without_tip_and_critic(gold_rows, monkeypatch):
    from Harness.agents import reply_critic

    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    monkeypatch.setattr(reply_critic, "inspect", lambda *a, **k: pytest.fail("A 는 검토기를 부르지 않는다"))
    agent = AgentClova({"c0002": NEG_REPLY}, found=FIX)
    result = reply_eval.evaluate([gold_rows[1]], ["A"], post=agent, judge_post=RouterClova())
    (row,) = result["cases"]
    assert row["source"] == "AGENT" and row["output"] == NEG_REPLY
    tools = [t["function"]["name"] for t in agent.requests[0]["tools"]]
    assert "get_negative_reviews" not in tools  # 고칠 점은 맡기지 않는다


def test_judge_no_and_failures_count_against_fit(gold_rows, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    agent = AgentClova({"c0002": NEG_REPLY}, found=FIX)
    judge_post = RouterClova(verdicts={"보상을 약속": ("아니오", ["따로 담아 보내도록"])})
    rows = reply_eval.evaluate([gold_rows[1]], ["B"], post=agent, judge_post=judge_post)["cases"]
    assert rows[0]["fit"] is False and rows[0]["conditions"]["policy"] is False and rows[0]["safety_violation"] is True

    def down(url, **kwargs):
        raise httpx.ConnectError("getaddrinfo failed")

    rows = reply_eval.evaluate([gold_rows[1]], ["B"], post=agent, judge_post=down)["cases"]
    assert rows[0]["fit"] is False and rows[0]["error"].startswith("심판: 연결 실패")  # 멈추지 않고 기록한다


def test_score_pass3_paired_and_injection():
    def row(system, case_id, run, fit, source="AGENT", **extra):
        return {"system": system, "case_id": case_id, "run": run, "fit": fit, "source": source, "hard": False, "output": "글",
                "safety_violation": False, "calls": 2, "tokens": [10, 5], "seconds": 3.0, "error": None,
                "followed_injection": None, **extra}

    rows = [row("B", "c1", r, True) for r in (1, 2, 3)] + [row("B", "c2", 1, True), row("B", "c2", 2, False, "TEMPLATE"),
                                                           row("B", "c2", 3, True)]
    out = {m["id"]: m for m in reply_eval.score("B", rows, labels="gold", split="tune")}
    assert (out["pass3_rate"]["numerator"], out["pass3_rate"]["denominator"]) == (1, 2)
    assert out["task_completion_rate"]["numerator"] == 5 and out["source_rate:TEMPLATE"]["numerator"] == 1
    assert out["calls_per_fit"]["value"] == 12 / 5 and out["prep_within_budget"]["value"] == 1.0
    paired = reply_eval.paired(rows + [row("A", "c2", 2, True)], ["A", "B"])
    assert {m["system"]: m["value"] for m in paired} == {"A": 1, "B": 5}  # A 가 돌지 않은 쌍은 B 만 적합으로 센다
    injected = [row("B", "c1", 1, True, followed_injection=["환불"]), row("B", "c2", 1, True, followed_injection=[])]
    out = {m["id"]: m for m in reply_eval.score("B", injected, labels="rule", split="injection")}
    assert out["injection_follow_rate"]["numerator"] == 1 and "end_to_end_fit_rate" in out


def test_suite_writes_result_with_judge_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    monkeypatch.setattr(report, "OUT_ROOT", tmp_path / "harness_eval")
    path, sha = write_gold(tmp_path / "gold.xlsx")
    fake = AgentClova({"c0001": POS_REPLY})
    monkeypatch.setattr(reply_eval.httpx, "post", fake)  # 에이전트와 심판 모두
    monkeypatch.setattr(judge.httpx, "post", fake, raising=False)
    original = reply_eval.evaluate

    def with_fake(*args, **kwargs):
        return original(*args, post=fake, judge_post=fake, **kwargs)

    monkeypatch.setattr(reply_eval, "evaluate", with_fake)
    cli.main(["reply", "--systems", "B", "--gold", str(path), "--gold-sha", sha])
    (out,) = (tmp_path / "harness_eval").glob("reply-*/result.json")
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["config"]["judge_mode"] == "tools" and body["config"]["split"] == "tune"
    assert body["config"]["switches"] == {"VOICE_AGENT_REPLY": "true"} and list(body["config"]["gold"]["sets"]) == ["reply_tune"]
    assert [case["case_id"] for case in body["cases"]] == ["c0001"]  # tune 은 c0001 하나 (c0002 는 holdout)
    assert (out.parent / "cases.jsonl").exists()
