"""F9 답 만들기 + F10 허락 기억하기. POST /v1/turn 하나를 처리한다.

v0.2.1: 칩(suggestions)이 없다. "도나야"로 부른 말(addressed)은 가게 말로 넘기지 않는다.
다른 탭을 여는 말은 navigate(tab) 로 답한다 (문서 16-1). 허락하면 그 자리에서 미리 써 둔 답글을 올린다 (D-10 → D-11).
인스타 단계(D-14, D-15)에서 "올려"는 게시 작업을 걸고 바로 답한다 (실제로 올리는 건 뒤에서, 끝나면 알림).

- 같은 request_id 가 다시 오면 저장해 둔 응답을 그대로 돌려준다 (단계가 두 번 넘어가지 않게).
- 뜻: 규칙(intent_rules) → 못 가르면 LLM(intent_judge, 3초) → 그것도 안 되면 heuristic.
- 브리핑 응답은 jobs/briefing.prepare 가 미리 만든 것을 꺼내기만 한다. 여기서는 단계 번호와 turn_id 만 붙인다.
- session(가게·날짜마다 하나)에 지금 단계(step), 보기 상태(mode: idle | briefing | detail | ended), 직전 응답 종류를 기억한다.
  ignore 와 not_understood 는 직전 상황을 바꾸지 않는다 (허락을 물은 뒤 주방 말이 끼어도 "응"을 허락으로 알아듣게).
- 아쉬운 리뷰 알림 (2026-11-18, jobs/review_loop.py): 앱이 알림을 열면(event: notice) ask_action 으로 묻는다.
  "응, 진행해"·"쿠폰 빼고"·"안 해"는 브리핑이 없어도 처리한다. 대답한 뒤에도 잠깐은 ask_action 상황으로 둔다
  (두 번 "응"해도 "이미 올렸어요"). 질문이 열려 있으면 "도나야, 진행해"처럼 불러서 한 말도 그 질문의 대답으로 본다.
- 비 오는 날 스토리 이벤트 (instagram/story_event.py): 브리핑 단계 story_event 에서 "응"이면 포스터를 그리기 시작한다.
  다 그린 알림(story_event)을 열면 session.story_id 를 두고, 그 뒤 action.* 대답은 story_event.decide 로 보낸다.
"""

import copy
import datetime as dt

from voice import activity, clock, repo, speech, staff_orders, width
from voice.agents import intent_judge
from voice.context import load
from voice.dialog import echo, intent_rules
from voice.dialog.intent_rules import Intent
from voice.instagram import posts, story_event
from voice.jobs import briefing as briefing_job
from voice.jobs import review_loop
from voice.jobs.briefing import GAUGE, STEP_KEYS, TOTAL, answer, say

BRIEFING_INTENTS = {"briefing.start", "briefing.next", "briefing.repeat", "briefing.restart", "briefing.jump",
                    "detail.show", "detail.read", "detail.back", "permission.yes", "permission.no",
                    "instagram.post", "instagram.later", "instagram.next_photo"}
SITUATIONS = {
    "ask_permission": "도나가 '아쉬운 리뷰에 제가 바로 답할까요?' 하고 허락을 물었어요",
    "ask": "도나가 '많이 나간 메뉴를 인스타에 올릴까요?' 하고 물었어요",
    "show_detail": "도나가 리뷰와 답글을 화면에 띄웠어요",
    "answer": "도나가 브리핑 중이에요",
    "end": "브리핑이 끝났어요",
    "ask_action": "도나가 '아쉬운 리뷰에 사과 답글을 올리고, 알바생 할 일에 고칠 것을 넣을까요?' 하고 물었어요",
    "ask_staff": "도나가 알바생 일로 '보낼까요?', '초대할까요?', '카카오톡으로 보낼까요?' 하고 물었어요",
    "ask_story": "도나가 비 오는 날 이벤트 포스터를 보여 주며 '스토리에 올리고, 알바생 할 일 맨 위에 이벤트 안내를 넣을까요?' 하고 물었어요",
    "ask_story_event": "도나가 '비 오는 날 이벤트 포스터를 만들어 스토리에 올릴까요?' 하고 물었어요",
}


class StoreNotFound(Exception):
    pass


def empty(kind: str) -> dict:
    return {"type": kind, "headline": None, "say": [], "cards": [], "expects_reply": False}


def asking_instagram(session: dict) -> bool:
    return session.get("step") == "instagram" and session.get("last_type") in ("ask", "show_detail")


def asking_story(session: dict) -> bool:
    """브리핑에서 '스토리 이벤트를 할까요?'를 묻고 대답을 기다리는 중."""
    return session.get("step") == "story_event" and session.get("last_type") == "ask"


def situation(session: dict) -> str:
    last = session.get("last_type") or ""
    if last == "ask_action" and session.get("story_id"):
        last = "ask_story"
    elif asking_story(session):
        last = "ask_story_event"
    return SITUATIONS.get(last, "도나는 듣고만 있어요")


def understand(text: str, session: dict, view, addressed: bool = False) -> Intent:
    found = intent_rules.match(text, session.get("last_type"), addressed, instagram=asking_instagram(session) or asking_story(session))
    if found is not None:
        return found
    judged = intent_judge.judge(view, text, situation(session))
    if judged and not (addressed and judged["intent"] == "not_for_donna"):
        name = intent_rules.unknown_to_silent(judged["intent"], text, addressed)  # 부르지 않은 알 수 없는 말은 가만히
        edits = intent_rules.edits_in(intent_rules.normalize(text)) if name.startswith("action.") else None
        slots = {k: judged[k] for k in intent_judge.STAFF_SLOTS if judged.get(k)} if name.startswith("staff.") else None
        return Intent(name, judged.get("owner_said") or intent_rules.tidy(text), judged.get("jump_to"), by="llm",
                      edits=edits, slots=slots or None)
    return intent_rules.heuristic(text, addressed)


# ── 단계 옮기기 ──


def _available(brief: dict) -> list[str]:
    return [key for key in STEP_KEYS if brief["steps"].get(key)]


def _go(brief: dict, session: dict, key: str | None) -> dict:
    if key is None:
        session.update(step=None, mode="ended")
        activity.log(brief["store_id"], "owner", "오늘 일정 브리핑을 들었어요", "briefing_heard")
        return {**briefing_job.end_response(brief["store_id"]), "briefing": _gauge("end")}
    session.update(step=key, mode="briefing")
    return _step(brief, key)


def _step(brief: dict, key: str) -> dict:
    return {**copy.deepcopy(brief["steps"][key]), "briefing": _gauge(key)}


def _gauge(key: str) -> dict:
    return {"step": GAUGE[key], "total": TOTAL, "step_key": key}


def _after(brief: dict, key: str | None, inclusive: bool = False) -> str | None:
    start = 0 if key is None else STEP_KEYS.index(key) + (0 if inclusive else 1)
    return next((k for k in STEP_KEYS[start:] if brief["steps"].get(k)), None)


def _not_ready() -> dict:
    return answer("아직 준비하고 있어요", [say("아직 준비하고 있어요.")], [])


def _navigate(view, tab: str) -> dict:
    """다른 탭을 연다 (문서 16-1). 앱은 그 탭으로 옮기고 say 를 읽는다."""
    from voice.api import tabs

    text = {"sales": lambda: tabs.sales(view.store_id)["say"], "week": lambda: tabs.week(view.store_id)["say"],
            "settings": lambda: "설정을 열었어요."}[tab]()
    return {**empty("navigate"), "tab": tab, "say": [say(line if line.endswith(".") else line + ".") for line in text.split(". ") if line]}


def _prefixed(response: dict, *texts: str) -> dict:
    return {**response, "say": [*(say(text) for text in texts), *response["say"]]}


def post_now(view, kind: str) -> dict:
    """브리핑 밖에서 "인스타에 올려 줘", "스토리 올려 줘". 사장님이 직접 시킨 것이라 다시 묻지 않는다."""
    if not posts.connection(view.store_id)["connected"]:
        return answer("인스타가 연결되지 않았어요", [say("인스타가 아직 연결되지 않았어요.")], [])
    built = posts.build_feed(view) if kind == "feed" else posts.build_story(view)
    if built is None:
        return answer("올릴 메뉴 사진이 없어요", [say("올릴 메뉴 사진이 모자라요.")], [])
    posts.queue_publish(view.store_id, posts.create(view.store_id, built))
    what = "인기 메뉴를" if kind == "feed" else "스토리를"
    return answer(f"인스타에 {what} 올릴게요", [say(f"인스타에 {what} 올릴게요."), say("다 올라가면 알려 드릴게요.")], [])


def instagram_reply(name: str, session: dict, brief: dict, view) -> dict:
    """인스타에 올릴까요(D-14) 뒤의 대답: 미리보기 넘기기, 올리기, 나중에."""
    if name == "instagram.next_photo":
        slides = brief["details"]["instagram"]["slides"]
        slide = session.get("insta_slide", 0) % len(slides) + 1
        session.update(insta_slide=slide, mode="detail")
        return {**copy.deepcopy(slides[slide - 1]), "briefing": _gauge("instagram")}
    if name == "instagram.later":
        activity.log(view.store_id, "owner", "인스타는 다음에 올리기로 했어요", "instagram_later")
        return _prefixed(_go(brief, session, _after(brief, "instagram")), "네, 내일 브리핑에서 다시 여쭤볼게요.")
    built = posts.build_feed(view)
    if built is None:
        return _prefixed(_go(brief, session, _after(brief, "instagram")), "올릴 메뉴 사진이 모자라요.")
    posts.queue_publish(view.store_id, posts.create(view.store_id, built))
    activity.log(view.store_id, "owner", "인스타에 인기 메뉴를 올리라고 했어요", "instagram_ok")
    brief = briefing_job.refresh_instagram(view.store_id) or brief  # 오늘은 다시 묻지 않는다
    return _prefixed(_go(brief, session, _after(brief, "instagram")), "네, 인스타에 올릴게요.", "다 올라가면 알려 드릴게요.")


def story_reply(name: str, session: dict, brief: dict, view) -> dict:
    """'스토리 이벤트를 할까요?' 뒤의 대답: 그리기 시작하고 브리핑을 이어 가거나, 하지 않는다."""
    yes = name in ("instagram.post", "permission.yes")
    if yes:
        story_event.start(view.store_id)
        lead = ["네, 이벤트 포스터를 그릴게요.", "1~2분 걸려요. 다 되면 알려 드릴게요."]
    else:
        activity.log(view.store_id, "owner", "스토리 이벤트는 하지 않기로 했어요", "story_event_later")
        story_event.save({"id": story_event.event_id(view.store_id, view.now.date()), "store_id": view.store_id,
                          "date": view.now.date().isoformat(), "state": "declined", "created_at": clock.iso(clock.now())})
        lead = ["네, 오늘은 이벤트를 하지 않을게요."]
    brief = briefing_job.refresh_instagram(view.store_id) or brief  # 오늘은 다시 묻지 않는다
    return _prefixed(_go(brief, session, _after(brief, "story_event")), *lead)


def dispatch(intent: Intent, session: dict, brief: dict | None, view) -> dict:
    name = intent.name
    if name in ("not_for_donna", "echo"):  # echo: 도나가 한 말이 마이크로 다시 들어온 것 (dialog/echo.py)
        return empty("ignore")
    if name == "unknown":
        return empty("not_understood")
    if name == "stop":
        session.update(step=None, mode="idle")
        return empty("stop")
    if name == "question":
        return answer_question(view, intent.owner_said)
    if name.startswith("navigate."):
        return _navigate(view, name.split(".", 1)[1])
    if session.get("story_id") and (name.startswith("action.") or name == "notice.open"):  # 스토리 이벤트 포스터를 묻는 중
        return {**story_event.decide(view, name, intent.edits, session["story_id"]), "keep_context": "ask_action"}
    if name.startswith("action.") or name == "notice.open":  # 아쉬운 리뷰 고리. 브리핑과 상관없이
        if name == "action.repeat":
            name = "notice.open"
        return {**review_loop.decide(view, name, intent.edits, session.get("alert_id")), "keep_context": "ask_action"}
    if name.startswith("staff."):  # 알바생 일 (voice/staff_orders.py). 브리핑과 상관없이
        return staff_orders.handle(view, intent, session)
    if name in ("instagram.feed", "instagram.story"):
        return post_now(view, name.split(".", 1)[1])
    if brief is None:
        return _not_ready()

    step = session.get("step")
    if asking_story(session) and name in ("permission.yes", "permission.no", "instagram.post", "instagram.later"):
        return story_reply(name, session, brief, view)
    if asking_instagram(session) and name in ("permission.yes", "permission.no"):  # LLM 이 허락 대답으로 가른 경우
        name = "instagram.post" if name == "permission.yes" else "instagram.later"
    if name.startswith("instagram."):
        if not asking_instagram(session) or not brief["details"].get("instagram"):
            return empty("not_understood")
        return instagram_reply(name, session, brief, view)
    if name in ("briefing.start", "briefing.restart"):
        return _go(brief, session, _after(brief, None, inclusive=True))
    if name == "briefing.next":
        if session.get("mode") == "ended":
            return _go(brief, session, None)
        return _go(brief, session, _after(brief, step) if step else _after(brief, None, inclusive=True))
    if name == "detail.read" and intent.jump_to:  # "아쉬운 리뷰 읽어 줘": 그 단계로 옮겨 첫 리뷰를 읽는다
        if brief["steps"].get(intent.jump_to) and brief["details"].get(intent.jump_to):
            session.update(step=intent.jump_to, mode="detail")
            return {**copy.deepcopy(brief["details"][intent.jump_to]["read"]), "briefing": _gauge(intent.jump_to)}
        name = "briefing.jump"  # 읽을 리뷰가 없으면 그 단계로만 옮긴다 (허락 질문 등)
    if name == "briefing.jump":
        target = intent.jump_to if intent.jump_to in STEP_KEYS else "reviews"
        if not brief["steps"].get(target) and not (target == "reviews" and brief["steps"].get("negative")):
            return answer("지금은 알려 드릴 게 없어요", [say("지금은 알려 드릴 게 없어요.")], [])
        return _go(brief, session, _after(brief, target, inclusive=True))
    if name == "briefing.repeat":
        if not step:
            return _go(brief, session, _after(brief, None, inclusive=True))
        response = _prefixed(_step(brief, step), "다시 말씀드릴게요.")
        response["headline"] = "다시 말씀드릴게요"
        session["mode"] = "briefing"
        return response
    if name in ("permission.yes", "permission.no"):
        if session.get("last_type") != "ask_permission":
            return empty("not_understood")
        yes = name == "permission.yes"
        repo.save_settings(view.store_id, {**repo.settings(view.store_id), "negative_review_auto_reply": yes})
        activity.log(view.store_id, "owner", "아쉬운 리뷰는 도나가 바로 답하게 맡겼어요" if yes else "아쉬운 리뷰는 직접 보기로 했어요", "permission")
        if yes:
            briefing_job.post_ready_negatives(view.store_id, clock.now())
        brief = briefing_job.prepare(view.store_id)  # 허락에 따라 3단계가 바뀐다 (답글은 미리 써 둬서 LLM 을 기다리지 않는다)
        if yes and brief["steps"].get("negative") and brief["steps"]["negative"]["type"] == "answer":
            session.update(step="negative", mode="briefing")
            return _prefixed(_step(brief, "negative"), "네, 앞으로는 제가 바로 답할게요.")
        lead = "네, 앞으로는 제가 바로 답할게요." if yes else "네, 아쉬운 리뷰는 제가 답하지 않고 알려만 드릴게요."
        return _prefixed(_go(brief, session, _after(brief, step or "negative")), lead)
    # detail.*
    if not step:
        return empty("not_understood")
    detail = brief["details"].get(step)
    if name == "detail.show" and detail:
        session.update(mode="detail", insta_slide=1)
        return {**copy.deepcopy(detail["show"]), "briefing": _gauge(step)}
    if name == "detail.read" and detail:
        session["mode"] = "detail"
        return {**copy.deepcopy(detail["read"]), "briefing": _gauge(step)}
    session["mode"] = "briefing"
    if name == "detail.back":
        return {**_step(brief, step), "say": [say("브리핑으로 돌아왔어요.")]}
    return _prefixed(_step(brief, step), "이 내용은 더 보여 드릴 게 없어요.")


def answer_question(view, text: str) -> dict:
    """브리핑 밖 질문 (v0.2.0 범위 밖, 14장 11번). 아는 범위(예약, 비 소식)만 규칙으로 답한다."""
    now = clock.now()
    n = intent_rules.normalize(text)
    if "예약" in n and "답글" not in n:
        day = now.date() + dt.timedelta(days=2 if "모레" in n else 1 if "내일" in n else 0)
        word = "내일모레" if "모레" in n else "내일" if "내일" in n else "오늘"
        count = sum(1 for r in view.data.get("reservation", []) if r["starts_at"][:10] == day.isoformat())
        if count:
            return answer(width.fit("headline", f"{word} 예약 {count}팀이에요", f"예약 {count}팀이에요"),
                          [say(f"{word} 예약은 {speech.count(count, '팀')}이에요.")], [])
        topic = speech.josa(word, "은", "는")
        return answer(f"{topic} 예약이 없어요", [say(f"{topic} 예약이 없어요.")], [])
    if "비" in n or "날씨" in n:
        rainy = [w for w in view.data.get("weather", []) if w["date"] >= now.date().isoformat() and w.get("rain_chance", 0) >= 0.6]
        if rainy:
            day = dt.date.fromisoformat(rainy[0]["date"])
            return answer(f"{speech.weekday(day)}요일에 비 소식이 있어요", [say(f"{speech.weekday(day)}요일에 비 소식이 있어요.")], [])
        return answer("이번 주엔 비 소식이 없어요", [say("이번 주엔 비 소식이 없어요.")], [])
    return answer("그건 아직 몰라요", [say("그건 아직 몰라요.")], [])


def handle(request: dict) -> dict:
    store_id = request["store_id"]
    view = load(store_id)
    if view is None:
        raise StoreNotFound(store_id)
    turn_key = f"{store_id}:{request['request_id']}"
    saved = repo.get("turn", turn_key)
    if saved:
        return saved["response"]

    session_id = request.get("session_id") or f"sess_{clock.now():%Y%m%d}_{store_id}"
    session = repo.get("session", session_id) or {"id": session_id, "store_id": store_id, "step": None, "mode": "idle", "last_type": None}
    utterance = request.get("utterance") or None
    if request.get("event") == "notice":
        notice = repo.get("notice", request.get("notice_id") or "") or {}
        if notice.get("kind") == story_event.KIND:  # 이벤트 포스터를 다 그렸어요
            session["story_id"] = notice.get("alert_id")
            session.pop("alert_id", None)
        else:
            session.pop("story_id", None)
            session["alert_id"] = notice.get("alert_id") or (review_loop.pending(store_id) or {}).get("id")
        intent = Intent("notice.open", None)
    elif request.get("event") == "auto_next" or utterance is None:
        intent = Intent("briefing.next", None)
    else:
        addressed = bool(utterance.get("addressed"))
        # 묻고 있는 아쉬운 리뷰가 있으면 "도나야, 진행해"도 그 대답이다 (허락 질문·자세히 보기 중이면 그쪽이 먼저)
        live = review_loop.pending(store_id) if addressed else None
        if session.get("last_type") not in ("ask_permission", "show_detail") and live:
            session["last_type"] = "ask_action"
            if live["state"] in review_loop.PENDING:  # 묻고 있는 리뷰가 있으면 그 대답이다 (스토리 이벤트보다 먼저)
                session.pop("story_id", None)
        if session.get("last_type") != "ask_action":
            session.pop("alert_id", None)
            session.pop("story_id", None)
        if echo.is_echo(store_id, utterance["text"]):
            intent = Intent("echo", intent_rules.tidy(utterance["text"]))
        else:
            intent = understand(utterance["text"], session, view, addressed)

    brief = briefing_job.current(store_id)
    response = dispatch(intent, session, brief, view)
    response.setdefault("briefing", None)
    if response["type"] not in ("ignore", "not_understood"):
        session["last_type"] = response.get("keep_context") or response["type"]
    response = {
        "turn_id": f"t_{repo.next_number(f'turn:{store_id}'):04d}", "type": response["type"], "intent": intent.name,
        "owner_said": None if response["type"] == "ignore" else intent.owner_said, "briefing": response["briefing"],
        "headline": response["headline"], "say": response["say"], "cards": response["cards"],
        "expects_reply": response["expects_reply"],
        **({"permission": response["permission"]} if response.get("permission") else {}),
        **({"action": response["action"]} if response.get("action") else {}),
        **({"ask": response["ask"]} if response.get("ask") else {}),
        **({"tab": response["tab"]} if response.get("tab") else {}),
        **({"open": response["open"]} if response.get("open") else {}),
    }
    echo.remember(store_id, [item["text"] for item in response["say"]])  # 이 말이 마이크로 다시 들어오면 흘려듣는다
    session["last_turn_id"] = response["turn_id"]
    repo.put("session", session_id, store_id, session)
    repo.put("turn", turn_key, store_id, {"request": request, "response": response})
    return response
