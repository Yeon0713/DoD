"""voice 스위트: 음성 백엔드 POST /v1/turn 응답 시간을 말 종류별로 잰다.

목표 (docs/v0.2.0-voice-agent-handoff.md 11장)
  briefing  브리핑 단계(start, next, repeat, jump, detail, auto_next, restart, stop)  1초 안
  question  그 밖 질문 (예약·비 소식·매출 같은 규칙 질문과, 규칙이 못 갈라 판정 에이전트로 가는 질문)  3초 안
  kitchen   주방 대화 (가만히 있어야 하는 말. 응답은 ignore)  3초 안
  앱 시간 초과는 5초. 5초를 넘기거나 오류(500 등)로 끝난 말은 timeout 으로 센다.
종류는 사장님이 한 말의 종류(정답)다. 도나가 어떻게 가렸는지가 아니다.

방법
  FastAPI TestClient 로 앱과 같은 요청을 보낸다 (네트워크·TTS 는 빠진 서버 처리 시간). 회차마다 저장소를 비우고 13장 기준 데이터
  (s001, 11/17 09:00)를 넣고 브리핑을 준비한 뒤, TURNS 의 말 20개를 차례로 보낸다.
  브리핑 준비는 CLOVA 를 끄고 한다 (답글 에이전트를 부르지 않는다. 브리핑 단계 응답은 미리 만든 것을 꺼내기만 하므로 준비 방식과
  /v1/turn 시간은 상관없다). 저장소·기록은 결과 폴더(voice.db, clova_usage.db, harness_trace.db)에 둔다. TTS 는 끈다.

시스템 (--systems, 기본 rule+judge)
  rule        CLOVA 를 끈 채로 잰다. 규칙이 못 가른 말은 heuristic 으로 간다 (CLOVA 키 없이 돈다)
  rule+judge  운영과 같이 판정 에이전트(voice/agents/intent_judge, 3초)를 켠다. 실제 CLOVA

지표 (시스템마다)
  turn_within_target:<kind>  목표 안에 끝난 말 / 그 종류의 말 전체 (오류도 분모에 넣고 실패로 센다)
  turn_p50:<kind>, turn_p95:<kind>, turn_max:<kind>  잰 초 (p95 는 가장 가까운 순위 방식)
  turn_over_timeout_rate     5초를 넘기거나 오류로 끝난 말 / 모든 말
  turn_judge_within_budget   CLOVA 를 부른 말 중 3초 안 / CLOVA 를 부른 말
  turn_clova_calls           CLOVA 호출 수 합
--dry-run 이면 판정 에이전트를 부를 것 같은 말 수(규칙만 돌려 셈, 직전 상황은 '브리핑 중'으로 둔 어림)만 보여 준다.
"""

import argparse
import os
import statistics
import time

import httpx

from app.core.config import settings
from Harness.evals import metrics, report

QUESTION = 5
SYSTEMS = ("rule", "rule+judge")
TARGETS = {"briefing": 1.0, "question": 3.0, "kitchen": 3.0}
APP_TIMEOUT_SECONDS = 5.0
JUDGE_BUDGET_SECONDS = 3.0
SWITCHES = {"VOICE_AGENT_INTENT": "true"}
STORE_ID = "s001"
SESSION_ID = "sess_20261117_s001"
PREPARE_AT = "2026-11-17T09:00:00+09:00"

# (말, 종류, addressed). 말이 None 이면 auto_next 이벤트 (앱이 말하기를 마치고 다음 단계로 넘김)
TURNS: tuple[tuple[str | None, str, bool], ...] = (
    ("오늘 일정 브리핑해 줘", "briefing", False),
    ("3번 테이블 치워 줘", "kitchen", False),
    ("다음", "briefing", False),
    ("다시 말해 줘", "briefing", False),
    ("내일 예약 몇 팀이야", "question", False),
    ("화면에 보여 줘", "briefing", False),
    ("읽어 줘", "briefing", False),
    ("돌아가기", "briefing", False),
    ("육수 좀 더 끓여", "kitchen", False),
    (None, "briefing", False),
    ("좋은 리뷰 보여 줘", "briefing", False),
    ("오늘 손님 많을 것 같아?", "question", True),
    ("다음", "briefing", False),
    ("이번 주 비 와?", "question", False),
    ("불 줄여 봐", "kitchen", False),
    ("처음부터 다시", "briefing", False),
    ("요즘 국물 맛 괜찮다는 말 많아?", "question", False),
    ("이번 주 매출 어때", "question", False),
    ("뭐부터 하면 좋을까", "question", True),
    ("그만", "briefing", False),
)

timer = time.perf_counter  # 테스트에서 바꾼다


class VoiceSystemUnavailable(ValueError):
    pass


def parse_systems(text: str) -> list[str]:
    names = [part.strip() for part in text.split(",") if part.strip()]
    unknown = [name for name in names if name not in SYSTEMS]
    if unknown or not names:
        raise VoiceSystemUnavailable(f"voice 스위트 시스템은 {', '.join(SYSTEMS)} 중에서 골라요 (받은 값: {text!r})")
    return list(dict.fromkeys(names))


def likely_judge_turns() -> list[str]:
    """규칙이 못 가를 것 같은 말 (판정 에이전트를 부른다). 직전 상황을 '브리핑 중'으로 둔 어림이다."""
    from voice.dialog import intent_rules

    return [text for text, _, addressed in TURNS
            if text is not None and intent_rules.match(text, "answer", addressed) is None]


def planned_calls(names: list[str], runs: int) -> dict:
    per_run = len(likely_judge_turns())
    return {name: {"typical": per_run * runs if name == "rule+judge" else 0,
                   "max": per_run * runs * 2 if name == "rule+judge" else 0} for name in names}


def _body(number: int, text: str | None, addressed: bool) -> dict:
    return {"request_id": f"req_{number:04d}", "store_id": STORE_ID, "session_id": SESSION_ID,
            "client_time": PREPARE_AT, "event": "auto_next" if text is None else None,
            "utterance": None if text is None else {"text": text, "confidence": 0.93, "source": "voice", "addressed": addressed},
            "context": {"last_turn_id": None, "donna_was_speaking": False, "heard_until": None}}


def prepare(client) -> None:
    """저장소를 비우고 13장 기준 데이터로 11/17 09:00 브리핑을 준비한다 (CLOVA 끔)."""
    from voice.tests.conftest import baseline

    saved_key = settings.clova_studio_api_key
    settings.clova_studio_api_key = ""
    try:
        client.post("/v1/dev/reset")
        client.post("/v1/dev/clock", json={"now": PREPARE_AT})
        client.post("/v1/dev/fixtures", json=baseline())
        client.post("/v1/dev/run", json={"store_id": STORE_ID, "job": "prepare_briefing"})
    finally:
        settings.clova_studio_api_key = saved_key


def one_run(system: str, run: int, post) -> list[dict]:
    """대본 한 번. 말마다 {run, step, text, kind, seconds, calls, status, type, intent, ...} 한 줄."""
    from fastapi.testclient import TestClient

    from voice import clock, context
    from voice.main import create_app

    # with 를 쓰지 않아 시연 가게 넣기·작업 큐 스레드가 돌지 않는다. 서버 오류는 앱이 받는 것처럼 500 으로 받는다
    client = TestClient(create_app(), raise_server_exceptions=False)
    clock.set_now(None)
    prepare(client)
    saved_key = settings.clova_studio_api_key
    if system == "rule":
        settings.clova_studio_api_key = ""
    rows = []
    try:
        for step, (text, kind, addressed) in enumerate(TURNS, 1):
            counting = report.CountingPost(post)
            context.post = counting
            started = timer()
            error = None
            try:
                response = client.post("/v1/turn", json=_body(step, text, addressed))
                status = response.status_code
                body = response.json() if status == 200 else {}
                if status != 200:
                    error = f"HTTP {status}"
            except Exception as exc:  # 한 말이 실패해도 대본은 이어 간다
                status, body, error = None, {}, f"{type(exc).__name__}: {exc}"
            seconds = round(timer() - started, 4)
            rows.append({"case_id": f"turn:{step}", "system": system, "run": run, "step": step,
                         "text": text if text is not None else "(auto_next)", "kind": kind, "addressed": addressed,
                         "seconds": seconds, "target": TARGETS[kind], "calls": counting.calls, "status": status,
                         "error": error, "type": body.get("type"), "intent": body.get("intent"),
                         "output": body.get("headline")})
    finally:
        settings.clova_studio_api_key = saved_key
    return rows


def failed(row: dict) -> bool:
    return row["error"] is not None or row["seconds"] > APP_TIMEOUT_SECONDS


def score(name: str, rows: list[dict]) -> list[dict]:
    out = []
    for kind, target in TARGETS.items():
        chosen = [row for row in rows if row["kind"] == kind]
        measured = [row["seconds"] for row in chosen if row["error"] is None]
        out.append(metrics.metric(f"turn_within_target:{kind}", f"/v1/turn {kind} {target:g}초 안 비율", question=QUESTION,
                                  system=name, numerator=sum(1 for row in chosen if row["error"] is None and row["seconds"] <= target),
                                  denominator=len(chosen)))
        for id, label, value in (("p50", "중앙값", statistics.median(measured) if measured else None),
                                 ("p95", "p95", metrics.percentile(measured, 95)),
                                 ("max", "최댓값", max(measured) if measured else None)):
            out.append(metrics.value_metric(f"turn_{id}:{kind}", f"/v1/turn {kind} 응답 시간 {label}", question=QUESTION,
                                            system=name, value=value, unit="seconds"))
    out.append(metrics.metric("turn_over_timeout_rate", f"/v1/turn {APP_TIMEOUT_SECONDS:g}초 초과·오류 비율", question=QUESTION,
                              system=name, numerator=sum(map(failed, rows)), denominator=len(rows), higher_is_better=False,
                              note=f"오류 {sum(1 for row in rows if row['error'])}"))
    judged = [row for row in rows if row["calls"]]
    out.append(metrics.metric("turn_judge_within_budget", f"CLOVA 를 부른 말의 {JUDGE_BUDGET_SECONDS:g}초 안 비율",
                              question=QUESTION, system=name,
                              numerator=sum(1 for row in judged if row["error"] is None and row["seconds"] <= JUDGE_BUDGET_SECONDS),
                              denominator=len(judged)))
    out.append(metrics.value_metric("turn_clova_calls", "CLOVA 호출 수 합", question=QUESTION, system=name,
                                    value=sum(row["calls"] for row in rows), unit="calls"))
    return out


def evaluate(names: list[str], *, runs: int = 1, out=None, post=None) -> dict:
    """out 이 있으면 저장소·기록을 그 폴더에 둔다 (테스트는 tmp_path). post 는 판정 에이전트 쪽 CLOVA (테스트에서 가짜)."""
    from voice import clock, config, context, tts

    saved = {"db": config.DB_PATH, "tts": tts.ENABLED, "post": context.post,
             "env": {key: os.environ.get(key) for key in SWITCHES}}
    if out is not None:
        config.DB_PATH = out / "voice.db"
    tts.ENABLED = False
    os.environ.update(SWITCHES)
    restore_cache = report.disable_cache()
    rows: list[dict] = []
    try:
        for name in names:
            for run in range(1, runs + 1):
                rows += one_run(name, run, post or httpx.post)
    finally:
        restore_cache()
        clock.set_now(None)
        config.DB_PATH, tts.ENABLED, context.post = saved["db"], saved["tts"], saved["post"]
        for key, value in saved["env"].items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    out_metrics = [metric for name in names for metric in score(name, [row for row in rows if row["system"] == name])]
    return {"metrics": out_metrics, "cases": rows, "calls": sum(row["calls"] for row in rows)}


def run(args: argparse.Namespace):
    """python -m Harness.evals voice [--systems rule+judge] [--runs 3] [--dry-run]"""
    names = args.system_names
    plan = planned_calls(names, args.runs)
    print(f"/v1/turn 응답 시간: 말 {len(TURNS)}개 × 회차 {args.runs}, 시스템 {', '.join(names)}", flush=True)
    for name, calls in plan.items():
        print(f"  {name}: 예상 CLOVA 호출 약 {calls['typical']}회 (최대 {calls['max']})", flush=True)
    if getattr(args, "dry_run", False):
        print("--dry-run: CLOVA 를 부르지 않고 끝냅니다", flush=True)
        return plan
    config = {"model": settings.clova_studio_model if "rule+judge" in names else None, "runs": args.runs,
              "turns": len(TURNS), "targets": TARGETS, "app_timeout_seconds": APP_TIMEOUT_SECONDS,
              "judge_budget_seconds": JUDGE_BUDGET_SECONDS, "fixture": "voice/fixtures/s001_baseline.json",
              "prepare_at": PREPARE_AT, "transport": "FastAPI TestClient (네트워크·TTS 제외)",
              "switches": dict(SWITCHES) if "rule+judge" in names else {}, "planned_calls": plan}
    eval_run = report.start("voice", config=config, systems=names)
    print(f"결과 폴더: {eval_run.out}", flush=True)
    result = evaluate(names, runs=args.runs, out=eval_run.out)
    eval_run.metrics, eval_run.cases = result["metrics"], result["cases"]
    eval_run.config["agent_calls"] = result["calls"]
    path = eval_run.finish()
    for metric in result["metrics"]:
        if metric["id"].startswith(("turn_within_target", "turn_over_timeout")):
            print(f"  {metric['system']} {metric['id']}: {metric['numerator']}/{metric['denominator']}", flush=True)
    print(f"result.json: {path}")
    return path

