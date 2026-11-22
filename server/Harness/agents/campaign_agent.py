"""③ 상황 마케팅 에이전트: 메뉴판 후보와 포스터 멘트를 한 번에 정해 같은 날의 주제를 맞춘다.

지금은 메뉴 후보(menu_candidates)와 포스터 멘트(ment.suggest)를 따로 물어 같은 날 주제가 어긋날 수 있다.
포스터 이미지 생성은 에이전트 밖에서 지금의 poster_ai/jobs.py 가 한다.

task 키
  plan_id          MENU_ORDER 또는 POSTER 할 일 id
  date             그날 (YYYY-MM-DD)
  tag              "EVENT" | "GAME" | "SEASON" | None  (과거 비슷한 날 메뉴 비중을 찾을 기준)
  kind             세부 종류 (UNIV_FESTIVAL, NATIONAL_TEAM, WINTER …) | None
  ref_id           행사·경기 id | None
  exclude_menu_ids supervisor 가 빼라고 한 메뉴 id 목록 (있을 때)
  supervisor_note  supervisor 가 준 조율 지시 (있을 때)

검사: 메뉴 id·이름 목록 대조, 길이(headline 18자, line 45자, reason 60자), 가격·할인·보상 금지,
판매 주장("인기" 등)은 과거 비슷한 날 데이터(n ≥ 1)를 조회했을 때만, 숫자는 근거 대조.
물러나기: 지금의 menu_candidates() + ment.suggest().
"""

import datetime as dt
import json
import re

from app.core.seoul_time import to_seoul
from app.menu_board.menu_candidates import KIND_NAMES, menu_candidates
from app.menu_board.menu_share_lift import menu_share_lift
from app.planner.data_shapes import PlanItem
from app.poster_ai import ment
from app.poster_ai.situation import from_plan
from Harness import guards, runner
from Harness.grounding import Evidence, ungrounded_numbers
from Harness.spec import AgentSpec, Budget, Proposal, RunContext, Tool
from Harness.store_tools import DAY_CONTEXT, MENU_LIST, day_label, hour_label
from Harness.tools import array, load_prompt, obj, string

MAX_MENUS = 5
MAX_REASON = 60
MAX_THEME = 40
MAX_LABEL = 10
# 기존 포스터 멘트 검사(ment._clean)가 허용하던 여유와 같게: 프롬프트는 18자·45자를 부탁하고, 검사는 +4자·+15자까지 받는다
MAX_HEADLINE = ment.HEADLINE_MAX + 4
MAX_LINE = ment.LINE_MAX + 15
MENT_KINDS = ["EVENT", "GAME", "WEATHER", "MENU"]
SIMILAR_DAY_TOOL = "get_similar_day_menu_share"
HANGUL_RE = re.compile(r"[가-힣]")
DEFAULT_LABELS = {"EVENT": "행사 손님", "GAME": "응원 문구", "WEATHER": "날씨 메뉴", "MENU": "대표 메뉴"}


# ── task 만들기 ──


def _situation_of(ctx: RunContext, day: dt.date, ref_id: str | None) -> tuple[str | None, str | None, str | None]:
    """(tag, kind, ref_id). 행사·경기 id 가 주어지면 그것을, 아니면 그날 달력 이유 중 효과가 가장 큰 것을 쓴다."""
    inputs = ctx.snapshot.inputs
    event = next((e for e in inputs.events if e.event_id == ref_id), None) if ref_id else None
    if event:
        return "EVENT", event.kind, event.event_id
    game = next((g for g in inputs.games if g.game_id == ref_id), None) if ref_id else None
    if game:
        return "GAME", game.kind, game.game_id
    reasons = [r for c in ctx.snapshot.calendar_cells if c.date == day for r in c.reasons if r.tag in ("EVENT", "GAME", "SEASON")]
    if not reasons:
        return None, None, None
    best = max(reasons, key=lambda r: r.effect)
    if best.tag == "SEASON":
        return "SEASON", best.ref_id.removeprefix("season_").upper(), None
    return _situation_of(ctx, day, best.ref_id)


def task_for_plan_item(item: PlanItem, ctx: RunContext) -> dict:
    parts = item.plan_id.split(":")
    if item.task_type not in ("MENU_ORDER", "POSTER") or len(parts) != 3:
        raise ValueError(f"메뉴판·포스터 할 일이 아니에요: {item.plan_id}")
    day = dt.date.fromisoformat(parts[2])
    ref_id = parts[1] if item.task_type == "POSTER" else None
    tag, kind, ref = _situation_of(ctx, day, ref_id)
    return {"plan_id": item.plan_id, "date": day.isoformat(), "tag": tag, "kind": kind, "ref_id": ref}


# ── 도구 ──


def similar_day_menu_share(ctx: RunContext, task: dict, args: dict) -> dict:
    tag, kind = task.get("tag"), task.get("kind")
    if not tag or not kind:
        return {"n": 0, "note": "비교할 행사·경기·계절이 없는 날이에요"}
    lift = menu_share_lift(ctx.snapshot.inputs, tag, kind, dt.date.fromisoformat(task["date"]))
    names = {m.menu_id: m.name for m in ctx.snapshot.inputs.menus}
    ranked = sorted(lift.lift_pp.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "situation": KIND_NAMES.get(kind, kind),
        "n": lift.n,
        "n_eff": round(lift.n_eff, 1),
        "unit": "%p (평소 판매 비중 대비 변화)",
        "menus": [{"menu_id": m, "name": names.get(m, m), "lift_pp": round(v, 1)} for m, v in ranked[:8]],
    }


def event_detail(ctx: RunContext, task: dict, args: dict) -> dict:
    inputs = ctx.snapshot.inputs
    ref = task.get("ref_id")
    event = next((e for e in inputs.events if e.event_id == ref), None)
    if event:
        return {"type": "행사", "title": event.title, "kind": KIND_NAMES.get(event.kind, event.kind),
                "distance_km": round(event.distance_km, 1),
                "starts": f"{day_label(to_seoul(event.start_at).date())} {hour_label(to_seoul(event.start_at).hour)}",
                "ends": day_label(to_seoul(event.end_at).date())}
    game = next((g for g in inputs.games if g.game_id == ref), None)
    if game:
        return {"type": "경기", "title": game.title, "kind": KIND_NAMES.get(game.kind, game.kind),
                "starts": f"{day_label(to_seoul(game.start_at).date())} {hour_label(to_seoul(game.start_at).hour)}"}
    return {"type": "없음", "note": "행사·경기가 없는 날이에요", "situation": KIND_NAMES.get(task.get("kind") or "", "")}


SIMILAR_DAY = Tool(
    SIMILAR_DAY_TOOL,
    "과거 비슷한 날(같은 종류 행사·경기·계절) 메뉴별 판매 비중이 평소보다 몇 %p 달라졌는지. n 은 쓴 날 수",
    obj({}),
    similar_day_menu_share,
)
EVENT_DETAIL = Tool("get_event_detail", "이번 행사·경기의 이름, 종류, 거리, 시작 시각", obj({}), event_detail)
SUBMIT = Tool(
    "submit_campaign",
    "그날의 메뉴판 후보와 포스터 문구를 제출한다",
    obj({
        "theme": string("그날의 주제 한 줄"),
        "menu_ids": array(string("menu_id"), "메뉴판 맨 위에 올릴 메뉴 id 1~5개, 어울리는 순서대로"),
        "reason": string("고른 이유 한 문장, 60자 안, '~요.'로 끝"),
        "ments": array(
            obj({
                "kind": string("문구 종류", MENT_KINDS),
                "label": string("사장님이 고를 때 볼 이름, 10자 안"),
                "headline": string("포스터 큰 글자, 18자 안. 줄을 나누려면 \\n"),
                "line": string("작은 글자 한 문장, 45자 안"),
                "menu": string("추천 메뉴 이름 그대로, 없으면 빈 글자"),
            }),
            "포스터 문구. 처음에는 3개, 거절된 뒤에는 아직 필요한 개수만",
        ),
    }, required=[]),  # 거절된 뒤에는 아직 확정되지 않은 부분만 낸다 (통과한 부분은 확정된다)
)


# ── 프롬프트와 검사 ──


def user_message(task: dict, ctx: RunContext) -> str:
    day = dt.date.fromisoformat(task["date"])
    situation = KIND_NAMES.get(task.get("kind") or "", "행사·경기·계절 없음")
    text = f"날짜: {day_label(day)}\n상황: {situation}\n도구로 확인한 뒤 submit_campaign 으로 내줘."
    names = _menu_names(ctx)
    excluded = [names.get(m, m) for m in task.get("exclude_menu_ids") or []]
    if excluded:
        text += f"\n빼야 할 메뉴: {', '.join(excluded)}"
    if task.get("supervisor_note"):
        text += f"\n\n조율 지시: {task['supervisor_note']}"
    return text


def _menu_names(ctx: RunContext) -> dict[str, str]:
    return {m.menu_id: m.name for m in ctx.snapshot.inputs.menus}


def _similar_day_n(evidence: Evidence) -> int:
    best = 0
    for entry in evidence.entries:
        if entry["source"] == SIMILAR_DAY_TOOL:
            try:
                best = max(best, int(json.loads(entry["text"]).get("n", 0)))
            except (ValueError, TypeError, AttributeError):
                continue
    return best


def _too_long(what: str, value: str, limit: int) -> str | None:
    """길이 거절 이유: 어느 칸의 어떤 값이 몇 자인지, 몇 자로 줄여야 하는지까지 적는다 (모델이 그 칸만 고치게)."""
    if not value:
        return f"{what} 가 비었어요. 채워 주세요"
    if len(value) > limit:
        return f'{what} "{value}"({len(value)}자)를 {limit}자 이하로 줄여 주세요'
    return None


def _reason_text(reason: str) -> str:
    """끝맺음만 틀린 이유는 고쳐 쓴다: '~요', '~요!' → '~요.' (형식은 코드가 고치고 판단만 모델에게 묻는다)."""
    trimmed = reason.strip().rstrip("!~ ")
    return trimmed + "." if trimmed.endswith("요") else reason.strip()


def _check_ment(number: int, raw: object, menu_names: set[str], excluded_names: list[str]) -> str | None:
    what = f"{number}번 문구"
    if not isinstance(raw, dict):
        return f"{what}에 kind, label, headline, line, menu 를 채워 주세요"
    kind, label = raw.get("kind"), str(raw.get("label") or "").strip()
    headline = str(raw.get("headline") or "").replace("\\n", "\n").strip()
    line, menu = str(raw.get("line") or "").strip(), str(raw.get("menu") or "").strip()
    whole = f"{headline} {line}"
    excluded = next((name for name in excluded_names if name in whole or name == menu), None)
    return guards.first(
        None if kind in MENT_KINDS else f"{what} kind 는 {', '.join(MENT_KINDS)} 중 하나여야 해요 (지금: {kind})",
        None if not HANGUL_RE.search(label) else _too_long(f"{what} label", label, MAX_LABEL),  # 한글이 아니면 finalize 가 채운다
        _too_long(f"{what} headline", headline.replace("\n", ""), MAX_HEADLINE),
        _too_long(f"{what} line", line, MAX_LINE),
        None if not menu or menu in menu_names else f'{what} menu "{menu}" 는 메뉴 목록에 없어요. 목록의 이름을 그대로 쓰거나 비워 주세요',
        None if not guards.price_or_discount(whole) else f"{what}: {guards.price_or_discount(whole)}",
        None if not guards.promise(whole) else f"{what}: {guards.promise(whole)}",
        None if not excluded else f"{what}에 빼야 할 메뉴({excluded})를 썼어요. 다른 메뉴로 바꿔 주세요",
    )


def _check_menu_part(args: dict, evidence: Evidence, task: dict, names: dict[str, str]) -> str | None:
    """메뉴판 부분(theme, menu_ids, reason) 검사."""
    excluded = list(task.get("exclude_menu_ids") or [])
    menu_ids = [str(m) for m in args.get("menu_ids") or []] if isinstance(args.get("menu_ids"), list) else []
    theme, reason = str(args.get("theme") or "").strip(), _reason_text(str(args.get("reason") or ""))
    banned = next((m for m in menu_ids if m in excluded), None)
    claims = guards.sales_claim_words(reason)
    loose = ungrounded_numbers(f"{theme} {reason}", evidence)
    return guards.first(
        _too_long("theme", theme, MAX_THEME),
        None if 1 <= len(menu_ids) <= MAX_MENUS else f"menu_ids 는 1~{MAX_MENUS}개여야 해요 (지금 {len(menu_ids)}개)",
        None if len(set(menu_ids)) == len(menu_ids) else "menu_ids 에 같은 id 가 겹쳤어요",
        None if not guards.not_in(menu_ids, names, "") else f"menu_ids 에 목록에 없는 menu_id 가 있어요: {', '.join(m for m in menu_ids if m not in names)}",
        None if banned is None else f"빼야 할 메뉴({names.get(banned, banned)}, {banned})를 menu_ids 에서 빼 주세요",
        _too_long("reason", reason, MAX_REASON),
        None if reason.endswith("요.") else f'reason "{reason}" 을 \'~요.\'로 끝나는 한 문장으로 써 주세요',
        guards.price_or_discount(reason),
        None if not claims or _similar_day_n(evidence) >= 1 else (
            f"reason 의 판매 주장({', '.join(claims)})은 {SIMILAR_DAY_TOOL} 결과(n 1 이상)가 있을 때만 쓸 수 있어요. 그 말을 빼 주세요"),
        None if not loose else f"theme·reason 에 도구 결과에 없는 숫자를 썼어요: {', '.join(dict.fromkeys(loose))}. 그 숫자를 빼 주세요",
    )


def _check_one_ment(number: int, raw: object, evidence: Evidence, task: dict, names: dict[str, str], taken: list[dict]) -> str | None:
    """문구 하나 검사. taken: 이미 확정한 문구 (같은 문구는 다시 받지 않는다)."""
    excluded_names = [names[m] for m in task.get("exclude_menu_ids") or [] if m in names]
    problem = _check_ment(number, raw, set(names.values()), excluded_names)
    if problem:
        return problem
    text = f"{raw.get('headline')} {raw.get('line')}"
    claims = guards.sales_claim_words(text)
    if claims and _similar_day_n(evidence) < 1:
        return f"{number}번 문구의 판매 주장({', '.join(claims)})은 {SIMILAR_DAY_TOOL} 결과(n 1 이상)가 있을 때만 쓸 수 있어요. 그 말을 빼 주세요"
    loose = ungrounded_numbers(text, evidence)
    if loose:
        return f"{number}번 문구에 도구 결과에 없는 숫자를 썼어요: {', '.join(dict.fromkeys(loose))}. 그 숫자를 빼 주세요"
    for key in ("headline", "line"):
        value = str(raw.get(key) or "").strip()
        if any(str(t.get(key) or "").strip() == value for t in taken):
            return f'{number}번 문구의 {key} "{value}" 는 이미 확정한 문구와 같아요. 다른 방향(행사, 날씨, 대표 메뉴 중 아직 안 쓴 것)으로 새로 써 주세요'
    return None


def check(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    """통과한 부분은 task["_locked"] 에 확정하고, 틀린 부분만 다시 받는다.

    실제 CLOVA 는 거절 이유를 받아도 제출 전체를 거의 그대로 다시 내는 일이 잦았다 (같은 문구 3개를 세 번 연속).
    그래서 한 번에 하나만 고치면 되게, 맞은 부분은 확정하고 거절 메시지에 아직 필요한 것만 적는다.
    """
    names = _menu_names(ctx)
    locked = task.setdefault("_locked", {"menu": None, "ments": []})
    problems: list[str] = []

    if locked["menu"] is None:
        if any(args.get(key) for key in ("theme", "menu_ids", "reason")):
            problem = _check_menu_part(args, evidence, task, names)
            if problem:
                problems.append(problem)
            else:
                locked["menu"] = {"theme": str(args["theme"]).strip(), "menu_ids": [str(m) for m in args["menu_ids"]],
                                  "reason": _reason_text(str(args["reason"]))}
        else:
            problems.append("메뉴판 부분(theme, menu_ids, reason)이 아직 없어요")

    ments = args.get("ments") if isinstance(args.get("ments"), list) else []
    for number, raw in enumerate(ments, 1):
        if len(locked["ments"]) >= 3:
            break
        problem = _check_one_ment(number, raw, evidence, task, names, locked["ments"])
        if problem:
            problems.append(problem)
        else:
            locked["ments"].append(raw)

    if locked["menu"] is not None and len(locked["ments"]) >= 3:
        return None
    done = (["메뉴판(theme, menu_ids, reason)"] if locked["menu"] else []) + [
        f'문구 "{_one_line(m.get("headline"))}"' for m in locked["ments"]]
    need = (["메뉴판(theme, menu_ids, reason)"] if locked["menu"] is None else []) + (
        [f"포스터 문구 {3 - len(locked['ments'])}개"] if len(locked["ments"]) < 3 else [])
    return (
        f"확정한 것: {', '.join(done) or '없음'}. 아직 필요한 것: {', '.join(need)}.\n"
        + ("걸린 이유:\n- " + "\n- ".join(problems) if problems else "")
    )


def _one_line(text: object) -> str:
    return str(text or "").replace("\\n", " ").replace("\n", " ").strip()


def _label(ment: dict) -> str:
    """label 은 사장님이 고를 때 보는 이름일 뿐이라, 한글이 아니면(실제 CLOVA 가 event1 을 고집한 일이 있다) 거절 대신 채운다."""
    label = str(ment.get("label") or "").strip()
    return label if HANGUL_RE.search(label) else DEFAULT_LABELS[ment["kind"]]


def finalize(args: dict, task: dict, ctx: RunContext) -> dict:
    """여러 번에 걸쳐 확정한 부분(task["_locked"])으로 제안을 만든다."""
    locked = task["_locked"]
    return {
        **locked["menu"],
        "ments": [
            {"kind": m["kind"], "label": _label(m), "headline": str(m["headline"]).replace("\\n", "\n").strip(),
             "line": str(m["line"]).strip(), "menu": str(m.get("menu") or "").strip()}
            for m in locked["ments"][:3]
        ],
    }


def fallback(task: dict, ctx: RunContext) -> dict | None:
    """지금의 menu_candidates() + (포스터 할 일이면) ment.suggest()."""
    excluded = set(task.get("exclude_menu_ids") or [])
    picked = menu_candidates(ctx.store, ctx.snapshot.inputs.menus, task["kind"], post=ctx.post) if task.get("kind") else None
    menu_ids = [m for m in (picked.menu_ids if picked else ()) if m not in excluded]
    ments = []
    if task["plan_id"].startswith("POSTER:"):
        ments = [m.to_dict() for m in ment.suggest(from_plan(ctx.snapshot, task["plan_id"]))[0]]
    if not menu_ids and not ments:
        return None
    return {"theme": "", "menu_ids": menu_ids, "reason": picked.reason if picked and menu_ids else "", "ments": ments}


SPEC = AgentSpec(
    name="campaign_agent",
    system_prompt=lambda task, ctx: load_prompt("campaign_agent.txt", ctx.store),
    user_message=user_message,
    tools=[MENU_LIST, SIMILAR_DAY, DAY_CONTEXT, EVENT_DETAIL],
    submit=SUBMIT,
    check=check,
    task_id=lambda task: task["plan_id"],
    fallback=fallback,
    finalize=finalize,
    budget=Budget(max_steps=6, max_rejections=3, max_seconds=40),  # 검사 항목이 많아 거절을 한 번 더 받는다
    temperature=0.5,
    retry_hint="확정한 부분은 다시 내지 말고, 아직 필요한 것만 넣어 {submit} 로 다시 제출해 줘.",
    # 어느 행사인지(ref_id)는 user 메시지에 없고 도구만 읽는다. plan_id 는 넣지 않는다: 같은 날·같은 상황의 메뉴판과 포스터는 결과를 나눠 쓴다 (H8)
    cache_scope=lambda task: [task["date"], task.get("tag"), task.get("kind"), task.get("ref_id")],
)


def plan_campaign(
    item: PlanItem, ctx: RunContext, *, exclude_menu_ids: list[str] | None = None, supervisor_note: str | None = None,
) -> Proposal | None:
    """메뉴판(MENU_ORDER) / 포스터(POSTER) 할 일의 메뉴 후보와 포스터 문구."""
    task = task_for_plan_item(item, ctx)
    if exclude_menu_ids:
        task["exclude_menu_ids"] = list(exclude_menu_ids)
    if supervisor_note:
        task["supervisor_note"] = supervisor_note
    return runner.run(SPEC, task, ctx)
