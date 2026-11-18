"""F7 브리핑 묶음 만들기. 출근 한 시간 전에 돌고, 준비한 뒤 새 리뷰가 들어오면 다시 돈다.

순서
  1. F6 답글 예약: 답글 기다리는 좋은 리뷰에 올릴 때·이유를 정하고(규칙) 답글을 쓴다(voice_reply 에이전트)
  2. 아쉬운 리뷰에 답글을 미리 써 둔다 (voice_reply). 허락하면 그 자리에서 바로 올리고, 거절한 가게면 초안으로 둔다
  3. F5 좋아한 점(규칙)
  4. 인스타에 올릴 것 (연결한 가게만, 많이 나간 메뉴 3개 + 가게 소개. 올리는 건 사장님이 "올려" 한 뒤)
  5. 홈 요약 + 단계 응답 + 단계마다 자세히 보기(show/read)를 만들어 briefing 표에 저장한다
/v1/turn 은 여기서 만든 것을 꺼내기만 한다 (LLM 없음). 모든 화면 글은 width 한도 안에 들어가게 fit 으로 고른다.

v0.2.1 화면 규칙 (문서 17장, Figma 'v0.2.1 : 디자인개선' D-07 ~ D-16)
- 칩(추천 답변)이 없다. 응답에 suggestions 를 넣지 않는다.
- 카드 줄(rows)에 이름표(label)가 없다. value 는 혼자 읽혀야 하고, 숫자는 아라비아 숫자로 쓴다.
- caption 은 카드에 없는 것(이유, 질문)일 때만 준다.
- 고칠 점(tip improve)은 화면에서 뺐다 (17-4). 인스타 단계(4)는 인스타를 연결한 가게에만 있다 (D-14, D-15).
"""

import datetime as dt

from voice import activity, clock, config, repo, speech, width
from voice.agents import voice_reply
from voice.clock import iso, parse
from voice.context import VoiceStore, load
from voice.instagram import posts, story_event
from voice.jobs import queue, schedule, strengths

TOTAL = 5  # 게이지바 다섯 칸: 일정, 리뷰, 좋은 리뷰, 인스타, 끝. 건너뛴 칸이 있어도 그대로다 (문서 10장)
STEP_KEYS = ["schedule", "reviews", "negative", "positive", "scheduling", "instagram", "story_event"]
GAUGE = {"schedule": 1, "reviews": 2, "negative": 2, "positive": 3, "scheduling": 3, "instagram": 4, "story_event": 4, "end": 5}
INSTAGRAM_ROW = {"id": "p_instagram", "kind": "instagram", "value": "인기 메뉴 피드 준비"}
ORDINAL = ["첫", "둘째", "셋째", "넷째", "다섯째"]
RAIN_CHANCE = 0.6


def say(text: str, caption: str | None = None, focus: list[str] | None = None) -> dict:
    return {"text": text, "caption": caption, "focus": focus or []}


def answer(headline: str, says: list[dict], cards: list[dict], kind: str = "answer", **extra) -> dict:
    return {"type": kind, "headline": headline, "say": says, "cards": cards, "expects_reply": False, **extra}


# ── 데이터 고르기 ──


def _today(items: list[dict], today: dt.date) -> list[dict]:
    return sorted((i for i in items if parse(i["starts_at"]).date() == today), key=lambda i: i["starts_at"])


def weather_on(view: VoiceStore, day: dt.date) -> dict | None:
    return next((w for w in view.data.get("weather", []) if w["date"] == day.isoformat()), None)


def rain_today(view: VoiceStore, day: dt.date) -> dict | None:
    w = weather_on(view, day)
    return w if w and w.get("rain_chance", 0) >= RAIN_CHANCE else None


def rain_text(w: dict, day: dt.date) -> str:
    """'오후 2시부터 비' 또는 '하루 종일 비' (화면 글)."""
    hour = w.get("rain_from")
    return f"{speech.clock_label(dt.datetime(day.year, day.month, day.day, hour))}부터 비" if hour else "하루 종일 비"


def awaiting(view: VoiceStore) -> list[dict]:
    """답글 기다리는 리뷰: 아직 올리지 않은 것 (예약해 둔 답글 포함)."""
    return [r for r in view.reviews() if r.get("reply_status", "none") != "posted"]


def auto_replied(view: VoiceStore, now: dt.datetime) -> list[dict]:
    """지난 하루 동안 도나가 바로 답한 아쉬운 리뷰 (최근 것 먼저). 사장님이 알림을 듣고 "진행해"로 올린 것은 이미 아시니 빼다."""
    since = now - dt.timedelta(days=1)
    found = [r for r in view.reviews() if r.get("reply_by") == "donna" and r.get("sentiment") == "negative"
             and r.get("reply_status") == "posted" and r.get("reply_trigger") != "owner_yes"
             and since <= parse(r["reply_posted_at"]) <= now]
    return sorted(found, key=lambda r: r["reply_posted_at"], reverse=True)


def recent_positive(view: VoiceStore, now: dt.datetime) -> list[dict]:
    since = now - config.POSITIVE_WINDOW
    return [r for r in view.reviews() if r.get("sentiment") == "positive" and since <= parse(r["written_at"]) <= now]


# ── 1~2: 미리 해 두는 일 ──


def schedule_replies(view: VoiceStore, now: dt.datetime) -> int:
    """답글 기다리는 좋은 리뷰마다 올릴 때(schedule.occasion_for: 평일 리뷰 → 토요일 오전, 주말 리뷰 → 24~48시간 안 식사 피크
    한 시간 전)를 정하고 답글을 써 둔다. 그날의 날씨·행사는 글에만 들어간다."""
    waiting = [r for r in view.reviews() if r.get("sentiment") == "positive" and r.get("reply_status", "none") == "none"]
    if not waiting:
        return 0
    for review in sorted(waiting, key=lambda r: r["written_at"]):
        slot = schedule.occasion_for(review, view.data, view.store, now)
        occasion = {**slot, "post_at": iso(slot["post_at"])}
        written = voice_reply.write(view, review, "SCHEDULED", occasion)
        review.update({
            "reply_status": "scheduled", "reply_by": "donna", "reply_text": written["text"], "reply_source": written["source"],
            "reply_notes": written["notes"], "reply_post_at": occasion["post_at"],
            "reply_reason": {key: slot[key] for key in ("kind", "label", "meal", "context", "explanation")},
        })
        repo.save_review(review)
        queue.add(view.store_id, "post_scheduled", slot["post_at"])
    return len(waiting)


def draft_negative(view: VoiceStore) -> None:
    """아쉬운 리뷰에 답글을 미리 써 둔다. 허락하면 이 글을 바로 올린다 (말하는 동안 LLM 을 기다리지 않게).
    허락을 거절한 가게면 초안(drafted)으로 보여 준다."""
    declined = repo.settings(view.store_id).get("negative_review_auto_reply") is False
    for review in view.reviews():
        if review.get("sentiment") != "negative" or review.get("reply_status", "none") != "none":
            continue
        if not review.get("reply_ready"):
            written = voice_reply.write(view, review, "DRAFT" if declined else "AUTO")
            review["reply_ready"] = written
        if declined:
            review.update({"reply_status": "drafted", "reply_by": "donna", "reply_text": review["reply_ready"]["text"],
                           "reply_source": review["reply_ready"]["source"]})
        repo.save_review(review)


def post_ready_negatives(store_id: str, now: dt.datetime) -> list[dict]:
    """허락을 받은 그 자리에서, 미리 써 둔 답글을 밤사이 아쉬운 리뷰에 올린다 (Figma D-10 → D-11)."""
    view = load(store_id)
    posted = []
    for review in view.reviews():
        if review.get("sentiment") != "negative" or review.get("reply_status", "none") != "none":
            continue
        ready = review.get("reply_ready") or voice_reply.write(view, review, "AUTO")
        review.update({
            "reply_status": "posted", "reply_by": "donna", "reply_text": ready["text"], "reply_source": ready["source"],
            "reply_posted_at": iso(now), "replied_in_minutes": max(1, round((now - parse(review["written_at"])).total_seconds() / 60)),
            "reply_trigger": "permission",
        })
        posted.append(repo.save_review(review))
    if posted:
        activity.log(store_id, "donna", f"아쉬운 리뷰 {len(posted)}개에 답글을 올렸어요", "negative_replied")
    return posted


# ── 3: 단계 응답 ──


def step_schedule(view: VoiceStore, today: dt.date) -> dict:
    events, games = _today(view.data.get("event", []), today), _today(view.data.get("game", []), today)
    reservations = _today(view.data.get("reservation", []), today)
    general = [r for r in reservations if r["party_size"] < config.GROUP_MIN_PEOPLE]
    groups = [r for r in reservations if r["party_size"] >= config.GROUP_MIN_PEOPLE]
    rain = rain_today(view, today)
    if not (events or games or reservations or rain):
        return answer("오늘은 평소와 같아요", [say("오늘은 행사나 예약이 없어요."), say("평소와 같아요.")], [])

    rows: list[dict] = []
    says = [say("오늘 일정이에요.")]
    for item, kind, rid in ((events[:1], "event", "s_event"), (games[:1], "game", "s_game")):
        if item:
            start = parse(item[0]["starts_at"])
            value = width.fit("rows.value", f"{item[0]['name']} {speech.clock_label(start)}", item[0]["name"])
            rows.append({"id": rid, "kind": kind, "value": value})
    names = [e["name"] for e in events[:1]] + [g["name"] for g in games[:1]]
    if names:
        joined = speech.josa(names[0], "과", "와") + " " + names[1] if len(names) == 2 else names[0]
        says.append(say(f"{speech.josa(joined, '이', '가')} 있어요.", None, [r["id"] for r in rows]))
    if rain:
        rows.append({"id": "s_rain", "kind": "weather", "value": rain_text(rain, today)})
    evening = bool(general) and all(parse(r["starts_at"]).hour >= 17 for r in general)
    if general:
        rows.append({"id": "s_resv", "kind": "reservation", "value": f"{'저녁 ' if evening else ''}예약 {len(general)}팀"})
    for number, group in enumerate(groups[:2], 1):
        start = parse(group["starts_at"])
        value = width.fit("rows.value", f"{speech.clock_label(start)} 단체 {group['party_size']}명", f"단체 {group['party_size']}명")
        rows.append({"id": "s_group" if number == 1 else f"s_group{number}", "kind": "group_reservation", "value": value})

    for number, group in enumerate(groups[:2], 1):
        start = parse(group["starts_at"])
        says.append(say(f"{speech.clock_label(start)}에 단체 손님 {speech.count(group['party_size'], '분')}이 오세요.", None,
                         ["s_group" if number == 1 else f"s_group{number}"]))
    if general:
        lead = "저녁 예약은" if evening else "예약은"
        tail = "이고," if rain else "이에요."
        says.append(say(f"{lead} {speech.count(len(general), '팀')}{tail}", None, ["s_resv"]))
    if rain:
        when = f"{speech.clock_label(dt.datetime(today.year, today.month, today.day, rain['rain_from']))}부터" if rain.get("rain_from") else "하루 종일"
        says.append(say(f"{when} 비 소식이 있어요.", None, ["s_rain"]))

    if groups:
        start = parse(groups[0]["starts_at"])
        people = groups[0]["party_size"]
        headline = width.fit("headline", f"{speech.clock_label(start)}에 단체 {people}명이 와요", f"단체 {people}명이 와요")
    elif names:
        busy: dict[str, int] = {}
        for item in events + games + reservations:
            part = speech.daypart(parse(item["starts_at"]).hour)
            busy[part] = busy.get(part, 0) + 1
        part, n = max(busy.items(), key=lambda kv: kv[1])
        headline = f"오늘은 {speech.josa(part, '이', '가')} 바빠요" if n >= 2 else "오늘 일정이 있어요"
    elif general:
        headline = f"{'저녁 ' if evening else ''}예약이 {len(general)}팀이에요"
    else:
        headline = "오늘은 비 소식이 있어요"
    return answer(headline, says, [{"type": "rows", "id": "schedule", "rows": rows[:4]}])


def step_reviews(waiting: list[dict]) -> dict | None:
    if not waiting:
        return None
    pos = sum(1 for r in waiting if r.get("sentiment") == "positive")
    neg = len(waiting) - pos
    total = len(waiting)
    return answer(
        f"답글 기다리는 리뷰 {total}개",
        [say("이제 리뷰예요."),
         say(f"답글을 기다리는 리뷰가 {speech.count(total, '개')}예요."),
         say(f"좋은 리뷰 {speech.count(pos, '개')}, 아쉬운 리뷰 {speech.count(neg, '개')}예요.", None, ["c_pos", "c_neg"])],
        [{"type": "counts", "id": "review_counts", "items": [
            {"id": "c_pos", "kind": "positive", "label": "좋은 리뷰", "count": pos, "unit": "개"},
            {"id": "c_neg", "kind": "negative", "label": "아쉬운 리뷰", "count": neg, "unit": "개"}]}],
    )


def review_card(review: dict, reply: dict | None) -> dict:
    """v0.2.1: 리뷰 원문과 실제 단 답글을 그대로 보여 준다. 별점은 별로만 보이고 말로 읽지 않는다 (D-11)."""
    return {"type": "review", "id": review["id"], "variant": "full", "rating": review["rating"],
            "text": review["text"], "written_at": review["written_at"], "reply": reply}


def told(summary: str) -> str:
    """'면이 불어서 왔대요' → '면이 불어서 왔다는' (… 리뷰를 남기셨어요)."""
    body = summary.rstrip(".")
    if body.endswith("래요"):
        return body[:-2] + "라는"
    if body.endswith("대요"):
        return body[:-2] + "다는"
    return body + "는"


def _when(written: dt.datetime, now: dt.datetime) -> str:
    days = (now.date() - written.date()).days
    if days == 0:
        return "오늘"
    if days == 1:
        return "어젯밤" if written.hour >= 18 else "어제"
    return f"{speech.weekday(written.date())}요일에"


def replied_answer(review: dict, now: dt.datetime) -> dict:
    """도나가 아쉬운 리뷰에 답한 것 (D-11). 허락받은 그 자리에서 올렸으면 '방금'."""
    written = parse(review["written_at"])
    who = "배달로 드신 손님이" if review.get("order_channel") == "delivery" else "가게에서 드신 손님이"
    just_now = review.get("reply_trigger") == "permission"
    minutes = review.get("replied_in_minutes") or 1
    headline = "방금 답글을 달았어요" if just_now else f"{minutes}분 만에 답했어요"
    second = "방금 사과 답글을 달았어요." if just_now else f"{minutes}분 만에 사과 답글을 달았어요."
    says = [say(f"{_when(written, now)} {who} {told(review['summary'])} 리뷰를 남기셨어요.", None, [review["id"]])]
    if review.get("reply_trigger") == "timeout":  # 영업 중 알림에 대답이 없어 사과만 먼저 올린 것 (jobs/review_loop.py)
        says.append(say(f"{minutes}분 만에 사과 답글만 먼저 달았어요.", None, [review["id"]]))
        record = repo.get("alert", f"al_{review['id']}") or {}
        left = [w for w, on in (("서비스 안내", record.get("compensation")), ("할 일", record.get("card"))) if on]
        if left:
            says.append(say(f"{speech.josa('와 '.join(left), '은', '는')} 넣지 않았어요."))
    else:
        says.append(say(second, None, [review["id"]]))
    reply = {"text": review["reply_text"], "posted_at": review["reply_posted_at"], "by": "donna"}
    return answer(headline, says, [review_card(review, reply)])


def step_negative(view: VoiceStore, now: dt.datetime, waiting: list[dict]) -> tuple[dict | None, dict | None]:
    """아쉬운 리뷰 단계와 자세히 보기. 허락 설정에 따라 갈린다 (문서 10장 '3단계의 갈림')."""
    allowed = repo.settings(view.store_id).get("negative_review_auto_reply")
    waiting_neg = [r for r in waiting if r.get("sentiment") == "negative"]

    if allowed is None:
        if not waiting_neg:
            return None, None
        response = answer(
            "제가 바로 답할까요?",
            # 2026-11-18: 영업 중에 온 아쉬운 리뷰는 바로 여쭤보고 사장님 한마디로 올린다 (review_loop). 이 허락은
            # 문 닫은 뒤에 온 리뷰, 여쭤봐도 대답이 없을 때 사과만 먼저 다는 것이다.
            [say("아쉬운 리뷰는 빨리 답할수록 좋아요.", "아쉬운 리뷰는 빨리 답할수록 좋아요."),
             say("영업 중에 오면 바로 여쭤볼게요."),
             say("문 닫은 뒤에 왔거나 대답이 없으실 때는, 제가 30분 안에 사과 답글을 달고 브리핑 때 알려 드릴까요?", None, ["pm_reply", "pm_brief"])],
            [{"type": "rows", "id": "permission", "rows": [
                {"id": "pm_reply", "kind": "reply", "value": "30분 안에 사과 답글"},
                {"id": "pm_brief", "kind": "briefing", "value": "브리핑 때 알려 드려요"},
                {"id": "pm_off", "kind": "off", "value": "언제든 말로 끌 수 있어요"}]}],
            kind="ask_permission", permission={"key": "negative_review_auto_reply"},
        )
        response["expects_reply"] = True
        return response, None

    if allowed is True:
        replied = auto_replied(view, now)
        if not replied:
            return None, None
        review = replied[0]
        response = replied_answer(review, now)
        return response, _detail(review, response["cards"][0]["reply"], "제가 올린 답글이에요.")

    # 허락을 거절함: 아쉬운 리뷰와 써 둔 초안을 보여 준다 (14장 7번 제안). 올리지는 않는다
    if not waiting_neg:
        return None, None
    review = sorted(waiting_neg, key=lambda r: r["written_at"], reverse=True)[0]
    n = len(waiting_neg)
    draft = {"text": review.get("reply_text") or "", "posted_at": None, "by": "donna"}
    response = answer(
        f"아쉬운 리뷰가 {n}개 있어요",
        [say(f"아쉬운 리뷰가 {speech.count(n, '개')} 있어요."),
         say(f"{told(review['summary'])} 리뷰예요.", None, [review["id"]]),
         say("답글 초안을 써 뒀어요.", None, [review["id"]])],
        [review_card(review, draft)],
    )
    return response, _detail(review, draft, "제가 써 둔 답글 초안이에요.")


def _detail(review: dict, reply: dict, reply_intro: str) -> dict:
    card = review_card(review, reply)
    return {
        "show": answer("리뷰와 답글이에요", [say("화면에 띄웠어요.")], [card], kind="show_detail"),
        "read": answer("리뷰와 답글이에요", [
            say("손님 리뷰예요."), say(review["text"], None, [review["id"]]),
            say(reply_intro), say(reply["text"], None, [review["id"]]),
        ], [card]),
    }


def step_positive(view: VoiceStore, now: dt.datetime) -> dict | None:
    reviews = recent_positive(view, now)
    if len(reviews) < config.POSITIVE_MIN:
        return None
    found = strengths.analyze(reviews, view.menus, view.store.get("strengths"))
    items = found["top"]
    bars = [{"id": f"b_{n}", "label": item["label"], "count": item["count"]} for n, item in enumerate(items, 1)]
    says = [say(f"최근 일주일 좋은 리뷰 {speech.count(found['total'], '개')}를 봤어요.")]
    if items:
        says.append(say(f"{items[0]['label']} 칭찬이 가장 많았어요.", None, ["b_1"]))
    says.append(say(found["keep_tip"] + ".", None, ["tip_keep"]))
    return answer(
        width.fit("headline", found["headline"], "좋은 리뷰가 많아요"), says,
        [{"type": "bars", "id": "strengths", "unit": "개", "items": bars},  # 앱은 "리뷰 9개"로 보인다 (그 말이 나온 리뷰 수)
         {"type": "tip", "id": "tip_keep", "kind": "keep", "text": width.fit("tip", found["keep_tip"], "지금처럼 맛과 응대를 지켜 주세요")}],
    )


def step_scheduling(view: VoiceStore, now: dt.datetime) -> tuple[dict | None, dict | None]:
    scheduled = [r for r in view.reviews() if r.get("reply_status") == "scheduled"]
    rows = schedule.rows(scheduled, view.menus, now, view.store.get("rain_menu"))
    if not rows:
        return None, None
    says = [say("좋은 리뷰 답글은 손님이 외식을 고민할 때 올리려고 예약해 뒀어요.")]
    for row in rows:
        says.append(say(f"{row['explanation']}.", None, [row["id"]]))  # say 는 한 문장씩
        if row.get("context_line"):
            says.append(say(f"{row['context_line']}.", None, [row["id"]]))
    card_rows = [{k: v for k, v in row.items() if k not in ("explanation", "context_line")} for row in rows]
    response = answer("답글은 예약해 뒀어요", says, [{"type": "scheduled", "id": "scheduled_replies", "items": card_rows}])

    by_id = {r["id"]: r for r in scheduled}
    cards, reading = [], [say("예약한 답글을 읽어 드릴게요.")]
    for row in rows:
        for review_id in row["review_ids"]:
            review = by_id[review_id]
            label = f"{row['day_label']}요일 {row['time_label']}에 올릴 답글"
            cards.append(review_card(review, {"text": review["reply_text"], "posted_at": None, "by": "donna", "scheduled_label": label}))
            reading += [say(f"{label}이에요.", None, [review_id]), say(review["reply_text"], None, [review_id])]
    detail = {
        "show": answer("예약한 답글이에요", [say("화면에 띄웠어요.")], cards, kind="show_detail"),
        "read": answer("예약한 답글이에요", reading, cards),
    }
    return response, detail


def step_instagram(view: VoiceStore) -> tuple[dict | None, dict | None]:
    """인스타에 올릴까요 (D-14). 연결 안 됨, 오늘 이미 올림, 메뉴 사진이 3개보다 적으면 건너뛴다.
    자세히 보기는 올라갈 모양 그대로 한 장씩 (D-15, '다음 사진'으로 넘긴다)."""
    connection = posts.connection(view.store_id)
    if not connection["connected"] or posts.posted_on(view.store_id, "feed", view.now.date()):
        return None, None
    built = posts.build_feed(view)
    if built is None:
        return None, None
    top = built["menus"]
    names = [m["name"] for m in top["items"]]
    says = [say(f"{top['period']} 가장 많이 나간 메뉴는 {', '.join(names[:-1])}, {speech.josa(names[-1], '이에요', '예요')}.", None, ["top_menus"])]
    cards = [{"type": "menus", "id": "top_menus", "title": f"{top['period']} 많이 나간 메뉴", "items": top["items"]}]
    if built["quote"]:
        says.append(say(f"손님 리뷰 “{built['quote']}”{'을' if speech.has_batchim(built['quote']) else '를'} 글에 넣었어요.", None, ["insta_quote"]))
        cards.append({"type": "quote", "id": "insta_quote", "label": "글에 넣을 손님 리뷰", "text": f"“{built['quote']}”"})
    says.append(say("인스타에 올릴까요?"))
    response = answer("인스타에 올릴까요?", says, cards, kind="ask", ask={"key": "instagram_post"})
    response["expects_reply"] = True

    total = len(built["slides"])
    slides = []
    for number in range(1, total + 1):
        card = posts.preview_card(built, number, view.store, connection.get("handle"))
        lines = [say("화면에 띄웠어요."), say(f"{speech.count(total, '장')} 중 첫 장이에요.")] if number == 1 else [say(f"{ORDINAL[number - 1]} 장이에요.")]
        slides.append({**answer("이렇게 올라가요", lines, [card], kind="show_detail"), "expects_reply": True})
    caption_lines = [line for line in built["caption"].split("\n") if line and "·" not in line]
    read = {**answer("인스타에 올릴 글이에요", [say("인스타에 올릴 글을 읽어 드릴게요."), *[say(line) for line in caption_lines]],
                     slides[0]["cards"]), "expects_reply": True}
    return response, {"show": slides[0], "read": read, "slides": slides}


def refresh_instagram(store_id: str) -> dict | None:
    """오늘 브리핑의 인스타 단계(인기 메뉴, 스토리 이벤트)만 다시 만든다 (연결했을 때, 올렸을 때, 이벤트에 대답했을 때). 답글을 다시 쓰지 않아서 바로 끝난다."""
    brief = current(store_id)
    if brief is None:
        return None
    view = load(store_id)
    step, detail = step_instagram(view)
    brief["steps"]["instagram"] = step
    brief["steps"]["story_event"] = story_event.step(view)
    brief["details"].pop("instagram", None)
    if detail:
        brief["details"]["instagram"] = detail
    rows = [row for row in brief["home_rows"] if row["id"] != "p_instagram"]
    brief["home_rows"] = rows + [INSTAGRAM_ROW] if step and len(rows) < 4 else rows
    return repo.put("briefing", f"{store_id}:{brief['date']}", store_id, brief)


def plain_detail(step: dict) -> dict:
    """리뷰 카드가 없는 단계의 자세히 보기: 같은 카드를 띄우고 짧게 한 마디."""
    return {
        "show": {**step, "type": "show_detail", "say": [say("화면에 띄웠어요.")], "expects_reply": False},
        "read": {**step, "type": "answer", "expects_reply": False},
    }


def end_response(store_id: str) -> dict:
    """브리핑 끝 (D-16 '오늘 아침에 한 것'). 허락하자마자 단 답글까지 들어가야 해서 그때그때 만든다."""
    view = load(store_id)
    now = clock.now()
    done: list[tuple[str, str]] = []  # (화면 글, 말할 때 쓰는 줄기)
    if auto_replied(view, now):
        done.append(("아쉬운 리뷰에 답글", "아쉬운 리뷰에 답했"))
    if any(r.get("reply_status") == "scheduled" and parse(r["reply_post_at"]) > now for r in view.reviews()):
        done.append(("좋은 리뷰 답글 예약", "좋은 리뷰 답글은 예약했"))
    feed = posts.posted_on(store_id, "feed", now.date())
    if any(p["status"] == "published" for p in feed):
        done.append(("인스타에 인기 메뉴 올림", "인스타에 인기 메뉴를 올렸"))
    elif feed:
        done.append(("인스타에 올리는 중", "인스타에 올리고 있"))
    event = story_event.get(story_event.event_id(store_id, now.date()))
    if event and event["state"] == "generating":
        done.append(("이벤트 포스터 그리는 중", "이벤트 포스터를 그리고 있"))
    says = [say("오늘 브리핑은 여기까지예요.")]
    if done:
        stems = [stem for _, stem in done]
        says.append(say("".join(f"{s}고, " for s in stems[:-1]) + f"{stems[-1]}어요."))
    rows = [{"id": f"d_{n}", "kind": "done", "value": text} for n, (text, _) in enumerate(done)]
    return answer("브리핑은 여기까지예요", says,
                  [{"type": "rows", "id": "checked", "title": "오늘 아침에 한 것", "rows": rows}] if rows else [], kind="end")


def home_rows(view: VoiceStore, today: dt.date, waiting: list[dict], scheduled_n: int, instagram: bool = False) -> list[dict]:
    """홈 '오늘 준비한 것' (D-07). 이름표 없이 한 줄로 읽힌다."""
    reservations = _today(view.data.get("reservation", []), today)
    groups = [r for r in reservations if r["party_size"] >= config.GROUP_MIN_PEOPLE]
    parts = []
    if _today(view.data.get("event", []), today):
        parts.append("행사")
    if _today(view.data.get("game", []), today):
        parts.append("경기")
    if groups:
        parts.append(f"단체 {groups[0]['party_size']}명")
    elif reservations:
        parts.append(f"예약 {len(reservations)}팀")
    rain = rain_today(view, today)
    if rain:
        parts.append("오후 비" if (rain.get("rain_from") or 0) >= 12 else "비")
    rows = [{"id": "p_schedule", "kind": "schedule",
             "value": width.fit("rows.value", ", ".join(parts), "오늘 일정이 있어요") if parts else "평소와 같아요"}]
    if waiting:
        rows.append({"id": "p_reviews", "kind": "reviews", "value": f"밤사이 리뷰 {len(waiting)}개 읽어 둠"})
    if scheduled_n:
        rows.append({"id": "p_replies", "kind": "scheduled_replies", "value": f"좋은 리뷰 답글 {scheduled_n}개 예약"})
    if instagram:
        rows.append(INSTAGRAM_ROW)
    return rows


def spoken(briefing: dict) -> list[str]:
    """이 브리핑에서 도나가 소리 내어 읽을 문장 전부 (목소리를 미리 만들어 둔다)."""
    texts: list[str] = []
    details = [d[k] for d in briefing["details"].values() for k in ("show", "read")] + [s for d in briefing["details"].values() for s in d.get("slides", [])]
    for response in [*briefing["steps"].values(), *details]:
        for item in (response or {}).get("say", []):
            if item["text"] not in texts:
                texts.append(item["text"])
    return texts


def prepare(store_id: str) -> dict | None:
    """브리핑 묶음을 만들어 저장한다. 가게가 없으면 None."""
    view = load(store_id)
    if view is None:
        return None
    now = clock.now()
    newly_scheduled = schedule_replies(view, now)
    draft_negative(load(store_id))
    view = load(store_id)  # 위에서 바꾼 리뷰를 다시 읽는다
    waiting = awaiting(view)

    steps: dict[str, dict | None] = {"schedule": step_schedule(view, now.date()), "reviews": step_reviews(waiting)}
    steps["negative"], negative_detail = step_negative(view, now, waiting)
    steps["positive"] = step_positive(view, now)
    steps["scheduling"], scheduling_detail = step_scheduling(view, now)
    steps["instagram"], instagram_detail = step_instagram(view)
    steps["story_event"] = story_event.step(view)  # 비 오는 날 스토리 이벤트 (instagram/story_event.py)
    details = {key: plain_detail(step) for key, step in steps.items() if step and step["type"] == "answer"}
    if negative_detail:
        details["negative"] = negative_detail
    if scheduling_detail:
        details["scheduling"] = scheduling_detail
    if instagram_detail:
        details["instagram"] = instagram_detail
    scheduled_n = sum(len(i["review_ids"]) for i in (steps["scheduling"] or {"cards": [{"items": []}]})["cards"][0]["items"])

    overnight = [r for r in view.reviews() if now - dt.timedelta(days=1) <= parse(r["written_at"]) <= now]
    if overnight:
        activity.log(store_id, "donna", f"리뷰 {len(overnight)}개를 읽고 나눴어요", "reviews_read")
    if newly_scheduled:
        activity.log(store_id, "donna", f"좋은 리뷰 답글 {newly_scheduled}개를 예약했어요", "replies_scheduled")
    activity.log(store_id, "donna", "오늘 일정 브리핑을 준비했어요", "briefing_prepared")

    briefing = {
        "store_id": store_id, "date": now.date().isoformat(), "prepared_at": iso(now),
        "home_rows": home_rows(view, now.date(), waiting, scheduled_n, instagram=bool(steps["instagram"])),
        "steps": steps, "details": details,
        "sources": {"replies": sorted({r.get("reply_source") for r in view.reviews() if r.get("reply_source")} - {None})},
    }
    saved = repo.put("briefing", f"{store_id}:{briefing['date']}", store_id, briefing)
    from voice import tts  # 목소리를 미리 만든다 (뒤에서. 기다리지 않는다)

    tts.prewarm(spoken(saved))
    return saved


def current(store_id: str) -> dict | None:
    return repo.get("briefing", f"{store_id}:{clock.now().date().isoformat()}")
