"""현장 변수 사원: 오늘 날씨·예약(특이사항 메모)을 보고 알바생 할 일을 제안한다 (에이전트 조직 개편 5단계, agent-org-plan.md 5-2).

원칙 한 줄(프롬프트): 오늘의 날씨·예약 때문에 평소 매뉴얼에 없는 일이 필요한가? 필요할 때만, 없으면 빈 목록.
검사
  1. quote 가 그 출처(오늘 날씨 또는 그 예약)의 도구 결과에 글자 그대로 있다
  2. 숫자는 도구 결과에 있는 것만 (근거 대조). 알레르기는 메모에 적힌 이름 그대로만 (틀리면 위험한 정보)
  3. 제목·내용 폭, 가격·약속 금지, 알바생이 할 수 없는 일 금지 (quote_judge staff_scope. 묻지 못하면 내지 않는다)
결과는 제안뿐이다. 사장님께 매번 묻고(2026-11-20 결정), 승인하면 넣는다 (jobs/staff_tasks.py).
today_impact 가 참이면 긴급이다 (오늘 안 하면 손님이 바로 겪는 일, proposals.urgent).
"""

import re

from Harness import guards, runner
from Harness.agents import quote_judge
from Harness.grounding import Evidence, ungrounded_numbers
from Harness.spec import AgentSpec, Budget, RunContext, Tool
from Harness.tools import NO_ARGS, array, obj, string
from voice import clock, config, proposals, repo, staff, width
from voice.agents import load_prompt
from voice.context import VoiceStore, run_context

MAX_ITEMS = 3
RUN_KIND = "field_run"  # 그날 현장 변수 사원을 돌렸다는 표시 (브리핑 준비가 여러 번 돌아도 하루 한 번)
UNCHECKED = "검토 안 됨"
ALLERGY_RE = re.compile(r"(\S+?)\s*알레르기")
PHASES = ["before_open", "open", "closing"]
# 모델에게는 우리말로 고르게 하고 코드로 바꾼다. 영어 값(before_open …)을 enum 이나 설명에 두면, 모델이 앞서 글로 쓴 계획에 끌려
# 다른 값을 쓰려다 CLOVA 가 생성을 40009 ("Unsupported function")로 버렸다. 우리말 enum 은 같은 대화에서 3번 모두 통과 (2026-11-21 재현)
PHASE_LABELS = {"문 열기 전": "before_open", "영업 중": "open", "마감": "closing"}
PHASE_OF = {**PHASE_LABELS, **{p: p for p in PHASES}}


def _view(ctx: RunContext) -> VoiceStore:
    return ctx.snapshot  # type: ignore[return-value]


def today_weather(ctx: RunContext, task: dict, args: dict) -> dict:
    day = ctx.now.date().isoformat()
    w = next((w for w in _view(ctx).data.get("weather", []) if w["date"] == day), None)
    if not w:
        return {"note": "오늘 날씨 정보가 없어요"}
    from voice.jobs.briefing import rain_text

    rain = rain_text(w, ctx.now.date()) if w.get("rain_chance", 0) >= 0.6 else None  # '오후 2시부터 비' (브리핑과 같은 말)
    return {"id": f"weather:{day}", "label": w.get("label"), "rain_chance_percent": round(w.get("rain_chance", 0) * 100),
            "rain_mm": w.get("rain_mm"), "temp_min": w.get("temp_min"), "temp_max": w.get("temp_max"), "rain": rain}


def today_reservations(ctx: RunContext, task: dict, args: dict) -> dict:
    day = ctx.now.date().isoformat()
    found = [{"id": r["id"], "time": r["starts_at"][11:16], "people": r["party_size"], "memo": r.get("memo")}
             for r in _view(ctx).data.get("reservation", []) if r["starts_at"][:10] == day]
    return {"reservations": sorted(found, key=lambda r: r["time"])} if found else {"note": "오늘 예약이 없어요"}


def staff_tasks(ctx: RunContext, task: dict, args: dict) -> dict:
    tasks = [t for t in staff.store_tasks(ctx.store_id) if not t["canceled"]]
    return {"manual": [t["title"] for t in tasks if t["repeat"] == "daily"],
            "today": [t["title"] for t in tasks if t["repeat"] != "daily" and t["date"] <= ctx.now.date().isoformat() <= t["until"]]}


WEATHER = Tool("get_today_weather", "오늘 날씨 (비 시작 시각, 강수확률, 기온)", NO_ARGS, today_weather)
RESERVATIONS = Tool("get_today_reservations", "오늘 예약 (시각, 인원, 손님이 남긴 특이사항 메모)", NO_ARGS, today_reservations)
TASKS = Tool("get_staff_tasks", "알바생 매뉴얼(매일 할 일)과 오늘 이미 있는 할 일 제목", NO_ARGS, staff_tasks)
ITEM = obj({
    "title": string(f"알바생 화면에 보일 짧은 제목 ({width.limit_note('staff.title')})"),
    "detail": string(f"무엇을 어떻게 하는지 한 문장 ({width.limit_note('staff.detail')})"),
    "phase": string("언제 할 일인가", enum=list(PHASE_LABELS)),
    "today_impact": {"type": "boolean", "description": "오늘 안 하면 손님이 바로 겪는 일이면 true"},
    "source_type": string("근거", enum=["weather", "reservation"]),
    "source_id": string("근거의 id (날씨 id 또는 예약 id)"),
    "quote": string("근거 도구 결과에서 글자 그대로 옮긴 말"),
})
SUBMIT = Tool("submit_field_tasks", "오늘 날씨·예약 때문에 필요한 알바생 할 일 (없으면 빈 목록)",
              obj({"items": array(ITEM, f"할 일 목록. 최대 {MAX_ITEMS}개, 필요 없으면 빈 목록")}))


def user_message(task: dict, ctx: RunContext) -> str:
    return f"오늘: {ctx.now:%Y-%m-%d}\n오늘 날씨와 예약을 보고, 평소 매뉴얼에 없는 알바생 할 일이 필요하면 submit_field_tasks 로 내 줘."


def _source_text(ctx: RunContext, item: dict) -> str:
    if item.get("source_type") == "weather":
        return str(today_weather(ctx, {}, {}))
    found = next((r for r in today_reservations(ctx, {}, {}).get("reservations", []) if r["id"] == item.get("source_id")), None)
    return str(found) if found else ""


def check(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    items = args.get("items")
    if not isinstance(items, list):
        return "items 는 목록이어야 해요"
    if len(items) > MAX_ITEMS:
        return f"할 일은 {MAX_ITEMS}개까지만 내 주세요"
    for n, item in enumerate(items, 1):
        title, detail = (item.get("title") or "").strip(), (item.get("detail") or "").strip()
        quote = (item.get("quote") or "").strip()
        if not title or not detail or item.get("phase") not in PHASE_OF:
            return f"{n}번째 할 일의 title, detail 을 채우고 phase 는 {', '.join(PHASE_LABELS)} 중 하나로 써 주세요"
        source = _source_text(ctx, item)
        if not source:
            return f"{n}번째 할 일의 source_id '{item.get('source_id')}' 는 오늘 날씨·예약에 없어요"
        if not quote or quote not in source:
            return f"{n}번째 할 일의 quote 는 근거 도구 결과에서 글자 그대로 옮겨 주세요"
        if not width.fits(title, "staff.title"):
            return f"{n}번째 할 일의 " + width.too_long("title", title, "staff.title")
        if not width.fits(detail, "staff.detail"):
            return f"{n}번째 할 일의 " + width.too_long("detail", detail, "staff.detail")
        reason = guards.first(guards.price_or_discount(f"{title} {detail}"), guards.promise(f"{title} {detail}"))
        if reason:
            return reason
        loose = ungrounded_numbers(f"{title} {detail}", evidence)
        if loose:
            return f"{n}번째 할 일에 도구 결과에 없는 숫자가 있어요: {', '.join(dict.fromkeys(loose))}"
        allergies = ALLERGY_RE.findall(f"{title} {detail}")
        made_up = [a for a in allergies if a not in source]  # 손님 정보는 그 할 일의 근거(그 예약 메모)에만 있어야 한다
        if made_up:
            return (f"{n}번째 할 일의 알레르기({', '.join(made_up)})는 그 할 일의 근거에 없어요. "
                    "알레르기는 그 예약 메모를 근거로 한 할 일에만, 메모에 적힌 그대로 써 주세요")
        outside = quote_judge.ask("staff_scope", f"{title}. {detail}", ctx)
        if outside is None:
            notes.append(UNCHECKED)
            return None
        if outside:
            return f"{n}번째 할 일에 알바생이 지금 있는 것으로 할 수 없는 일이 있어요: {', '.join(outside)}"
    return None


SPEC = AgentSpec(
    name="voice_field_tasks",
    system_prompt=lambda task, ctx: load_prompt("field_tasks.txt", ctx.store),
    user_message=user_message,
    tools=[WEATHER, RESERVATIONS, TASKS],
    submit=SUBMIT,
    check=check,
    task_id=lambda task: task["date"],
    budget=Budget(max_steps=5, max_rejections=2, max_seconds=40),
    temperature=0.3,
)


def suggest(view: VoiceStore) -> list[dict] | None:
    """[{title, detail, phase, today_impact, source_type, source_id, quote}] 또는 None (끔, 실패, 검토 못 함)."""
    if not config.agent_on("field"):
        return None
    proposal = runner.run(SPEC, {"date": view.now.date().isoformat()}, run_context(view))
    if proposal is None or proposal.source != "AGENT" or UNCHECKED in proposal.notes:
        return None
    return [{k: (v.strip() if isinstance(v, str) else v) for k, v in item.items()} for item in proposal.content.get("items") or []]


def propose_today(view: VoiceStore) -> list[dict]:
    """오늘 몫을 한 번만 제안으로 남긴다 (브리핑 준비가 여러 번 돌아도). 오늘 아침 브리핑에서 묻는다."""
    day = view.now.date().isoformat()
    run_id = f"{view.store_id}:{day}"
    if repo.get(RUN_KIND, run_id):
        return []
    items = suggest(view)
    if items is None:  # 끔·실패: 표시를 남기지 않아 다음 준비 때 다시 해 본다
        return []
    repo.put(RUN_KIND, run_id, view.store_id, {"id": run_id, "date": day, "items": len(items), "at": clock.iso(clock.now())})
    made = []
    for item in items:
        why = (f"오늘 {item['quote']} 소식이 있어요." if item["source_type"] == "weather"
               else f"예약 메모에 '{item['quote']}'라고 있어요.")
        made.append(proposals.create(
            view.store_id, dept="quality", by="field_variable", ask_on=day,
            payload={"title": item["title"], "detail": item["detail"], "phase": PHASE_OF[item["phase"]], "repeat": "today", "days": 1,
                     "must_confirm": True, "urgent": False, "today_impact": bool(item.get("today_impact"))},
            reason={"type": item["source_type"], "id": item["source_id"], "quote": item["quote"], "date": day, "why": why},
        ))
    return made
