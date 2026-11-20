"""부서 팀장 판단과 도나의 부서 사이 충돌 거르기 (에이전트 조직 개편 7단계, donna-voice/docs/agent-org-plan.md 7-1·7-2).

브리핑 준비(밤)에서 사원들이 끝난 뒤 돈다.
  1. 팀장 (agents/team_lead): 부서마다 오늘 사원 결과를 판단한다. 뺀 할 일 제안은 state=dropped, 마케팅 계획은 lead.verdict=drop
  2. 부서 보고: repo 종류 dept_report (id <가게>:<날짜>:<부서>) {dept, date, items, verdicts, order, summary, source}
  3. 부서 사이 충돌 (코드): 최근 7일 아쉬운 리뷰에 나온 메뉴를 마케팅이 올리자고 하면 마케팅 계획을 뺀다
     (Harness/conflicts.py PROMOTES_COMPLAINED_MENU 와 같은 생각). 빼면 인스타는 지금 규칙(많이 나간 메뉴)으로 돌아간다
도나는 이 결과를 읽어 묶어 보고한다: 브리핑은 뺀 것을 묻지 않고(proposals.for_briefing), 남긴 순서로 묻는다.
팀장이 실패하거나 꺼져 있으면 모두 남긴다 (lead.source=FALLBACK).
"""

import datetime as dt

from voice import clock, marketing, proposals, repo, staff
from voice.clock import parse

KIND = "dept_report"
COMPLAINT_DAYS = dt.timedelta(days=7)


def report_id(store_id: str, day: str, dept: str) -> str:
    return f"{store_id}:{day}:{dept}"


def _proposal_items(view, day: str) -> dict[str, list[dict]]:
    """오늘 물을, 아직 팀장이 보지 않은 할 일 제안 (부서별)."""
    from voice.jobs import staff_tasks

    found: dict[str, list[dict]] = {}
    for p in proposals.for_briefing(view.store_id, day):
        if p.get("lead"):
            continue
        text = f"{p['payload']['title']} — {p['payload'].get('detail') or ''} ({staff_tasks._why(view, p, view.now)})"
        found.setdefault(p["dept"], []).append({"id": p["id"], "by": p["by"], "text": text})
    return found


def _already(store_id: str, day: str) -> list[str]:
    return [t["title"] for t in staff.store_tasks(store_id) if not t["canceled"] and (t["repeat"] == "daily" or t["date"] <= day <= t["until"])]


def _apply(view, dept: str, items: list[dict], result: dict | None, day: str) -> dict:
    verdicts = result["verdicts"] if result else {i["id"]: {"verdict": "keep", "reason": ""} for i in items}
    order = result["order"] if result else [i["id"] for i in items]
    source = "AGENT" if result else "FALLBACK"
    for item in items:
        verdict = verdicts[item["id"]]
        lead = {**verdict, "rank": order.index(item["id"]) if item["id"] in order else len(order), "source": source}
        if dept == "marketing":
            plan = repo.get(marketing.KIND, item["id"])
            repo.put(marketing.KIND, item["id"], view.store_id, {**plan, "lead": lead})
            continue
        found = proposals.get(item["id"])
        repo.put(proposals.KIND, item["id"], view.store_id,
                 {**found, "lead": lead, **({"state": "dropped"} if verdict["verdict"] == "drop" else {})})
    return repo.put(KIND, report_id(view.store_id, day, dept), view.store_id, {
        "dept": dept, "date": day, "items": [i["id"] for i in items], "verdicts": verdicts, "order": order,
        "summary": result["summary"] if result else None, "source": source, "at": clock.iso(clock.now()),
    })


def run_leads(view) -> list[dict]:
    """세 부서 팀장을 돌리고 부서 보고를 남긴다. 그 뒤 부서 사이 충돌을 거른다."""
    from voice.agents import team_lead

    day = view.now.date().isoformat()
    groups = _proposal_items(view, day)
    plan = repo.get(marketing.KIND, marketing.plan_id(view.store_id, day))
    if plan and not plan.get("lead"):
        groups["marketing"] = [{"id": marketing.plan_id(view.store_id, day), "by": "topic_finder",
                                "text": f"인스타 소재: {plan['angle']} / 글: {plan.get('body') or '(템플릿 글)'}"}]
    reports = []
    for dept, items in groups.items():
        result = team_lead.review(view, dept, items, already=_already(view.store_id, day))
        reports.append(_apply(view, dept, items, result, day))
    cross_check(view)
    return reports


def lead_one(view, proposal: dict) -> bool:
    """영업 중 바로 묻는 제안 하나를 팀장이 짧게 본다 (2026-11-20 결정: 실시간 길도 팀장을 거친다). 남기면 True."""
    from voice.agents import team_lead
    from voice.jobs import staff_tasks

    day = view.now.date().isoformat()
    item = {"id": proposal["id"], "by": proposal["by"],
            "text": f"{proposal['payload']['title']} — {proposal['payload'].get('detail') or ''} ({staff_tasks._why(view, proposal, view.now)})"}
    result = team_lead.review(view, proposal["dept"], [item], already=_already(view.store_id, day), realtime=True)
    verdict = result["verdicts"][proposal["id"]] if result else {"verdict": "keep", "reason": ""}
    found = proposals.get(proposal["id"])
    repo.put(proposals.KIND, proposal["id"], view.store_id, {
        **found, "lead": {**verdict, "rank": 0, "source": "AGENT" if result else "FALLBACK"},
        **({"state": "dropped"} if verdict["verdict"] == "drop" else {})})
    return verdict["verdict"] == "keep"


def complained_menus(view) -> set[str]:
    """최근 7일 아쉬운 리뷰 글에 나온 메뉴 id."""
    since = view.now - COMPLAINT_DAYS
    texts = [r.get("text", "") for r in view.reviews() if r.get("sentiment") == "negative" and parse(r["written_at"]) >= since]
    return {m["id"] for m in view.menus if any(m["name"] in t for t in texts)}


def cross_check(view) -> list[str]:
    """부서 사이 충돌 (코드, LLM 없음). 걸린 것의 설명 목록."""
    found = []
    plan = repo.get(marketing.KIND, marketing.plan_id(view.store_id, view.now.date().isoformat()))
    if plan and (plan.get("lead") or {}).get("verdict") != "drop":
        bad = complained_menus(view) & set(plan["menu_ids"])
        if bad:
            names = [m["name"] for m in view.menus if m["id"] in bad]
            reason = f"아쉬운 리뷰가 있는 메뉴({', '.join(names)})를 홍보하지 않아요"
            repo.put(marketing.KIND, marketing.plan_id(view.store_id, plan["date"]), view.store_id,
                     {**plan, "lead": {"verdict": "drop", "reason": reason, "rank": 0, "source": "CROSS_CHECK"}})
            found.append(reason)
    return found
