"""평가 근거 맞춤·실패 원인·기준선: fail_cause 판정, 최초 유효율·재시도 회복, 기준선 S(reply)·R(batch),
정상 답글 근거 표시(needs_order_info, needs_store_fact). 가짜 CLOVA 로만 본다."""

import json

import httpx
import pytest

from app.core import clova
from app.core.config import settings
from Harness import limiter
from Harness.evals import batch_eval, cli, fail_cause, guards_eval, judge, reply_eval
from Harness.tests.fake_gold import write_gold
from Harness.tests.fakes import FakeClova
from Harness.tests.test_eval_guards import RouterClova
from Harness.tests.test_eval_reply import FIX, NEG_REPLY, ServerClova

pytest.importorskip("openpyxl")

REAL_ASK = clova.ask  # conftest 가 막아 둔 단일 호출을 기준선 S 시험에서만 되살린다 (post 는 늘 가짜)


@pytest.fixture
def gold_rows(tmp_path):
    from Harness.evals import gold

    return gold.load_gold(*write_gold(tmp_path / "gold.xlsx"))


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    judge.reset_model_errors()
    monkeypatch.setattr(limiter, "sleep", lambda seconds: None)
    yield
    judge.reset_model_errors()


def step(kind, name=None, run="r1", detail=None, parent=None):
    return {"run_id": run, "parent_run_id": parent, "kind": kind, "name": name,
            "detail": json.dumps(detail, ensure_ascii=False) if detail is not None else None, "at": "2026-11-18T10:00:00+09:00"}


# ── 실패 원인 판정 ──


@pytest.mark.parametrize("steps, events, expected", [
    ([step("start"), step("llm", "failed"), step("fallback", "ok")], [429, 429], "transport"),
    ([step("start"), step("llm", "failed"), step("fallback", "ok")], ["ReadTimeout"], "transport"),
    ([step("start"), step("llm", "failed"), step("fallback", "ok")], [400], "other"),
    ([step("start"), step("submit", detail={"accepted": False}), step("submit", detail={"accepted": False}),
      step("end", "too_many_rejections")], [], "rejected"),
    ([step("start"), step("end", "time_budget")], [], "budget"),
    ([step("start"), step("end", "call_budget")], [], "budget"),
    ([step("start"), step("llm", "stop"), step("llm", "length")], [], "no_submit"),
    ([], [], "other"),
])
def test_classify_causes(steps, events, expected):
    assert fail_cause.classify("FALLBACK", steps, events, top_run_id="r1")[0] == expected


def test_success_has_no_cause_even_with_transport_events():
    assert fail_cause.classify("AGENT", [step("llm", "failed")], [429]) == ("none", "")
    assert fail_cause.classify_single_call("SINGLE_CALL", []) == ("none", "")


def test_submit_stats_follow_worker_runs_and_recovery():
    steps = [step("start", run="top"), step("submit", run="w1", parent="top", detail={"accepted": False, "reason": "길이"}),
             step("submit", run="w1", parent="top", detail={"accepted": False, "reason": "보상"}),
             step("submit", run="w1", parent="top", detail={"accepted": True})]
    assert fail_cause.submit_stats(steps) == {"submits": 3, "first_ok": False, "rejections": 2, "recovered_at": 2}
    assert fail_cause.attempts_stats([]) == {"submits": 0, "first_ok": None, "rejections": 0, "recovered_at": None}


def test_single_call_causes():
    rejected = [{"answered": True, "accepted": False, "event": None}, {"answered": True, "accepted": False, "event": None}]
    assert fail_cause.classify_single_call("TEMPLATE", rejected)[0] == "rejected"
    down = [{"answered": False, "accepted": None, "event": 503}, {"answered": False, "accepted": None, "event": "ConnectError"}]
    assert fail_cause.classify_single_call("TEMPLATE", down)[0] == "transport"


# ── reply: 기준선 S, 전송 실패, 지표 ──


def test_baseline_s_captures_attempts_without_changing_write_one(gold_rows, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    monkeypatch.setattr(clova, "ask", REAL_ASK)
    too_long = "가" * 400  # rejection_reason: 너무 김
    agent = FakeClova(too_long, NEG_REPLY)
    result = reply_eval.evaluate([gold_rows[1]], ["S"], post=agent, judge_post=RouterClova())
    (row,) = result["cases"]
    assert row["source"] == "SINGLE_CALL" and row["output"] == NEG_REPLY and row["fail_cause"] == "none"
    assert row["submit_stats"] == {"submits": 2, "first_ok": False, "rejections": 1, "recovered_at": 1}
    assert [r["temperature"] for r in agent.requests] == [0.5, 0.3]  # 지금 서비스와 같은 두 번
    m = {x["id"]: x for x in result["metrics"]}
    assert m["agent_fit_rate"]["value"] is None and m["task_completion_rate"]["value"] is None  # S 는 해당 없음
    assert m["source_rate:SINGLE_CALL"]["numerator"] == 1
    assert (m["first_pass_valid_rate"]["numerator"], m["first_pass_valid_rate"]["denominator"]) == (0, 1)
    assert (m["retry_recovery_rate"]["numerator"], m["retry_recovery_rate"]["denominator"]) == (1, 1)
    assert "1번 거절 뒤 1건" in m["retry_recovery_rate"]["note"] and "정규식" in m["first_pass_valid_rate"]["note"]
    assert m["fail_cause_rate:none"]["value"] == 1.0


def test_baseline_s_both_rejected_is_template(gold_rows, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    monkeypatch.setattr(clova, "ask", REAL_ASK)
    result = reply_eval.evaluate([gold_rows[1]], ["S"], post=FakeClova("짧", "짧"), judge_post=RouterClova())
    (row,) = result["cases"]
    assert row["source"] == "TEMPLATE" and row["output"] is None and row["fail_cause"] == "rejected"
    m = {x["id"]: x for x in result["metrics"]}
    assert m["retry_recovery_rate"]["numerator"] == 0 and m["retry_recovery_rate"]["denominator"] == 1


def test_transport_failure_is_its_own_cause_and_no_transport_metric(gold_rows, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    monkeypatch.setattr(limiter, "RATE_LIMIT_RETRIES", 0)

    def busy(url, **kwargs):
        return httpx.Response(429, json={"status": {"code": "42901"}}, request=httpx.Request("POST", url))

    result = reply_eval.evaluate([gold_rows[1]], ["B"], post=busy, judge_post=RouterClova())
    (row,) = result["cases"]
    assert row["source"] != "AGENT" and row["fail_cause"] == "transport" and 429 in row["transport_events"]
    m = {x["id"]: x for x in result["metrics"]}
    assert m["fail_cause_rate:transport"]["numerator"] == 1
    assert m["agent_fit_rate_no_transport"]["denominator"] == 0 and m["agent_fit_rate_no_transport"]["value"] is None
    assert m["agent_fit_rate"]["denominator"] == 1  # 주 지표는 그대로 (분모 요청 전체)
    assert m["first_pass_valid_rate"]["value"] is None  # 제출이 없으면 분모 0 → null


def test_b_first_pass_counts_trace_submits(gold_rows, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    result = reply_eval.evaluate([gold_rows[1]], ["B"], post=ServerClova({"c0002": NEG_REPLY}, found=FIX), judge_post=RouterClova())
    (row,) = result["cases"]
    assert row["source"] == "AGENT" and row["fail_cause"] == "none"
    assert row["submit_stats"]["submits"] >= 1 and row["submit_stats"]["first_ok"] is True
    assert "LLM 검토기" in row["check_kind"]


def test_cli_systems_s_only_on_server_path(tmp_path, monkeypatch):
    assert reply_eval.parse_systems("s,a,b") == ["S", "A", "B"]
    with pytest.raises(Exception):
        reply_eval.parse_systems("C")
    path, sha = write_gold(tmp_path / "gold.xlsx")
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    with pytest.raises(SystemExit, match="서버 경로"):
        cli.main(["reply", "--systems", "S,A", "--path", "voice", "--gold", str(path), "--gold-sha", sha])


# ── batch: 기준선 R ──


def test_batch_rule_baseline_r(gold_rows):
    result = batch_eval.evaluate(["R"], gold_rows=gold_rows, diagnosis_ids=["d1", "d2"], batch_ids=["b_menu"])
    rows = result["cases"]
    assert [(r["case_id"], r["part"]) for r in rows] == [("d1", "diagnosis"), ("d2", "diagnosis")]  # 묶음 조율은 해당 없음
    d1 = rows[0]
    assert d1["source"] == "RULE" and d1["output"] == "최근 7일 동안 맛 불만이 3건 들어왔어요."
    assert d1["cause_found"] is False and d1["grounded"] is None and d1["fail_cause"] is None
    assert rows[1]["cause_found"] is False  # d2 는 확신도 low 를 기대하는데 R 에는 확신도가 없다
    m = {x["id"]: x for x in result["metrics"]}
    assert m["diagnosis_cause_found"]["value"] == 0
    assert m["diagnosis_agent"]["value"] is None and m["diagnosis_grounded"]["value"] is None
    assert m["conflicts_left"]["value"] is None
    assert batch_eval.parse_systems("r,a,b") == ["R", "A", "B"]


# ── guards: 정상 답글의 근거 표시 ──


def test_context_flags_mark_order_info_and_store_fact():
    menus = ["감자전", "초계국수"]
    flags = guards_eval.context_flags("감자전도 맛있게 드셨다니 기뻐요. 저희는 매일 아침 육수를 끓여요.", "국수 맛있어요", menus, [])
    assert flags["needs_order_info"] and flags["order_menus"] == ["감자전"]
    assert flags["needs_store_fact"] and flags["unbacked"] == ["저희는 매일 아침 육수를 끓여요."]
    backed = guards_eval.context_flags("저희는 매일 아침 육수를 끓여요.", "국수 맛있어요", menus, ["매일 아침 육수를 끓여요"])
    assert not backed["needs_store_fact"]  # 확정 사실로 설명됨
    in_review = guards_eval.context_flags("초계국수 칭찬 감사해요.", "초계국수 맛있어요", menus, [])
    assert not in_review["needs_order_info"]  # 리뷰에 나온 메뉴


def test_normal_set_split_only_when_facts_exist(gold_rows):
    plain = guards_eval.gold_cases(gold_rows)
    assert guards_eval.CONTEXT_SET not in plain  # 사실 확정 전: 세트 그대로 (표시만)
    split = guards_eval.gold_cases(gold_rows, facts=["셀프바 순두부는 무료"], menus=["국수"])
    moved = split.get(guards_eval.CONTEXT_SET, [])
    assert len(split["normal"]) + len(moved) == len(plain["normal"])
    assert all(row["set"] == guards_eval.CONTEXT_SET for row in moved)
    row = {"set": guards_eval.CONTEXT_SET}
    assert not guards_eval._in_set(row, "all") and not guards_eval._in_set(row, "gold")  # 주 지표에서 뺀다


def test_case_row_keeps_context_without_changing_set_hash(gold_rows):
    from Harness.evals import derive

    sets = guards_eval.gold_cases(gold_rows)
    before = derive.sha256_of(sets["normal"])
    case = sets["normal"][0]
    row = guards_eval.case_row("regex", 1, case, guards_eval.Judgement(ok=True))
    assert set(row["context"]) == {"needs_order_info", "order_menus", "needs_store_fact", "unbacked"}
    assert derive.sha256_of(sets["normal"]) == before  # 이어 돌리기(--resume)의 세트 해시가 그대로


# ── budget 중 429 대기 ──


def test_budget_with_429_is_subset_and_noted():
    waits = {"count": 2, "seconds": 20.0, "estimated": False}
    assert fail_cause.with_waits("budget", "time_budget", waits) == "time_budget; 429 대기 2번, 20초"
    assert fail_cause.with_waits("transport", "429", waits) == "429"  # budget 이 아니면 그대로
    rows = [{"fail_cause": "budget", "waited_429": waits}, {"fail_cause": "budget", "waited_429": {"count": 0, "seconds": 0}},
            {"fail_cause": "none", "waited_429": waits}]
    m = {x["id"]: x for x in reply_eval.cause_metrics("A", rows)}
    assert m["fail_cause_rate:budget"]["numerator"] == 2 and m["fail_cause_rate:budget_with_429"]["numerator"] == 1
    assert sum(m[f"fail_cause_rate:{c}"]["numerator"] for c in fail_cause.CAUSES) == 3  # 부분 집합은 합계에 없다
    assert "부분 집합" in m["fail_cause_rate:budget_with_429"]["note"]


def test_evaluate_counts_real_429_waits_per_case(gold_rows, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    monkeypatch.setattr(limiter, "RATE_LIMIT_RETRIES", 2)
    inner = ServerClova({"c0002": NEG_REPLY}, found=FIX)
    first = [True]

    def post(url, **kwargs):  # 첫 호출만 429 (Retry-After 3초), 그다음은 정상
        if first[0]:
            first[0] = False
            return httpx.Response(429, headers={"Retry-After": "3"}, json={"status": {"code": "42901"}}, request=httpx.Request("POST", url))
        return inner(url, **kwargs)

    (row,) = reply_eval.evaluate([gold_rows[1]], ["B"], post=post, judge_post=RouterClova())["cases"]
    assert row["waited_429"] == {"count": 1, "seconds": 3.0, "estimated": False} and 429 in row["transport_events"]
    assert row["fail_cause"] == "none" and "429" not in row["fail_detail"]  # 성공 사례에는 붙이지 않는다
    assert limiter.wait_after_429.__name__ == "wait_after_429" and limiter.wait_after_429.__module__ == "Harness.limiter"  # 되돌림


# ── 확정한 가게 사실을 모든 쪽에 ──


def test_confirmed_facts_reach_agent_critic_judge_and_normal_set(gold_rows):
    facts = guards_eval.load_store_facts()
    assert "셀프바 강릉 초당순두부 무료" in facts and "새뱅이 장칼국수" in facts
    sets = guards_eval.gold_cases(gold_rows, facts=facts)
    assert all(row["store_facts"] == facts for row in sets["normal"] + sets["violation"])  # critic·심판 입력
    assert set(guards_eval.gold_store().menus) == set(guards_eval.eval_menu_names())
    menus = {m["name"] for m in reply_eval.eval_menus()}
    assert "새뱅이 장칼국수" in menus  # 장칼국수의 다른 이름
    fixture = reply_eval.load_fixture()
    now = reply_eval.fixture_now(fixture)
    view = reply_eval.make_view(fixture, reply_eval.make_review(gold_rows[1], now, "gold"), now)
    assert view.store["facts"] == facts  # 음성 에이전트
    assert batch_eval.voice_view(gold_rows)[0].store["facts"] == facts


def test_free_items_in_facts_do_not_need_order_info():
    menus = ["초당순두부", "감자전"]
    facts = ["셀프바 강릉 초당순두부 무료"]
    flags = guards_eval.context_flags("초당순두부도 맛있게 드셨다니 기뻐요.", "국수 맛있어요", menus, facts)
    assert not flags["needs_order_info"]  # 무료로 모두에게 주는 것
    flags = guards_eval.context_flags("감자전도 맛있게 드셨다니 기뻐요.", "국수 맛있어요", menus, facts)
    assert flags["order_menus"] == ["감자전"]
