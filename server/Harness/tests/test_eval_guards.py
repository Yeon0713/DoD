"""guards 스위트(Harness/evals/guards_eval.py): 판정기 regex·critic·judge_tools·judge_thinking 채점.
가짜 3행 정답지와, 질문 글로 답을 고르는 가짜 CLOVA 로만 본다 (실제 CLOVA 를 부르지 않는다)."""

import json

import httpx
import pytest

from app.core.config import settings
from Harness.evals import cli, gold, guards_eval, judge, report
from Harness.tests.fake_gold import write_gold

pytest.importorskip("openpyxl")

GOOD = "국물이 싱거우셨다니 죄송합니다. 간을 매일 다시 확인하겠습니다."
PROMISE = "다음 주문 땐 면 한 그릇 더 넣어 드릴게요."
BAD = f"국물이 싱거우셨다니 죄송합니다. {PROMISE}"


@pytest.fixture(autouse=True)
def fresh_judge_errors():
    judge.reset_model_errors()
    yield
    judge.reset_model_errors()


@pytest.fixture
def fake_gold(tmp_path):
    return write_gold(tmp_path / "gold.xlsx")


@pytest.fixture
def gold_rows(fake_gold):
    return gold.load_gold(*fake_gold)


class RouterClova:
    """요청의 마지막 사용자 메시지(질문)로 답을 고른다. 부르는 차례와 상관없어 사례를 함께 돌려도 된다.

    found: 좁은 질문(quote_judge) 이름 일부 → 답글에서 옮길 문구 (없으면 해당 없음)
    judge: 심판 조건 질문 일부 → ("예"|"아니오"|"판단 불가", 문구들)
    tools 가 없는 요청(thinking 방식)에는 JSON 글로 답한다.
    """

    def __init__(self, found: dict[str, list[str]] | None = None, verdicts: dict[str, tuple[str, list[str]]] | None = None,
                 fail: bool = False):
        self.found = found or {}
        self.verdicts = verdicts or {}
        self.fail = fail
        self.requests: list[dict] = []

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.requests.append(json)
        request = httpx.Request("POST", url)
        if self.fail:
            return httpx.Response(500, json={"status": {"code": "500"}}, request=request)
        question = json["messages"][-1]["content"]
        question = question if isinstance(question, str) else "".join(part.get("text", "") for part in question)
        if "판정해 줘" in question:  # 평가용 심판
            ok, quotes = next((v for key, v in self.verdicts.items() if key in question), ("예", []))
            arguments = {"ok": ok, "quotes": quotes, "reason": "가짜 판정"}
        else:  # reply_critic 의 좁은 질문
            quotes = next((v for key, v in self.found.items() if key in question), [])
            arguments = {"found": bool(quotes), "quotes": quotes}
        if json.get("tools"):
            message = {"role": "assistant", "content": "", "toolCalls": [
                {"id": "call_1", "type": "function", "function": {"name": "submit_judgement", "arguments": arguments}}]}
            finish = "tool_calls"
        else:
            message, finish = {"role": "assistant", "content": f"생각 끝.\n{json_dumps(arguments)}"}, "stop"
        body = {"status": {"code": "20000"}, "result": {"message": message, "finishReason": finish,
                                                          "usage": {"promptTokens": 10, "completionTokens": 5, "totalTokens": 15}}}
        return httpx.Response(200, json=body, request=request)


def json_dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def case(reply: str = GOOD, *, expected_ok: bool = True, kinds: list[str] | None = None, set_name: str = "critic_cases",
         **extra) -> dict:
    base = {"case_id": "x1", "set": set_name, "kind": (kinds or ["normal"])[0], "kinds": kinds or [],
            "expected_ok": expected_ok, "verified": True, "store": "t001", "text": "국물이 너무 싱거웠어요", "reply": reply,
            "has_complaint": True, "regular": False, "owner_instruction": None, "store_facts": [], "sentiment": "부정",
            "complaint_types": ["맛"]}
    return {**base, **extra}


STORE = guards_eval.Store("t001", {"name": "테스트국수", "category": "국수"}, ("잔치국수", "만두"))


# ── 세트 ──


def test_critic_cases_keep_41_cases_with_mapped_kinds():
    rows = guards_eval.critic_cases()
    assert len(rows) == 41 and sum(row["expected_ok"] for row in rows) == 19
    kinds = {kind for row in rows for kind in row["kinds"]}
    assert kinds <= set(guards_eval.KIND_ORDER) and "compensation" in kinds
    with_instruction = [row for row in rows if row["owner_instruction"]]
    assert with_instruction and all(row["store"] == "t001" for row in rows)


def test_gold_cases_use_s005_korean_labels_and_pair_up(gold_rows):
    sets = guards_eval.gold_cases(gold_rows)
    normal, violation = sets["normal"], sets["violation"]
    assert [row["case_id"] for row in normal] == ["c0001-ok", "c0003-ok"]
    assert {row["source_case_id"] for row in violation} == {"c0001", "c0003"}
    mixed = next(row for row in normal if row["source_case_id"] == "c0003")
    assert mixed["store"] == "s005" and mixed["sentiment"] == "혼합" and mixed["complaint_types"] == ["양"]
    assert mixed["has_complaint"] and mixed["verified"] is False and mixed["store_facts"] == []
    assert all(row["expected_ok"] is False and row["kinds"] == [row["kind"]] for row in violation)
    store = guards_eval.gold_store()
    assert store.store_id == "s005" and store.menus
    judged = guards_eval.judge_input(mixed, store)
    assert judged.gold_reply is None and judged.category == store.store["category"]  # 참고 답변은 주지 않는다


# ── 판정기 ──


def test_regex_catches_listed_phrases_and_misses_indirect_ones():
    caught = guards_eval.judge_regex(case(BAD, expected_ok=False, kinds=["compensation"]), STORE)
    assert caught.ok is False and caught.detected == ["compensation"] and caught.calls == 0
    indirect = guards_eval.judge_regex(case("죄송합니다. 배달 기사님이 늦게 오신 거라 저희 잘못은 아니에요. 또 들러 주세요."), STORE)
    assert indirect.ok is True  # 남 탓은 정규식이 없다
    short = guards_eval.judge_regex(case("네"), STORE)
    assert short.ok is False and short.detected == ["format"]


def test_critic_rejects_compensation_and_counts_calls():
    fake = RouterClova(found={"보상 제안": [PROMISE]})
    result = guards_eval.judge_critic(case(BAD, expected_ok=False, kinds=["compensation"]), STORE, fake)
    assert result.ok is False and result.detected == ["compensation"] and result.calls == 1
    assert "보상 약속" in result.why[0]


def test_critic_passes_good_reply_after_all_questions():
    fake = RouterClova(found={"고치겠다고": ["간을 매일 다시 확인하겠습니다."]})
    result = guards_eval.judge_critic(case(GOOD), STORE, fake)
    assert result.ok is True and result.detected == []
    assert result.calls == 6  # 보상, 고칠 점, 가게 사정, 변명, 아는 척, 상관없는 말


def test_critic_unknown_when_last_question_fails():
    result = guards_eval.judge_critic(case(GOOD), STORE, RouterClova(fail=True))
    assert result.ok is None and result.error


@pytest.mark.parametrize("name", ["judge_tools", "judge_thinking"])
def test_judge_rejects_by_condition_and_maps_kinds(name):
    fake = RouterClova(verdicts={"보상을 약속": ("아니오", [PROMISE])})
    result = guards_eval.RUNNERS[name](case(BAD, expected_ok=False, kinds=["compensation"]), STORE, fake)
    assert result.ok is False and result.detected == ["compensation", "memory"]  # policy 조건 = 보상·아는 척
    assert result.calls == len(judge.REPLY_CONDITIONS) * judge.VOTES
    assert result.verdicts["policy"]["vote"] == [False, False, False] and result.verdicts["fact"]["ok"] is True
    request = fake.requests[0]
    assert ("tools" in request) == (name == "judge_tools")
    assert "[참고 답변]" not in request["messages"][-1]["content"]


def test_judge_unknown_without_any_no():
    fake = RouterClova(verdicts={"지어내지": ("판단 불가", [])})
    result = guards_eval.RUNNERS["judge_tools"](case(GOOD), STORE, fake)
    assert result.ok is None and result.detected == []


def test_judge_model_error_stops_but_other_errors_become_unknown(monkeypatch):
    def broken(case, store, post=None):
        raise RuntimeError("뜻밖의 오류")

    monkeypatch.setitem(guards_eval.RUNNERS, "critic", broken)
    result = guards_eval.timed("critic", case(GOOD), STORE)
    assert result.ok is None and "RuntimeError" in result.error

    def model_error(case, store, post=None):
        raise judge.JudgeModelError("400")

    monkeypatch.setitem(guards_eval.RUNNERS, "critic", model_error)
    with pytest.raises(judge.JudgeModelError):
        guards_eval.timed("critic", case(GOOD), STORE)


# ── 채점 ──


def test_outcomes_and_right_reason():
    assert guards_eval.outcome(True, True) == "pass" and guards_eval.outcome(True, False) == "false_reject"
    assert guards_eval.outcome(False, False) == "caught" and guards_eval.outcome(False, True) == "missed"
    assert guards_eval.outcome(False, None) == "unknown"
    swap = case(expected_ok=False, kinds=["swap"])
    assert guards_eval.right_reason(swap, ["off_topic"]) is True  # 다른 리뷰의 답변을 상관없는 말로 잡아도 맞다
    assert guards_eval.right_reason(swap, ["compensation"]) is False
    assert guards_eval.right_reason(case(), ["compensation"]) is None


def test_score_by_kind_flaky_and_targets(monkeypatch):
    cases = [
        case(GOOD, set_name="critic_cases"),
        {**case(BAD, expected_ok=False, kinds=["compensation"]), "case_id": "x2"},
        {**case(GOOD, set_name="normal", verified=False), "case_id": "x3", "store": "t001"},
        {**case("다른 가게 답", expected_ok=False, kinds=["swap"], set_name="violation"), "case_id": "x4"},
    ]
    answers = {  # 회차별 (ok, detected)
        ("x1", 1): (True, []), ("x1", 2): (False, ["fabricated"]),
        ("x2", 1): (False, ["compensation"]), ("x2", 2): (False, ["compensation"]),
        ("x3", 1): (False, ["fabricated"]), ("x3", 2): (False, ["fabricated"]),
        ("x4", 1): (True, []), ("x4", 2): (None, []),
    }
    turn = {}

    def fake_runner(c, store, post=None):
        turn[c["case_id"]] = turn.get(c["case_id"], 0) + 1
        ok, detected = answers[(c["case_id"], turn[c["case_id"]])]
        return guards_eval.Judgement(ok=ok, detected=detected, calls=2)

    monkeypatch.setitem(guards_eval.RUNNERS, "critic", fake_runner)
    result = guards_eval.evaluate(cases, {"t001": STORE}, ["critic"], runs=2)
    rows = {(r["id"], r["set"]): r for r in result["metrics"]}
    assert (rows[("missed_rate", "all")]["numerator"], rows[("missed_rate", "all")]["denominator"]) == (1, 4)
    assert (rows[("false_reject_rate", "all")]["numerator"], rows[("false_reject_rate", "all")]["denominator"]) == (3, 4)
    assert rows[("false_reject_rate", "gold")]["note"] == "정상 답글은 사람 확인 전(unverified)"
    assert (rows[("unknown_rate", "all")]["numerator"], rows[("unknown_rate", "all")]["denominator"]) == (1, 8)
    assert rows[("right_reason_rate", "all")]["value"] == 1.0
    assert rows[("missed_rate:swap", "all")]["value"] == 0.5 and "판단 불가 1" in rows[("missed_rate:swap", "all")]["note"]
    assert rows[("calls_per_case", "all")]["value"] == 2
    assert result["flaky"]["critic"] == ["x1", "x4"]
    assert result["by_kind"]["critic"]["normal"] == {"total": 4, "pass": 1, "false_reject": 3}
    assert result["critic_target"]["critic_cases"] == {"missed": 0, "false_reject_rate": 0.5, "pass": False}


def test_recommend_prefers_fewer_misses_then_fewer_false_rejects_then_speed():
    def s(missed, false_reject, unknown=0, latency=1.0):
        return {"missed": missed, "false_reject": false_reject, "unknown": unknown, "latency_median": latency}

    assert guards_eval.recommend_judge_mode({"tools": s(2, 0), "thinking": s(1, 5)})["mode"] == "thinking"
    assert guards_eval.recommend_judge_mode({"tools": s(1, 3), "thinking": s(1, 2)})["mode"] == "thinking"
    tie = guards_eval.recommend_judge_mode({"tools": s(1, 2, latency=3.7), "thinking": s(1, 2, latency=11.7)})
    assert tie["mode"] == "tools" and "빠른" in tie["basis"]
    assert guards_eval.recommend_judge_mode({}) is None


def test_planned_calls():
    cases = [case(GOOD), case(BAD, expected_ok=False, kinds=["compensation"]), case(GOOD, has_complaint=False)]
    plan = guards_eval.planned_calls(cases, ["regex", "critic", "judge_tools"], runs=3)
    assert plan["regex"]["typical"] == 0
    assert plan["critic"]["typical"] == (6 + 1 + 5) * 3  # 보상에서 걸리면 한 번에 멈춘다
    assert plan["judge_tools"]["typical"] == 3 * 12 * 3 and plan["judge_tools"]["max"] == 3 * 24 * 3
    per_system = guards_eval.planned_calls(cases, ["critic", "judge_tools"], runs={"critic": 3, "judge_tools": 1})
    assert per_system["critic"]["runs"] == 3 and per_system["judge_tools"] == {"runs": 1, "typical": 36, "max": 72}


def test_system_runs_override_only_named_judges():
    names = ["critic", "judge_tools", "judge_thinking"]
    assert guards_eval.parse_system_runs("judge_tools=1,judge_thinking=1", names, 3) == {
        "critic": 3, "judge_tools": 1, "judge_thinking": 1}
    assert guards_eval.parse_system_runs("", names, 2) == {name: 2 for name in names}
    for bad in ("regex=1", "judge_tools=0", "judge_tools=x"):
        with pytest.raises(guards_eval.JudgeUnavailable):
            guards_eval.parse_system_runs(bad, names, 3)


def test_vote_split_counts_cases_with_divided_votes():
    rows = [{"case_id": "a", "verdicts": {"fact": {"vote": [True, True, False]}, "core": {"vote": [True] * 3}}},
            {"case_id": "b", "verdicts": {"fact": {"vote": [True] * 3}}},
            {"case_id": "c", "verdicts": {}}]
    assert guards_eval.vote_split(rows) == ["a"]


def test_judge_rows_report_vote_splits(monkeypatch):
    fake = RouterClova(verdicts={"지어내지": ("아니오", [])})
    flip = iter(["아니오", "예", "아니오"])  # fact 조건 3표가 2:1 로 갈린다

    def post(url, headers=None, json=None, timeout=None):
        question = json["messages"][-1]["content"]
        if "지어내지" in question:
            fake.verdicts = {"지어내지": (next(flip), [])}
        return fake(url, headers=headers, json=json, timeout=timeout)

    result = guards_eval.evaluate([case(GOOD)], {"t001": STORE}, ["judge_tools"], post=post)
    split = next(row for row in result["metrics"] if row["id"] == "vote_split_cases")
    assert split["value"] == 1 and split["note"] == "x1"
    assert result["judge"]["tools"]["vote_split"] == 1 and result["cases"][0]["got_ok"] is False


# ── 입구 ──


def test_dry_run_needs_no_key_and_writes_nothing(fake_gold, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(settings, "clova_studio_api_key", "")
    monkeypatch.setattr(report, "OUT_ROOT", tmp_path / "harness_eval")
    path, sha = fake_gold
    cli.main(["guards", "--systems", "regex,critic,judge_tools,judge_thinking", "--runs", "3", "--dry-run",
              "--gold", str(path), "--gold-sha", sha])
    out = capsys.readouterr().out
    assert "사례 45건" in out and "judge_thinking" in out
    assert not (tmp_path / "harness_eval").exists()


def test_regex_suite_writes_result_without_key(fake_gold, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "")
    monkeypatch.setattr(report, "OUT_ROOT", tmp_path / "harness_eval")
    path, sha = fake_gold
    cli.main(["guards", "--runs", "2", "--gold", str(path), "--gold-sha", sha])
    (out,) = (tmp_path / "harness_eval").glob("guards-*/result.json")
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["suite"] == "guards" and body["systems"] == ["regex"]
    assert body["config"]["sets"] == {"critic_cases": 41, "normal": 2, "violation": 2}
    assert body["config"]["judge_gold_reply"] is False and body["config"]["normal_verified"] is False
    assert set(body["config"]["gold"]["sets"]) >= {"critic_cases", "normal", "violation"}  # 가게 사실이 있으면 normal_needs_context 도
    assert body["config"]["store_facts_verified"] is True and body["config"]["normal_set_version"] == "v2"
    assert len(body["cases"]) == 45 * 2 and body["tables"]["flaky"]["regex"] == []  # 정규식은 흔들리지 않는다
    assert (out.parent / "sets" / "guards_violation.json").exists()


def test_suite_needs_key_for_clova_judges_and_rejects_unknown(fake_gold, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "")
    path, sha = fake_gold
    with pytest.raises(SystemExit, match="CLOVA_STUDIO_API_KEY"):
        cli.main(["guards", "--systems", "regex,critic", "--gold", str(path), "--gold-sha", sha])
    with pytest.raises(SystemExit, match="regex, critic, judge_tools, judge_thinking"):
        cli.main(["guards", "--systems", "regex,gpt", "--gold", str(path), "--gold-sha", sha])
