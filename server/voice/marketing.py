"""마케팅 부서의 오늘 계획 (에이전트 조직 개편 6단계, donna-voice/docs/agent-org-plan.md).

브리핑 준비 때(밤) 인스타를 연결한 가게만 돈다: 소재 발굴 사원(agents/topic_finder) → 피드·캡션 작성 사원(agents/caption_writer).
결과는 repo 종류 marketing_plan (id <가게>:<날짜>) 에 남고, 팀장(7단계)이 판단한다. instagram/posts.build_feed 가 읽는다.
  {store_id, date, menu_ids, angle, body, hashtags, sources: {topic, caption}, lead}
사원이 실패하면 그 부분만 지금 규칙(이번 달 많이 나간 메뉴 3개, 템플릿 글)으로 둔다. 올리는 것은 사장님이 "올려" 한 뒤다.
"""

from voice import clock, repo

KIND = "marketing_plan"


def plan_id(store_id: str, day: str) -> str:
    return f"{store_id}:{day}"


def today(view) -> dict | None:
    """오늘 계획 (팀장이 뺀 것은 None)."""
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
    if topic is None:
        return None
    names = [m["name"] for m in view.menus if m["id"] in topic["menu_ids"]]
    caption = caption_writer.write(view, names, topic["angle"], posts.quote(view))
    return repo.put(KIND, plan_id(view.store_id, day), view.store_id, {
        "store_id": view.store_id, "date": day, "menu_ids": topic["menu_ids"], "angle": topic["angle"],
        "body": caption["body"] if caption else None, "hashtags": caption["hashtags"] if caption else [],
        "sources": {"topic": "AGENT", "caption": "AGENT" if caption else "TEMPLATE"}, "lead": None, "created_at": clock.iso(clock.now()),
    })
