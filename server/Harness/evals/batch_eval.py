"""batch 스위트: 원인 진단과 알림 묶음 조율 (질문 2·4). A(단일 에이전트)와 B(지금 하네스)를 비교한다.
사례가 적어서 비율이 아니라 건수로 적는다 (지표 value 는 건수, note 에 "B 4건 중 2건").

진단 (사례는 scenarios.py)
  B  d1~d3: complaint_agent.diagnose, d4: voice improve_tip.suggest (VOICE_AGENT_IMPROVE 를 실행 안에서만 켬)
  A  d1~d3: single_agent 의 diagnose(할 일 하나 묶음), d4: single_agent.prepare_voice(jobs 없음, tip=True)
  R  기준선: 규칙 한 줄. app/planner/rule_complaint_fix 의 REVIEW_FIX 카드 문구("최근 7일 동안 … 불만이 N건 들어왔어요.")
     LLM 없음. 같은 판정 규칙을 그대로 적용한다. 가설이 없으므로 원인 찾음은 0 이 정상이다.
     d2(단서 없음, confidence low 기대)는 R 에 확신도가 없어 통과하지 않는다. 숫자 근거·과제 완료·묶음 조율은 R 에 해당 없음.
  A·B 진단 사례에는 reply 스위트와 같은 fail_cause·제출 통계(Harness/evals/fail_cause)를 남긴다.
  판정 (코드): cause_found  심은 원인 말 묶음이 가설(고칠 점) 글에 모두 있는지. d2 는 confidence low 인지
             grounded     가설 글의 숫자가 그 실행의 도구 결과(harness_trace.db)에 모두 있는지 (grounding.ungrounded_numbers)
  점검 목록이 사장님이 할 수 있는 일인지는 사람이 본다 (결과에 checklist 를 남긴다).

묶음 조율 (t001, 일꾼 초안은 scenarios.fixed_proposals 고정)
  B  supervisor.coordinate_batch(묶음, 고정 초안). 재작업 한도 등은 고치지 않는다
  A  single_agent.run_batch(묶음 할 일들) — 묶음 전체를 처음부터 한 번에 쓴다. 포스터(campaign)는 A 가 못 해서 b_menu 는 A 에서 뺀다
  conflicts_left  최종 묶음에 남은 심은 충돌. 불만 메뉴 홍보·같은 손님 두 번은 conflicts.find_conflicts 규칙으로,
                  답글·진단 불일치는 심판 consistency 조건이 '아니오'면 남은 것으로 센다. 경고 메모만 붙인 것도 남은 것이다
                  (규칙은 두 할 일이 함께 있으면 언제나 충돌로 보므로, 같은 손님 두 번은 한쪽을 빼야만 풀린 것으로 센다)
  fit_in_batch    묶음 안 리뷰 답글 중 reply 스위트 기준 적합(심판 4조건 + 형식) 건수. B 는 조율 전(고정 초안)·후, A 는 후
  rework_limit_ok B 의 재작업이 할 일당 1번, 묶음당 3건(supervisor.MAX_REVISIONS) 이하
  no_conflict_calls  충돌 없는 묶음에서 B 의 supervisor 추가 CLOVA 호출이 0 인 묶음 수

심판 방식은 --judge-mode (guards 결과로 기본값을 정하기 전에는 tools 임시). config.judge_mode 에 적는다.
"""

import argparse
import datetime as dt
import json
import logging
import os
import threading
import time
from collections import Counter

import httpx

from app.core.config import settings
from Harness import grounding, trace
from Harness.evals import fail_cause, gold, judge, metrics, reply_checks, report, scenarios, systems
from Harness.evals.guards_eval import CaseAborted, GuardedPost, load_store_facts

logger = logging.getLogger(__name__)

QUESTION_FIT, QUESTION_TASK = 2, 4
JUDGE_DEADLINE_SECONDS = 600
SWITCHES = {"VOICE_AGENT_IMPROVE": "true"}
A_TASK_TYPES = {"REVISIT_REPLY", "REORDER_NUDGE", "REVIEW_FIX"}  # single_agent.run_batch 가 맡는 할 일
RULE = "R"  # 기준선: 규칙 한 줄 (진단만)


def parse_systems(text: str) -> list[str]:
    """batch 의 --systems: A, B 와 기준선 R."""
    names = list(dict.fromkeys(part.strip().upper() for part in text.split(",") if part.strip()))
    rest = [name for name in names if name != RULE]
    if rest:
        systems.parse_names(",".join(rest))
    if not names:
        raise ValueError("시스템을 하나 이상 고르세요 (R, A, B)")
    return names


class EventPost:
    """post 를 감싸 사례의 전송 사건(200 이 아닌 응답 상태, 예외 이름)을 모은다."""

    def __init__(self, post):
        self.post, self.events = post, []

    def __call__(self, url, **kwargs):
        try:
            response = self.post(url, **kwargs)
        except Exception as error:
            self.events.append(type(error).__name__)
            raise
        if getattr(response, "status_code", 200) != 200:
            self.events.append(response.status_code)
        return response


def rule_line(complaint_type: str, count: int) -> str:
    """rule_complaint_fix 의 REVIEW_FIX 카드 문구와 같은 문장."""
    from app.planner.rule_complaint_fix import COMPLAINT_NAMES

    return f"최근 7일 동안 {COMPLAINT_NAMES[complaint_type]} 불만이 {count}건 들어왔어요."


def rule_diagnosis(case_id: str, gold_rows: list[dict]) -> dict:
    """기준선 R 의 '진단': 위험 신호 하나를 규칙 문장 한 줄로."""
    if case_id == "d4":
        reviews, topic = scenarios.voice_reviews(gold_rows, voice_view(gold_rows)[1])
        kind = next((k for k, v in scenarios.VOICE_TOPICS.items() if v == topic), None)
        text = rule_line(kind, len(reviews)) if kind else ""
    else:
        snap = scenarios.snapshot(case_id)
        risk = next(iter(snap.risk_signals), None)
        text = rule_line(risk.complaint_type, len(risk.review_ids)) if risk else ""
    return {"source": "RULE", "text": text, "hypotheses": [text] if text else [], "confidence": None, "checklist": []}


# ── 실행 id 모으기 ──


class RunIds:
    """trace.record 를 감싸 이 스레드에서 시작한 (부모 없는) 에이전트 실행 id 를 모은다."""

    def __init__(self):
        self.local = threading.local()
        self.saved = None

    def __enter__(self):
        self.saved = trace.record

        def record(**kwargs):
            ids = getattr(self.local, "ids", None)
            if ids is not None and kwargs.get("parent_run_id") is None and kwargs.get("step") == 0 and kwargs["run_id"] not in ids:
                ids.append(kwargs["run_id"])
            return self.saved(**kwargs)

        trace.record = record
        return self

    def __exit__(self, *exc):
        trace.record = self.saved

    def start(self) -> None:
        self.local.ids = []

    def take(self) -> list[str]:
        ids, self.local.ids = list(getattr(self.local, "ids", []) or []), None
        return ids


def tool_evidence(run_ids: list[str]) -> grounding.Evidence:
    """그 실행들(과 아래 일꾼 실행)의 입력(user 메시지)과 도구 결과로 근거 장부를 만든다. 러너가 검사에 쓴 장부와 같게 (H6).
    잘려서 JSON 이 깨진 줄(예전 기록)은 잘린 원문을 근거로 쓰지 않고 건너뛴다."""
    evidence = grounding.Evidence()
    for run_id in run_ids:
        for step in trace.steps_of(run_id):
            if step["kind"] not in ("start", "tool") or not step.get("detail"):
                continue
            try:
                detail = json.loads(step["detail"])
            except (TypeError, ValueError):
                logger.warning("잘린 실행 기록은 근거로 쓰지 않아요: %s %s %s", step["run_id"], step["kind"], step.get("name"))
                continue
            if step["kind"] == "start":
                if isinstance(detail, dict) and detail.get("input"):
                    evidence.add("input", detail["input"])
            else:
                evidence.add(step.get("name") or "tool", detail.get("result", detail) if isinstance(detail, dict) else detail)
    return evidence


def cause_found(text: str, expect: dict, confidence: str | None) -> bool:
    if expect.get("confidence"):
        return confidence == expect["confidence"]
    return bool(text) and all(any(word in text for word in group) for group in expect["groups"])


# ── 진단 ──


def _diagnosis_t001(system: str, case_id: str, post) -> dict:
    from Harness.agents import complaint_agent
    from Harness.spec import RunContext

    snap = scenarios.snapshot(case_id)
    item = scenarios.plan_item(snap, scenarios.RISK_PLAN_ID)
    ctx = RunContext(snapshot=snap, now=scenarios.NOW_T001, post=post)
    if system == "B":
        proposal = complaint_agent.diagnose(item, ctx)
    else:
        proposal = systems.get("A").task("diagnose")(item, ctx)
    content = proposal.content if proposal else {}
    hypotheses = [h.get("text", "") for h in content.get("hypotheses") or []]
    return {"source": proposal.source if proposal else "NONE", "text": " ".join(hypotheses), "hypotheses": hypotheses,
            "confidence": content.get("confidence"), "checklist": content.get("checklist") or []}


def _diagnosis_voice(system: str, view, now: dt.datetime) -> dict:
    from voice.agents import improve_tip

    if system == "B":
        tip = improve_tip.suggest(view, now)
    else:
        tip = systems.get("A").task("voice_prepare")(view, [], now, tip=True)["tip"]
    return {"source": tip.get("source") or "NONE", "text": tip.get("text") or "", "hypotheses": [tip.get("text") or ""],
            "confidence": None, "checklist": []}


def voice_view(gold_rows: list[dict]):
    """d4 의 초옹장 보기 (사례마다 새로). 정답 세트 리뷰를 날짜만 옮겨 넣는다."""
    from Harness.evals.reply_eval import eval_menus, fixture_now, load_fixture
    from voice.context import VoiceStore

    fixture = load_fixture()
    now = fixture_now(fixture)
    reviews, topic = scenarios.voice_reviews(gold_rows, now)
    data = {"review": reviews, "weather": list(fixture.get("weather", [])), "event": [], "game": []}
    store = {**fixture["store"], "menus": eval_menus(), "facts": load_store_facts()}  # 평가용 초옹장 메뉴·가게 사실 (확인함)
    return VoiceStore(store["id"], store, data, now), now, topic


def diagnosis_row(system: str, run: int, case_id: str, *, gold_rows: list[dict], post, run_ids: RunIds) -> dict:
    from voice import clock, context

    events = EventPost(post)
    counting = report.CountingPost(events)
    run_ids.start()
    started = time.perf_counter()
    error = None
    expect = scenarios.EXPECT[case_id]
    try:
        if system == RULE:
            found = rule_diagnosis(case_id, gold_rows)
            if case_id == "d4":
                expect = scenarios.d4_expect(voice_view(gold_rows)[2])
        elif case_id == "d4":
            view, now, topic = voice_view(gold_rows)
            expect = scenarios.d4_expect(topic)
            saved = context.post
            context.post = counting
            clock.set_now(now)
            try:
                found = _diagnosis_voice(system, view, now)
            finally:
                context.post = saved
                clock.set_now(None)
        else:
            found = _diagnosis_t001(system, case_id, counting)
    except Exception as exc:  # 한 사례가 실패해도 나머지는 잰다
        found, error = {"source": "NONE", "text": "", "hypotheses": [], "confidence": None, "checklist": []}, f"{type(exc).__name__}: {exc}"
    ids = run_ids.take()
    rule = system == RULE
    loose = grounding.ungrounded_numbers(found["text"], tool_evidence(ids)) if found["text"] and not rule else []
    if rule:  # 규칙 문장의 숫자는 데이터에서 센 것이라 근거 대조 대상이 아니다
        cause, detail, stats = None, "", {}
    else:
        steps = [step for run_id in ids for step in trace.steps_of(run_id)]
        cause, detail = fail_cause.classify(found["source"], steps, events.events, top_run_id=ids[0] if ids else None)
        stats = fail_cause.submit_stats(steps)
    return {
        "case_id": case_id, "part": "diagnosis", "system": system, "run": run, "run_id": ids[0] if ids else None,
        "source": found["source"], "output": found["text"], "hypotheses": found["hypotheses"], "confidence": found["confidence"],
        "checklist": found["checklist"], "expect": expect, "cause_found": cause_found(found["text"], expect, found["confidence"]),
        "ungrounded_numbers": loose, "grounded": None if rule else bool(found["text"]) and not loose,
        "fail_cause": cause, "fail_detail": detail, "transport_events": list(events.events), "submit_stats": stats,
        "calls": counting.calls, "tokens": list(counting.tokens), "seconds": round(time.perf_counter() - started, 3), "error": error,
    }


# ── 묶음 조율 ──


def _review_case(snap, item) -> dict | None:
    """답글 할 일 → reply 스위트 채점에 쓰는 리뷰 정보 (재주문 인사는 None)."""
    if item.task_type != "REVISIT_REPLY":
        return None
    review = next((r for r in snap.reviews if r.review_id == item.basis.ref_id), None)
    if review is None or review.label is None:
        return None
    return {"text": review.text, "order_channel": "hall" if review.platform == "NAVER" else "delivery",
            "gold": {"sentiment": review.label.sentiment, "complaint_types": list(review.label.complaint_types), "reply": None}}


def reply_fit(snap, item, proposal, mode: str, judge_post) -> dict | None:
    """답글 하나가 reply 스위트 기준으로 적합한지. 답글 할 일이 아니면 None."""
    from Harness.evals.reply_eval import judge_reply

    case = _review_case(snap, item)
    if case is None:
        return None
    text = (proposal.content.get("text") if proposal else "") or ""
    if not text.strip():
        return {"fit": False, "conditions": {}, "error": "답글 없음"}
    menus = [m.name for m in snap.inputs.menus]
    checks = reply_checks.checks(text, review_text=case["text"], order_channel=case["order_channel"],
                                 sentiment=case["gold"]["sentiment"], complaint_types=case["gold"]["complaint_types"],
                                 own_menus=menus, other_menus=[], today=f"{scenarios.NOW_T001:%Y-%m-%d}")
    verdicts, error = judge_reply(case, text, menus, snap.store.get("category", ""), mode, judge_post)
    conditions = {name: (verdicts.get(name) or {}).get("ok") for name in judge.REPLY_CONDITIONS}
    conditions["format"] = reply_checks.format_ok(checks)
    return {"fit": all(v is True for v in conditions.values()), "conditions": conditions, "error": error}


def consistency_left(snap, plan_ids: list[str], proposals: dict, mode: str, judge_post) -> tuple[bool, dict]:
    """답글·진단 불일치가 남았는지: 진단 가설과 같은 불만 답글을 심판 consistency 로 본다. '아니오'·판단 불가면 남은 것."""
    fix = proposals.get(scenarios.RISK_PLAN_ID)
    replies = [pid for pid in plan_ids if pid.startswith("REVISIT_REPLY") and proposals.get(pid)]
    if fix is None or not replies or not fix.content.get("hypotheses"):
        return False, {}
    diagnosis = " ".join(h.get("text", "") for h in fix.content["hypotheses"])
    out = {}
    for pid in replies:
        case = _review_case(snap, scenarios.plan_item(snap, pid))
        data = judge.JudgeInput(review_text=case["text"], reply=proposals[pid].content.get("text", ""),
                                category=snap.store.get("category", ""), sentiment=case["gold"]["sentiment"],
                                complaint_types=case["gold"]["complaint_types"], menus=[m.name for m in snap.inputs.menus],
                                diagnosis=diagnosis)
        try:
            verdict = judge.judge("consistency", data, mode=mode, store_id="eval:batch",
                                  post=GuardedPost(judge_post, deadline=JUDGE_DEADLINE_SECONDS))
            out[pid] = verdict.as_dict()
        except CaseAborted as error:
            out[pid] = {"ok": None, "error": f"심판: {error}"}
    return any(v.get("ok") is not True for v in out.values()), out


def remaining(case_id: str, snap, plan_ids: list[str], proposals: dict, notes: dict, mode: str, judge_post) -> tuple[list[str], dict]:
    """최종 묶음에 남은 심은 충돌 종류들과 심판 기록."""
    from Harness.conflicts import find_conflicts
    from Harness.spec import RunContext

    planted = scenarios.PLANTED[case_id]
    live = {p: v for p, v in proposals.items() if v is not None}
    ctx = RunContext(snapshot=snap, now=scenarios.NOW_T001)
    rule = {c.kind for c in find_conflicts(plan_ids, live, ctx)}
    left, judged = [], {}
    for kind in planted:
        if kind == "REPLY_VS_DIAGNOSIS":
            still, judged = consistency_left(snap, plan_ids, live, mode, judge_post)
            if still:
                left.append(kind)
        elif kind in rule:
            left.append(kind)
    return left, judged


def _rework(run_id: str | None) -> dict:
    """B supervisor 실행의 재작업 요청(ask_* 도구) 수: 할 일별, 합. 기록이 깨져 할 일을 모르는 요청은 unreadable 로 따로 센다."""
    per_item: Counter = Counter()
    unreadable = 0
    if run_id:
        for step in trace.steps_of(run_id):
            if step["kind"] == "tool" and str(step.get("name") or "").startswith("ask_"):
                try:
                    args = json.loads(step["detail"]).get("args") or {}
                except (TypeError, ValueError, AttributeError):
                    unreadable += 1
                    continue
                per_item[args.get("plan_id") or "?"] += 1
    total = sum(per_item.values()) + unreadable  # 묶음당 한도는 할 일을 몰라도 센다
    from Harness.supervisor import MAX_REVISIONS

    return {"per_item": dict(per_item), "total": total, "ok": total <= MAX_REVISIONS and all(n <= 1 for n in per_item.values()),
            "unreadable": unreadable}


def batch_row(system: str, run: int, case_id: str, *, mode: str, post, judge_post, run_ids: RunIds) -> dict | None:
    if system == RULE:  # 규칙 기준선은 묶음 조율을 하지 않는다 (해당 없음)
        return None
    from Harness.spec import RunContext

    snap = scenarios.snapshot(case_id)
    plan_ids = scenarios.BATCH_PLAN_IDS[case_id]
    items = [scenarios.plan_item(snap, pid) for pid in plan_ids]
    if system == "A" and any(item.task_type not in A_TASK_TYPES for item in items):
        return None  # A 는 포스터·메뉴판을 맡지 않는다
    counting = report.CountingPost(post)
    ctx = RunContext(snapshot=snap, now=scenarios.NOW_T001, post=counting)
    fixed = scenarios.fixed_proposals()
    before = {pid: fixed[pid] for pid in plan_ids}
    run_ids.start()
    started = time.perf_counter()
    error, notes, headline, source, rework = None, {}, None, "NONE", None
    try:
        if system == "B":
            from Harness.supervisor import coordinate_batch

            result = coordinate_batch(plan_ids, dict(before), ctx)
            final, notes, headline, source = result.proposals, result.item_notes, result.headline, result.source
            rework = _rework(result.run_id if result.source != "NONE" else None)
        else:
            final = systems.get("A").task("batch")(items, ctx)
            sources = {p.source for p in final.values() if p is not None}
            source = "AGENT" if sources == {"AGENT"} else "FALLBACK" if sources else "NONE"
    except Exception as exc:
        final, error = {pid: None for pid in plan_ids}, f"{type(exc).__name__}: {exc}"
    seconds = round(time.perf_counter() - started, 3)
    ids = run_ids.take()
    calls = counting.calls
    left, judged = remaining(case_id, snap, plan_ids, final, notes, mode, judge_post)
    fit_after = {pid: reply_fit(snap, item, final.get(pid), mode, judge_post) for pid, item in zip(plan_ids, items)}
    fit_before = ({pid: reply_fit(snap, item, before.get(pid), mode, judge_post) for pid, item in zip(plan_ids, items)}
                  if system == "B" else {})
    return {
        "case_id": case_id, "part": "batch", "system": system, "run": run, "run_id": ids[0] if ids else None, "source": source,
        "planted": scenarios.PLANTED[case_id], "left": left, "consistency": judged, "headline": headline, "item_notes": notes,
        "output": {pid: (p.content if p else None) for pid, p in final.items()},
        "fit_before": {k: v for k, v in fit_before.items() if v is not None},
        "fit_after": {k: v for k, v in fit_after.items() if v is not None},
        "rework": rework, "calls": calls, "tokens": list(counting.tokens), "seconds": seconds, "error": error,
    }


# ── 채점 (건수) ──


def _count(id: str, name: str, system: str, count: int, total: int, *, question: int, higher: bool = True) -> dict:
    return metrics.value_metric(id, name, question=question, system=system, value=count if total else None, unit="cases",
                                higher_is_better=higher, note=f"{system} {total}건 중 {count}건" if total else "해당 사례 없음")


def score(name: str, rows: list[dict]) -> list[dict]:
    from Harness.evals.reply_eval import attempt_metrics, cause_metrics

    diag = [r for r in rows if r["part"] == "diagnosis"]
    batch = [r for r in rows if r["part"] == "batch"]
    rule = name == RULE
    agentic = [] if rule else diag  # 규칙 기준선에는 근거 대조·과제 완료가 해당 없음
    out = [
        _count("diagnosis_cause_found", "심은 원인을 찾은 진단", name, sum(r["cause_found"] for r in diag), len(diag),
               question=QUESTION_FIT),
        _count("diagnosis_grounded", "숫자 근거가 맞는 진단", name, sum(bool(r["grounded"]) for r in agentic), len(agentic),
               question=QUESTION_FIT),
        _count("diagnosis_agent", "진단 과제 완료 (AGENT)", name, sum(r["source"] == "AGENT" for r in agentic), len(agentic),
               question=QUESTION_TASK),
    ]
    if not rule and diag:
        out.extend({**m, "id": f"diagnosis_{m['id']}", "name": f"진단 {m['name']}"} for m in cause_metrics(name, diag))
        out.extend({**m, "id": f"diagnosis_{m['id']}", "name": f"진단 {m['name']}"} for m in attempt_metrics(name, diag))
    planted = sum(len(r["planted"]) for r in batch)
    left = sum(len(r["left"]) for r in batch)
    out.append(metrics.value_metric("conflicts_left", "남은 충돌", question=QUESTION_TASK, system=name,
                                    value=left if planted else None, unit="conflicts", higher_is_better=False,
                                    note=f"심은 충돌 {planted}개 중 {left}개 남음" if planted else "해당 사례 없음"))
    after = [v for r in batch for v in r["fit_after"].values()]
    out.append(_count("fit_in_batch", "묶음 안 답글 적합 (조율 후)", name, sum(v["fit"] for v in after), len(after),
                      question=QUESTION_FIT))
    before = [v for r in batch for v in r["fit_before"].values()]
    if before:
        out.append(_count("fit_in_batch_before", "묶음 안 답글 적합 (조율 전)", name, sum(v["fit"] for v in before), len(before),
                          question=QUESTION_FIT))
    reworked = [r for r in batch if r["rework"] is not None]
    if reworked:
        out.append(_count("rework_limit_ok", "재작업 한도 지킴", name, sum(r["rework"]["ok"] for r in reworked), len(reworked),
                          question=QUESTION_TASK))
    clean = [r for r in batch if not r["planted"]]
    if name == "B" and clean:
        out.append(_count("no_conflict_calls", "충돌 없는 묶음에서 추가 호출 0", name, sum(r["calls"] == 0 for r in clean),
                          len(clean), question=QUESTION_TASK))
    return out


# ── 실행 ──


def evaluate(names: list[str], *, runs: int = 1, mode: str = "tools", gold_rows: list[dict] | None = None,
             diagnosis_ids=scenarios.DIAGNOSIS_CASES, batch_ids=scenarios.BATCH_CASES, post=None, judge_post=None,
             on_case=None) -> dict:
    """진단·묶음 사례 × 시스템 × 회차. 사례는 하나씩 돈다 (음성 쪽 시계·post 가 모듈 전역이라)."""
    post = post or httpx.post
    rows = []
    saved_env = {key: os.environ.get(key) for key in SWITCHES}
    os.environ.update(SWITCHES)
    restore_cache = report.disable_cache()  # 회차마다, 같은 입력의 다른 사례마다 새로 부르게
    try:
        with RunIds() as run_ids:
            for run in range(1, runs + 1):
                for name in names:
                    for case_id in diagnosis_ids:
                        if case_id == "d4" and not gold_rows:
                            continue
                        row = diagnosis_row(name, run, case_id, gold_rows=gold_rows or [], post=post, run_ids=run_ids)
                        rows.append(row)
                        if on_case:
                            on_case(row)
                    for case_id in batch_ids:
                        row = batch_row(name, run, case_id, mode=mode, post=post, judge_post=judge_post, run_ids=run_ids)
                        if row is not None:
                            rows.append(row)
                            if on_case:
                                on_case(row)
    finally:
        restore_cache()
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return {"metrics": [m for name in names for m in score(name, [r for r in rows if r["system"] == name])], "cases": rows}


def run(args: argparse.Namespace):
    """python -m Harness.evals batch --systems A,B --runs 3 [--judge-mode tools]. 정답지는 d4 에만 쓴다 (없으면 d4 를 뺀다)."""
    names = args.system_names
    try:
        path, sha, gold_rows = gold.from_args(args)
    except gold.GoldError as error:
        print(f"[알림] 정답지 없이 d4 를 뺍니다: {error}", flush=True)
        path, sha, gold_rows = None, None, []
    mode = args.judge_mode
    restore_cache = report.disable_cache()
    try:
        config = {"model": settings.clova_studio_model, "judge_model": settings.eval_judge_model, "judge_mode": mode,
                  "judge_mode_note": "guards 결과로 기본 방식을 정하기 전 임시 값" if mode == "tools" else "",
                  "judge_votes": judge.VOTES, "runs": args.runs, "switches": dict(SWITCHES), "store_facts": load_store_facts(),
                  "a_skips": ["b_menu (포스터는 단일 에이전트가 맡지 않음)"]}
        eval_run = report.start("batch", config=config, systems=names)
        if path:
            eval_run.config["gold"] = gold.config_entry(path, sha)
        print(f"결과 폴더: {eval_run.out}", flush=True)
        jsonl = eval_run.out / "cases.jsonl"

        def on_case(row: dict) -> None:
            with jsonl.open("a", encoding="utf-8") as file:
                file.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            flag = row.get("cause_found") if row["part"] == "diagnosis" else f"남은 충돌 {row['left']}"
            print(f"  [{row['system']} 회차{row['run']}] {row['case_id']} {row['source']} {flag} 호출 {row['calls']}"
                  + (f" 오류 {row['error']}" if row["error"] else ""), flush=True)

        result = evaluate(names, runs=args.runs, mode=mode, gold_rows=gold_rows, on_case=on_case)
        eval_run.metrics, eval_run.cases = result["metrics"], result["cases"]
        out = eval_run.finish()
        print(f"result.json: {out}")
        return out
    finally:
        restore_cache()
