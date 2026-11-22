"""② 반복 불만 원인 분석 에이전트.

지금 REVIEW_FIX 카드는 "최근 7일 동안 맛 불만이 3건 들어왔어요" 한 줄뿐이다. 이 에이전트가 주문 시각, 근무 인원,
날씨를 오가며 원인 가설과 점검 목록을 붙인다.

task 키
  plan_id          REVIEW_FIX 할 일 id (없으면 risk_id 로 대신)
  risk_id          위험 신호 id
  supervisor_note  supervisor 가 준 조율 지시 (있을 때)

검사: 근거 대조 엄격 모드. 가설과 점검 목록의 모든 숫자가 입력이나 도구 결과에 있어야 한다.
가설마다 실제로 부른 도구를 evidence 로 1개 이상 적어야 한다.
물러나기: 지금의 이유 한 줄.
"""

import datetime as dt
from collections import Counter

from app.analysis.review.hcx_classifier import mask_personal_info
from app.core.seoul_time import to_seoul
from app.planner.data_shapes import PlanItem, RiskSignal
from app.planner.rule_complaint_fix import COMPLAINT_NAMES
from Harness import runner
from Harness.grounding import Evidence, ungrounded_numbers
from Harness.spec import AgentSpec, Budget, Proposal, RunContext, Tool
from Harness.store_tools import DAY_CONTEXT, day_label, hour_label, parse_date
from Harness.tools import array, load_prompt, obj, string

PLATFORM_NAMES = {"BAEMIN": "배달의민족", "NAVER": "네이버 플레이스", "YOGIYO": "요기요", "COUPANG": "쿠팡이츠"}
CHANNEL_NAMES = {"HALL": "매장", "DELIVERY": "배달", "TAKEOUT": "포장", "BAEMIN": "배달의민족", "YOGIYO": "요기요", "COUPANG": "쿠팡이츠"}
USUAL_DAYS = 28  # 평소: 구간 앞 4주
MAX_RANGE_DAYS = 14
MAX_HYPOTHESIS = 80
MAX_CHECK_ITEM = 40


def find_risk(ctx: RunContext, risk_id: str) -> RiskSignal | None:
    return next((r for r in ctx.snapshot.risk_signals if r.risk_id == risk_id), None)


def task_for_plan_item(item: PlanItem, ctx: RunContext) -> dict:
    if item.task_type != "REVIEW_FIX":
        raise ValueError(f"반복 불만 할 일이 아니에요: {item.task_type}")
    return {"plan_id": item.plan_id, "risk_id": item.basis.ref_id}


# ── 도구 ──


def risk_reviews(ctx: RunContext, task: dict, args: dict) -> dict:
    risk = find_risk(ctx, task["risk_id"])
    if risk is None:
        return {"error": "위험 신호를 찾지 못했어요"}
    inputs = ctx.snapshot.inputs
    orders = {o.order_id: o for o in inputs.orders}
    menu_names = {m.menu_id: m.name for m in inputs.menus}
    items_by_order: dict[str, list[str]] = {}
    for item in inputs.order_items:
        items_by_order.setdefault(item.order_id, []).append(menu_names.get(item.menu_id, item.menu_id))
    rows, hours, weekdays, channels, menus = [], Counter(), Counter(), Counter(), Counter()
    by_id = {r.review_id: r for r in ctx.snapshot.reviews}
    for review_id in risk.review_ids:
        review = by_id.get(review_id)
        if review is None:
            continue
        order = orders.get(review.order_id) if review.order_id else None
        row = {
            "written": f"{day_label(to_seoul(review.written_at).date())} {hour_label(to_seoul(review.written_at).hour)}",
            "rating": review.rating,
            "platform": PLATFORM_NAMES.get(review.platform, review.platform),
            "text": mask_personal_info(review.text)[:80],
        }
        if order is not None:
            at = to_seoul(order.ordered_at)
            ordered_menus = items_by_order.get(order.order_id, [])
            row["order"] = {"at": f"{day_label(at.date())} {hour_label(at.hour)}",
                            "channel": CHANNEL_NAMES.get(order.channel, order.channel), "menus": ordered_menus}
            hours[hour_label(at.hour)] += 1
            weekdays[day_label(at.date())[-4:-1]] += 1
            channels[CHANNEL_NAMES.get(order.channel, order.channel)] += 1
            menus.update(set(ordered_menus))
        rows.append(row)
    return {
        "complaint": COMPLAINT_NAMES[risk.complaint_type],
        "review_count": len(rows),
        "reviews": rows,
        "common": {
            "order_hours": dict(hours.most_common()),
            "order_weekdays": dict(weekdays.most_common()),
            "channels": dict(channels.most_common()),
            "menus": dict(menus.most_common(5)),
        },
    }


def _hour_counts(ctx: RunContext, first: dt.date, last: dt.date) -> Counter:
    counts = Counter()
    for order in ctx.snapshot.inputs.orders:
        at = to_seoul(order.ordered_at)
        if first <= at.date() <= last and order.ordered_at <= ctx.now:
            counts[at.hour] += 1
    return counts


def orders_by_hour(ctx: RunContext, task: dict, args: dict) -> dict:
    try:
        first, last = parse_date(args.get("date_from")), parse_date(args.get("date_to"))
    except ValueError as error:
        return {"error": str(error)}
    if last < first:
        first, last = last, first
    if (last - first).days + 1 > MAX_RANGE_DAYS:
        return {"error": f"구간은 {MAX_RANGE_DAYS}일 이하로 잡아 주세요"}
    days = (last - first).days + 1
    now_counts = _hour_counts(ctx, first, last)
    usual_counts = _hour_counts(ctx, first - dt.timedelta(days=USUAL_DAYS), first - dt.timedelta(days=1))
    rows = []
    for hour in sorted(set(now_counts) | set(usual_counts)):
        per_day = now_counts[hour] / days
        usual = usual_counts[hour] / USUAL_DAYS
        rows.append({
            "hour": hour_label(hour),
            "orders_per_day": round(per_day, 1),
            "usual_per_day": round(usual, 1),
            "times_usual": round(per_day / usual, 1) if usual else None,
        })
    busiest = max(rows, key=lambda r: r["orders_per_day"])["hour"] if rows else None
    return {"from": day_label(first), "to": day_label(last), "days": days, "usual_days": USUAL_DAYS,
            "busiest_hour": busiest, "by_hour": rows}


def staff_shifts(ctx: RunContext, task: dict, args: dict) -> dict:
    try:
        day = parse_date(args.get("date"))
    except ValueError as error:
        return {"error": str(error)}
    on_duty: dict[int, set[str]] = {}
    for shift in ctx.snapshot.inputs.shifts:
        start, end = to_seoul(shift.starts_at), to_seoul(shift.ends_at)
        for hour in range(24):
            slot_start = dt.datetime.combine(day, dt.time(hour), tzinfo=start.tzinfo)
            if start < slot_start + dt.timedelta(hours=1) and end > slot_start:
                on_duty.setdefault(hour, set()).add(shift.staff_key)
    return {
        "date": day_label(day),
        "staff_total": len(set().union(*on_duty.values())) if on_duty else 0,
        "by_hour": [{"hour": hour_label(h), "staff": len(keys)} for h, keys in sorted(on_duty.items())],
        "note": "근무 기록에 있는 인원만 센다. 직원 이름은 주지 않는다",
    }


RISK_REVIEWS = Tool("get_risk_reviews", "불만 리뷰들의 주문 시각, 요일, 메뉴, 채널, 리뷰 글과 공통점 집계", obj({}), risk_reviews)
ORDERS_BY_HOUR = Tool(
    "get_orders_by_hour",
    "날짜 구간(14일 이하)의 시간대별 하루 평균 주문 수와 평소(구간 앞 4주) 대비 배수",
    obj({"date_from": string("시작 날짜 YYYY-MM-DD"), "date_to": string("끝 날짜 YYYY-MM-DD")}),
    orders_by_hour,
)
STAFF_SHIFTS = Tool("get_staff_shifts", "그날 시간대별 근무 인원 수 (이름 없음)", obj({"date": string("날짜 YYYY-MM-DD")}), staff_shifts)
SUBMIT = Tool(
    "submit_diagnosis",
    "원인 가설과 점검 목록을 제출한다",
    obj({
        "hypotheses": array(
            obj({"text": string("가설 한 문장, 80자 안, '~요'로 끝"), "evidence": array(string("도구 이름"), "근거가 된 도구 이름")}),
            "원인 가설 1~2개",
        ),
        "checklist": array(string("점검할 일, 40자 안"), "사장님이 점검할 일 정확히 3개"),
        "confidence": string("근거가 분명하면 high, 공통점을 못 찾았으면 low", ["high", "low"]),
    }),
)


# ── 프롬프트와 검사 ──


def user_message(task: dict, ctx: RunContext) -> str:
    risk = find_risk(ctx, task["risk_id"])
    if risk is None:
        text = f"위험 신호 {task['risk_id']} 를 찾지 못했어요. confidence low 로 제출해 줘."
    else:
        first, last = to_seoul(risk.first_at).date(), to_seoul(risk.last_at).date()
        text = (
            f"반복 불만: {COMPLAINT_NAMES[risk.complaint_type]}\n"
            f"근거 리뷰 {len(risk.review_ids)}건, 첫 리뷰 {day_label(first)}, 마지막 리뷰 {day_label(last)} "
            f"({first.isoformat()} ~ {last.isoformat()})\n"
            f"오늘: {day_label(to_seoul(ctx.now).date())}\n"
            "주문량·근무 인원은 불만 주문이 있던 날짜로 조회해. 오늘은 아직 영업 중이라 비교에 쓰지 마.\n"
            "도구로 공통점을 찾아 submit_diagnosis 로 내줘."
        )
    if task.get("supervisor_note"):
        text += f"\n\n조율 지시: {task['supervisor_note']}"
    return text


def check(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    confidence = args.get("confidence")
    if confidence not in ("high", "low"):
        return "confidence 는 high 나 low 여야 해요"
    hypotheses, checklist = args.get("hypotheses"), args.get("checklist")
    if not isinstance(hypotheses, list) or not 1 <= len(hypotheses) <= 2:
        return f"가설(hypotheses)은 1~2개여야 해요 (지금 {len(hypotheses) if isinstance(hypotheses, list) else 0}개)"
    if not isinstance(checklist, list) or len(checklist) != 3:
        return f"점검 목록(checklist)은 정확히 3개여야 해요 (지금 {len(checklist) if isinstance(checklist, list) else 0}개)"
    called = set(evidence.sources()) - {"input"}
    texts = []
    for h in hypotheses:
        if not isinstance(h, dict) or not str(h.get("text") or "").strip():
            return "가설마다 text 가 있어야 해요"
        text = str(h["text"]).strip()
        if len(text) > MAX_HYPOTHESIS:
            return f'가설 "{text}"({len(text)}자)를 {MAX_HYPOTHESIS}자 이하로 줄여 주세요'
        cited = [str(e) for e in h.get("evidence") or []]
        if confidence == "high" and not set(cited) & called:
            return f"가설 '{text}' 의 evidence 에 실제로 부른 도구 이름을 1개 이상 적어 주세요 (부른 도구: {', '.join(sorted(called)) or '없음'})"
        texts.append(text)
    for item in checklist:
        item = str(item).strip()
        if not item or len(item) > MAX_CHECK_ITEM:
            return f'점검할 일 "{item}"({len(item)}자)을 1~{MAX_CHECK_ITEM}자로 써 주세요'
        texts.append(item)
    loose = ungrounded_numbers(" ".join(texts), evidence)
    if loose:
        return f"도구 결과에 없는 숫자를 썼어요: {', '.join(dict.fromkeys(loose))}. 도구가 준 숫자만 쓰거나 숫자를 빼 주세요"
    return None


def finalize(args: dict, task: dict, ctx: RunContext) -> dict:
    return {
        "risk_id": task["risk_id"],
        "confidence": args["confidence"],
        "hypotheses": [{"text": str(h["text"]).strip(), "evidence": [str(e) for e in h.get("evidence") or []]} for h in args["hypotheses"]],
        "checklist": [str(item).strip() for item in args["checklist"]],
    }


def fallback(task: dict, ctx: RunContext) -> dict | None:
    """지금의 이유 한 줄 (rule_complaint_fix 와 같은 문장)."""
    risk = find_risk(ctx, task["risk_id"])
    if risk is None:
        return None
    line = f"최근 7일 동안 {COMPLAINT_NAMES[risk.complaint_type]} 불만이 {len(risk.review_ids)}건 들어왔어요."
    return {"risk_id": risk.risk_id, "confidence": "none", "hypotheses": [], "checklist": [], "reason_line": line}


SPEC = AgentSpec(
    name="complaint_agent",
    system_prompt=lambda task, ctx: load_prompt("complaint_agent.txt", ctx.store),
    user_message=user_message,
    tools=[RISK_REVIEWS, ORDERS_BY_HOUR, STAFF_SHIFTS, DAY_CONTEXT],
    submit=SUBMIT,
    check=check,
    task_id=lambda task: task.get("plan_id") or task["risk_id"],
    fallback=fallback,
    finalize=finalize,
    budget=Budget(max_steps=8, max_rejections=2, max_seconds=60),
    temperature=0.2,
    cache_scope=lambda task: task["risk_id"],  # risk_id 는 user 메시지에 없고 도구와 finalize 가 읽는다 (H8)
)


def diagnose(item: PlanItem, ctx: RunContext, *, supervisor_note: str | None = None) -> Proposal | None:
    """반복 불만 할 일(REVIEW_FIX)의 원인 가설과 점검 목록."""
    task = task_for_plan_item(item, ctx)
    if supervisor_note:
        task["supervisor_note"] = supervisor_note
    return runner.run(SPEC, task, ctx)
