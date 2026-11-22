"""아침 브리핑에서 알바생 할 일 묻기 (에이전트 조직 개편 3단계, donna-voice/docs/agent-org-plan.md 3-4).

밤사이 아쉬운 리뷰 교정(고객 응대), 반복 → 매뉴얼(매뉴얼 코칭), 현장 변수(품질 관리) 제안을 한 단계에서 묶어 묻는다.
  "알바생 할 일로 넣을 게 두 개 있어요. 첫째, 배달 용기 이중 실링. … 둘째, … 넣을까요?"
대답: "응" → 모두 넣음 / "두 번째는 빼" → 그것만 빼고 다시 묻기 / "두 번째는 빼고 넣어" → 빼고 넣음 / "안 해" → 모두 안 넣음
브리핑에서 묻지 못한 것은 그날 사장님이 다음에 "도나야"라고 부를 때 먼저 묻는다 (turn.handle). 그날 문 닫을 때까지 못 물으면
다음 준비 때 버린다 (proposals.expire). 사장님 대답 없이는 넣지 않는다.
"""

import datetime as dt
import re

from app.core.seoul_time import at_time
from voice import hours, hr, proposals, speech, width
from voice.clock import parse
from voice.context import VoiceStore

MAX_ASK = width.MAX_ITEMS["rows"]
ALLERGY_RE = re.compile(r"(\S+?)\s*알레르기")
PEOPLE_RE = re.compile(r"(\d+|한|두|세|네|다섯)\s*(?:명|분)")
PEOPLE_WORDS = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5}
ORDINAL = ["첫째", "둘째", "셋째", "넷째"]


def _obj(word: str) -> str:
    return speech.josa(word, "을", "를")


def briefing_day(store: dict, now: dt.datetime, *, after_today: bool = False) -> str:
    """이 제안을 물을 아침 브리핑 날: 오늘 문 열기 전이면 오늘, 아니면 다음 여는 날."""
    day = now.date()
    today = hours.on(store, day)
    if not after_today and today and now < at_time(day, today["open"]):
        return day.isoformat()
    for ahead in range(1, 15):
        if hours.on(store, day + dt.timedelta(days=ahead)):
            return (day + dt.timedelta(days=ahead)).isoformat()
    return (day + dt.timedelta(days=1)).isoformat()


def propose_fix(store_id: str, review: dict, card: dict, *, state: str = "proposed", ask_on: str | None = None) -> dict:
    """아쉬운 리뷰 교정 카드 제안 (모두 확인, 이틀, 긴급 아님)."""
    return proposals.create(
        store_id, dept="customer", by="negative_review", state=state, ask_on=ask_on,
        payload={"title": card["title"], "detail": card["detail"], "phase": "open", "days": 2, "must_confirm": True, "urgent": False},
        reason={"type": "review", "review_id": review["id"]},
        link={"type": "review", "review_id": review["id"], "alert_id": f"al_{review['id']}", "review_text": review["text"]},
    )


def _why(view: VoiceStore, p: dict, now: dt.datetime) -> str:
    reason = p["reason"]
    if reason["type"] == "review":
        from voice.jobs.briefing import _when, told

        review = view.review(reason["review_id"]) or {}
        summary = review.get("summary") or "아쉽다는"
        when = _when(parse(review["written_at"]), now) if review.get("written_at") else "최근"
        return f"{when} {told(summary)} 리뷰 때문이에요."
    if reason["type"] == "repeat":
        return f"일주일에 {speech.count(reason['count'], '번')} 나와서 매일 할 일로 올려요."
    return reason.get("why") or ""  # 현장 변수: "예약 메모에 '…'라고 있어요."


def step(view: VoiceStore, now: dt.datetime, *, lead: list[str] | None = None) -> dict | None:
    """물을 제안이 있으면 ask_tasks 응답. tasks 에 묻는 제안 id 가 순서대로 있다.
    업무 직급대로 (인사과 4-c): 맨 앞 제안의 업무가 인턴이면 그것 하나만, 사원이면 사원 업무 제안을 묶어서 묻는다."""
    from voice.jobs.briefing import answer, say

    found = proposals.for_briefing(view.store_id, now.date().isoformat())
    if not found:
        return None
    if _asks(found[0]) == "each":
        asking = found[:1]
    else:
        asking = [p for p in found if _asks(p) != "each"][:MAX_ASK]
    says = [say(text) for text in lead or []]
    booked = reservation_view(view, asking[0]) if len(asking) == 1 else None
    if booked:  # 예약 손님 요청사항에서 나온 할 일 하나: 예약, 요청, 받는 사람, 기간을 줄로 (H-11)
        says += [say(booked["why"]), say("알바생 할 일에 넣을까요?")]
        response = answer("알바생 할 일에 넣을까요?", says, booked["cards"], kind="ask_tasks", tasks=[asking[0]["id"]])
        response["expects_reply"] = True
        return response
    if len(asking) == 1:
        p = asking[0]
        says += [say(_why(view, p, now)), say(f"알바생 할 일에 {_obj(p['payload']['title'])} 넣을까요?")]
    else:
        says.append(say(f"알바생 할 일로 넣을 게 {speech.count(len(asking), '개')} 있어요."))
        for i, p in enumerate(asking):
            says.append(say(f"{ORDINAL[i]}, {p['payload']['title']}. {_why(view, p, now)}"))
        says.append(say("넣을까요?"))
    items = [{"id": p["id"], "title": f"{i + 1}. {p['payload']['title']}", "sub": p["payload"].get("detail") or "", "state": "todo",
              **({"tone": "urgent"} if p["payload"].get("urgent") else {})} for i, p in enumerate(asking)]
    response = answer("알바생 할 일 넣을까요?", says, [{"type": "checklist", "id": "staff_tasks", "title": "알바생 할 일에 넣을 것",
                                                    "items": items}], kind="ask_tasks", tasks=[p["id"] for p in asking])
    response["expects_reply"] = True
    return response


def reservation_view(view: VoiceStore, p: dict, *, added: bool = False) -> dict | None:
    """예약 메모에서 나온 제안이면 H-11 줄 카드와 요청사항 카드, 그리고 이유 한 마디. 아니면 None.
    알레르기는 메모에 적힌 이름 그대로만 쓴다 (field_tasks 검사와 같은 원칙)."""
    reason = p.get("reason") or {}
    if reason.get("type") != "reservation":
        return None
    found = next((r for r in view.data.get("reservation", []) if r["id"] == reason.get("id")), None)
    memo = (found or {}).get("memo") or reason.get("quote") or ""
    if not found or not memo:
        return None
    start = parse(found["starts_at"])
    hour = start.hour % 12 or 12
    short = f"{hour}시" + (f" {start.minute}분" if start.minute else "")
    rows = [{"id": "t_resv", "kind": "reservation", "value": f"{speech.clock_label(start)} {found['party_size']}명 예약"}]
    allergy, people = ALLERGY_RE.search(memo), PEOPLE_RE.search(memo)
    n = (int(people.group(1)) if people.group(1).isdigit() else PEOPLE_WORDS[people.group(1)]) if people else None
    if allergy:
        rows.append({"id": "t_need", "kind": "warning", "value": f"{allergy.group(1)} 알레르기 손님" + (f" {n}명" if n else "")})
        why = f"{short} 예약 손님 중 {speech.count(n, '분') + '이' if n else '한 분이'} {allergy.group(1)} 알레르기가 있어요."
    else:
        rows.append({"id": "t_need", "kind": "task", "value": width.fit("rows.value", p["payload"]["title"], p["payload"]["title"][:16])})
        why = f"{short} 예약 손님이 요청사항을 남겼어요."
    rows.append({"id": "t_who", "kind": "person", "value": "오늘 나온 사람 모두"})
    rows.append({"id": "t_when", "kind": "time", "value": "오늘만" if p["payload"].get("repeat", "today") == "today" else "매일"})
    card = {"type": "rows", "id": "staff_task_rows", "rows": rows, **({"note": "알바생 할 일에 넣음"} if added else {})}
    cards = [card] if added else [card, {"type": "quote", "id": "staff_task_memo", "label": "예약 손님이 적은 요청사항", "text": f"“{memo}”"}]
    return {"why": why, "cards": cards}


def unasked_today(view: VoiceStore, now: dt.datetime) -> bool:
    """오늘 물을 제안이 남았고, 아직 문 닫기 전이다 (브리핑에서 못 물은 것을 다음 '도나야' 때 묻는다)."""
    if hours.business_day(view.store, now) is None:  # 자정 넘김 가게의 새벽은 어제 영업
        return False
    return bool(proposals.for_briefing(view.store_id, now.date().isoformat()))


def _asks(p: dict) -> str | None:
    return hr.asks(p["store_id"], hr.JOB_OF_PROPOSAL[p["by"]])


def _then_next(view: VoiceStore, response: dict) -> dict:
    """정한 뒤 남은 제안(인턴은 한 건씩, 사원은 넘친 것)이 있으면 이어서 묻는다."""
    from voice import clock

    follow = step(view, clock.now())
    if follow is None:
        return response
    return {**follow, "say": response["say"] + follow["say"]}


def _record(p: dict, reaction: str, said: str | None) -> None:
    """할 일 제안 한 건의 결재를 인사과에 남긴다 (업무는 제안한 담당 by 로 가린다)."""
    hr.record(p["store_id"], hr.JOB_OF_PROPOSAL[p["by"]], p["id"], reaction, said)


def decide(view: VoiceStore, name: str, edits: dict | None, session: dict, said: str | None = None) -> dict:
    """ask_tasks 뒤의 대답. 묻던 제안 id 는 session['tasks_pending'] (말한 순서)."""
    from voice.jobs.briefing import answer, say

    asked = [p for p in (proposals.get(pid) for pid in session.get("tasks_pending") or []) if p and p["state"] == "asked"]
    if not asked:
        session.pop("tasks_pending", None)
        return answer("지금은 물어본 게 없어요", [say("지금은 여쭤본 게 없어요.")], [])
    drop = [asked[i - 1] for i in (edits or {}).get("drop_index") or [] if 1 <= i <= len(asked)]
    keep = [p for p in asked if p not in drop]
    if name in ("action.cancel",) or (edits or {}).get("no_card"):
        for p in asked:
            proposals.decline(p["id"], "owner_no")
            _record(p, "rejected", said)
        session.pop("tasks_pending", None)
        return _then_next(view, answer("넣지 않을게요", [say("네, 알바생 할 일은 넣지 않을게요.")], []))
    if name == "action.approve":
        for p in drop:
            proposals.decline(p["id"], "owner_edit")
            _record(p, "rejected", said)  # "두 번째는 빼": 뺀 건만 반려
        for p in keep:
            proposals.apply(p["id"], "owner_yes")
            _record(p, "approved", said)
        session.pop("tasks_pending", None)
        if not keep:
            return _then_next(view, answer("넣지 않을게요", [say("네, 알바생 할 일은 넣지 않을게요.")], []))
        booked = reservation_view(view, keep[0], added=True) if len(keep) == 1 else None
        if booked:  # H-12: 방금 넣은 할 일을 그대로 보여 준다
            return _then_next(view, answer("알바생 할 일에 넣었어요", [say("알바생 할 일에 넣었어요.")], booked["cards"]))
        titles = ", ".join(p["payload"]["title"] for p in keep)
        return _then_next(view, answer("할 일 넣었어요", [say(f"알바생 할 일에 {_obj(titles)} 넣었어요."), say("알바생이 확인하면 알려 드릴게요.")], []))
    if name == "action.edit" and drop:
        for p in drop:
            proposals.decline(p["id"], "owner_edit")
            _record(p, "rejected", said)
        session["tasks_pending"] = [p["id"] for p in keep]
        if not keep:
            session.pop("tasks_pending", None)
            return answer("넣지 않을게요", [say("네, 알바생 할 일은 넣지 않을게요.")], [])
        dropped = ", ".join(ORDINAL[asked.index(p)] for p in drop)
        titles = ", ".join(p["payload"]["title"] for p in keep)
        response = answer("이렇게 넣을까요?", [say(f"{speech.josa(dropped, '은', '는')} 빼고, {_obj(titles)} 넣을까요?")], [],
                          kind="ask_tasks", tasks=[p["id"] for p in keep])
        response["expects_reply"] = True
        return response
    response = answer("알바생 할 일 넣을까요?", [say("넣으시려면 '응, 넣어'라고 말씀해 주세요.")], [], kind="ask_tasks",
                      tasks=[p["id"] for p in asked])
    response["expects_reply"] = True
    return response


def remember_asked(response: dict, session: dict) -> None:
    """ask_tasks 응답을 돌려줄 때 묻는 중으로 적는다."""
    if response.get("type") == "ask_tasks" and response.get("tasks"):
        proposals.mark_asked(response["tasks"])
        session["tasks_pending"] = list(response["tasks"])
