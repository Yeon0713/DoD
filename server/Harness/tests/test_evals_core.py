"""평가 공통 틀(Harness/evals): 결과 폴더와 result.json, 지표 계산, CLOVA X 심판. 실제 CLOVA 는 부르지 않는다."""

import json
import sqlite3

import pytest

from app.core import clova_usage_log
from Harness import cache, clova_tools, trace
from Harness.evals import cli, judge, metrics, report, systems
from Harness.tests.fakes import FakeClova, call


@pytest.fixture(autouse=True)
def fresh_judge_errors():
    judge.reset_model_errors()
    yield
    judge.reset_model_errors()


class UrlFake(FakeClova):
    """FakeClova 에 부른 주소도 남긴다 (모델 이름이 주소에 들어간다)."""

    def __init__(self, *turns):
        super().__init__(*turns)
        self.urls: list[str] = []

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.urls.append(url)
        return super().__call__(url, headers=headers, json=json, timeout=timeout)


def submit(ok: str, quotes: list[str] | None = None, reason: str = "까닭") -> list:
    return [call(judge.SUBMIT_NAME, {"ok": ok, "quotes": quotes or [], "reason": reason})]


REPLY = "국물이 싱거우셨다니 죄송합니다. 저희는 매일 아침 육수를 직접 끓여요. 다음엔 간을 더 맞추겠습니다."


def judge_input(**extra) -> judge.JudgeInput:
    base = {"review_text": "국물이 싱거웠어요 010-1234-5678", "reply": REPLY, "category": "국수", "sentiment": "부정",
            "complaint_types": ["맛"], "menus": ["잔치국수", "만두"], "gold_reply": "싱거우셨다니 죄송해요. 간을 다시 볼게요."}
    return judge.JudgeInput(**{**base, **extra})


# ── 결과 폴더와 result.json ──


def test_start_makes_suite_folder_and_swaps_logs(tmp_path):
    run = report.start("reply", config={"model": "HCX-005"}, systems=["A", "B"], root=tmp_path)
    assert run.out.parent == tmp_path and run.out.name.startswith("reply-")
    assert clova_usage_log.LOG_PATH == run.out / "clova_usage.db"
    assert trace.TRACE_PATH == run.out / "harness_trace.db"
    again = report.start("reply", root=tmp_path)  # 같은 초에 또 만들어도 덮어쓰지 않는다
    assert again.out != run.out and again.out.exists()


def test_result_json_has_common_shape_and_null_for_zero_denominator(tmp_path):
    run = report.start("reply", config={"model": "HCX-005", "judge_mode": "tools"}, systems=["B"], root=tmp_path)
    run.add_metric(metrics.metric("reply_fit_rate", "답글 적합률", question=2, system="B", numerator=3, denominator=4))
    run.add_metric(metrics.metric("injection_follow_rate", "리뷰 속 지시 따름률", question=4, system="B", numerator=0,
                                  denominator=0, higher_is_better=False))
    run.add_case({"case_id": "c1", "system": "B", "run": 1, "output": "전문", "fit": True})
    run.validation = {"judge": {"missed": 0, "bad_total": 0}}
    body = json.loads(run.finish().read_text(encoding="utf-8"))

    assert set(body) == {"schema", "suite", "started_at", "finished_at", "git", "config", "systems", "metrics", "cases", "validation"}
    assert body["schema"] == 1 and body["suite"] == "reply" and body["systems"] == ["B"]
    assert set(body["git"]) == {"commit", "branch", "dirty"}
    assert body["config"]["judge_mode"] == "tools"
    fit, follow = body["metrics"]
    assert fit["value"] == 0.75 and fit["unit"] == "ratio" and fit["higher_is_better"] is True
    assert set(fit) == {"id", "question", "name", "system", "value", "numerator", "denominator", "unit", "higher_is_better", "note"}
    assert follow["value"] is None and follow["note"]  # 분모 0 이면 null 과 까닭
    assert body["cases"][0]["output"] == "전문"


def test_hashes_and_cache_switch(tmp_path):
    prompt = tmp_path / "p.txt"
    prompt.write_text("가", encoding="utf-8")
    assert report.prompt_hashes([prompt]) == {"p.txt": report.sha256_of("가")}
    assert report.sha256_of([{"b": 1, "a": 2}]) == report.sha256_of([{"a": 2, "b": 1}])  # 키 순서와 상관없다

    cache.put(("x", "s", "d", "p"), "기억")
    restore = report.disable_cache()
    cache.put(("x", "s", "d", "p"), "기억")
    assert cache.get(("x", "s", "d", "p")) is None  # 측정 중에는 매번 새로 부른다
    restore()
    assert cache.get(("x", "s", "d", "p")) == "기억"


def test_counting_post_counts_calls_and_tokens():
    fake = FakeClova("가", "나")
    post = report.CountingPost(fake)
    for _ in range(2):
        clova_tools.chat_with_tools([{"role": "user", "content": "u"}], [], feature="t", store_id=None, post=post)
    assert post.calls == 2 and post.tokens == [200, 40]


def test_rejections_read_from_trace():
    trace.record(run_id="r1", parent_run_id=None, agent="a", store_id="t001", step=1, kind="submit", name="submit_reply",
                 detail={"accepted": False, "reason": "보상 약속"})
    trace.record(run_id="w1", parent_run_id="r1", agent="b", store_id="t001", step=1, kind="submit", name="submit_reply",
                 detail='{"accepted": false, "reason": "잘린 이유…')
    trace.record(run_id="r1", parent_run_id=None, agent="a", store_id="t001", step=2, kind="submit", name="submit_reply",
                 detail={"accepted": True})
    assert report.rejections("r1") == ["보상 약속", "잘린 이유…"]


# ── 지표 ──


def test_ratio_and_rates():
    assert metrics.ratio(1, 4) == 0.25 and metrics.ratio(0, 0) is None
    row = metrics.value_metric("seconds_median", "중앙값", question=5, system="A", value=None, unit="seconds")
    assert row["value"] is None and row["numerator"] is None and row["note"]


def test_precision_recall_f1_counts_failures_as_misses():
    gold = ["부정", "부정", "긍정", "긍정"]
    predicted = ["부정", None, "부정", "긍정"]  # None = 분류하지 못함 → 정답이 부정이면 놓친 것
    result = metrics.precision_recall_f1(gold, predicted, "부정")
    assert (result["tp"], result["fp"], result["fn"]) == (1, 1, 1)
    assert result["precision"] == 0.5 and result["recall"] == 0.5 and result["f1"] == 0.5
    assert metrics.precision_recall_f1(["긍정"], ["긍정"], "부정")["f1"] is None  # 정답에도 예측에도 없으면 None


def test_macro_f1_skips_labels_absent_everywhere():
    gold = ["긍정", "긍정", "부정"]
    predicted = ["긍정", "부정", "부정"]
    result = metrics.macro_f1(gold, predicted, ["긍정", "부정", "혼합"])
    assert result["per_label"]["혼합"] is None
    assert result["value"] == pytest.approx((2 / 3 + 2 / 3) / 2)


def test_all_pass_needs_every_run_to_pass():
    results = {"c1": [True, True, True], "c2": [True, None, True], "c3": [True, True], "c4": [False, True, True]}
    assert metrics.all_pass(results, k=3) == (1, 4)
    assert metrics.all_pass({}, k=3) == (0, 0)


def test_latency_counts_timeouts_in_denominator():
    result = metrics.latency([2.0, 4.0, None, 9.0], budget=5)
    assert result["median"] == 4.0 and result["max"] == 9.0
    assert result["within_budget"] == 2 and result["within_budget_rate"] == 0.5
    assert metrics.per_fit(10, 0) is None and metrics.per_fit(10, 4) == 2.5


# ── 심판 ──


def test_majority_of_three_votes():
    assert judge.majority([True, True, False]) is True
    assert judge.majority([False, None, False]) is False
    assert judge.majority([True, False, None]) is None  # 과반이 없으면 판단 불가
    assert judge.majority([]) is None


def test_tools_mode_request_turns_thinking_off_and_forces_submit():
    fake = UrlFake(submit("예"), submit("예"), submit("아니오", ["저희는 매일 아침 육수를 직접 끓여요."]))
    verdict = judge.judge("fact", judge_input(), mode="tools", post=fake)

    assert verdict.ok is True and [v.ok for v in verdict.votes] == [True, True, False]
    assert all(url.endswith("/v3/chat-completions/HCX-007") for url in fake.urls)
    body = fake.requests[0]
    assert body["thinking"] == {"effort": "none"}  # 추론을 끈다 (function calling 과 같이 쓸 수 없다)
    assert body["toolChoice"] == {"type": "function", "function": {"name": "submit_judgement"}}
    assert body["tools"][0]["function"]["parameters"]["properties"]["ok"]["enum"] == ["예", "아니오", "판단 불가"]
    assert "maxTokens" not in body and body["maxCompletionTokens"] >= 1024 and body["temperature"] == 0.3
    with sqlite3.connect(clova_usage_log.LOG_PATH) as conn:
        rows = conn.execute("SELECT feature, model FROM calls").fetchall()
    assert rows == [("eval_judge:fact", "HCX-007")] * 3


def test_reasoning_model_uses_max_completion_tokens_and_keeps_old_shape_for_others():
    tools = [{"type": "function", "function": {"name": "x"}}]
    ask = [{"role": "user", "content": "u"}]
    fake = FakeClova("가", "나", "다", "라")
    clova_tools.chat_with_tools(ask, tools, feature="t", store_id=None, max_tokens=300, post=fake, model="HCX-007")
    clova_tools.chat_with_tools(ask, tools, feature="t", store_id=None, max_tokens=300, post=fake, model="HCX-007",
                                thinking_effort="none")
    clova_tools.chat_with_tools(ask, [], feature="t", store_id=None, max_tokens=4000, post=fake, model="HCX-007",
                                thinking_effort="low")
    clova_tools.chat_with_tools(ask, tools, feature="t", store_id=None, max_tokens=300, post=fake)  # 기본 모델 HCX-005
    without_effort, with_none, reasoning, default = fake.requests

    for body in (without_effort, with_none):  # 도구를 보내면 thinking 을 언제나 끈다 (빼면 기본 low 라 400)
        assert "maxTokens" not in body and body["maxCompletionTokens"] == 1024
        assert body["thinking"] == {"effort": "none"} and body["tools"] == tools
    assert "maxTokens" not in reasoning and reasoning["maxCompletionTokens"] == 4000
    assert reasoning["thinking"] == {"effort": "low"} and "tools" not in reasoning and "toolChoice" not in reasoning
    assert default["maxTokens"] == 1024 and "maxCompletionTokens" not in default and "thinking" not in default


def test_thinking_mode_request_has_no_tools_and_reads_trailing_json():
    answer = '생각해 보면 지어낸 말이 있어요.\n```json\n{"ok": "아니오", "quotes": ["저희는 매일 아침 육수를 직접 끓여요."], "reason": "등록한 사실에 없음"}\n```'
    fake = UrlFake(answer, answer, answer)
    verdict = judge.judge("fact", judge_input(), mode="thinking", post=fake)

    body = fake.requests[0]
    assert "tools" not in body and "toolChoice" not in body
    assert body["thinking"]["effort"] not in (None, "none")
    assert "maxTokens" not in body and body["maxCompletionTokens"] == judge.THINKING_MAX_TOKENS
    assert "JSON 하나만" in body["messages"][0]["content"]
    assert verdict.ok is False and verdict.quotes == ["저희는 매일 아침 육수를 직접 끓여요."]
    assert verdict.as_dict()["quote"] == "저희는 매일 아침 육수를 직접 끓여요."


def test_thinking_mode_asks_again_once_then_gives_up_on_bad_json():
    good = '{"ok": "예", "quotes": [], "reason": "없음"}'
    fake = FakeClova("모르겠어요", good, "형식 없음", "또 형식 없음", good)
    verdict = judge.judge("fact", judge_input(), mode="thinking", post=fake, votes=3)

    first, second, third = verdict.votes
    assert first.ok is True and first.calls == 2  # 한 번 더 물어 받았다
    assert fake.requests[1]["messages"][-1]["role"] == "user" and "JSON 하나만" in fake.requests[1]["messages"][-1]["content"]
    assert second.ok is None and second.calls == 2 and "모양" in second.error  # 두 번 다 틀리면 판단 불가
    assert third.ok is True
    assert verdict.ok is True and fake.done()


def test_quote_not_in_reply_is_dropped_and_asked_again():
    fake = FakeClova(
        submit("아니오", ["답글에 없는 말"]),
        submit("아니오", ["저희는 매일 아침 육수를 직접 끓여요."]),
        submit("아니오", ["답글에 없는 말"]), submit("아니오", ["이것도 없는 말"]),
        submit("예"),
    )
    verdict = judge.judge("fact", judge_input(), post=fake)

    first, second, third = verdict.votes
    assert first.ok is False and first.quotes == ["저희는 매일 아침 육수를 직접 끓여요."] and first.calls == 2
    assert "글자 그대로" in fake.tool_messages(1)[0]
    assert second.ok is None and "글자 그대로 없음" in second.error
    assert third.ok is True
    assert verdict.ok is None  # 아니오, 판단 불가, 예 → 과반 없음


def test_false_without_quote_is_kept_for_missing_content():
    fake = FakeClova(*(submit("아니오", [], "싱겁다는 불만에 답하지 않음") for _ in range(3)))
    verdict = judge.judge("core", judge_input(reply="찾아 주셔서 감사합니다."), post=fake)
    assert verdict.ok is False and verdict.quotes == [] and fake.done()


def test_cannot_judge_answer_is_none():
    fake = FakeClova(*(submit("판단 불가") for _ in range(3)))
    verdict = judge.judge("response", judge_input(), post=fake)
    assert verdict.ok is None and verdict.as_dict()["vote"] == [None, None, None]


def test_inputs_hide_system_and_send_gold_reply_only_to_core():
    fake = FakeClova(*(submit("예") for _ in range(6)))
    judge.judge("fact", judge_input(), votes=1, post=fake)
    judge.judge("core", judge_input(), votes=1, post=fake)
    judge.judge("consistency", judge_input(diagnosis="19시 주문 몰림과 근무 1명"), votes=1, post=fake)
    fact_user, core_user, consistency_user = (body["messages"][1]["content"] for body in fake.requests[:3])

    assert "참고 답변" not in fact_user and "간을 다시 볼게요" not in fact_user
    assert "참고용 예시이며 표현이 달라도 된다" in core_user and "간을 다시 볼게요" in core_user
    assert "[진단]" in consistency_user and "19시 주문 몰림" in consistency_user and "[진단]" not in core_user
    assert "010-1234-5678" not in fact_user  # 리뷰 글은 개인정보를 가린 뒤
    for text in (fact_user, core_user, consistency_user):
        assert "시스템" not in text and "멀티" not in text and "단일" not in text
    system = fake.requests[0]["messages"][0]["content"]
    assert "{공통정책}" not in system and "도나 답글 공통 정책" in system and "{업종}" not in system


def test_repeated_400_stops_with_model_error():
    fake = FakeClova(*([400] * 6))
    with pytest.raises(judge.JudgeModelError, match="HCX-007"):
        judge.judge("fact", judge_input(), post=fake)


def test_empty_reply_fails_without_calling():
    fake = FakeClova()
    verdict = judge.judge("fact", judge_input(reply="  "), post=fake)
    assert verdict.ok is False and verdict.calls == 0


def test_last_json_reads_only_the_trailing_object():
    assert judge.last_json('앞 {"a": 1} 뒤 {"ok": "예", "quotes": [], "reason": "{괄호}"}') == {"ok": "예", "quotes": [], "reason": "{괄호}"}
    assert judge.last_json('{"ok": "예"} 그리고 설명') is None
    assert judge.last_json("") is None


def test_every_condition_has_a_prompt_file():
    for condition in judge.CONDITIONS.values():
        text = judge.system_prompt(condition, "tools", "국수")
        assert "도나 답글 공통 정책" in text and "실제 데이터가 아니라" in text


# ── 시스템과 입구 ──


def test_systems_b_has_every_task_and_a_reports_missing(monkeypatch):
    b = systems.get("B")
    assert set(b.tasks) == set(systems.TASKS)
    with pytest.raises(systems.SystemUnavailable):
        systems.parse_names("A,C")
    assert systems.parse_names("b, a, B") == ["B", "A"]
    monkeypatch.setattr(systems, "SINGLE_AGENT_MODULE", "Harness.agents.no_such_single_agent")
    with pytest.raises(systems.SystemUnavailable, match="아직 없어요"):
        systems.get("A")


def test_cli_help_lists_suites(capsys):
    with pytest.raises(SystemExit) as done:
        cli.main(["--help"])
    assert done.value.code == 0
    text = capsys.readouterr().out
    for name in cli.SUITES:
        assert name in text
    assert "--judge-mode" in text and "--systems" in text and "--concurrency" in text
