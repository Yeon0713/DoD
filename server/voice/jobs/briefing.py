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

import copy
import datetime as dt

from voice import activity, audit, clock, config, departments, holidays, hr, locks, marketing, proposals, repo, speech, tts, width
from voice.agents import field_tasks, fix_card, voice_reply
from voice.audit import log as audit_log
from voice.clock import iso, parse
from voice.context import VoiceStore, load
from voice.instagram import posts, story_event
from voice.jobs import auto_reply, batch_ask, done_report, hr_night, queue, revise_jobs, schedule, staff_tasks, strengths

# v0.2.1 H (Figma '새 오늘 일정 브리핑', 2026-11-22): 요약 세 줄 → "상세 브리핑을 시작할까요?" → 상세 (인스타 → 리뷰 → 알바생) → 끝.
# 진행 띠는 네 칸: 요약, 인스타, 리뷰, 알바생. 건너뛴 칸이 있어도 그대로다.
# 요약 세 줄(sum_*)은 같은 카드를 두고 지금 말하는 줄만 진하게 바꾼다 (H-02 ~ H-04). 묻지 않는 단계는 가만히 있어도 넘어간다.
TOTAL = 4
STEP_KEYS = ["sum_weather", "sum_reviews", "sum_resv", "detail_ask", "holiday",
             "story_event", "instagram",
             "reviews", "scheduling", "positive_scheduled", "negative", "negative_done", "done_report",
             "staff_tasks"]
GAUGE = {"sum_weather": 1, "sum_reviews": 1, "sum_resv": 1, "detail_ask": 1, "holiday": 1,
         "story_event": 2, "instagram": 2,
         "reviews": 3, "scheduling": 3, "positive_scheduled": 3, "negative": 3, "negative_done": 3, "done_report": 3,
         "staff_tasks": 4, "end": 4}
SUMMARY_KEYS = ("sum_weather", "sum_reviews", "sum_resv")
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


def _at_hour(day: dt.date, hour: int) -> str:
    return speech.clock_label(dt.datetime(day.year, day.month, day.day, hour))


def rain_text(w: dict, day: dt.date) -> str:
    """'오전 11시~저녁 8시 비', '오후 2시부터 비' 또는 '하루 종일 비' (화면 글). 끝나는 시각(rain_to)이 있으면 범위로."""
    hour, until = w.get("rain_from"), w.get("rain_to")
    if hour and until:
        return f"{_at_hour(day, hour)}~{_at_hour(day, until)} 비"
    return f"{_at_hour(day, hour)}부터 비" if hour else "하루 종일 비"


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


def schedule_replies(view: VoiceStore, now: dt.datetime, *, promoted: bool = False) -> int:
    """답글 기다리는 좋은 리뷰마다 올릴 때(schedule.occasion_for: 평일 리뷰 → 토요일 오전, 주말 리뷰 → 24~48시간 안 식사 피크
    한 시간 전)를 정하고 답글을 써 둔다. 그날의 날씨·행사는 글에만 들어간다.
    칭찬 리뷰 답글 직급 (인사과 4-b): 대리·과장은 지금처럼 예약한다. 인턴·사원은 써 두기만 하고(awaiting) 브리핑에서 "이렇게
    예약할까요?"로 묻는다. 대답이 없어 올릴 날이 지난 awaiting 은 다음 날 준비 때 때와 글을 새로 정해 다시 묻는다 (9-0 b).
    같은 날 다시 준비할 때(시계 옮기기, 새 리뷰)는 다시 쓰지 않는다 (영업 중에 LLM 을 부르지 않게).
    promoted: 이번 평가에서 묻던 직급이 대리로 올랐다. 묻던 답글(awaiting) 중 올릴 때가 남은 것은 그대로 예약하고,
    지난 것은 새로 정해 예약한다 (known-bugs B3)."""
    asks = hr.asks(view.store_id, "positive_reply") is not None

    def stale(review: dict) -> bool:
        at = parse(review["reply_post_at"])
        return at <= now if promoted else at.date() < now.date()

    if promoted:
        for review in view.reviews():
            if review.get("reply_status") == "awaiting" and not stale(review):
                if repo.save_review_if({**review, "reply_status": "scheduled", "reply_trigger": "auto"}, "awaiting"):
                    queue.add(view.store_id, "post_scheduled", parse(review["reply_post_at"]))
    waiting = [r for r in view.reviews() if r.get("sentiment") == "positive" and not r.get("reply_deleted_at") and (
        r.get("reply_status", "none") == "none" or (r.get("reply_status") == "awaiting" and stale(r)))]
    if not waiting:
        return 0
    for review in sorted(waiting, key=lambda r: r["written_at"]):
        before = review.get("reply_status", "none")  # none 또는 다시 묻는 awaiting. 쓰는 사이 바뀌었으면 덮지 않는다
        slot = schedule.occasion_for(review, view.data, view.store, now)
        occasion = {**slot, "post_at": iso(slot["post_at"])}
        written = voice_reply.write(view, review, "SCHEDULED", occasion)
        settled = audit.settle(view.store_id, "positive_reply", written.get("audit"))
        if settled == "template":  # 인턴·사원: 감사를 끝내 통과하지 못한 글 대신 템플릿으로 묻는다
            written = {**written, "text": voice_reply.template(view, review, occasion), "source": "TEMPLATE"}
        ask_it = asks or settled == "hold"  # 대리·과장의 보류 건: 예약하지 않고 그 건만 묻는다 (step_scheduling)
        review.update({
            "reply_status": "awaiting" if ask_it else "scheduled", "reply_by": "donna", "reply_text": written["text"],
            "reply_source": written["source"], "reply_notes": written["notes"], "reply_post_at": occasion["post_at"],
            "reply_reason": {key: slot[key] for key in ("kind", "label", "meal", "context", "explanation")},
            "reply_trigger": None if ask_it else "auto",  # auto: 묻지 않고 예약 → 올릴 때 인사과에 done
            "reply_audit": written.get("audit"), "audit_hold": settled == "hold",
        })
        if repo.save_review_if(review, before):  # 답글을 쓰는 사이 사장님이 직접 답했으면 덮지 않는다
            if settled == "hold":
                audit_log.mark_hold(view.store_id, review["id"])
            elif not asks:
                queue.add(view.store_id, "post_scheduled", slot["post_at"])
    return 0 if asks else sum(1 for r in waiting if not r.get("audit_hold"))


def draft_negative(view: VoiceStore) -> None:
    """아쉬운 리뷰에 답글을 미리 써 둔다. 아침 브리핑에서 "올릴까요?"에 "응"이면 이 글을 바로 올린다 (말하는 동안 LLM 을 기다리지 않게)."""
    for review in view.reviews():
        if review.get("sentiment") != "negative" or review.get("reply_status", "none") != "none" or review.get("reply_deleted_at"):
            continue  # 사장님이 지운 답글은 다시 쓰지 않는다 (사후 취소, 인사과 5단계)
        if not review.get("reply_ready"):  # 교정 카드를 먼저 정해 답글이 같은 조치를 약속하게 한다 (2026-11-20, 안 B)
            found = fix_card.card_for(view, review)
            fix = {"cause": found["summary"], "action": found["card"]["detail"], "reply": found["reply"]} if found["card"] else None
            written = voice_reply.write(view, review, "AUTO", fix=fix)
            settled = audit.settle(view.store_id, "negative_reply", written.get("audit"))
            if settled == "template":  # 인턴·사원: 감사를 끝내 통과하지 못한 글 대신 템플릿 초안
                written = {**written, "text": voice_reply.template(view, review, None, fix), "source": "TEMPLATE"}
            review["audit_hold"] = settled == "hold"  # 대리·과장의 보류 건 (아쉬운 리뷰 단계에서 묻는다)
            if review["audit_hold"]:
                audit_log.mark_hold(view.store_id, review["id"])
            # 교정 할 일을 빼거나 버린 뒤 올리면 그 조치를 약속하지 않는 글로 (batch_ask.ready_reply, known-bugs B7)
            review["reply_ready"] = {**written, "plain": found["plain"]} if fix else written
            auto_reply.propose_overnight(view.store_id, review, found, view.now)  # 할 일은 아침 브리핑에서 묻는다
        repo.save_review_if(review, "none")  # 답글을 쓰는 사이 알림(review_loop.alert)이 proposed 로 바꿨으면 덮지 않는다


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

    # 말하는 순서는 화면 카드 위에서 아래로 (행사·경기 → 비 → 예약 → 단체, 2026-11-18)
    if rain:
        when = f"{speech.clock_label(dt.datetime(today.year, today.month, today.day, rain['rain_from']))}부터" if rain.get("rain_from") else "하루 종일"
        says.append(say(f"{when} 비 소식이 있어요.", None, ["s_rain"]))
    if general:
        lead = "저녁 예약은" if evening else "예약은"
        tail = "이고," if groups else "이에요."
        says.append(say(f"{lead} {speech.count(len(general), '팀')}{tail}", None, ["s_resv"]))
    for number, group in enumerate(groups[:2], 1):
        start = parse(group["starts_at"])
        says.append(say(f"{speech.clock_label(start)}에 단체 손님 {speech.count(group['party_size'], '분')}이 오세요.", None,
                         ["s_group" if number == 1 else f"s_group{number}"]))

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


# ── H: 요약 세 줄 → 상세 브리핑 물음 (Figma v0.2.1 H-02 ~ H-05) ──


def arrived(view: VoiceStore, now: dt.datetime) -> list[dict]:
    """밤사이 도착한 리뷰 (지난 하루). 도나가 이미 답한 것도 센다 (H-03 '도착한 리뷰 5건', H-08 좋은 4건·아쉬운 1건)."""
    return [r for r in view.reviews() if now - dt.timedelta(days=1) <= parse(r["written_at"]) <= now]


def short_clock(moment: dt.datetime) -> str:
    """'3시', '3시 30분' (오전·오후 없이. H-04 '3시 손님 요청사항')."""
    hour = moment.hour % 12 or 12
    return f"{hour}시 {moment.minute}분" if moment.minute else f"{hour}시"


def with_memo(reservations: list[dict]) -> list[dict]:
    return [r for r in reservations if (r.get("memo") or "").strip()]


def summary_steps(view: VoiceStore, today: dt.date, reviews_in: list[dict]) -> dict[str, dict | None]:
    """요약 세 줄 (날씨, 도착한 리뷰, 예약)과 상세 브리핑 물음. 같은 카드를 두고 단계마다 지금 말하는 줄만 진하게 한다.
    없는 줄은 빼고, 그 단계도 없다. 줄이 하나도 없으면 물음만 남는다."""
    rain = rain_today(view, today)
    reservations = _today(view.data.get("reservation", []), today)
    events, games = _today(view.data.get("event", []), today), _today(view.data.get("game", []), today)
    memos = with_memo(reservations)
    groups = [r for r in reservations if r["party_size"] >= config.GROUP_MIN_PEOPLE]

    rows: list[dict] = []
    if rain:
        rows.append({"id": "s_rain", "kind": "weather", "value": rain_text(rain, today)})
    if reviews_in:
        rows.append({"id": "s_reviews", "kind": "reviews", "value": f"도착한 리뷰 {len(reviews_in)}건"})
    for item, kind in ((events[:1], "event"), (games[:1], "game")):
        if item:
            start = parse(item[0]["starts_at"])
            rows.append({"id": f"s_{kind}", "kind": kind,
                         "value": width.fit("rows.value", f"{item[0]['name']} {speech.clock_label(start)}", item[0]["name"])})
    if reservations:
        value = f"예약 {len(reservations)}팀" + (f", 요청사항 {len(memos)}건" if memos else "")
        rows.append({"id": "s_resv", "kind": "reservation", "value": value})
    card = [{"type": "rows", "id": "summary", "rows": rows[:4]}] if rows else []

    def show(headline: str, says: list[dict]) -> dict:
        return answer(width.fit("headline", headline, headline[:14]), says, copy.deepcopy(card))

    steps: dict[str, dict | None] = {key: None for key in SUMMARY_KEYS}
    if rain:
        start = rain.get("rain_from")
        if start and rain.get("rain_to"):
            line = f"오늘은 {_at_hour(today, start)}부터 {_at_hour(today, rain['rain_to'])} 사이에 비 소식이 있습니다."
        elif start:
            line = f"오늘은 {_at_hour(today, start)}부터 비 소식이 있습니다."
        else:
            line = "오늘은 하루 종일 비 소식이 있습니다."
        steps["sum_weather"] = show(f"{_at_hour(today, start)}부터 비가 와요" if start else "오늘은 비가 와요",
                                    [say(line, None, ["s_rain"])])
    if reviews_in:
        steps["sum_reviews"] = show(f"도착한 리뷰는 {len(reviews_in)}건이에요",
                                    [say(f"오늘 도착한 리뷰는 {speech.count(len(reviews_in), '건')}입니다.", None, ["s_reviews"])])
    if reservations or events or games:
        says: list[dict] = []
        names = [e["name"] for e in events[:1]] + [g["name"] for g in games[:1]]
        if names:
            joined = speech.josa(names[0], "과", "와") + " " + names[1] if len(names) == 2 else names[0]
            says.append(say(f"오늘은 {speech.josa(joined, '이', '가')} 있어요.", None, [r["id"] for r in rows if r["kind"] in ("event", "game")]))
        if memos:
            at = short_clock(parse(memos[0]["starts_at"]))
            headline = f"{at} 손님 요청사항이 왔어요"
            says.append(say(f"오늘 예약은 총 {speech.count(len(reservations), '건')}이며, {at} 예약 손님의 요청사항이 도착했습니다.", None, ["s_resv"]))
        elif groups:
            start = parse(groups[0]["starts_at"])
            headline = f"{speech.clock_label(start)}에 단체 {groups[0]['party_size']}명이 와요"
            says.append(say(f"오늘 예약은 총 {speech.count(len(reservations), '건')}이고, {speech.clock_label(start)}에 단체 손님 "
                            f"{speech.count(groups[0]['party_size'], '분')}이 오세요.", None, ["s_resv"]))
        elif reservations:
            headline = f"예약이 {len(reservations)}팀이에요"
            says.append(say(f"오늘 예약은 총 {speech.count(len(reservations), '건')}입니다.", None, ["s_resv"]))
        else:
            headline = "오늘 일정이 있어요"
        steps["sum_resv"] = show(headline, says)

    ask = answer("상세 브리핑을 시작할까요?" if rows else "오늘은 평소와 같아요",
                 [say("상세 브리핑을 시작할까요?")] if rows else [say("오늘은 행사나 예약이 없어요."), say("상세 브리핑을 시작할까요?")],
                 copy.deepcopy(card), kind="ask", ask={"key": "detail"})
    ask["expects_reply"] = True
    steps["detail_ask"] = ask
    return steps


def step_reviews(reviews_in: list[dict]) -> dict | None:
    """밤사이 도착한 리뷰를 좋은 리뷰와 아쉬운 리뷰로 나눠 센다 (H-08). 이 뒤에 예약한 답글(H-09)과 바로 단 답글(H-10)이 온다."""
    if not reviews_in:
        return None
    pos = sum(1 for r in reviews_in if r.get("sentiment") == "positive")
    neg = len(reviews_in) - pos
    return answer(
        f"리뷰 {len(reviews_in)}건이 도착했습니다",
        [say(f"도착한 리뷰는 좋은 리뷰 {speech.count(pos, '건')}, 아쉬운 리뷰 {speech.count(neg, '건')}이에요.", None, ["c_pos", "c_neg"])],
        [{"type": "counts", "id": "review_counts", "items": [
            {"id": "c_pos", "kind": "positive", "label": "좋은 리뷰", "count": pos, "unit": "건"},
            {"id": "c_neg", "kind": "negative", "label": "아쉬운 리뷰", "count": neg, "unit": "건"}]}],
    )


def slot_label(moment: dt.datetime) -> str:
    """'토요일 오전 11시'."""
    return f"{speech.weekday(moment.date())}요일 {speech.clock_label(moment)}"


def step_positive_scheduled(view: VoiceStore, now: dt.datetime) -> dict | None:
    """묻지 않고 예약해 둔 좋은 리뷰 답글 (H-09). 리뷰 한 줄과 예약한 답글을 짝지어 보인다.
    칭찬 답글을 묻는 직급(인턴·사원)이면 scheduling 단계가 대신 묻는다."""
    if hr.asks(view.store_id, "positive_reply") is not None:
        return None
    fresh = {r["id"] for r in arrived(view, now)}  # 밤사이 온 리뷰만 (그 전에 예약한 답글은 지난 브리핑에서 알렸다)
    found = sorted((r for r in view.reviews() if r["id"] in fresh and r.get("sentiment") == "positive" and r.get("reply_status") == "scheduled"
                    and r.get("reply_text") and parse(r["reply_post_at"]) > now), key=lambda r: r["written_at"], reverse=True)
    if not found:
        return None
    slots = sorted({r["reply_post_at"] for r in found})
    first = parse(slots[0])
    says = []
    if len(slots) == 1:
        headline = f"{slot_label(first)}에\n답변을 예약해두었습니다"  # Figma H-09 처럼 두 줄
        says.append(say(f"좋은 리뷰 {speech.count(len(found), '건')}은 {slot_label(first)}에 답변을 예약해두었습니다.", None, ["scheduled_list"]))
    else:
        headline = "좋은 리뷰 답변을 예약해두었습니다"
        says.append(say(f"좋은 리뷰 {speech.count(len(found), '건')}은 손님이 외식을 고민할 때 올리려고 답변을 예약해두었습니다.", None, ["scheduled_list"]))
    reason = (found[0].get("reply_reason") or {}).get("explanation")
    if reason:
        says.append(say(reason.rstrip(".") + "."))
    items = [{"id": r["id"], "quote": f"“{r['text']}”", "reply": r["reply_text"]} for r in found[:4]]
    return answer(headline, says, [{"type": "reply_list", "id": "scheduled_list", "items": items}])


def step_negative_done(view: VoiceStore, now: dt.datetime) -> dict | None:
    """허락받은 대로(부정 리뷰 답글 대리·과장) 밤사이 바로 단 사과 답글 (H-10). 사후 보고(done_report)에서는 이 답글을 빼고,
    이 단계를 앱에 보내면 보고한 것으로 적는다 (report)."""
    found = auto_replied(view, now)
    if not found:
        return None
    review = found[0]
    minutes = max(1, round((parse(review["reply_posted_at"]) - parse(review["written_at"])).total_seconds() / 60))
    took = f"{minutes}분" if minutes < 60 else f"{minutes // 60}시간"
    says = [say(f"아쉬운 리뷰 {speech.count(len(found), '건')}은 허락해 주신 대로 {took} 만에 답변했어요.", "허락해 주신 대로 바로 답했어요", [review["id"]])]
    card = review_card(review, {"text": review["reply_text"], "posted_at": review["reply_posted_at"], "by": "donna"})
    refs = {r["id"] for r in found}
    report = [e["id"] for e in hr.report_items(view.store_id, now) if e["job"] == "negative_reply" and e["ref"] in refs]
    return answer(f"{took} 만에 답했어요", says, [card], report=report)


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


def step_negative(view: VoiceStore, now: dt.datetime, waiting: list[dict]) -> tuple[dict | None, dict | None]:
    """아쉬운 리뷰 단계와 자세히 보기. 부정 리뷰 답글 직급에 따라 갈린다 (인사과 4-a, 허락 질문 D-10 은 없앰).
    인턴·사원: 써 둔 답글을 "올릴까요?"로 묻는다 (인턴은 한 건씩, 사원은 묶어서, jobs/batch_ask.py).
    대리·과장: 묻지 않고 올렸으므로 이 단계는 없다. 올린 것은 done_report 단계가 알린다 (인사과 5단계).
    다만 바로 답하기가 실패해 남은 리뷰(auto_reply_failed_at)는 묶어 묻는다. 대답이 없으면 다음 날 또 묻는다 (known-bugs B6).
    감사팀이 끝내 통과시키지 않아 올리지 않은 리뷰(audit_hold)도 함께 묻는다 (감사팀 결정 7)."""
    mode = hr.asks(view.store_id, "negative_reply")
    if mode is None:  # 대리·과장: 바로 답하기가 실패해 남은 것과 감사 보류 건만 묶어 묻는다 (known-bugs B6)
        waiting, mode = [r for r in waiting if r.get("auto_reply_failed_at") or r.get("audit_hold")], "batch"
    waiting_neg = sorted((r for r in waiting if r.get("sentiment") == "negative"), key=lambda r: r["written_at"], reverse=True)
    response = batch_ask.ask(view, [{"job": "negative_reply", "ref": r["id"]} for r in waiting_neg], mode)
    if response is None:
        return None, None
    first = view.review(response["action"]["items"][0]["ref"])  # 자세히 보기·읽어 주기는 지금 묻는 첫 리뷰와 써 둔 초안
    draft = {"text": first["reply_ready"]["text"], "posted_at": None, "by": "donna"}
    return response, _detail(first, draft, "제가 써 둔 답글 초안이에요.")


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
    """예약 답글 단계. 칭찬 리뷰 답글 인턴·사원은 써 둔 답글을 "이렇게 예약할까요?"로 묻는다 (jobs/batch_ask.py).
    대리·과장은 묻지 않고 예약했으므로 단계를 보이지 않는다 (올린 것은 사후 보고, 9-0 c). 다만 감사 보류 건은 묶어 묻는다 (감사팀 결정 7)."""
    mode = hr.asks(view.store_id, "positive_reply")
    waiting = sorted((r for r in view.reviews() if r.get("reply_status") == "awaiting"), key=lambda r: r["reply_post_at"])
    if mode is None:
        waiting = [r for r in waiting if r.get("audit_hold")]
    asked = batch_ask.ask(view, [{"job": "positive_reply", "ref": r["id"]} for r in waiting], mode or "batch")
    if asked is not None:
        return asked, None
    if mode is None:
        return None, None
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


def auto_instagram(view: VoiceStore, now: dt.datetime) -> dict | None:
    """인스타 게시가 대리면 브리핑 준비 때 만든 게시물을 그날 첫 식사 피크 한 시간 전에 올린다 (9-0 d). 사원·인턴은 묻는다 (9-0 e)."""
    if hr.asks(view.store_id, "instagram_post") is not None or not posts.connection(view.store_id)["connected"]:
        return None
    if posts.posted_on(view.store_id, "feed", now.date()) or (marketing.today(view) or {}).get("audit_hold"):
        return None  # 감사 보류: 게시 예약을 하지 않고 인스타 단계에서 묻는다 (감사팀 결정 7)
    built = posts.build_feed(view)
    if built is None:
        return None
    due = next((at for at, _ in schedule.slots(view.store, now.date(), 1) if at > now), now)
    post = posts.save({**posts.create(view.store_id, built), "auto": True})  # auto: 올라가면 인사과에 done
    return posts.queue_publish(view.store_id, post, due)


def step_instagram(view: VoiceStore) -> tuple[dict | None, dict | None]:
    """인스타에 올릴까요 (D-14). 연결 안 됨, 오늘 이미 올림, 메뉴 사진이 3개보다 적으면 건너뛴다. 대리면 묻지 않는다 (auto_instagram).
    자세히 보기는 올라갈 모양 그대로 한 장씩 (D-15, '다음 사진'으로 넘긴다)."""
    held = bool((marketing.today(view) or {}).get("audit_hold"))
    if hr.asks(view.store_id, "instagram_post") is None and not held:
        return None, None  # 대리: 묻지 않고 올렸다. 감사 보류면 묻는다
    if not held and story_event.get(story_event.event_id(view.store_id, view.now.date())):
        return None, None  # H: 비 오는 날 이벤트가 있는 날은 스토리만 묻는다 (감사가 보류한 글은 그날도 묻는다)
    connection = posts.connection(view.store_id)
    if not connection["connected"] or posts.posted_on(view.store_id, "feed", view.now.date()):
        return None, None
    built = posts.build_feed(view)
    if built is None:
        return None, None
    top = built["menus"]
    names = [m["name"] for m in top["items"]]
    if top.get("angle"):  # 마케팅 소재 사원이 고른 메뉴와 이야기 (voice/marketing.py)
        says = [say(f"오늘은 {speech.josa(top['angle'], '이라는', '라는')} 이야기로 {', '.join(names)} 사진을 골랐어요.", None, ["top_menus"])]
        cards = [{"type": "menus", "id": "top_menus", "title": "오늘 올릴 메뉴", "items": top["items"]}]
    else:
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
    # 홈 줄은 H-01 차례대로 다시 짠다 (인스타·이벤트 줄은 일정·리뷰 다음 자리. 끝에 붙이면 네 줄이 찬 날은 빠졌다)
    now = clock.now()
    scheduled_n = sum(1 for r in view.reviews() if r.get("reply_status") == "scheduled" and parse(r["reply_post_at"]) > now)
    brief["home_rows"] = home_rows(view, now.date(), arrived(view, now), scheduled_n, story=bool(brief["steps"]["story_event"]),
                                   instagram=bool(step))
    return repo.put("briefing", f"{store_id}:{brief['date']}", store_id, brief)


def plain_detail(step: dict) -> dict:
    """리뷰 카드가 없는 단계의 자세히 보기: 같은 카드를 띄우고 짧게 한 마디."""
    return {
        "show": {**step, "type": "show_detail", "say": [say("화면에 띄웠어요.")], "expects_reply": False},
        "read": {**step, "type": "answer", "expects_reply": False},
    }


def hm(moment: dt.datetime) -> str:
    """'9:04' (끝 화면 줄 아래 시각)."""
    return f"{moment.hour}:{moment.minute:02d}"


def end_response(store_id: str, session: dict | None = None) -> dict:
    """브리핑 끝 (H-12b '오늘 아침에 한 것'). 줄마다 무엇을 했고 언제 했는지 적는다. 허락하자마자 한 일까지 들어가야 해서 그때그때 만든다.
    session.heard: 단계를 앱에 보낸 시각 (예약해 둔 답글을 들은 때를 '9:05에 토요일 답변을 예약했어요'로 적는다, dialog/turn.py)."""
    view = load(store_id)
    now = clock.now()
    heard = (session or {}).get("heard") or {}
    rows: list[dict] = []

    def add(value: str, sub: str) -> None:
        rows.append({"id": f"d_{len(rows)}", "kind": "done", "value": value, "sub": sub})

    event = story_event.get(story_event.event_id(store_id, now.date()))
    if event and event["state"] in story_event.DONE and event.get("decided_at"):
        add(f"{event.get('headline') or '이벤트'} 스토리", f"{hm(parse(event['decided_at']))}에 스토리에 올렸어요")
    elif event and event["state"] == "generating":
        add("이벤트 포스터", "지금 그리고 있어요")
    feed = posts.posted_on(store_id, "feed", now.date())
    if any(p["status"] == "published" for p in feed):
        add("인스타에 인기 메뉴", "피드에 올렸어요")
    elif feed:
        add("인스타에 인기 메뉴", "지금 올리고 있어요")
    fresh = {r["id"] for r in arrived(view, now)}
    scheduled = [r for r in view.reviews() if r["id"] in fresh and r.get("sentiment") == "positive" and r.get("reply_status") == "scheduled"
                 and parse(r["reply_post_at"]) > now]
    if scheduled:
        first = parse(min(r["reply_post_at"] for r in scheduled))
        when = f"{hm(parse(heard['positive_scheduled']))}에 " if heard.get("positive_scheduled") else ""
        add(f"좋은 리뷰 {len(scheduled)}건 답변", f"{when}{speech.weekday(first.date())}요일 답변을 예약했어요")
    replied = auto_replied(view, now)
    if replied:
        minutes = max(1, round((parse(replied[0]["reply_posted_at"]) - parse(replied[0]["written_at"])).total_seconds() / 60))
        took = f"{minutes}분" if minutes < 60 else f"{minutes // 60}시간"
        add(f"아쉬운 리뷰 {len(replied)}건 답변", f"{took} 만에 답변했어요")
    asked = [r for r in view.reviews() if r.get("sentiment") == "negative" and r.get("reply_trigger") == "owner_yes"
             and r.get("reply_status") == "posted" and parse(r["reply_posted_at"]).date() == now.date()]
    if asked:  # 브리핑에서 여쭤보고 올린 사과 답글 (Figma J-12b '9:06에 고쳐서 올렸어요')
        last = max(asked, key=lambda r: r["reply_posted_at"])
        fixed = any((r.get("reply_ready") or {}).get("revised") for r in asked)
        add(f"아쉬운 리뷰 {len(asked)}건 사과 답변", f"{hm(parse(last['reply_posted_at']))}에 {'고쳐서 ' if fixed else ''}올렸어요")
    today = now.date().isoformat()
    for p in repo.all_of(proposals.KIND, store_id):
        if p["state"] == "applied" and (p.get("decided_at") or "")[:10] == today and p.get("decided_by") != "auto":
            # 할 일 제목(staff.title 16)이 줄 한도(rows.value 14)보다 길 수 있다
            add(width.fit("rows.value", p["payload"]["title"], "알바생 할 일"), f"{hm(parse(p['decided_at']))}에 알바생 할 일에 넣었어요")
    cards = [{"type": "rows", "id": "checked", "title": "오늘 아침에 한 것", "rows": rows[:4]}] if rows else []
    response = answer("오늘 브리핑은 여기까지예요", [say("오늘 브리핑은 여기까지예요.")], cards, kind="end")
    if hr_night.has_scene(store_id):  # 시연: 끝 화면을 보여 준 뒤 밤 9시 인사과 보고로 (K-01)
        response["next_scene"] = {"event": "night_hr", "after_ms": hr_night.SCENE_AFTER_MS}
    return response


def home_rows(view: VoiceStore, today: dt.date, reviews_in: list[dict], scheduled_n: int, *, story: bool = False,
              instagram: bool = False) -> list[dict]:
    """홈 '오늘 일정 브리핑 준비했어요' (H-01). 이름표 없이 한 줄로 읽힌다. 많아야 네 줄:
    오늘 일정(비, 예약) → 밤사이 리뷰 → 비 오는 날 이벤트(또는 인기 메뉴 피드) → 예약 손님 요청사항 → 예약한 답글."""
    reservations = _today(view.data.get("reservation", []), today)
    groups = [r for r in reservations if r["party_size"] >= config.GROUP_MIN_PEOPLE]
    parts = []
    if rain_today(view, today):
        parts.append("오늘 비")
    if _today(view.data.get("event", []), today):
        parts.append("행사")
    if _today(view.data.get("game", []), today):
        parts.append("경기")
    if groups:
        parts.append(f"단체 {groups[0]['party_size']}명")
    elif reservations:
        parts.append(f"예약 {len(reservations)}팀")
    rows = [{"id": "p_schedule", "kind": "schedule",
             "value": width.fit("rows.value", ", ".join(parts), "오늘 일정이 있어요") if parts else "평소와 같아요"}]
    if reviews_in:
        rows.append({"id": "p_reviews", "kind": "reviews", "value": f"밤사이 리뷰 {len(reviews_in)}건 읽어 둠"})
    if story:
        rows.append({"id": "p_story", "kind": "instagram", "value": "비 오는 날 이벤트 준비"})
    elif instagram:
        rows.append(INSTAGRAM_ROW)
    memos = with_memo(reservations)
    if memos:
        rows.append({"id": "p_request", "kind": "task", "value": f"{short_clock(parse(memos[0]['starts_at']))} 손님 요청사항 받아 둠"})
    if scheduled_n:
        rows.append({"id": "p_replies", "kind": "scheduled_replies", "value": f"좋은 리뷰 답글 {scheduled_n}건 예약"})
    drafted_n = sum(1 for r in view.reviews() if r.get("reply_status") == "awaiting")  # 칭찬 답글 인턴·사원: 써 두고 묻는다
    if drafted_n:
        rows.append({"id": "p_replies_ask", "kind": "scheduled_replies", "value": f"좋은 리뷰 답글 {drafted_n}건 써 둠"})
    return rows[:4]


def prepare(store_id: str) -> dict | None:
    """브리핑 묶음을 만들어 저장한다. 가게가 없으면 None.
    같은 가게의 준비는 한 번에 하나만 돈다 (작업 큐와 사장님의 "응"이 겹쳐도 답글을 두 번 쓰지 않게)."""
    with locks.lock("prepare", store_id):
        return _prepare(store_id)


def _prepare(store_id: str) -> dict | None:
    view = load(store_id)
    if view is None:
        return None
    now = clock.now()
    revise_jobs.expire(store_id)  # 날이 바뀐 뒤 남은 고쳐 쓰기 작업 (감사팀 9-3)
    asked = {job: hr.asks(store_id, job) for job in ("negative_reply", "positive_reply")}
    hr.evaluate(store_id, now.date())  # 인사과 격주 평가 (평가일이 아니거나 이미 했으면 바로 돌아온다, voice/hr.py)
    # 묻던 답글 업무가 이번 평가로 대리가 됐다: 대리는 묻지 않으므로 기다리던 답글을 올리거나 예약한다 (known-bugs B3)
    promoted = {job for job, mode in asked.items() if mode is not None and hr.asks(store_id, job) is None}
    proposals.expire(store_id, now.date().isoformat())  # 물을 날이 지난 할 일 제안은 버린다 (브리핑을 듣지 않으면 넣지 않는다)
    proposals.promote_repeats(store_id)  # 매뉴얼 코칭: 일주일에 세 번 나온 할 일은 매일 할 일로 올리자고 묻는다
    newly_scheduled = schedule_replies(view, now, promoted="positive_reply" in promoted)
    draft_negative(load(store_id))
    if "negative_reply" in promoted:
        auto_reply.post_ready(store_id)
    field_tasks.propose_today(load(store_id))  # 현장 변수 사원: 오늘 날씨·예약 때문에 필요한 알바생 할 일 (2026-11-20)
    holidays.read_naver(load(store_id))  # 네이버 휴무 안내에서 쉬는 날을 읽어 확인 전으로 둔다 (아래 holiday 단계에서 묻는다)
    marketing.plan_today(load(store_id))  # 마케팅: 소재 발굴 → 캡션 작성 (인스타를 연결한 가게만, voice/marketing.py)
    auto_instagram(load(store_id), now)  # 인스타 게시 대리: 묻지 않고 첫 식사 피크 한 시간 전에 올린다 (9-0 d)
    story_event.prepare_poster(load(store_id))  # 비 오는 날 이벤트 포스터를 미리 그려 둔다 (브리핑에서 바로 보여 주고 묻게, 2026-11-22)
    departments.run_reports(load(store_id))  # 부서 보고를 남기고, 부서 사이 충돌을 거른다 (voice/departments.py)
    story_event.auto_post(load(store_id))  # 포스터 대리(밤 9시 승진): 묻지 않고 올리고 저녁에 보고한다
    hr_night.schedule(store_id, now.date())  # 밤 9시 인사과 보고 (jobs/hr_night.py)
    view = load(store_id)  # 위에서 바꾼 리뷰를 다시 읽는다
    overnight = arrived(view, now)
    if overnight:
        activity.log(store_id, "donna", f"리뷰 {len(overnight)}개를 읽고 나눴어요", "reviews_read")
    if newly_scheduled:
        activity.log(store_id, "donna", f"좋은 리뷰 답글 {newly_scheduled}개를 예약했어요", "replies_scheduled")
    activity.log(store_id, "donna", "오늘 일정 브리핑을 준비했어요", "briefing_prepared")
    return assemble(store_id)


def assemble(store_id: str) -> dict | None:
    """밤사이 해 둔 일(리뷰 분류, 답글, 예약, 제안, 포스터)로 오늘 브리핑 단계를 짠다. 모델을 부르지 않는다.
    prepare 끝에서 부르고, 밤사이 준비 결과 저장본을 넣은 뒤에도 부른다 (voice/prepared_snapshot.py):
    저장본은 데이터만 쓰고 단계는 지금 코드로 다시 짜서, 브리핑 순서·문구를 고쳐도 저장본을 다시 만들 필요가 없다."""
    view = load(store_id)
    if view is None:
        return None
    now = clock.now()
    waiting = awaiting(view)
    reviews_in = arrived(view, now)
    steps: dict[str, dict | None] = {**summary_steps(view, now.date(), reviews_in), "holiday": holidays.step(view),
                                     "reviews": step_reviews(reviews_in)}
    steps["negative_done"] = step_negative_done(view, now)  # H-10: 허락받은 대로 바로 단 사과 답글
    shown = set((steps["negative_done"] or {}).get("report") or [])
    steps["done_report"], report_detail = done_report.step(view, now, skip=shown)  # 그 밖에 대리·과장이 처리한 것 (인사과 5단계)
    steps["negative"], negative_detail = step_negative(view, now, waiting)
    steps["scheduling"], scheduling_detail = step_scheduling(view, now)
    steps["positive_scheduled"] = step_positive_scheduled(view, now)  # H-09: 예약해 둔 좋은 리뷰 답글
    steps["instagram"], instagram_detail = step_instagram(view)
    steps["story_event"] = story_event.step(view)  # 비 오는 날 스토리 이벤트 (instagram/story_event.py)
    steps["staff_tasks"] = staff_tasks.step(view, now)  # 알바생 할 일 묻기 (jobs/staff_tasks.py, 2026-11-20)
    details = {key: plain_detail(step) for key, step in steps.items() if step and step["type"] == "answer"}
    if negative_detail:
        details["negative"] = negative_detail
    if report_detail:
        details["done_report"] = report_detail
    if scheduling_detail:
        details["scheduling"] = scheduling_detail
    if instagram_detail:
        details["instagram"] = instagram_detail
    scheduled_n = sum(1 for r in view.reviews() if r.get("reply_status") == "scheduled" and parse(r["reply_post_at"]) > now)

    briefing = {
        "store_id": store_id, "date": now.date().isoformat(), "prepared_at": iso(now),
        "home_rows": home_rows(view, now.date(), reviews_in, scheduled_n, story=bool(steps["story_event"]),
                               instagram=bool(steps["instagram"])),
        "steps": steps, "details": details,
        "sources": {"replies": sorted({r.get("reply_source") for r in view.reviews() if r.get("reply_source")} - {None})},
    }
    saved = repo.put("briefing", f"{store_id}:{briefing['date']}", store_id, briefing)
    tts.warm(briefing_lines(briefing))  # 단계가 넘어갈 때 목소리를 기다리지 않게 미리 합성
    return saved


def briefing_lines(briefing: dict) -> list[str]:
    """브리핑에서 도나가 읽을 문장 (단계, 끝 인사)."""
    lines = [s["text"] for step in briefing["steps"].values() if step for s in step["say"]]
    return lines + ["오늘 브리핑은 여기까지예요.", "스토리에 올렸어요.", "알바생 할 일에 넣었어요.", "네.", "네. 오늘 브리핑을 시작할까요?"]


def refresh_steps(store_id: str) -> dict | None:
    """대답으로 바뀌는 묻는 단계(알바생 할 일, 쉬는 날, 아쉬운 리뷰 답글)만 다시 만든다 (대답한 뒤, 브리핑 밖에서 물은 뒤)."""
    brief = current(store_id)
    view = load(store_id)
    if brief is None or view is None:
        return brief
    brief["steps"]["staff_tasks"] = staff_tasks.step(view, clock.now())
    brief["steps"]["holiday"] = holidays.step(view)
    brief["steps"]["scheduling"], _ = step_scheduling(view, clock.now())
    brief["steps"]["negative"], negative_detail = step_negative(view, clock.now(), awaiting(view))
    if negative_detail:
        brief["details"]["negative"] = negative_detail
    return repo.put("briefing", f"{store_id}:{brief['date']}", store_id, brief)



def current(store_id: str) -> dict | None:
    return repo.get("briefing", f"{store_id}:{clock.now().date().isoformat()}")
