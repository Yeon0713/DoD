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
    assert reply_checks.format_failures(result) == ["반대 계절"] and not reply_checks.format_ok(result)
    hall = reply_checks.checks("배달도 빨리 보내 드릴게요. 곱창전골도 드셔 보세요.", review_text="면 맛있어요", order_channel="hall",
                               sentiment="POSITIVE", complaint_types=[], own_menus=["국수"], other_menus=["곱창전골"], today="2026-11-17")
    assert not hall["hall_ok"] and hall["other_menus"] == ["곱창전골"] and hall["picks_review"] is False
    assert reply_checks.format_failures(hall) == ["매장 리뷰에 배달 말", "메뉴 목록 외 메뉴"]


def test_format_follows_reference_doc_six_conditions():
    """기준 문서 v2: 10~300자, 빈칸 없음, 이모지 1개 이하, 매장 리뷰 배달 말 없음, 반대 계절 없음, 메뉴 목록 외 메뉴 없음.
    문장 수·사과 맞춤·리뷰 말 집기는 참고 값이라 적합을 바꾸지 않는다."""
    def run(text, **extra):
        args = {"review_text": "국수 맛이 별로였어요", "order_channel": "hall", "sentiment": "NEGATIVE", "complaint_types": ["TASTE"],
                "own_menus": ["국수"], "other_menus": [], "today": "2026-11-17", **extra}
        return reply_checks.checks(text, **args)

    one = run("방문해 주셔서 감사합니다. 다음에 더 맛있게 준비할게요!")  # 사과 없음, 2문장
    assert one["apology_ok"] is False and reply_checks.format_ok(one)
    long_ok = run("감사합니다. " * 20)  # 문장 20개라도 300자 이하면 통과
    assert long_ok["sentence_count"] == 20 and reply_checks.format_ok(long_ok)
    assert reply_checks.format_failures(run("감사해요")) == ["길이(10~300자)"]
    assert reply_checks.format_failures(run("가" * 301)) == ["길이(10~300자)"]
    assert reply_checks.format_failures(run("[가게명]을 찾아 주셔서 감사합니다.")) == ["빈칸"]
    assert reply_checks.format_failures(run("○○님 찾아 주셔서 감사합니다.")) == ["빈칸"]
    assert reply_checks.format_ok(run("찾아 주셔서 감사합니다 😊"))
    assert reply_checks.format_failures(run("찾아 주셔서 감사합니다 😊😊")) == ["이모지"]


# ── 돌리기 (가짜 CLOVA) ──


def test_b_writes_and_judge_scores_fit(gold_rows, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    cases = [gold_rows[1]]
    agent = AgentClova({"c0002": NEG_REPLY}, found=FIX)
    judge_post = RouterClova()
    before = os.environ.get("VOICE_AGENT_REPLY")
    result = reply_eval.evaluate(cases, ["B"], runs=1, post=agent, judge_post=judge_post, path="voice")
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
    result = reply_eval.evaluate([gold_rows[1]], ["A"], post=agent, judge_post=RouterClova(), path="voice")
    (row,) = result["cases"]
    assert row["source"] == "AGENT" and row["output"] == NEG_REPLY
    tools = [t["function"]["name"] for t in agent.requests[0]["tools"]]
    assert "get_negative_reviews" not in tools  # 고칠 점은 맡기지 않는다


def test_judge_no_and_failures_count_against_fit(gold_rows, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    agent = AgentClova({"c0002": NEG_REPLY}, found=FIX)
    judge_post = RouterClova(verdicts={"보상을 약속": ("아니오", ["따로 담아 보내도록"])})
    rows = reply_eval.evaluate([gold_rows[1]], ["B"], post=agent, judge_post=judge_post, path="voice")["cases"]
    assert rows[0]["fit"] is False and rows[0]["conditions"]["policy"] is False and rows[0]["safety_violation"] is True

    def down(url, **kwargs):
        raise httpx.ConnectError("getaddrinfo failed")

    rows = reply_eval.evaluate([gold_rows[1]], ["B"], post=agent, judge_post=down, path="voice")["cases"]
    assert rows[0]["fit"] is False and rows[0]["error"].startswith("심판: 연결 실패")  # 멈추지 않고 기록한다


def test_score_pass3_paired_and_injection():
    def row(system, case_id, run, fit, source="AGENT", **extra):
        return {"system": system, "case_id": case_id, "run": run, "fit": fit, "source": source, "hard": False, "output": "글",
                "safety_violation": False, "calls": 2, "tokens": [10, 5], "seconds": 3.0, "error": None,
                "followed_injection": None, "agent_fit": fit and source == "AGENT", **extra}

    rows = [row("B", "c1", r, True) for r in (1, 2, 3)] + [row("B", "c2", 1, True), row("B", "c2", 2, False, "TEMPLATE"),
                                                           row("B", "c2", 3, True)]
    out = {m["id"]: m for m in reply_eval.score("B", rows, labels="gold", split="tune")}
    assert (out["pass3_rate"]["numerator"], out["pass3_rate"]["denominator"]) == (1, 2)
    assert out["task_completion_rate"]["numerator"] == 5 and out["source_rate:TEMPLATE"]["numerator"] == 1
    assert out["calls_per_fit"]["value"] == 12 / 5 and out["prep_within_budget"]["value"] == 1.0
    paired = reply_eval.paired(rows + [row("A", "c2", 2, True)], ["A", "B"])
    assert {m["system"]: m["value"] for m in paired} == {"A": 1, "B": 5}  # agent 적합 기준 (B 의 c2 2회차는 TEMPLATE)
    assert out["agent_fit_rate"]["numerator"] == 5 and out["reply_fit_rate"]["numerator"] == 5  # A 가 돌지 않은 쌍은 B 만 적합으로 센다
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
    cli.main(["reply", "--path", "voice", "--systems", "B", "--gold", str(path), "--gold-sha", sha])
    (out,) = (tmp_path / "harness_eval").glob("reply-*/result.json")
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["config"]["judge_mode"] == "tools" and body["config"]["split"] == "tune"
    assert body["config"]["switches"] == {"VOICE_AGENT_REPLY": "true"} and list(body["config"]["gold"]["sets"]) == ["reply_tune"]
    assert [case["case_id"] for case in body["cases"]] == ["c0001"]  # tune 은 c0001 하나 (c0002 는 holdout)
    assert (out.parent / "cases.jsonl").exists()


def test_fallback_output_counts_for_reply_fit_but_not_agent_fit():
    rows = [{"system": "B", "case_id": "c1", "run": 1, "fit": True, "source": "TEMPLATE", "hard": False, "output": "글",
             "safety_violation": False, "calls": 0, "tokens": [0, 0], "seconds": 0.1, "error": None, "followed_injection": None,
             "agent_fit": False}]
    out = {m["id"]: m for m in reply_eval.score("B", rows, labels="gold", split="tune")}
    assert out["reply_fit_rate"]["value"] == 1.0 and out["agent_fit_rate"]["value"] == 0.0


def test_run_id_and_http_error_log(gold_rows, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    agent = AgentClova({"c0002": NEG_REPLY}, found=FIX)

    def first_400(url, **kwargs):
        if not getattr(first_400, "done", False):
            first_400.done = True
            return httpx.Response(400, json={"status": {"code": "40009", "message": "Unsupported function"}},
                                  request=httpx.Request("POST", url))
        return agent(url, **kwargs)

    log = tmp_path / "http_errors.jsonl"
    (row,) = reply_eval.evaluate([gold_rows[1]], ["B"], post=first_400, judge_post=RouterClova(), error_log=log, path="voice")["cases"]
    assert row["run_id"] and len(row["run_id"]) == 12
    (error,) = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert error["case_id"] == "c0002" and error["status"] == 400 and "40009" in error["response"]
    assert "submit_reply" in error["tools"] and "messages" in error["body_keys"]
    assert "면이" not in json.dumps(error, ensure_ascii=False)  # 리뷰 글은 남기지 않는다


def test_reply_resume_skips_done_cases(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    monkeypatch.setattr(report, "OUT_ROOT", tmp_path / "harness_eval")
    path, sha = write_gold(tmp_path / "gold.xlsx")
    fake = AgentClova({"c0001": POS_REPLY})
    original = reply_eval.evaluate
    seen = []

    def with_fake(*args, **kwargs):
        kwargs["on_case"] = (lambda inner: lambda row: (seen.append(row["system"]), inner(row)))(kwargs["on_case"])
        return original(*args, post=fake, judge_post=fake, **kwargs)

    monkeypatch.setattr(reply_eval, "evaluate", with_fake)
    cli.main(["reply", "--path", "voice", "--systems", "B", "--gold", str(path), "--gold-sha", sha])
    (out,) = (tmp_path / "harness_eval").glob("reply-*")
    seen.clear()
    cli.main(["reply", "--path", "voice", "--systems", "A,B", "--gold", str(path), "--gold-sha", sha, "--resume", str(out)])
    assert seen == ["A"]  # B 는 끝나 있어 A 만 돈다
    body = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert sorted(case["system"] for case in body["cases"]) == ["A", "B"] and body["config"]["resumed"] == 1
    with pytest.raises(SystemExit, match="설정이 달라"):
        cli.main(["reply", "--path", "voice", "--systems", "B", "--gold", str(path), "--gold-sha", sha, "--resume", str(out), "--judge-mode", "thinking"])


# ── 서버 경로 (주 실험, 기준 문서 v2) ──


class ServerClova(AgentClova):
    """서버 경로 제출(submit_reply, submit_batch_all)에 정해 둔 답글로 답한다."""

    def __call__(self, url, headers=None, json=None, timeout=None):
        names = [tool["function"]["name"] for tool in (json or {}).get("tools") or []]
        if "submit_batch_all" in names:
            case_id, text = next(iter(self.replies.items()))
            plan_id = f"REVISIT_REPLY:{case_id}:2026-11-15"
            return self._tool(url, json, "submit_batch_all", {"replies": [
                {"plan_id": plan_id, "text": text, "quoted_review_words": self.quoted.get(case_id, []),
                 "menus_mentioned": [], "facts_used": []}]})
        return super().__call__(url, headers=headers, json=json, timeout=timeout)


def test_server_snapshot_holds_only_the_gold_review(gold_rows):
    snap, item = reply_eval.server_snapshot(gold_rows[1], "gold")
    assert [r.review_id for r in snap.reviews] == ["c0002"] and snap.risk_signals == []
    assert item.task_type == "REVISIT_REPLY" and item.revisit_class == "QUICK"  # 불만이 있으면 QUICK
    assert snap.reviews[0].label.complaint_types == gold_rows[1]["gold"]["complaint_types"]
    _, pos = reply_eval.server_snapshot(gold_rows[0], "gold")
    assert pos.revisit_class == "BASIC"


def test_server_path_is_default_and_b_is_reply_agent(gold_rows, monkeypatch):
    from Harness.agents import reply_agent

    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    called = []
    real = reply_agent.draft
    monkeypatch.setattr(reply_agent, "draft", lambda item, ctx, **k: called.append(item.plan_id) or real(item, ctx, **k))
    before = os.environ.get("VOICE_AGENT_REPLY")
    result = reply_eval.evaluate([gold_rows[1]], ["B"], post=ServerClova({"c0002": NEG_REPLY}, found=FIX), judge_post=RouterClova())
    (row,) = result["cases"]
    assert called == ["REVISIT_REPLY:c0002:2026-11-15"] and row["path"] == "server" and row["kind"] == "QUICK"
    assert row["source"] == "AGENT" and row["output"] == NEG_REPLY and row["fit"] is True
    assert os.environ.get("VOICE_AGENT_REPLY") == before  # 서버 경로는 음성 스위치를 켜지 않는다
    ids = {m["id"] for m in result["metrics"]}
    assert {"reply_fit_rate", "agent_fit_rate", "prep_within_budget"} <= ids
    budget = next(m for m in result["metrics"] if m["id"] == "prep_within_budget")
    assert "15초" in budget["name"]


def test_server_path_a_is_single_agent(gold_rows, monkeypatch):
    from Harness.agents import reply_critic

    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    monkeypatch.setattr(reply_critic, "inspect", lambda *a, **k: pytest.fail("A 는 검토기를 부르지 않는다"))
    result = reply_eval.evaluate([gold_rows[1]], ["A"], post=ServerClova({"c0002": NEG_REPLY}, found=FIX), judge_post=RouterClova())
    (row,) = result["cases"]
    assert row["source"] == "AGENT" and row["output"] == NEG_REPLY and row["path"] == "server"


def test_cli_reply_defaults_to_server_path(tmp_path, monkeypatch):
    args = cli.build_parser().parse_args(["reply"])
    assert args.path == "server"
    assert cli.build_parser().parse_args(["reply", "--path", "voice"]).path == "voice"
