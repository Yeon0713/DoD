"""F9 답 만들기 + F10 허락 기억하기. POST /v1/turn 하나를 처리한다.

v0.2.1: 칩(suggestions)이 없다. "도나야"로 부른 말(addressed)은 가게 말로 넘기지 않는다.
다른 탭을 여는 말은 navigate(tab) 로 답한다 (문서 16-1). 허락하면 그 자리에서 미리 써 둔 답글을 올린다 (D-10 → D-11).

- 같은 request_id 가 다시 오면 저장해 둔 응답을 그대로 돌려준다 (단계가 두 번 넘어가지 않게).
- 뜻: 규칙(intent_rules) → 못 가르면 LLM(intent_judge, 3초) → 그것도 안 되면 heuristic.
- 브리핑 응답은 jobs/briefing.prepare 가 미리 만든 것을 꺼내기만 한다. 여기서는 단계 번호와 turn_id 만 붙인다.
- session(가게·날짜마다 하나)에 지금 단계(step), 보기 상태(mode: idle | briefing | detail | ended), 직전 응답 종류를 기억한다.
  ignore 와 not_understood 는 직전 상황을 바꾸지 않는다 (허락을 물은 뒤 주방 말이 끼어도 "응"을 허락으로 알아듣게).
"""

import copy
import datetime as dt

from voice import activity, clock, repo, speech, width
from voice.agents import intent_judge
from voice.context import load
from voice.dialog import intent_rules
from voice.dialog.intent_rules import Intent
from voice.jobs import briefing as briefing_job
from voice.jobs.briefing import GAUGE, STEP_KEYS, TOTAL, answer, say

BRIEFING_INTENTS = {"briefing.start", "briefing.next", "briefing.repeat", "briefing.restart", "briefing.jump",
                    "detail.show", "detail.read", "detail.back", "permission.yes", "permission.no"}
SITUATIONS = {
    "ask_permission": "도나가 '아쉬운 리뷰에 제가 바로 답할까요?' 하고 허락을 물었어요",
    "show_detail": "도나가 리뷰와 답글을 화면에 띄웠어요",
    "answer": "도나가 브리핑 중이에요",
    "end": "브리핑이 끝났어요",
}


class StoreNotFound(Exception):
    pass


def empty(kind: str) -> dict:
    return {"type": kind, "headline": None, "say": [], "cards": [], "expects_reply": False}


def understand(text: str, session: dict, view, addressed: bool = False) -> Intent:
    found = intent_rules.match(text, session.get("last_type"), addressed)
    if found is not None:
        return found
    judged = intent_judge.judge(view, text, SITUATIONS.get(session.get("last_type") or "", "도나는 듣고만 있어요"))
    if judged and not (addressed and judged["intent"] == "not_for_donna"):
        return Intent(judged["intent"], judged.get("owner_said") or intent_rules.tidy(text), judged.get("jump_to"), by="llm")
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


def _prefixed(response: dict, text: str) -> dict:
    return {**response, "say": [say(text), *response["say"]]}


def dispatch(intent: Intent, session: dict, brief: dict | None, view) -> dict:
    name = intent.name
    if name == "not_for_donna":
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
    if brief is None:
        return _not_ready()

    step = session.get("step")
    if name in ("briefing.start", "briefing.restart"):
        return _go(brief, session, _after(brief, None, inclusive=True))
    if name == "briefing.next":
        if session.get("mode") == "ended":
            return _go(brief, session, None)
        return _go(brief, session, _after(brief, step) if step else _after(brief, None, inclusive=True))
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
        session["mode"] = "detail"
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
    if request.get("event") == "auto_next" or utterance is None:
        intent = Intent("briefing.next", None)
    else:
        intent = understand(utterance["text"], session, view, bool(utterance.get("addressed")))

    brief = briefing_job.current(store_id)
    response = dispatch(intent, session, brief, view)
    response.setdefault("briefing", None)
    if response["type"] not in ("ignore", "not_understood"):
        session["last_type"] = response["type"]
    response = {
        "turn_id": f"t_{repo.next_number(f'turn:{store_id}'):04d}", "type": response["type"], "intent": intent.name,
        "owner_said": None if response["type"] == "ignore" else intent.owner_said, "briefing": response["briefing"],
        "headline": response["headline"], "say": response["say"], "cards": response["cards"],
        "expects_reply": response["expects_reply"],
        **({"permission": response["permission"]} if response.get("permission") else {}),
        **({"tab": response["tab"]} if response.get("tab") else {}),
    }
    session["last_turn_id"] = response["turn_id"]
    repo.put("session", session_id, store_id, session)
    repo.put("turn", turn_key, store_id, {"request": request, "response": response})
    return response
