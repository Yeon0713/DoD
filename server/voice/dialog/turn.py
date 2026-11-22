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
- 알바생 할 일 묻기 (jobs/staff_tasks.py, 2026-11-20): 브리핑 마지막 단계(ask_tasks)의 대답은 staff_tasks.decide 로 보낸다.
  브리핑에서 묻지 못한 할 일은 그날 사장님이 다음에 "도나야"라고 부르면 먼저 묻고, 대답한 뒤 원래 물은 말에 답한다.
- 고쳐 쓰기 ("좀 더 부드럽게", 감사팀 9장, jobs/revise_jobs.py): 고쳐 쓰기(LLM)와 감사를 기다리지 않고 "고쳐서 알려 드릴게요"로
  바로 답한다. 다 고치면 알림(revise_ready)을 보내고, 그 알림을 열면(session.revise_id) 고친 글로 다시 묻는다.
"""

import copy
import datetime as dt
import re

from voice import activity, clock, holidays, hr, locks, notebook, repo, speech, staff_orders, width
from voice.clock import iso, parse
from voice.agents import intent_judge
from voice.context import load
from voice.dialog import echo, intent_rules
from voice.dialog.intent_rules import Intent
from voice.instagram import posts, story_event
from voice.jobs import briefing as briefing_job
from voice.jobs import batch_ask, done_report, hr_batch, hr_night, review_loop, revise_jobs, staff_tasks
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
    "ask_story_event": "도나가 비 오는 날 이벤트 포스터 이야기를 하며 '스토리에 올릴까요?' 하고 물었어요",
    "ask_tasks": "도나가 '알바생 할 일로 첫째 …, 둘째 …를 넣을까요?' 하고 물었어요",
    "ask_holiday": "도나가 '○월 ○일을 쉬는 날로 적을게요. 맞아요?' 하고 물었어요",
    "ask_detail": "도나가 오늘 요약을 말한 뒤 '상세 브리핑을 시작할까요?' 하고 물었어요",
    "ask_start": "도나가 '오늘 브리핑을 시작할까요?' 하고 물었어요",
    "ask_promotion": "인사과가 '이 업무는 앞으로 먼저 처리하고 저녁에 보고할까요?' 하고 승진을 물었어요",
}
OFFER_UNTIL_HOUR = 12  # 이 시각 전(오전)에 처음 부르면 브리핑을 권한다
# "상세 브리핑을 시작할까요?"(H-05)의 대답. 같은 "응"도 묻는 상황에 따라 다른 뜻으로 갈려서 모두 받는다
DETAIL_YES = {"permission.yes", "instagram.post", "action.approve", "briefing.next"}
DETAIL_NO = {"permission.no", "instagram.later", "action.cancel"}
# 이 질문들을 묻는 중에는 놓친 알바생 할 일 질문으로 끼어들지 않는다
LATER_RE = re.compile(r"나중|다음에|내일")  # 인스타 "나중에": 반려로 세지 않는다 (9-0 n)
ASKING_TYPES = ("ask_action", "ask_staff", "ask_permission", "ask_tasks", "ask_holiday", "ask", "show_detail")
# 묻고 기다리는 세션 칸. 날짜가 바뀌면 비운다 (어제 물은 것이 오늘 첫 말을 가로채지 않게, 버그 V13)
ASKING_KEYS = ("notebook_pending", "deferred_text", "batch", "tasks_pending", "holiday_pending", "staff_pending",
               "alert_id", "story_id", "hr_batch", "revise_id")


class StoreNotFound(Exception):
    pass


def empty(kind: str) -> dict:
    return {"type": kind, "headline": None, "say": [], "cards": [], "expects_reply": False}


def asking_instagram(session: dict) -> bool:
    return session.get("step") == "instagram" and session.get("last_type") in ("ask", "show_detail")


def asking_story(session: dict) -> bool:
    """브리핑에서 '스토리 이벤트를 할까요?'를 묻고 대답을 기다리는 중."""
    return session.get("step") == "story_event" and session.get("last_type") == "ask"


def asking_detail(session: dict) -> bool:
    """브리핑 요약 뒤 '상세 브리핑을 시작할까요?'(H-05)를 묻고 대답을 기다리는 중."""
    return session.get("step") == "detail_ask" and session.get("last_type") == "ask"


def asking_start(session: dict) -> bool:
    """"도나야"만 부른 뒤 '오늘 브리핑을 시작할까요?'를 묻고 대답을 기다리는 중."""
    return bool(session.get("offer_start")) and session.get("last_type") == "ask"


def offer_briefing(brief: dict | None, session: dict) -> dict:
    """오전에 처음 "도나야"만 불렀고 오늘 브리핑을 아직 듣지 않았으면 '오늘 브리핑을 시작할까요?' (2026-11-22).
    한 번 물었으면 그날은 다시 묻지 않는다. 아니면 ignore (앱이 "네."로 대답한다)."""
    heard = session.get("step") or session.get("mode") in ("briefing", "detail", "ended")
    if brief is None or heard or session.get("offered") or clock.now().hour >= OFFER_UNTIL_HOUR:
        return empty("ignore")
    session.update(offered=True, offer_start=True)
    response = answer("오늘 브리핑을 시작할까요?", [say("네. 오늘 브리핑을 시작할까요?")],
                      [{"type": "rows", "id": "home_rows", "rows": copy.deepcopy(brief["home_rows"])}], kind="ask", ask={"key": "start_briefing"})
    response["expects_reply"] = True
    return response


def asking_promotion(session: dict) -> bool:
    """밤 9시 인사과가 '스토리는 먼저 올리고 저녁에 보고할까요?'(K-01)를 묻고 대답을 기다리는 중."""
    return bool(session.get("promotion")) and session.get("last_type") == "ask"


def situation(session: dict) -> str:
    last = session.get("last_type") or ""
    if last == "ask_action" and session.get("story_id"):
        last = "ask_story"
    elif asking_story(session):
        last = "ask_story_event"
    elif asking_detail(session):
        last = "ask_detail"
    elif asking_start(session):
        last = "ask_start"
    elif asking_promotion(session):
        last = "ask_promotion"
    return SITUATIONS.get(last, "도나는 듣고만 있어요")


def understand(text: str, session: dict, view, addressed: bool = False) -> Intent:
    found = intent_rules.match(text, session.get("last_type"), addressed, instagram=asking_instagram(session) or asking_story(session) or asking_detail(session) or asking_start(session) or asking_promotion(session))  # "응"·"아니"를 예/아니오로
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
        return {**briefing_job.end_response(brief["store_id"], session), "briefing": _gauge("end")}
    session.update(step=key, mode="briefing")
    session.setdefault("heard", {})[key] = iso(clock.now())
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


def instagram_reply(name: str, session: dict, brief: dict, view, said: str | None = None) -> dict:
    """인스타에 올릴까요(D-14) 뒤의 대답: 미리보기 넘기기, 올리기, 나중에. said: 사장님 말 (인사과 기록)."""
    if name == "instagram.next_photo":
        slides = brief["details"]["instagram"]["slides"]
        slide = session.get("insta_slide", 0) % len(slides) + 1
        session.update(insta_slide=slide, mode="detail")
        return {**copy.deepcopy(slides[slide - 1]), "briefing": _gauge("instagram")}
    if name == "instagram.revise":
        return _instagram_revise(session, brief, view, said)
    if name == "instagram.later":
        revise_jobs.cancel(view.store_id, "instagram")
        if not LATER_RE.search(intent_rules.normalize(said or "")):  # "나중에·다음에·내일"은 세지 않고, "안 해·올리지 마"는 반려 (9-0 n)
            hr.record(view.store_id, "instagram_post", f"instagram:{view.store_id}:{view.now.date().isoformat()}", "rejected", said)
        activity.log(view.store_id, "owner", "인스타는 다음에 올리기로 했어요", "instagram_later")
        return _prefixed(_go(brief, session, _after(brief, "instagram")), "네, 내일 브리핑에서 다시 여쭤볼게요.")
    revise_jobs.cancel(view.store_id, "instagram")  # 고치는 중이면 그만두고 지금 글로 올린다 (감사팀 9-3)
    built = posts.build_feed(view)
    if built is None:
        return _prefixed(_go(brief, session, _after(brief, "instagram")), "올릴 메뉴 사진이 모자라요.")
    post = posts.create(view.store_id, built)
    posts.queue_publish(view.store_id, post)
    hr.record(view.store_id, "instagram_post", f"instagram:{view.store_id}:{view.now.date().isoformat()}", "approved", said)
    activity.log(view.store_id, "owner", "인스타에 인기 메뉴를 올리라고 했어요", "instagram_ok")
    brief = briefing_job.refresh_instagram(view.store_id) or brief  # 오늘은 다시 묻지 않는다
    return _prefixed(_go(brief, session, _after(brief, "instagram")), "네, 인스타에 올릴게요.", "다 올라가면 알려 드릴게요.")


def _instagram_revise(session: dict, brief: dict, view, said: str | None) -> dict:
    """"좀 더 짧게 써 줘": 오늘 인스타 글을 뒤에서 지시대로 다시 쓰고(감사 포함) 알림으로 다시 묻는다 (인사과 6단계, 감사팀 9장).
    인사과 '조금 수정'은 지시를 받은 지금 남긴다. 고치는 동안 "올려"면 지금 글로 올린다."""
    if posts.build_feed(view) is None:
        return empty("not_understood")
    day = view.now.date().isoformat()
    hr.record(view.store_id, "instagram_post", f"instagram:{view.store_id}:{day}", "edited", said)
    revise_jobs.start(view.store_id, "instagram", day, "instagram_post", said or "", _instagram_work)
    return {**answer("고쳐서 알려 드릴게요", [say("네, 고쳐서 알려 드릴게요.")], []), "briefing": _gauge("instagram"),
            "keep_context": "ask"}  # 고치는 동안에도 "올려"·"나중에"를 인스타 대답으로 듣는다


def _instagram_work(job: dict):
    """뒤에서: 오늘 인스타 글을 고쳐 쓴다. 감사를 끝내 통과하지 못하면 고치지 못한 것으로."""
    from voice import marketing
    from voice.agents import caption_writer

    view = load(job["store_id"])
    built = posts.build_feed(view)
    plan = marketing.today(view)
    top = built["menus"] if built else None
    written = None
    if built:
        previous = (plan or {}).get("body") or built["caption"].split("\n\n")[0]
        written = caption_writer.write(view, [m["name"] for m in top["items"]], (plan or {}).get("angle") or f"{top['period']} 많이 나간 메뉴",
                                       built["quote"], revise={"previous": previous, "instruction": job["instruction"]})
    if written is not None and (written.get("audit") or {}).get("passed") is False:
        written = None

    def apply() -> str:
        if posts.posted_on(view.store_id, "feed", view.now.date()):
            return "discard"  # 고치는 사이 올렸다
        if written is None:
            return "failed"
        base = marketing.today(view) or {"store_id": view.store_id, "date": job["ref"], "menu_ids": [m["id"] for m in top["items"]],
                                         "angle": None, "sources": {"topic": "RULE"}, "lead": None, "created_at": clock.iso(clock.now())}
        repo.put(marketing.KIND, marketing.plan_id(view.store_id, job["ref"]), view.store_id,
                 {**base, "body": written["body"], "hashtags": written["hashtags"], "sources": {**base["sources"], "caption": "REVISED"}})
        briefing_job.refresh_instagram(view.store_id)
        return "ready"

    return apply


def _revise_open(view, job_id: str, session: dict, brief: dict | None) -> dict:
    """고친 알림(revise_ready)을 열었다: 고친 글(또는 못 고쳤다는 말)로 다시 묻는다."""
    job = revise_jobs.get(job_id)
    done = answer("이미 정했어요", [say("그건 이미 정했어요.")], [])
    if job is None or job["state"] not in ("ready", "failed"):
        return done
    ok = job["state"] == "ready"
    if job["target"] == "alert":
        record = repo.get("alert", job["ref"])
        if record is None or record["state"] not in review_loop.ASKING:
            return done
        session["alert_id"] = record["id"]
        lead = ["이렇게 고쳤어요."] if ok else ["지금은 고치지 못했어요.", "이대로 올릴지 다시 말씀해 주세요."]
        return {**review_loop.ask(view, record, lead=lead, headline="이렇게 올릴까요?"), "keep_context": "ask_action"}
    if job["target"] == "batch":
        response = batch_ask.reopen(view, job)
        return {**response, "keep_context": "ask_action"} if response else done
    if brief is None or not brief["steps"].get("instagram") or posts.posted_on(view.store_id, "feed", view.now.date()):
        return done
    session.update(step="instagram", mode="briefing", insta_slide=0)
    return _prefixed(_step(brief, "instagram"), "이렇게 고쳤어요." if ok else "지금은 고치지 못했어요.")


def story_reply(name: str, session: dict, brief: dict, view, said: str | None = None) -> dict:
    """'스토리 이벤트를 할까요?' 뒤의 대답: 그리기 시작하고 브리핑을 이어 가거나, 하지 않는다.
    밤사이 그려 둔 포스터를 보여 주며 물었으면 (story_event.waiting_in_briefing): "응"은 바로 올리고, 아니면 올리지 않는다."""
    yes = name in ("instagram.post", "permission.yes")
    record = story_event.get(story_event.event_id(view.store_id, view.now.date()))
    if story_event.waiting_in_briefing(record):
        edits = intent_rules.edits_in(intent_rules.normalize(said or ""))  # "할 일은 빼고 올려"
        decided = story_event.decide(view, "action.approve" if yes else "action.cancel", edits, record["id"], said)
        brief = briefing_job.refresh_instagram(view.store_id) or brief  # 오늘은 다시 묻지 않는다
        if yes and decided["headline"] != "올리지 않을게요":  # H-07: 올린 모양을 그대로 보여 준다. 가만히 있으면 다음 단계로
            session.update(step="story_event", mode="briefing")
            return {**answer("스토리에 올렸어요", [say("스토리에 올렸어요.")], [story_event.story_card(record, posted=True)]),
                    "briefing": _gauge("story_event")}
        lead = [s["text"] for s in decided["say"]] if yes else ["네, 오늘은 스토리를 올리지 않을게요."]
        return _prefixed(_go(brief, session, _after(brief, "story_event")), *lead)
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


def _batch_reply(view, intent: Intent, session: dict) -> dict:
    """묶음 질문의 대답. 브리핑 단계에서 물었으면 정한 뒤 다음 단계로 이어 간다."""
    response = batch_ask.decide(view, intent.name, intent.edits, session, intent.owner_said)
    step = session.get("step")
    in_briefing = session.get("mode") == "briefing" and step in STEP_KEYS
    if response.get("keep_batch"):  # 뒤에서 고치는 중: 그대로 묻는 중으로 둔다 (알림이 오면 다시 묻는다)
        return {**response, "keep_context": "ask_action", **({"briefing": _gauge(step)} if in_briefing else {})}
    if response["type"] == "ask_action":  # 다음 건을 이어 묻는다 (인턴) 또는 고쳐서 다시 묻는다
        return {**response, "keep_context": "ask_action", **({"briefing": _gauge(step)} if in_briefing else {})}
    if not in_briefing:
        return response
    brief = briefing_job.refresh_steps(view.store_id)
    if response.get("own_screen"):  # J-10b: 고쳐 올린 화면을 따로 보여 주고, 가만히 있으면 다음 단계로
        return {**response, "briefing": _gauge(step)}
    following = _go(brief, session, _after(brief, step))
    return {**following, "say": response["say"] + following["say"]}


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
    if name == "briefing.offer":  # "도나야"만 불렀다
        return offer_briefing(brief, session)
    if brief is not None and asking_start(session) and (name in DETAIL_YES or name in DETAIL_NO):  # "오늘 브리핑을 시작할까요?"의 대답
        session.pop("offer_start", None)
        if name in DETAIL_YES:
            return _go(brief, session, _after(brief, None, inclusive=True))
        return answer("필요하실 때 불러 주세요", [say("네, 필요하실 때 불러 주세요.")], [])
    if name == "notice.open" and session.pop("hr_night", False):  # 밤 9시 인사과 보고 (K-01)
        return hr_night.report(view) or answer("오늘은 보고할 게 없어요", [say("오늘은 인사과 보고가 없어요.")], [])
    if session.get("promotion") and session.get("last_type") == "ask" and (name in DETAIL_YES or name in DETAIL_NO):  # K-01 대답
        job = session.pop("promotion")
        return hr_night.decide(view, job, name in DETAIL_YES, intent.owner_said)
    if brief is not None and session.get("step") == "detail_ask" and session.get("last_type") == "ask":  # H-05 상세 브리핑을 시작할까요?
        if name in DETAIL_YES:
            return _go(brief, session, _after(brief, "detail_ask"))
        if name in DETAIL_NO:
            return _prefixed(_go(brief, session, None), "네, 필요하실 때 다시 불러 주세요.")
    if session.get("last_type") == "ask_tasks" and (name.startswith("action.") or name in ("permission.yes", "permission.no")):
        name = {"permission.yes": "action.approve", "permission.no": "action.cancel"}.get(name, name)
        response = staff_tasks.decide(view, name, intent.edits, session, intent.owner_said)
        briefing_job.refresh_steps(view.store_id)
        if session.get("step") == "staff_tasks" and session.get("mode") == "briefing" and response["type"] == "answer":
            response = {**response, "briefing": _gauge("staff_tasks")}  # 브리핑 중 대답(H-12): 가만히 있으면 끝(H-12b)으로 넘어간다
        return {**response, "answered_tasks": True, **({"keep_context": "ask_tasks"} if response["type"] == "ask_tasks" else {})}
    if name in ("store.holiday", "store.holiday_cancel"):  # 쉬는 날 (voice/holidays.py)
        return holidays.from_words(view, name, intent.owner_said)
    if name in ("holiday.yes", "holiday.no"):
        response = holidays.decide(view, name, session)
        briefing_job.refresh_steps(view.store_id)
        return response
    if name == "notice.open" and session.get("revise_id"):  # 뒤에서 고친 알림을 열었다 (감사팀 9장)
        return _revise_open(view, session.pop("revise_id"), session, brief)
    if name == "notice.open" and session.get("hr_batch"):  # 묶음 창 알림을 열었다
        return hr_batch.ask(view, session.pop("hr_batch")) or answer("이미 정했어요", [say("그건 이미 정했어요.")], [])
    if session.get("batch") and name.startswith("action."):  # 인턴·사원 결재 묻기 (jobs/batch_ask.py, 인사과 4단계)
        return _batch_reply(view, intent, session)
    if session.get("story_id") and (name.startswith("action.") or name == "notice.open"):  # 스토리 이벤트 포스터를 묻는 중
        return {**story_event.decide(view, name, intent.edits, session["story_id"], intent.owner_said), "keep_context": "ask_action"}
    if name.startswith("action.") or name == "notice.open":  # 아쉬운 리뷰 고리. 브리핑과 상관없이
        if name == "action.repeat":
            name = "notice.open"
        return {**review_loop.decide(view, name, intent.edits, session.get("alert_id"), intent.owner_said), "keep_context": "ask_action"}
    if name == "notebook.read":  # 업무 수첩 (voice/notebook.py, 인사과 7단계)
        return notebook.read(view.store_id)
    if name == "notebook.remove" or (name == "report.undo" and session.get("notebook_pending")):
        return notebook.remove_by_words(view.store_id, intent.owner_said, session)
    if name == "report.undo":  # 사후 취소 (jobs/done_report.py)
        return done_report.undo(view, intent.owner_said)
    if name.startswith("staff."):  # 알바생 일 (voice/staff_orders.py). 브리핑과 상관없이
        return staff_orders.handle(view, intent, session)
    if name in ("instagram.feed", "instagram.story"):
        return post_now(view, name.split(".", 1)[1])
    if brief is None:
        return _not_ready()

    step = session.get("step")
    if asking_story(session) and name in ("permission.yes", "permission.no", "instagram.post", "instagram.later"):
        return story_reply(name, session, brief, view, intent.owner_said)
    if asking_instagram(session) and name in ("permission.yes", "permission.no"):  # LLM 이 허락 대답으로 가른 경우
        name = "instagram.post" if name == "permission.yes" else "instagram.later"
    if name.startswith("instagram."):
        if not asking_instagram(session) or not brief["details"].get("instagram"):
            return empty("not_understood")
        return instagram_reply(name, session, brief, view, intent.owner_said)
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
        target = {"schedule": "sum_weather", "positive": "reviews"}.get(intent.jump_to, intent.jump_to)
        target = target if target in STEP_KEYS else "reviews"
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
    if name in ("permission.yes", "permission.no"):  # 허락 질문(D-10)은 없앴다 (인사과 4-a). 직급이 정한다
        return empty("not_understood")
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


def _missed_tasks(intent: Intent, session: dict, view, addressed: bool) -> bool:
    """"도나야"로 부른 말이고, 다른 것을 묻는 중이 아니고, 브리핑 밖이고, 오늘 못 물은 알바생 할 일이 남았다.
    브리핑을 부르는 말은 뺀다: 브리핑 마지막 단계(staff_tasks)가 묻는다 (2026-11-21, 앞에서 가로채 마지막 단계가 비던 것)."""
    return (addressed and intent.name not in ("echo", "not_for_donna", "stop", "unknown") and not intent.name.startswith("action.")
            and not intent.name.startswith("briefing.")
            and session.get("mode") != "briefing" and session.get("last_type") not in ASKING_TYPES
            and staff_tasks.unasked_today(view, clock.now()))


def handle(request: dict) -> dict:
    """같은 가게의 말은 하나씩 처리한다. /v1/turn 은 스레드풀에서 동시에 돌 수 있는데, 세션을 읽고 → 뜻 판정(최대 3초)을
    기다리고 → 세션을 쓰는 사이에 다른 말(auto_next, 겹친 말, 같은 request_id 재전송)이 끼면 단계가 두 번 넘어가거나 덮인다."""
    with locks.lock("turn", request["store_id"]):
        return _handle(request)


def _handle(request: dict) -> dict:
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
    today = clock.now().date().isoformat()  # 앱의 session_id 는 날짜를 넘겨 이어진다 (달력 날짜로 본다)
    if session.get("day") != today:
        for key in ASKING_KEYS:
            session.pop(key, None)
        if session.get("last_type") in ASKING_TYPES:
            session["last_type"] = None
        session["day"] = today
    utterance = request.get("utterance") or None
    addressed = False
    if request.get("event") == "notice":
        notice = repo.get("notice", request.get("notice_id") or "") or {}
        session.pop("hr_batch", None)
        session.pop("revise_id", None)
        if notice.get("kind") == revise_jobs.NOTICE:  # 뒤에서 고친 글 (감사팀 9장)
            session["revise_id"] = notice.get("alert_id")
            session.pop("story_id", None)
        elif notice.get("kind") == story_event.KIND:  # 이벤트 포스터를 다 그렸어요
            session["story_id"] = notice.get("alert_id")
            session.pop("alert_id", None)
        elif notice.get("kind") == hr_night.KIND:  # 밤 9시 인사과 보고 (jobs/hr_night.py)
            session["hr_night"] = True
            session.pop("alert_id", None)
            session.pop("story_id", None)
        elif notice.get("kind") == hr_batch.KIND:  # 사원 업무 묶음 창 (jobs/hr_batch.py)
            session["hr_batch"] = notice.get("alert_id")
            session.pop("alert_id", None)
            session.pop("story_id", None)
        else:
            session.pop("story_id", None)
            session["alert_id"] = notice.get("alert_id") or (review_loop.pending(store_id) or {}).get("id")
        intent = Intent("notice.open", None)
    elif request.get("event") == "called":  # "도나야"만 불렀다 (앱). 오전 첫 부름이면 브리핑을 권한다
        intent = Intent("briefing.offer", None)
    elif request.get("event") == "night_hr":  # 시연: 아침 브리핑 끝 화면 뒤 밤 9시로 (jobs/hr_night.py)
        if hr_night.has_scene(store_id):
            hr_night.jump_to_night(store_id)
            session["hr_night"] = True
            session["clock_moved"] = True
        intent = Intent("notice.open", None)
    elif request.get("event") == "auto_next" or utterance is None:
        intent = Intent("briefing.next", None)
    else:
        addressed = bool(utterance.get("addressed"))
        # 묻고 있는 아쉬운 리뷰가 있으면 "도나야, 진행해"도 그 대답이다 (다른 질문을 묻는 중이면 그쪽이 먼저)
        # 다만 알림이 그 질문보다 나중에 왔으면 알림의 대답이다 (버그 V10). 언제 물었는지 모르는 예전 세션은 질문이 먼저
        live = review_loop.pending(store_id) if addressed else None
        asked_at = session.get("last_at")
        other_question = (session.get("last_type") in ASKING_TYPES and session.get("last_type") != "ask_action"
                          and (asked_at is None or live is None or parse(asked_at) >= parse(live["created_at"])))
        if live and not other_question:
            session["last_type"] = "ask_action"
            if live["state"] in review_loop.ASKING:  # 묻고 있는 리뷰가 있으면 그 대답이다 (스토리 이벤트보다 먼저)
                session.pop("story_id", None)
        if session.get("last_type") != "ask_action":
            session.pop("alert_id", None)
            session.pop("story_id", None)
        if echo.is_echo(store_id, utterance["text"]):
            intent = Intent("echo", intent_rules.tidy(utterance["text"]))
        else:
            intent = understand(utterance["text"], session, view, addressed)

    brief = briefing_job.current(store_id)
    answered = False
    if _missed_tasks(intent, session, view, addressed):  # 브리핑에서 못 물은 알바생 할 일을 먼저 묻는다 (2026-11-20)
        response = staff_tasks.step(view, clock.now(), lead=["그 전에 하나만요."])
        session["deferred_text"] = utterance["text"]
    else:
        response = dispatch(intent, session, brief, view)
        answered = response.pop("answered_tasks", False)
        if answered and response["type"] != "ask_tasks" and session.get("deferred_text"):
            later = dispatch(understand(session.pop("deferred_text"), session, view, True), session, briefing_job.current(store_id), view)
            response = {**later, "say": response["say"] + later["say"], "cards": response["cards"] + later["cards"]}
    if response["type"] not in ("ask_tasks", "ignore", "not_understood") and not answered:
        session.pop("deferred_text", None)  # "그 전에 하나만요"에 대답하지 않고 넘어갔다. 원래 말은 버린다
    staff_tasks.remember_asked(response, session)
    batch_ask.remember(response, session)
    if not response.get("notebook_ask") and response["type"] not in ("ignore", "not_understood"):
        session.pop("notebook_pending", None)  # "어느 규칙을 지울까요?"에 대답하지 않고 넘어갔다
    if response.get("report"):  # 사후 보고를 앱에 보냈다 (9-0 h)
        hr.mark_reported(store_id, response["report"])
    if response.get("promotion"):  # 밤 9시 승진을 묻는 중 (K-01). 대답은 dispatch 가 hr_night.decide 로
        session["promotion"] = response["promotion"]
    if response.get("holiday"):  # 쉬는 날을 묻는 중 (holiday.yes / holiday.no 가 본다)
        session["holiday_pending"] = response["holiday"]
    response.setdefault("briefing", None)
    if response["type"] not in ("ignore", "not_understood"):
        session["last_type"] = response.get("keep_context") or response["type"]
        session["last_at"] = iso(clock.now())
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
        **({"next_scene": response["next_scene"]} if response.get("next_scene") else {}),
        **({"clock_moved": True} if session.pop("clock_moved", False) else {}),
    }
    echo.remember(store_id, [item["text"] for item in response["say"]])  # 이 말이 마이크로 다시 들어오면 흘려듣는다
    session["last_turn_id"] = response["turn_id"]
    repo.put("session", session_id, store_id, session)
    repo.put("turn", turn_key, store_id, {"request": request, "response": response})
    return response
