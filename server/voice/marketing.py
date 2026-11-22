"""마케팅 부서의 오늘 계획 (에이전트 조직 개편 6단계, donna-voice/docs/agent-org-plan.md).

브리핑 준비 때(밤) 인스타를 연결한 가게만 돈다: 소재 발굴 사원(agents/topic_finder) → 피드·캡션 작성 사원(agents/caption_writer).
결과는 repo 종류 marketing_plan (id <가게>:<날짜>) 에 남고, 부서 사이 충돌 거르기(departments.cross_check)가 뺄 수 있다(lead.verdict=drop).
instagram/posts.build_feed 가 읽는다.
  {store_id, date, menu_ids, angle, body, hashtags, sources: {topic, caption}, lead}
사원이 실패하면 그 부분만 지금 규칙(이번 달 많이 나간 메뉴 3개, 템플릿 글)으로 둔다. 올리는 것은 사장님이 "올려" 한 뒤다.
감사팀(voice/audit/)이 끝내 통과시키지 않으면: 인턴·사원은 소재면 계획 없음(지금 규칙), 캡션이면 템플릿 글.
대리는 걸린 것 그대로 두고 audit_hold 를 적어 묻지 않고 올리지 않게 한다 (briefing.auto_instagram, step_instagram).
  + {audit: {topic, caption}, audit_hold}
"""

from voice import audit, clock, repo

KIND = "marketing_plan"


def plan_id(store_id: str, day: str) -> str:
    return f"{store_id}:{day}"


def today(view) -> dict | None:
    """오늘 계획 (부서 사이 충돌로 뺀 것은 None)."""
    found = repo.get(KIND, plan_id(view.store_id, view.now.date().isoformat()))
    return None if not found or (found.get("lead") or {}).get("verdict") == "drop" else found


def plan_today(view) -> dict | None:
    """인스타를 연결한 가게의 오늘 소재·글을 하루 한 번 만든다."""
    from voice.agents import caption_writer, topic_finder
    from voice.instagram import posts

    day = view.now.date().isoformat()
    if not posts.connection(view.store_id)["connected"] or repo.get(KIND, plan_id(view.store_id, day)):
        return None
    topic = topic_finder.suggest(view)
    settled = audit.settle(view.store_id, "instagram_post", topic["audit"]) if topic else "ok"
    if topic is None or settled == "template":
        return None
    names = [m["name"] for m in view.menus if m["id"] in topic["menu_ids"]]
    caption = caption_writer.write(view, names, topic["angle"], posts.quote(view))
    caption_settled = audit.settle(view.store_id, "instagram_post", caption["audit"]) if caption else "ok"
    hold = "hold" in (settled, caption_settled)
    if caption_settled == "template":  # 캡션만 템플릿 글로 (캡션 담당에게만 되돌렸다)
        caption = None
    if hold:
        from voice.audit import log as audit_log

        for ref, found in ((f"topic:{day}", settled), (f"caption:{day}", caption_settled)):
            if found == "hold":
                audit_log.mark_hold(view.store_id, ref)
    return repo.put(KIND, plan_id(view.store_id, day), view.store_id, {
        "store_id": view.store_id, "date": day, "menu_ids": topic["menu_ids"], "angle": topic["angle"],
        "body": caption["body"] if caption else None, "hashtags": caption["hashtags"] if caption else [],
        "sources": {"topic": "AGENT", "caption": "AGENT" if caption else "TEMPLATE"}, "lead": None, "created_at": clock.iso(clock.now()),
        "audit": {"topic": topic["audit"], "caption": caption["audit"] if caption else None}, "audit_hold": hold,
    })
