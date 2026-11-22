"""현장 변수 사원: 오늘 날씨·예약(특이사항 메모)을 보고 알바생 할 일을 제안한다 (에이전트 조직 개편 5단계, agent-org-plan.md 5-2).

원칙 한 줄(프롬프트): 오늘의 날씨·예약 때문에 평소 매뉴얼에 없는 일이 필요한가? 필요할 때만, 없으면 빈 목록.
검사 (감사팀, voice/audit/)
  1차 코드 감사 rules.field_tasks
    1. quote 가 그 출처(오늘 날씨 또는 그 예약)의 도구 결과에 글자 그대로 있다
    2. 숫자는 도구 결과에 있는 것만 (근거 대조). 알레르기는 메모에 적힌 이름 그대로만 (틀리면 위험한 정보)
    3. 제목·내용 폭, 가격·약속 금지
  2차 LLM 감사 inspector.field_tasks: 할 일마다 알바생이 할 수 없는 일 (quote_judge staff_scope)
  끝내 불합격하거나 감사를 못 하면 내지 않는다 (결정 7)
결과는 제안뿐이다. 사장님께 매번 묻고(2026-11-20 결정), 승인하면 넣는다 (jobs/staff_tasks.py).
today_impact 가 참이면 긴급이다 (오늘 안 하면 손님이 바로 겪는 일, proposals.urgent).
"""

import re

from Harness import runner
from Harness.spec import AgentSpec, Budget, RunContext, Tool
from Harness.tools import NO_ARGS, array, obj, string
from voice import clock, config, notebook, proposals, repo, staff, width
from voice.agents import load_prompt
from voice import audit
from voice.audit import inspector, rules
from voice.audit import log as audit_log
from voice.context import VoiceStore, run_context

MAX_ITEMS = 3
RUN_KIND = "field_run"  # 그날 현장 변수 사원을 돌렸다는 표시 (브리핑 준비가 여러 번 돌아도 하루 한 번)
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


def source_text(ctx: RunContext, item: dict) -> str:
    """할 일 하나의 근거 글 (그 날씨 또는 그 예약). 없는 근거면 빈 글자."""
    if item.get("source_type") == "weather":
        return str(today_weather(ctx, {}, {}))
    found = next((r for r in today_reservations(ctx, {}, {}).get("reservations", []) if r["id"] == item.get("source_id")), None)
    return str(found) if found else ""


SPEC = AgentSpec(
    name="voice_field_tasks",
    system_prompt=lambda task, ctx: load_prompt("field_tasks.txt", ctx.store) + notebook.section(ctx.store_id, "field_variable"),
    user_message=user_message,
    tools=[WEATHER, RESERVATIONS, TASKS],
    submit=SUBMIT,
    check=rules.field_tasks,  # 1차 코드 감사 (감사팀)
    audit=inspector.field_tasks,  # 2차 LLM 감사 (감사팀)
    audit_returns=config.AUDIT_RETURNS,
    audit_seconds=config.AUDIT_ROUND_SECONDS,
    # 캐시 열쇠: 감사 기준 버전과 그날 날씨·예약. 날짜만 쓰면 예약을 바꾼 시연 데이터(s005_choongjang_h)에도 예전 제안을 돌려줬다 (2026-11-22)
    cache_scope=lambda task: (audit.version(), task.get("inputs")),
    task_id=lambda task: task["date"],
    budget=Budget(max_steps=5, max_rejections=2, max_seconds=40),
    temperature=0.3,
)


def suggest(view: VoiceStore) -> list[dict] | None:
    """[{title, detail, phase, today_impact, source_type, source_id, quote}] 또는 None (끔, 실패, 감사를 끝내 통과하지 못함·감사 못 함)."""
    if not config.agent_on("field"):
        return None
    day = view.now.date().isoformat()
    inputs = {"weather": [w for w in view.data.get("weather", []) if w["date"] == day],
              "reservations": [r for r in view.data.get("reservation", []) if r["starts_at"][:10] == day]}
    ctx = run_context(view)
    proposal = runner.run(SPEC, {"date": day, "inputs": inputs}, ctx)
    audit_log.record_run(view.store_id, "field_task", f"field:{day}", proposal, ctx.run_id)
    if proposal is None or proposal.source != "AGENT" or audit.settle(view.store_id, "field_task", proposal.audit) != "ok":
        return None
    return [{k: (v.strip() if isinstance(v, str) else v) for k, v in item.items()} for item in proposal.content.get("items") or []]


def allergy_items(view: VoiceStore) -> list[dict]:
    """예약 메모에 'OO 알레르기'가 있으면 모델 없이 규칙으로 할 일을 만든다 (2026-11-22, Figma v0.2.1 H-11 · H-13).
    알레르기는 틀리면 위험한 정보라서 메모에 적힌 이름 그대로, 영업 중에 모두 확인하는 오늘만 할 일로 둔다."""
    day = view.now.date().isoformat()
    items = []
    for r in sorted((r for r in view.data.get("reservation", []) if r["starts_at"][:10] == day), key=lambda r: r["starts_at"]):
        found = ALLERGY_RE.search(r.get("memo") or "")
        if not found:
            continue
        start = clock.parse(r["starts_at"])
        at = f"{start.hour % 12 or 12}시" + (f" {start.minute}분" if start.minute else "")
        items.append({"title": f"{at} 손님 {found.group(1)} 알레르기", "detail": f"{at} 예약 손님 메모: {r['memo'].strip()}",
                      "phase": "open", "today_impact": True, "source_type": "reservation", "source_id": r["id"], "quote": r["memo"].strip()})
    return items


def propose_today(view: VoiceStore) -> list[dict]:
    """오늘 몫을 한 번만 제안으로 남긴다 (브리핑 준비가 여러 번 돌아도). 오늘 아침 브리핑에서 묻는다.
    알레르기 메모는 규칙으로 먼저 만들고(allergy_items), 모델은 그 밖의 날씨·예약 할 일만 더한다."""
    day = view.now.date().isoformat()
    run_id = f"{view.store_id}:{day}"
    if repo.get(RUN_KIND, run_id):
        return []
    ruled = allergy_items(view)
    suggested = suggest(view)
    if suggested is None and not ruled:  # 끔·실패: 표시를 남기지 않아 다음 준비 때 다시 해 본다
        return []
    covered = {i["source_id"] for i in ruled}
    items = ruled + [i for i in suggested or [] if not (i["source_type"] == "reservation" and i["source_id"] in covered)]
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
