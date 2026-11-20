"""아쉬운 리뷰 닫힌 고리 (2026-11-18 팀 개선안, donna-voice/docs/test-scenarios-closed-loop.md L·E·T·G).

영업 중(문 열기 한 시간 전 ~ 문 닫을 때)에 아쉬운 리뷰가 오면
  1. 원인을 나누고(cause.py) 사과 답글과 알바생 교정 카드를 마련해, 사장님 앱에 알린다 (notice negative_review)
  2. 사장님이 알림을 열면 도나가 묻는다 (turn type ask_action): "사과 답글에 … 넣어 올리고, 알바생 할 일에 … 넣을까요?"
  3. "응, 진행해" → 답글을 올리고(플랫폼에 올린 것으로 적는다) 알바생 할 일에 교정 카드를 넣는다 (모두 확인 필요, 긴급 아님)
     "쿠폰 빼고 사과만", "카드는 넣지 마" → 고쳐서 다시 묻거나(올리라는 말이 같이 있으면) 바로 올린다. "안 해" → 초안만 남긴다
  4. 알바생이 카드를 확인하면 사장님께 알린다 (notice staff_checked) → 고리가 닫힌다
  대답이 없으면 15분 뒤 한 번 더 알리고, 25분이 되면 (허락했으면) 사과만 먼저 올린다. 허락이 없으면 초안으로 남긴다.
문을 닫은 뒤에 온 리뷰는 지금처럼 10분 뒤 바로 답하기(auto_reply)를 탄다.

상태 (저장소 종류 alert, id al_<리뷰 id>)
  alerted → reminded → (owner) posted → card_pinned → closed      (카드 없이 올리면 바로 closed)
                      → (owner) canceled                           (초안만. 나중에 "진행해"라고 하면 올린다)
                      → (25분) fallback_posted | left_draft         (그 뒤 "진행해"면 카드만 넣는다 / 올린다)
상태는 repo._lock 안에서 읽고 바꾼다. 사장님의 "응"과 25분 작업이 겹쳐도 한 번만 올린다.
보상 문장은 사장님이 설정에서 정한 것(settings.compensation)만, 코드가 붙인다 (voice_reply.compose / safe_reply).
"""

import datetime as dt

from app.core.seoul_time import at_time
from voice import activity, clock, config, hours, notices, proposals, repo, speech
from voice.agents import fix_card, voice_reply
from voice.clock import iso, parse
from voice.context import load
from voice.jobs import cause, queue, staff_tasks

PENDING = {"alerted", "reminded"}
ASKING = PENDING | {"auto_posted"}  # auto_posted: 자동 답글을 올리고 할 일만 묻는 중 (2026-11-20)
REOPENABLE = {"alerted", "reminded", "canceled", "left_draft"}
DONE = {"posted", "card_pinned", "closed", "carried"}  # carried: 대답이 없어 할 일을 다음 날 브리핑으로 넘김
LOOK_BACK = dt.timedelta(hours=2)  # "도나야, 진행해"가 가리킬 수 있는 알림
PLATFORMS = {"baemin": "배민", "naver": "네이버", "coupang": "쿠팡이츠", "yogiyo": "요기요"}
NOUNS = {"leak": "국물", "late": "배달", "swollen": "면", "missing": "누락", "cold": "국물", "taste": "맛", "hall": "응대"}


def _obj(word: str) -> str:
    return speech.josa(word, "을", "를")


# ── 들어올 때 ──


def in_alert_hours(store: dict, moment: dt.datetime) -> bool:
    today = hours.on(store, moment.date())
    if today is None:
        return False
    start = at_time(moment.date(), today["open"]) - config.ALERT_BEFORE_OPEN
    return start <= moment < at_time(moment.date(), today["close"])


def on_new_review(review: dict) -> str:
    """새 아쉬운 리뷰의 작업을 잡는다. 'alert' (영업 중) | 'auto_reply' (문 닫은 뒤) | 'none'."""
    if review.get("sentiment") != "negative":
        return "none"
    store_id, written = review["store_id"], parse(review["written_at"])
    payload = {"review_id": review["id"]}
    if in_alert_hours(repo.store(store_id), written):
        queue.add(store_id, "review_alert", written, payload)
        if _auto(store_id):  # 바로 답하기를 켠 가게: 묻지 않고 올린다. 할 일만 묻고, 대답이 없으면 다음 날 브리핑으로
            queue.add(store_id, "review_fix_carry", written + config.ALERT_FALLBACK_AFTER, payload)
        else:
            queue.add(store_id, "review_remind", written + config.ALERT_REMIND_AFTER, payload)
            queue.add(store_id, "review_fallback", written + config.ALERT_FALLBACK_AFTER, payload)
        return "alert"
    queue.add(store_id, "auto_reply", written + config.AUTO_REPLY_DELAY, payload)
    return "auto_reply"


def _auto(store_id: str) -> bool:
    return repo.settings(store_id).get("negative_review_auto_reply") is True


def _preset(store_id: str, kind: str) -> str | None:
    if kind not in cause.COMPENSATION_KEYS:
        return None
    return (repo.settings(store_id).get("compensation") or {}).get(kind) or None


def alert(store_id: str, review_id: str) -> dict | None:
    """작업 review_alert: 사과 답글과 교정 카드를 마련하고 사장님께 알린다."""
    view = load(store_id)
    review = view.review(review_id) if view else None
    if review is None or review.get("reply_status", "none") != "none":
        return None
    found = fix_card.card_for(view, review)  # 부정 리뷰 사원: 교정 카드 (에이전트, 실패하면 원인별 템플릿)
    card = found["card"]
    fix = {"cause": found["summary"], "action": card["detail"], "reply": found["reply"]} if card else None
    # 에이전트가 쓴 카드는 템플릿 답글에 그 조치가 없어서 답글도 에이전트가 같은 조치로 쓴다
    if config.ALERT_AGENT_REPLY or found["card_source"] == "AGENT":  # 답글 에이전트는 기본 꺼짐: 알림이 30초 늦어진다
        written = voice_reply.write(view, review, "AUTO", fix=fix)
    else:
        written = {"text": found["reply"], "source": "TEMPLATE", "notes": []}
    base, notes = voice_reply.safe_reply(written["text"], None, found["reply"])  # 에이전트 글에는 보상이 없어야 한다
    now = clock.now()
    auto = _auto(store_id)
    preset = None if auto else _preset(store_id, found["type"])  # 자동 답글에는 보상 문장을 붙이지 않는다 (2026-11-20)
    proposal = _propose(store_id, review, card) if card else None
    if proposal and proposal["state"] == "merged":  # 같은 할 일이 이미 알바생 화면에 있다. 다시 묻지 않는다
        card = None
    record = repo.put("alert", f"al_{review_id}", store_id, {
        "id": f"al_{review_id}", "store_id": store_id, "review_id": review_id, "state": "alerted",
        "cause": {k: found[k] for k in ("type", "detail", "summary")}, "card": card,
        "reply_base": base, "reply_plain": found["plain"], "reply_source": written["source"], "notes": written["notes"] + notes,
        "compensation": preset, "use_compensation": bool(preset), "use_card": bool(card),
        "created_at": iso(now), "deadline_at": iso(parse(review["written_at"]) + config.AUTO_REPLY_WINDOW),
        "task_id": None, "proposal_id": proposal["id"] if proposal else None, "decided_by": None, "decided_at": None,
    })
    review.update({"reply_status": "proposed", "summary": found["summary"], "cause": found["type"]})
    repo.save_review(review)
    platform = PLATFORMS.get(review.get("platform"), "리뷰 앱")
    if auto:
        return _auto_post(record, platform)
    notices.push(store_id, "negative_review", f"{platform}에 아쉬운 리뷰가 올라왔어요", opens_turn=True, alert_id=record["id"])
    return record


def _auto_post(record: dict, platform: str) -> dict:
    """바로 답하기를 켠 가게: 사과 답글을 바로 올리고 알린다. 교정 카드가 있으면 넣을지만 묻는다 (2026-11-20 결정)."""
    _post(record, "auto")
    text = f"{platform} 아쉬운 리뷰에 사과 답글을 올렸어요"
    if record["use_card"] and record["card"]:
        record = repo.put("alert", record["id"], record["store_id"], {**record, "state": "auto_posted"})
        notices.push(record["store_id"], "negative_auto", text, opens_turn=True, alert_id=record["id"])
    else:
        record = repo.put("alert", record["id"], record["store_id"], {**record, "state": "closed", "decided_by": "auto"})
        notices.push(record["store_id"], "negative_auto", text, say=[f"{text}."])
    return record


def carry(store_id: str, review_id: str) -> str | None:
    """작업 review_fix_carry (25분): 자동 답글 뒤 할 일 질문에 대답이 없으면 다음 날 아침 브리핑에서 묻는다."""
    with repo._lock:
        record = repo.get("alert", f"al_{review_id}")
        if not record or record["state"] != "auto_posted":
            return None
        day = staff_tasks.briefing_day(repo.store(store_id), clock.now(), after_today=True)
        if record.get("proposal_id"):
            proposals.carry(record["proposal_id"], day)
        repo.put("alert", record["id"], store_id, {**record, "state": "carried", "decided_by": "timeout", "decided_at": iso(clock.now())})
    return day


def remind(store_id: str, review_id: str) -> bool:
    """작업 review_remind (15분): 아직 대답이 없으면 한 번 더 알린다."""
    with repo._lock:
        record = repo.get("alert", f"al_{review_id}")
        if not record or record["state"] != "alerted":
            return False
        record = repo.put("alert", record["id"], store_id, {**record, "state": "reminded"})
    platform = PLATFORMS.get((repo.review(review_id) or {}).get("platform"), "리뷰 앱")
    notices.push(store_id, "negative_review", f"{platform} 아쉬운 리뷰에 아직 답하지 않았어요", opens_turn=True, alert_id=record["id"])
    return True


def fallback(store_id: str, review_id: str) -> str | None:
    """작업 review_fallback (25분): 대답이 없으면 허락한 가게는 사과만 먼저 올리고, 아니면 초안으로 남긴다."""
    with repo._lock:
        record = repo.get("alert", f"al_{review_id}")
        if not record or record["state"] not in PENDING:
            return None
        allowed = repo.settings(store_id).get("negative_review_auto_reply") is True
        record = {**record, "decided_by": "timeout", "decided_at": iso(clock.now())}
        if allowed:  # 사과만: 보상 문장과 교정 카드는 사장님이 정할 몫이라 넣지 않는다 (나중에 "진행해"면 카드만 넣는다)
            _post({**record, "use_card": False, "use_compensation": False}, "timeout")
            repo.put("alert", record["id"], store_id, {**record, "state": "fallback_posted"})
            notices.push(store_id, "reply_fallback", "대답이 없으셔서 사과 답글만 올렸어요", say=["대답이 없으셔서 사과 답글만 먼저 올렸어요."])
            result = "fallback_posted"
        else:
            review = repo.review(review_id)
            review.update({"reply_status": "none", "reply_ready": {"text": record["reply_plain"], "source": "TEMPLATE", "notes": []}})
            repo.save_review(review)
            repo.put("alert", record["id"], store_id, {**record, "state": "left_draft"})
            notices.push(store_id, "reply_fallback", "답글은 초안으로 남겨 뒀어요", say=["대답이 없으셔서 답글은 올리지 않고 초안으로 남겨 뒀어요."])
            result = "left_draft"
    from voice.jobs import briefing

    if briefing.current(store_id):
        briefing.prepare(store_id)
    return result


# ── 묻기 ──


def reply_text(record: dict) -> str:
    """지금 고른 대로 올릴 답글: (조치를 적은 사과 | 사과만) + (사장님이 정한 보상 문장)."""
    base = record["reply_base"] if record["use_card"] else record["reply_plain"]
    preset = record["compensation"] if record["use_compensation"] else None
    text, _ = voice_reply.safe_reply(voice_reply.compose(base, preset), preset, record["reply_plain"])
    return text


def _offer(record: dict) -> str:
    comp = record["use_compensation"] and record["compensation"]
    card = record["use_card"] and record["card"]
    if card:
        lead = "사과 답글에 다음 주문 서비스 안내를 넣어 올리고" if comp else "사과 답글을 올리고"
        return f"{lead}, 알바생 할 일에 {_obj(card['title'])} 넣을까요?"
    return "사과 답글에 다음 주문 서비스 안내를 넣어 올릴까요?" if comp else "사과 답글을 올릴까요?"


def _cards(record: dict, review: dict, *, posted: bool) -> list[dict]:
    from voice.jobs.briefing import review_card

    reply = {"text": review["reply_text"] if posted else reply_text(record), "by": "donna",
             "posted_at": review.get("reply_posted_at") if posted else None, "scheduled_label": None if posted else "올리기 전 답글"}
    cards = [review_card(review, reply)]
    if record["use_card"] and record["card"]:
        cards.append({"type": "checklist", "id": "fix_card", "title": "알바생 할 일에 넣은 것" if posted else "알바생 할 일에 넣을 것",
                      "items": [{"id": record["task_id"] or "fix_card_item", "title": record["card"]["title"],
                                 "sub": "알바생 확인 전" if posted else record["card"]["detail"], "state": "todo"}]})
    return cards


def _dropped(changed: list[str]) -> str:
    """['서비스 안내', '알바생 할 일'] → '서비스 안내와 알바생 할 일은 빼고'."""
    joined = "와 ".join(changed) if len(changed) == 2 else changed[0]
    return f"{speech.josa(joined, '은', '는')} 빼고"


def _action(record: dict) -> dict:
    return {"kind": "review_fix", "alert_id": record["id"], "compensation": bool(record["use_compensation"] and record["compensation"]),
            "staff_card": record["card"]["title"] if record["use_card"] and record["card"] else None, "deadline_at": record["deadline_at"]}


def ask(view, record: dict, *, lead: list[str] | None = None, headline: str | None = None) -> dict:
    """ask_action 응답. 처음 묻기, 다시 알림(reminded), 고친 뒤 다시 묻기(lead), 못 알아들었을 때."""
    from voice.jobs.briefing import answer, say, told

    review = repo.review(record["review_id"])
    summary = record["cause"]["summary"]
    offer = _offer(record)
    if record["state"] == "auto_posted":  # 답글은 올렸다. 할 일만 묻는다
        platform = PLATFORMS.get(review.get("platform"), "리뷰 앱")
        ask_card = f"알바생 할 일에 {_obj(record['card']['title'])} 넣을까요?"
        says = ([say(text) for text in lead] if lead is not None else
                [say(f"사장님, 방금 {platform}에 {told(summary)} 아쉬운 리뷰가 와서 사과 답글을 올렸어요.", summary)]) + [say(ask_card)]
        response = answer(headline or "할 일 넣을까요?", says, _cards(record, review, posted=True), kind="ask_action",
                          action={**_action(record), "kind": "review_fix_task"})
        response["expects_reply"] = True
        return response
    if lead is not None:
        says = [say(text) for text in lead] + [say(offer)]
    elif record["state"] == "reminded":
        noun = NOUNS.get(record["cause"].get("detail"), "아쉬운")
        left = max(1, round((parse(record["created_at"]) + config.ALERT_FALLBACK_AFTER - clock.now()).total_seconds() / 60))
        extras = [w for w, on in (("서비스 안내", record["use_compensation"] and record["compensation"]),
                                  ("할 일", record["use_card"] and record["card"])) if on]
        third = f"{'와 '.join(extras)}까지 넣어 올릴까요?" if extras else "사과 답글을 올릴까요?"
        says = [say(f"사장님, 아까 그 {noun} 리뷰요.", summary),
                say(f"{left}분 안에 대답이 없으시면 사과 답글만 먼저 올려 둘게요." if _auto(record["store_id"])
                    else f"{left}분 안에 대답이 없으시면 답글은 초안으로 남겨 둘게요."),
                say(third)]
    else:
        platform = PLATFORMS.get(review.get("platform"), "리뷰 앱")
        says = [say(f"사장님, 방금 {platform}에 {told(summary)} 아쉬운 리뷰가 올라왔어요.", summary), say(offer)]
    response = answer(headline or "아쉬운 리뷰가 왔어요", says, _cards(record, review, posted=False), kind="ask_action", action=_action(record))
    response["expects_reply"] = True
    return response


# ── 사장님이 정한 것 ──


def pending(store_id: str, *, include_decided: bool = False) -> dict | None:
    """'진행해'가 가리키는 알림: 최근 2시간 안, 아직 묻고 있는 것이 먼저."""
    now = clock.now()
    recent = [a for a in repo.all_of("alert", store_id) if now - parse(a["created_at"]) <= LOOK_BACK]
    recent.sort(key=lambda a: a["created_at"], reverse=True)
    for states in (ASKING, {"fallback_posted"}, REOPENABLE, DONE if include_decided else set()):
        found = next((a for a in recent if a["state"] in states), None)
        if found:
            return found
    return None


def _post(record: dict, trigger: str) -> dict:
    """답글을 올린다 (v0.2.x 는 플랫폼에 실제로 올리지 않고 올린 것으로 적는다, 문서 9장)."""
    review = repo.review(record["review_id"])
    now = clock.now()
    review.update({
        "reply_status": "posted", "reply_by": "donna", "reply_text": reply_text(record), "reply_source": record["reply_source"],
        "reply_posted_at": iso(now), "reply_trigger": trigger,
        "replied_in_minutes": max(1, round((now - parse(review["written_at"])).total_seconds() / 60)),
        "reply_summary": "사과하고, 할 일을 알바생에게 넣었어요" if record["use_card"] else "사과 답글을 올렸어요",
        "reply_kept": {"compensation": bool(record["use_compensation"] and record["compensation"]), "card": bool(record["use_card"])},
    })
    repo.save_review(review)
    activity.log(record["store_id"], "donna", "아쉬운 리뷰에 사과 답글을 올렸어요", f"fix:{record['review_id']}:reply", at=now)
    return review


def _propose(store_id: str, review: dict, card: dict) -> dict:
    """교정 카드를 제안으로 남긴다 (묻는 중). 넣는 것은 사장님이 "진행해" 한 뒤 proposals.apply 가 한다."""
    return staff_tasks.propose_fix(store_id, review, card, state="asked")


def _pin(record: dict, trigger: str) -> dict:
    """알바생 할 일에 교정 카드를 넣는다 (넣은 날과 다음 날, 저마다 확인). 긴급은 아니다 (퇴근을 막지 않는다)."""
    pid = record.get("proposal_id") or _propose(record["store_id"], repo.review(record["review_id"]), record["card"])["id"]
    task = proposals.apply(pid, trigger)
    activity.log(record["store_id"], "donna", f"알바생 할 일에 {_obj(record['card']['title'])} 넣었어요", f"fix:{record['review_id']}:card")
    return task


def _finish(record: dict, trigger: str) -> dict:
    """올리고(아직이면) 카드를 넣는다. 반환한 record 의 state 는 card_pinned | closed."""
    if record["state"] != "fallback_posted":
        _post(record, trigger)
    task = _pin(record, trigger) if record["use_card"] and record["card"] else None
    if task is None and record.get("proposal_id"):  # "카드는 넣지 마"
        proposals.decline(record["proposal_id"], trigger)
    state = "card_pinned" if task else "closed"
    return repo.put("alert", record["id"], record["store_id"], {
        **record, "state": state, "task_id": task["id"] if task else None,
        "decided_by": record.get("decided_by") or trigger, "decided_at": record.get("decided_at") or iso(clock.now()),
    })


def decide(view, intent_name: str, edits: dict | None, alert_id: str | None = None) -> dict:
    """사장님 대답 (action.approve | action.edit | action.cancel | action.unclear | notice.open)."""
    from voice.jobs.briefing import answer, say

    with repo._lock:
        # 어느 리뷰의 대답인가: 이 대화가 묻던 리뷰가 아직 묻는 중이면 그것, 아니면 지금 묻고 있는 가장 새 리뷰
        # (다른 기기에서 새 알림을 열었을 수 있다), 그것도 없으면 이 대화가 묻던 리뷰나 최근 리뷰 ("이미 올렸어요" 등)
        record = repo.get("alert", alert_id) if alert_id else None
        if record is None or record["state"] not in ASKING:
            live = pending(view.store_id)
            if live is not None and (live["state"] in ASKING or record is None):
                record = live
        if record is None:
            record = pending(view.store_id, include_decided=True)
        if record is None:
            return answer("지금은 물어본 게 없어요", [say("지금은 여쭤본 게 없어요.")], [])
        if intent_name == "notice.open":
            return ask(view, record) if record["state"] in ASKING else answer("이미 처리했어요", [say("그 리뷰는 이미 처리했어요.")], [])
        if record["state"] == "auto_posted":
            return _decide_task(view, record, intent_name, edits)
        if intent_name == "action.unclear":
            return ask(view, record, lead=["진행하시려면 '응, 진행해'라고 말씀해 주세요."], headline="이렇게 올릴까요?")
        if intent_name == "action.redo" and record["state"] in ASKING:  # "다시 만들어"를 승인으로 보고 올리던 것을 막는다 (2026-11-21)
            return ask(view, record, lead=["올리시려면 '응, 진행해', 올리지 않으시려면 '안 해'라고 말씀해 주세요."], headline="이렇게 올릴까요?")
        if record["state"] in DONE:
            return answer("답글은 이미 올렸어요", [say("답글은 이미 올렸어요.")], _cards(record, repo.review(record["review_id"]), posted=True))

        changed = []
        if edits and edits.get("drop_compensation") and record["use_compensation"]:
            record["use_compensation"] = False
            changed.append("서비스 안내")
        if edits and edits.get("no_card") and record["use_card"]:
            record["use_card"] = False
            changed.append("알바생 할 일")
        record = repo.put("alert", record["id"], record["store_id"], record)

        if intent_name == "action.cancel":
            if record["state"] in DONE | {"fallback_posted"}:
                return answer("답글은 이미 올렸어요", [say("답글은 이미 올렸어요.")], [])
            review = repo.review(record["review_id"])
            review.update({"reply_status": "drafted", "reply_by": "donna", "reply_text": reply_text(record), "reply_source": record["reply_source"]})
            repo.save_review(review)
            repo.put("alert", record["id"], record["store_id"], {**record, "state": "canceled", "decided_by": "owner_no", "decided_at": iso(clock.now())})
            return answer("올리지 않을게요", [say("네, 올리지 않을게요."), say("초안은 남겨 둘게요.")], [])

        if intent_name == "action.edit":
            if not changed:
                return ask(view, record, lead=["무엇을 뺄지 다시 말씀해 주세요."], headline="이렇게 올릴까요?")
            response = ask(view, record, lead=[], headline="이렇게 올릴까요?")
            response["say"] = [say(f"{_dropped(changed)}, {_offer(record)}")]
            return response

        # action.approve
        was = record["state"]
        record = _finish(record, "owner_yes")
    review = repo.review(record["review_id"])
    cards = _cards(record, review, posted=True)
    if was == "fallback_posted":
        if record["task_id"]:
            return answer("알바생 할 일을 넣었어요", [say("답글은 이미 올렸어요."), say("알바생 할 일만 넣었어요.")], cards)
        return answer("답글은 이미 올렸어요", [say("답글은 이미 올렸어요.")], cards)
    if record["compensation"] and not record["use_compensation"]:
        first = "서비스 안내는 빼고 사과 답글을 올렸어요."
    elif record["use_compensation"] and record["compensation"]:
        first = "서비스 안내를 넣어 사과 답글을 올렸어요."
    else:
        first = "사과 답글을 올렸어요."
    if record["task_id"]:
        says = [say(first), say(f"알바생 할 일에 {_obj(record['card']['title'])} 넣었어요."), say("알바생이 확인하면 알려 드릴게요.")]
        return answer("답글 올리고 할 일 넣었어요", says, cards)
    return answer("사과 답글을 올렸어요", [say(first)], cards)


def _decide_task(view, record: dict, intent_name: str, edits: dict | None) -> dict:
    """자동 답글 뒤 '할 일에 넣을까요?'의 대답. 답글은 이미 올렸다."""
    from voice.jobs.briefing import answer, say

    if intent_name == "action.unclear":
        return ask(view, record, lead=["넣으시려면 '응, 넣어'라고 말씀해 주세요."], headline="할 일 넣을까요?")
    if intent_name == "action.cancel" or (edits or {}).get("no_card"):
        if record.get("proposal_id"):
            proposals.decline(record["proposal_id"], "owner_no")
        repo.put("alert", record["id"], record["store_id"], {**record, "state": "closed", "decided_by": "owner_no",
                                                             "decided_at": iso(clock.now())})
        return answer("할 일은 넣지 않을게요", [say("네, 알바생 할 일은 넣지 않을게요.")], [])
    if intent_name == "action.approve":
        task = _pin(record, "owner_yes")
        record = repo.put("alert", record["id"], record["store_id"], {**record, "state": "card_pinned", "task_id": task["id"],
                                                                      "decided_by": "owner_yes", "decided_at": iso(clock.now())})
        says = [say(f"알바생 할 일에 {_obj(record['card']['title'])} 넣었어요."), say("알바생이 확인하면 알려 드릴게요.")]
        return answer("할 일 넣었어요", says, _cards(record, repo.review(record["review_id"]), posted=True))
    return ask(view, record, lead=["넣을지 다시 말씀해 주세요."], headline="할 일 넣을까요?")


# ── 알바생이 확인했을 때 ──


def on_staff_confirm(task: dict, person: dict) -> None:
    source = task.get("source") or {}
    record = repo.get("alert", source.get("alert_id")) if source.get("alert_id") else None
    line = f"{person['call']} 씨가 {_obj(task['title'])} 확인했어요"
    key = f"fix:{source.get('review_id')}:checked" if source.get("type", "review") == "review" else f"{source['type']}:{source.get('id')}:checked"
    activity.log(task["store_id"], "donna", line, key)
    if record and record["state"] == "card_pinned":
        repo.put("alert", record["id"], record["store_id"], {**record, "state": "closed", "checked_by": person["id"], "checked_at": iso(clock.now())})
    notices.push(task["store_id"], "staff_checked", line, say=[f"{line}."])
