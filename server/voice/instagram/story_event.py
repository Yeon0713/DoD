"""비 오는 날 스토리 이벤트 → 알바생 할 일 (개선안 [2]-3 A3, 고리 [2] 온라인 → 오프라인).

  1. 비 오는 날 브리핑에서 도나가 묻는다 (단계 story_event, type ask): "… 이벤트 포스터를 만들어 스토리에 올릴까요?"
  2. "응" → 뒤에서 AI 포스터를 그린다 (메인 서버 app/poster_ai, 50초 ~ 2분). 다 되면 알림(story_event, opens_turn)
  3. 사장님 앱이 알림을 열면 미리보기와 함께 묻는다 (type ask_action): "스토리에 올리고, 알바생 할 일 맨 위에 … 넣을까요?"
     "응, 올려" → 스토리 게시 작업 / "다시 그려 줘" → 다시 그림 / "할 일은 넣지 마" → 스토리만 / "안 해" → 하지 않음
  4. 스토리가 올라가면 알바생 할 일 맨 위에 이벤트 카드를 넣는다 (urgent). 게시에 실패하면 카드를 넣지 않는다.

이벤트 혜택은 사장님이 설정에 정해 둔 문장(settings.story_event)만 쓴다. 가게가 손님에게 하는 약속이라 지어내지 않는다.
  {"headline": "비 오는 날 이벤트", "offer": "매장을 태그해 스토리에 올려 주시면 음료 1캔을 드려요", "staff_task": "스토리 태그 손님 음료 1캔 드리기"}
그림 모델에는 이 글자를 그대로 넣으라고 한다 (app/poster_ai/prompt.py).

상태 (저장소 종류 story_event, id se_<가게>_<날짜>: 하루 하나)
  generating → ready → approved → published → card_pinned
             → failed (그림 실패, 게시 실패)       ready → declined
"""

import datetime as dt
import io
import logging
import threading

from PIL import Image

from app.poster_ai import image_engine
from app.poster_ai import prompt as poster_prompt
from app.poster_ai.situation import Situation
from voice import activity, clock, notices, repo, speech, staff
from voice.clock import iso
from voice.context import VoiceStore, load
from voice.instagram import media, posts

logger = logging.getLogger(__name__)

KIND = "story_event"
DONE = {"approved", "published", "card_pinned"}
_drawing = threading.Lock()  # 한 번에 하나만 그린다 (구독 사용량을 한꺼번에 쓰지 않게)


def _spawn(target, *args) -> None:
    threading.Thread(target=target, args=args, daemon=True, name="story-poster").start()


spawn = _spawn  # 테스트에서는 바로 돌린다


def _obj(word: str) -> str:
    return speech.josa(word, "을", "를")


def event_id(store_id: str, day: dt.date) -> str:
    return f"se_{store_id}_{day.isoformat()}"


def get(se_id: str | None) -> dict | None:
    return repo.get(KIND, se_id) if se_id else None


def save(record: dict) -> dict:
    return repo.put(KIND, record["id"], record["store_id"], record)


def preset(store_id: str) -> dict | None:
    """사장님이 정해 둔 이벤트. 혜택(offer)과 알바생 할 일(staff_task)이 없으면 None (제안하지 않는다)."""
    found = repo.settings(store_id).get("story_event") or {}
    if not (found.get("offer") and found.get("staff_task")):
        return None
    return {"headline": found.get("headline") or "비 오는 날 이벤트", "offer": found["offer"], "staff_task": found["staff_task"]}


# ── 1. 브리핑에서 묻기 ──


def step(view: VoiceStore) -> dict | None:
    """브리핑 단계 story_event. 비 오는 날 + 설정 있음 + 인스타 연결 + 오늘 아직 안 함 + 1등 메뉴 사진이 있을 때만."""
    from voice.jobs.briefing import answer, rain_text, rain_today, say

    today = view.now.date()
    rain = rain_today(view, today)
    event = preset(view.store_id)
    if not (rain and event and posts.connection(view.store_id)["connected"]):
        return None
    if get(event_id(view.store_id, today)) or not posts.top_menus(view, 1)["items"]:
        return None
    says = [say(f"오늘은 {rain_text(rain, today)} 소식이 있어요."),
            say("비 오는 날 손님을 부르는 스토리 이벤트를 준비했어요."),
            say(f"{event['offer']}.", None, ["story_offer"]),
            say("이벤트 포스터를 만들어 스토리에 올릴까요?")]
    response = answer("스토리 이벤트를 할까요?", says, _offer_cards(event, posted=False), kind="ask", ask={"key": "story_event"})
    response["expects_reply"] = True
    return response


def _offer_cards(event: dict, *, posted: bool, use_card: bool = True) -> list[dict]:
    cards = [{"type": "quote", "id": "story_offer", "label": event["headline"], "text": event["offer"]}]
    if use_card:
        cards.append({"type": "checklist", "id": "event_card", "title": "알바생 할 일 맨 위에 넣은 것" if posted else "알바생 할 일에 넣을 것",
                      "items": [{"id": "event_card_item", "title": staff_title(event), "sub": "알바생 확인 전" if posted else "스토리가 올라가면 넣어요",
                                 "state": "todo", "tone": "urgent"}]})
    return cards


def staff_title(event: dict) -> str:
    return f"[이벤트] {event['staff_task']}"


# ── 2. 그리기 ──


def start(store_id: str) -> dict | None:
    """오늘 이벤트 포스터를 (다시) 그리기 시작한다. 이미 올렸거나 그리는 중이면 그대로 둔다."""
    view = load(store_id)
    event = preset(store_id)
    if view is None or event is None:
        return None
    se_id = event_id(store_id, view.now.date())
    with repo._lock:
        record = get(se_id)
        if record and record["state"] in DONE | {"generating"}:
            return record
        record = save({
            "id": se_id, "store_id": store_id, "date": view.now.date().isoformat(), "state": "generating", **event,
            "use_card": True, "drawn": (record or {}).get("drawn", 0), "image_url": None, "post_id": None, "task_id": None,
            "error": None, "started_at": iso(clock.now()), "created_at": (record or {}).get("created_at") or iso(clock.now()),
        })
    activity.log(store_id, "owner", "비 오는 날 스토리 이벤트를 하기로 했어요", "story_event_ok")
    spawn(draw, se_id)
    return record


def _situation(view: VoiceStore) -> Situation:
    from voice.jobs.briefing import weather_on

    store = view.store
    weather = weather_on(view, view.now.date()) or {}
    return Situation(store_id=view.store_id, store_name=store["name"], category=store.get("category") or "", address=store.get("address") or "",
                     date=view.now.date(), kind="RAIN", title="비 오는 날", temp_max=weather.get("temp_max"), temp_min=weather.get("temp_min"),
                     rain_mm=weather.get("rain_mm"), weather_tags=["RAIN"], menus=[m["name"] for m in view.menus])


def _prompt(view: VoiceStore, record: dict) -> tuple[str, list]:
    """그림 모델에 줄 프롬프트와 첨부 그림 (로고, 1등 메뉴 사진)."""
    top = posts.top_menus(view, 1)["items"][0]
    files = []
    logo = view.store.get("logo_url")
    if logo:
        files.append(media.source_path(logo))
    files.append(media.source_path(top["photo_url"]))
    choice = poster_prompt.PosterChoice(headline=record["headline"], line=record["offer"], style="PHOTO", menu=top["name"],
                                        photo_labels=(top["name"],), has_logo=bool(logo))
    return poster_prompt.build(_situation(view), choice), files


def draw(se_id: str) -> dict | None:
    """그림을 그려 MEDIA_DIR/<se_id>/poster_<n>.jpg 로 두고 사장님께 알린다. 실패하면 failed 로 두고 알린다."""
    with _drawing:
        record = get(se_id)
        if record is None or record["state"] != "generating":
            return record
        store_id = record["store_id"]
        try:
            view = load(store_id)
            text, files = _prompt(view, record)
            story = image_engine.to_story(image_engine.generate(text, files))
            number = record["drawn"] + 1
            path = media.MEDIA_DIR / se_id / f"poster_{number}.jpg"  # 다시 그리면 이름을 바꾼다 (앱이 옛 그림을 들고 있지 않게)
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.open(io.BytesIO(story)).convert("RGB").save(path, "JPEG", quality=media.QUALITY)  # 인스타는 JPEG 만 받는다
        except Exception as error:  # PosterEngineError(로그인·사용량·시간 초과), 사진 파일 오류
            logger.warning("이벤트 포스터를 그리지 못했어요 %s: %s", se_id, error)
            save({**record, "state": "failed", "error": str(error)})
            notices.push(store_id, KIND, "이벤트 포스터를 그리지 못했어요", say=["이벤트 포스터를 그리지 못했어요."])
            return get(se_id)
        record = save({**record, "state": "ready", "drawn": number, "image_url": f"/media/{se_id}/{path.name}", "ready_at": iso(clock.now())})
    notices.push(store_id, KIND, "이벤트 포스터를 다 만들었어요", opens_turn=True, alert_id=se_id)
    return record


# ── 3. 미리보기와 대답 ──


def _preview(view: VoiceStore, record: dict) -> dict:
    """앱의 insta_post 카드 (4:5 로 보인다. 포스터는 위 12%, 아래 15% 에 중요한 글자를 두지 않아 잘려도 글이 남는다)."""
    connection = posts.connection(view.store_id)
    return {"type": "insta_post", "id": "story_preview", "handle": connection.get("handle") or "", "logo_url": view.store.get("logo_url"),
            "slide": 1, "slides": 1, "photo_url": record["image_url"], "top_label": "", "title": "", "caption": record["offer"]}


def _offer(record: dict) -> str:
    if record["use_card"]:
        return f"스토리에 올리고, 알바생 할 일 맨 위에 {_obj(staff_title(record))} 넣을까요?"
    return "알바생 할 일은 빼고 스토리만 올릴까요?"


def ask(view: VoiceStore, record: dict, *, lead: list[str] | None = None, headline: str | None = None) -> dict:
    from voice.jobs.briefing import answer, say

    says = [say(text) for text in (lead if lead is not None else ["이벤트 포스터를 다 만들었어요.", "화면에 띄웠어요."])]
    cards = [_preview(view, record), *_offer_cards(record, posted=False, use_card=record["use_card"])[1:]]
    response = answer(headline or "이벤트 포스터를 다 만들었어요", [*says, say(_offer(record))], cards, kind="ask_action")
    response["expects_reply"] = True
    return response


def _status(record: dict) -> tuple[str, str]:
    """묻는 중이 아닐 때의 대답 (화면 제목, 말)."""
    return {
        "generating": ("아직 그리고 있어요", "포스터를 아직 그리고 있어요. 다 되면 알려 드릴게요."),
        "failed": ("포스터를 못 그렸어요", "이벤트 포스터를 그리지 못했어요. 다시 그리려면 '다시 그려 줘'라고 말씀해 주세요."),
        "declined": ("이벤트는 하지 않아요", "오늘 스토리 이벤트는 하지 않기로 하셨어요."),
    }.get(record["state"], ("스토리는 이미 올렸어요", "이벤트 스토리는 이미 올렸어요."))


def decide(view: VoiceStore, intent_name: str, edits: dict | None, se_id: str | None) -> dict:
    """알림을 연 뒤의 대답 (notice.open | action.approve | action.edit | action.cancel | action.unclear | action.repeat | action.redo)."""
    from voice.jobs.briefing import answer, say

    record = get(se_id) or get(event_id(view.store_id, view.now.date()))
    if record is None:
        return answer("지금은 물어본 게 없어요", [say("지금은 여쭤본 게 없어요.")], [])
    if intent_name == "action.redo":
        if record["state"] in DONE | {"generating"}:
            headline, text = _status(record)
            return answer(headline, [say(text)], [])
        start(view.store_id)
        return answer("포스터를 다시 그릴게요", [say("네, 포스터를 다시 그릴게요."), say("1~2분 걸려요. 다 되면 알려 드릴게요.")], [])
    if record["state"] != "ready":
        headline, text = _status(record)
        return answer(headline, [say(text)], [])
    if intent_name in ("notice.open", "action.repeat"):
        return ask(view, record)
    if intent_name == "action.unclear":
        return ask(view, record, lead=["올리시려면 '응, 올려'라고 말씀해 주세요."], headline="이렇게 올릴까요?")
    if intent_name == "action.cancel":
        save({**record, "state": "declined", "decided_at": iso(clock.now())})
        activity.log(view.store_id, "owner", "스토리 이벤트는 올리지 않기로 했어요", "story_event_no")
        return answer("올리지 않을게요", [say("네, 올리지 않을게요.")], [])

    if edits and edits.get("no_card") and record["use_card"]:
        record = save({**record, "use_card": False})
        if intent_name == "action.edit":
            return ask(view, record, lead=[], headline="이렇게 올릴까요?")
    elif intent_name == "action.edit":
        return ask(view, record, lead=["무엇을 바꿀지 다시 말씀해 주세요."], headline="이렇게 올릴까요?")

    # action.approve
    with repo._lock:
        record = get(record["id"])
        if record["state"] != "ready":  # 다른 기기에서 먼저 대답했다
            headline, text = _status(record)
            return answer(headline, [say(text)], [])
        built = {"kind": "story", "slides": [{"src": record["image_url"], "top_label": record["headline"], "title": record["offer"]}],
                 "caption": None, "quote": None}
        post = posts.create(view.store_id, built)
        post = posts.save({**post, "event_id": record["id"]})
        record = save({**record, "state": "approved", "post_id": post["id"], "decided_at": iso(clock.now())})
    posts.queue_publish(view.store_id, post)
    says = [say("네, 이벤트 스토리를 올릴게요.")]
    if record["use_card"]:
        says.append(say(f"올라가면 알바생 할 일 맨 위에 {_obj(staff_title(record))} 넣을게요."))
    return answer("이벤트 스토리를 올릴게요", says, [_preview(view, record)])


# ── 4. 올라간 뒤 ──


def on_post_done(store_id: str, post: dict) -> None:
    """posts.publish 가 이벤트 스토리를 올렸거나(published) 못 올렸을 때(failed) 부른다."""
    record = get(post.get("event_id"))
    if record is None:
        return
    if post["status"] != "published":
        save({**record, "state": "failed", "error": post.get("error")})
        notices.push(store_id, KIND, "이벤트 스토리를 올리지 못했어요",
                     say=["이벤트 스토리를 올리지 못했어요.", "알바생 할 일에도 넣지 않았어요."])
        return
    activity.log(store_id, "donna", "인스타에 비 오는 날 이벤트 스토리를 올렸어요", "story_event_posted")
    if not record["use_card"]:
        save({**record, "state": "published", "permalink": post.get("permalink")})
        notices.push(store_id, KIND, "이벤트 스토리를 올렸어요", say=["이벤트 스토리를 올렸어요."])
        return
    title = staff_title(record)
    task = staff.add_task(store_id, title, "open", urgent=True, detail=record["offer"], origin="story_event",
                          source={"type": KIND, "id": record["id"], "post_id": post["id"], "permalink": post.get("permalink")})
    save({**record, "state": "card_pinned", "task_id": task["id"], "permalink": post.get("permalink")})
    activity.log(store_id, "donna", f"알바생 할 일에 {_obj(title)} 넣었어요", "story_event_card")
    notices.push(store_id, KIND, "이벤트 스토리를 올렸어요",
                 say=["이벤트 스토리를 올렸어요.", f"알바생 할 일 맨 위에 {_obj(title)} 넣었어요."])
