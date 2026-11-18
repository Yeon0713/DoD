"""intent 스위트: 음성 앱 F8 뜻 판정 (질문 4). A/B 비교가 아니라 공통 부품을 잰다.

시스템 (--systems, 기본 rule,rule+judge)
  rule        규칙(voice/dialog/intent_rules.match) → 못 가르면 heuristic. CLOVA 를 부르지 않는다
  rule+judge  운영과 같은 순서(voice/dialog/turn.understand): 규칙 → 판정 에이전트(voice/agents/intent_judge, 3초) → heuristic
              판정 에이전트는 VOICE_AGENT_INTENT 스위치를 본다. 실행 안에서만 켜고 끝나면 되돌린다

정답 세트 Harness/evals/data/intents_v1.json
  문서(docs/v0.2.0-voice-agent-handoff.md) 7장 intent 예, 13장 시나리오 C(C1~C8), intent 마다 말 바꾸기 5·오타 3,
  주방 대화 20(not_for_donna), 뜻 모르는 말 10(unknown). 한 줄: id, text, addressed, context{briefing_step,
  donna_was_speaking, last_type}, expected_intent, expected_jump_to(briefing.jump 일 때). verified_by 가 비면 사람 확인 전.
  맞힘: intent 가 같고, 정답에 jump_to 가 있으면 그것도 같다.

지표 (시스템마다, 분모는 요청 전체 × 회차)
  intent_accuracy      맞힌 / 전체
  wrong_answer_rate    정답이 not_for_donna·unknown 인데 그 둘이 아닌 intent 로 답한 / 정답이 그 둘인 것 (낮을수록 좋다. 가장 중요)
  missed_command_rate  정답이 명령(그 둘이 아닌 것)인데 not_for_donna 로 무시한 / 정답이 명령인 것 (낮을수록 좋다)
  judge_latency        판정 에이전트를 부른 말의 응답 초 중앙값 (note 에 최댓값). judge_within_budget 은 3초 안 비율
  rule_coverage        규칙만으로 가른 / 전체

오발성 세분. '반응'은 not_for_donna·unknown 이 아닌 뜻으로 답한 것, '무시'는 not_for_donna.
  false_activation_rate          정답이 not_for_donna 인 말 중 반응한 / 정답이 not_for_donna 인 말 (wrong_answer_rate 의 부분 집합)
  window_false_answer_rate       8초 창(addressed false 이고 직전 상황이 있는 말: last_type·briefing_step 이 있거나 도나가 말하던 중)
                                 안의 주방 대화 중 반응한 / 그 주방 대화
  missed_command_rate_addressed  "도나야"로 부른 말(addressed true) 중 무시한 / 부른 말 전체 (목표 0)
  wake_accept_rate               호출어 세트(source wake) 중 부른 말(정답이 not_for_donna 가 아님)을 무시하지 않은 / 그 말
  wake_false_accept_rate         호출어 세트 중 부르지 않은 비슷한 말(정답 not_for_donna)에 반응한 / 그 말
  호출어 세트는 앱이 호출어를 떼지 못하고 글자 그대로 보낸 말(addressed false)이다. 백엔드가 그 말을 어떻게 받는지 잰다.
  앱의 실제 호출어 감지(음성)는 여기서 재지 않는다.

--dry-run 이면 규칙만 돌려 판정 에이전트를 부를 말 수(= 예상 CLOVA 호출 수)를 보여 주고 끝낸다.
"""

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path

import httpx

from app.core.config import settings
from Harness.evals import metrics, report

QUESTION = 4
DATA = Path(__file__).resolve().parent / "data" / "intents_v1.json"
SYSTEMS = ("rule", "rule+judge")
SILENT = ("not_for_donna", "unknown")
JUDGE_BUDGET_SECONDS = 3
SWITCHES = {"VOICE_AGENT_INTENT": "true"}


class IntentSystemUnavailable(ValueError):
    pass


def parse_systems(text: str) -> list[str]:
    names = [part.strip() for part in text.split(",") if part.strip()]
    unknown = [name for name in names if name not in SYSTEMS]
    if unknown or not names:
        raise IntentSystemUnavailable(f"뜻 판정 시스템은 {', '.join(SYSTEMS)} 중에서 골라요 (받은 값: {text!r})")
    return list(dict.fromkeys(names))


def load_cases(path: Path = DATA) -> tuple[dict, list[dict]]:
    body = json.loads(path.read_text(encoding="utf-8"))
    return body, body["cases"]


def make_view():
    """판정 에이전트 프롬프트에 쓰는 가게 보기 (s005 시연 가게, 리뷰 없음)."""
    from Harness.evals.reply_eval import fixture_now, load_fixture
    from voice.context import VoiceStore

    fixture = load_fixture()
    store = {**fixture["store"], "facts": []}
    return VoiceStore(store["id"], store, {"review": [], "weather": [], "event": [], "game": []}, fixture_now(fixture))


def classify(system: str, case: dict, view) -> dict:
    """{intent, jump_to, by, judge_seconds}. by: rule | llm | heuristic."""
    from voice.agents import intent_judge
    from voice.dialog import intent_rules
    from voice.dialog.turn import SITUATIONS

    text, addressed = case["text"], bool(case.get("addressed"))
    last_type = (case.get("context") or {}).get("last_type")
    found = intent_rules.match(text, last_type, addressed)
    if found is not None:
        return {"intent": found.name, "jump_to": found.jump_to, "by": "rule", "judge_seconds": None}
    seconds = None
    if system == "rule+judge":  # turn.understand 와 같은 순서
        started = time.perf_counter()
        judged = intent_judge.judge(view, text, SITUATIONS.get(last_type or "", "도나는 듣고만 있어요"))
        seconds = round(time.perf_counter() - started, 3)
        if judged and not (addressed and judged["intent"] == "not_for_donna"):
            return {"intent": judged["intent"], "jump_to": judged.get("jump_to"), "by": "llm", "judge_seconds": seconds}
    fallback = intent_rules.heuristic(text, addressed)
    return {"intent": fallback.name, "jump_to": fallback.jump_to, "by": "heuristic", "judge_seconds": seconds}


def is_correct(case: dict, got: dict) -> bool:
    if got["intent"] != case["expected_intent"]:
        return False
    return not case.get("expected_jump_to") or got.get("jump_to") == case["expected_jump_to"]


def score(name: str, rows: list[dict]) -> list[dict]:
    total = len(rows)
    silent = [row for row in rows if row["expected_intent"] in SILENT]
    commands = [row for row in rows if row["expected_intent"] not in SILENT]
    judged = [row["judge_seconds"] for row in rows if row["judge_seconds"] is not None]
    out = [
        metrics.metric("intent_accuracy", "뜻 판정 정확도", question=QUESTION, system=name,
                       numerator=sum(row["correct"] for row in rows), denominator=total),
        metrics.metric("wrong_answer_rate", "잘못 답한 비율 (가만히 있어야 할 말에)", question=QUESTION, system=name,
                       numerator=sum(row["intent"] not in SILENT for row in silent), denominator=len(silent),
                       higher_is_better=False),
        metrics.metric("missed_command_rate", "명령을 무시한 비율", question=QUESTION, system=name,
                       numerator=sum(row["intent"] == "not_for_donna" for row in commands), denominator=len(commands),
                       higher_is_better=False),
        metrics.metric("rule_coverage", "규칙만으로 가른 비율", question=QUESTION, system=name,
                       numerator=sum(row["by"] == "rule" for row in rows), denominator=total),
    ]
    if name == "rule+judge":
        latency = metrics.latency(judged, JUDGE_BUDGET_SECONDS)
        out.append(metrics.value_metric("judge_latency", "판정 에이전트 응답 시간 중앙값", question=QUESTION, system=name,
                                        value=latency["median"], unit="seconds",
                                        note=f"최댓값 {latency['max']}초, 판정 {len(judged)}건"))
        out.append(metrics.metric("judge_within_budget", f"판정 {JUDGE_BUDGET_SECONDS}초 안 비율", question=QUESTION,
                                  system=name, numerator=latency["within_budget"] or 0, denominator=latency["total"]))
    return out + misfire_metrics(name, rows)


def in_window(row: dict) -> bool:
    """8초 창 안의 말: 부르지 않았고(addressed false), 도나가 브리핑 중이거나 묻거나 답한 직후."""
    context = row.get("context") or {"last_type": row.get("last_type")}  # 예전 결과 줄에는 last_type 만 있다
    return not row["addressed"] and bool(context.get("last_type") or context.get("briefing_step") is not None
                                         or context.get("donna_was_speaking"))


def misfire_metrics(name: str, rows: list[dict]) -> list[dict]:
    """오발성 세분. 정의는 모듈 설명."""
    kitchen = [row for row in rows if row["expected_intent"] == "not_for_donna"]
    window = [row for row in kitchen if in_window(row)]
    addressed = [row for row in rows if row["addressed"]]
    wake = [row for row in rows if row.get("source") == "wake"]
    wake_call = [row for row in wake if row["expected_intent"] != "not_for_donna"]
    wake_not = [row for row in wake if row["expected_intent"] == "not_for_donna"]

    def reacted(row: dict) -> bool:
        return row["intent"] not in SILENT

    def ignored(row: dict) -> bool:
        return row["intent"] == "not_for_donna"

    return [
        metrics.metric("false_activation_rate", "부르지 않았는데 반응한 비율 (주방 대화에)", question=QUESTION, system=name,
                       numerator=sum(map(reacted, kitchen)), denominator=len(kitchen), higher_is_better=False),
        metrics.metric("window_false_answer_rate", "8초 창 안 주방 대화에 반응한 비율", question=QUESTION, system=name,
                       numerator=sum(map(reacted, window)), denominator=len(window), higher_is_better=False),
        metrics.metric("missed_command_rate_addressed", "\"도나야\"로 부른 말을 무시한 비율", question=QUESTION, system=name,
                       numerator=sum(map(ignored, addressed)), denominator=len(addressed), higher_is_better=False),
        metrics.metric("wake_accept_rate", "호출어 변형을 부른 말로 받은 비율", question=QUESTION, system=name,
                       numerator=sum(not ignored(row) for row in wake_call), denominator=len(wake_call)),
        metrics.metric("wake_false_accept_rate", "호출어와 비슷한 말에 반응한 비율", question=QUESTION, system=name,
                       numerator=sum(map(reacted, wake_not)), denominator=len(wake_not), higher_is_better=False),
    ]


def evaluate(cases: list[dict], names: list[str], *, runs: int = 1, post=None) -> dict:
    """post 는 판정 에이전트 쪽 CLOVA (테스트에서 가짜). rule 은 결정적이라 한 번만 돈다."""
    from voice import context

    view = make_view()
    counting = report.CountingPost(post or httpx.post)
    saved_post, saved_env = context.post, {key: os.environ.get(key) for key in SWITCHES}
    context.post = counting
    os.environ.update(SWITCHES)
    restore_cache = report.disable_cache()  # 같은 말을 회차마다 새로 판정하게
    rows: list[dict] = []
    try:
        for name in names:
            for run in range(1, (runs if name == "rule+judge" else 1) + 1):
                for case in cases:
                    got = classify(name, case, view)
                    rows.append({"case_id": case["id"], "system": name, "run": run, "source": case.get("source"),
                                 "text": case["text"], "addressed": bool(case.get("addressed")),
                                 "last_type": (case.get("context") or {}).get("last_type"),
                                 "context": dict(case.get("context") or {}),
                                 "expected_intent": case["expected_intent"], "expected_jump_to": case.get("expected_jump_to"),
                                 **got, "correct": is_correct(case, got)})
    finally:
        restore_cache()
        context.post = saved_post
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    out = [metric for name in names for metric in score(name, [row for row in rows if row["system"] == name])]
    confusion = {name: dict(Counter(f"{row['expected_intent']} → {row['intent']}" for row in rows
                                    if row["system"] == name and not row["correct"])) for name in names}
    return {"metrics": out, "cases": rows, "confusion": confusion, "calls": counting.calls}


def judge_needed(cases: list[dict]) -> list[dict]:
    """규칙이 못 가른 말 (rule+judge 에서 판정 에이전트를 부르는 말). CLOVA 를 부르지 않는다."""
    from voice.dialog import intent_rules

    return [case for case in cases if intent_rules.match(case["text"], (case.get("context") or {}).get("last_type"),
                                                         bool(case.get("addressed"))) is None]


def planned_calls(cases: list[dict], names: list[str], runs: int) -> dict:
    """{시스템: {typical, max}}. typical 은 판정 에이전트를 부를 말 수 × 회차, max 는 429 뒤 한 번 더 부른 경우."""
    needed = len(judge_needed(cases))
    return {name: {"typical": needed * runs, "max": needed * runs * 2} if name == "rule+judge" else {"typical": 0, "max": 0}
            for name in names}


def print_plan(cases: list[dict], names: list[str], runs: int) -> dict:
    plan = planned_calls(cases, names, runs)
    for name, calls in plan.items():
        print(f"  {name}: 예상 CLOVA 호출 {calls['typical']}회 (429 로 다시 부르면 최대 {calls['max']}회)")
    print("--dry-run: CLOVA 를 부르지 않고 끝냅니다", flush=True)
    return plan


def run(args: argparse.Namespace):
    """python -m Harness.evals intent --runs 3 [--systems rule,rule+judge]"""
    names = args.system_names
    body, cases = load_cases()
    if args.ids:
        wanted = {part for part in args.ids.split(",") if part}
        cases = [case for case in cases if case["id"] in wanted]
    print(f"뜻 판정 {len(cases)}건, 시스템 {', '.join(names)}, 회차 {args.runs}", flush=True)
    if getattr(args, "dry_run", False):
        return print_plan(cases, names, args.runs)
    config = {"model": settings.clova_studio_model if "rule+judge" in names else None, "runs": args.runs,
              "data": {"file": DATA.name, "version": body.get("version"), "sha256": report.file_sha256(DATA),
                       "verified_by": body.get("verified_by")},
              "switches": dict(SWITCHES) if "rule+judge" in names else {}, "judge_budget_seconds": JUDGE_BUDGET_SECONDS}
    eval_run = report.start("intent", config=config, systems=names)
    print(f"결과 폴더: {eval_run.out}", flush=True)
    result = evaluate(cases, names, runs=args.runs)
    eval_run.metrics, eval_run.cases = result["metrics"], result["cases"]
    eval_run.tables["wrong"] = result["confusion"]
    eval_run.config["agent_calls"] = result["calls"]
    out = eval_run.finish()
    print(f"result.json: {out}")
    return out

