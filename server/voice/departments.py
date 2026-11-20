"""부서 보고와 도나의 부서 사이 충돌 거르기 (에이전트 조직 개편 7단계, 2026-11-21 팀장 없앰: donna-voice/docs/agent-structure.md 5장).

브리핑 준비(밤)에서 사원들이 끝난 뒤 돈다.
  1. 부서 보고: repo 종류 dept_report (id <가게>:<날짜>:<부서>) {dept, date, items, order, source: "code"}
     순서는 코드가 정한다: 긴급 → 고객 응대 → 품질 관리 → 마케팅 → 들어온 순서 (proposals.for_briefing)
  2. 부서 사이 충돌 (코드): 최근 7일 아쉬운 리뷰에 나온 메뉴를 마케팅이 올리자고 하면 마케팅 계획을 뺀다
     (Harness/conflicts.py PROMOTES_COMPLAINED_MENU 와 같은 생각). 빼면 인스타는 지금 규칙(많이 나간 메뉴)으로 돌아간다
사원의 검사를 통과한 결과는 모두 남는다. 부서 요약 문장은 도나가 브리핑을 묶을 때 만든다.
"""

import datetime as dt

from voice import marketing, proposals, repo
from voice.clock import parse

KIND = "dept_report"
COMPLAINT_DAYS = dt.timedelta(days=7)


def report_id(store_id: str, day: str, dept: str) -> str:
    return f"{store_id}:{day}:{dept}"


def run_reports(view) -> list[dict]:
    """부서마다 오늘 물을 결과를 보고로 남긴다. 그 뒤 부서 사이 충돌을 거른다."""
    day = view.now.date().isoformat()
    groups: dict[str, list[str]] = {}
    for p in proposals.for_briefing(view.store_id, day):  # 이미 코드 순서대로다
        groups.setdefault(p["dept"], []).append(p["id"])
    if marketing.today(view):
        groups["marketing"] = [marketing.plan_id(view.store_id, day)]
    reports = [repo.put(KIND, report_id(view.store_id, day, dept), view.store_id,
                        {"dept": dept, "date": day, "items": ids, "order": ids, "source": "code"})
               for dept, ids in sorted(groups.items(), key=lambda g: proposals.DEPT_ORDER.index(g[0]))]
    cross_check(view)
    return reports


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
