"""F7 브리핑 묶음 만들기. 출근 한 시간 전에 돌고, 준비한 뒤 새 리뷰가 들어오면 다시 돈다.

순서
  1. F6 답글 예약: 답글 기다리는 좋은 리뷰에 올릴 때·이유를 정하고(규칙) 답글을 쓴다(voice_reply 에이전트)
  2. 허락을 거절한 가게면 아쉬운 리뷰에 답글 초안을 써 둔다 (올리지 않음)
  3. F4 고칠 점(improve_tip 에이전트), F5 좋아한 점(규칙)
  4. 홈 요약 + 5단계 응답 + 단계마다 자세히 보기(show/read) + 끝 응답을 만들어 briefing 표에 저장한다
/v1/turn 은 여기서 만든 것을 꺼내기만 한다 (LLM 없음). 모든 화면 글은 width 한도 안에 들어가게 fit 으로 고른다.
"""

import datetime as dt

from voice import clock, config, repo, speech, width
from voice.agents import improve_tip, voice_reply
from voice.clock import iso, parse
from voice.context import VoiceStore, load
from voice.jobs import queue, schedule, strengths

TOTAL = 5
STEP_KEYS = ["schedule", "reviews", "negative", "positive", "scheduling"]
REPEAT_CHIPS = ["다시 말해 줘", "다음"]
DETAIL_CHIPS = ["화면에 보여 줘", "다음"]


def say(text: str, caption: str | None = None, focus: list[str] | None = None) -> dict:
    return {"text": text, "caption": caption, "focus": focus or []}


def answer(headline: str, says: list[dict], cards: list[dict], suggestions: list[str], kind: str = "answer", **extra) -> dict:
    return {"type": kind, "headline": headline, "say": says, "cards": cards, "suggestions": suggestions,
            "expects_reply": False, **extra}


# ── 데이터 고르기 ──


def _today(items: list[dict], today: dt.date) -> list[dict]:
    return sorted((i for i in items if parse(i["starts_at"]).date() == today), key=lambda i: i["starts_at"])


def awaiting(view: VoiceStore) -> list[dict]:
    """답글 기다리는 리뷰: 아직 올리지 않은 것 (예약해 둔 답글 포함)."""
    return [r for r in view.reviews() if r.get("reply_status", "none") != "posted"]


def auto_replied(view: VoiceStore, now: dt.datetime) -> list[dict]:
    """지난 하루 동안 도나가 바로 답한 아쉬운 리뷰 (최근 것 먼저)."""
    since = now - dt.timedelta(days=1)
    found = [r for r in view.reviews() if r.get("reply_by") == "donna" and r.get("sentiment") == "negative"
             and r.get("reply_status") == "posted" and since <= parse(r["reply_posted_at"]) <= now]
    return sorted(found, key=lambda r: r["reply_posted_at"], reverse=True)


def recent_positive(view: VoiceStore, now: dt.datetime) -> list[dict]:
    since = now - config.POSITIVE_WINDOW
    return [r for r in view.reviews() if r.get("sentiment") == "positive" and since <= parse(r["written_at"]) <= now]


# ── 1~3: 미리 해 두는 일 ──


def schedule_replies(view: VoiceStore, now: dt.datetime) -> None:
    waiting = [r for r in view.reviews() if r.get("sentiment") == "positive" and r.get("reply_status", "none") == "none"]
    if not waiting:
        return
    for review, slot in schedule.assign(waiting, schedule.occasions(view.data, now.date())):
        occasion = {**slot, "post_at": iso(slot["post_at"])}
        written = voice_reply.write(view, review, "SCHEDULED", occasion)
        review.update({
            "reply_status": "scheduled", "reply_by": "donna", "reply_text": written["text"], "reply_source": written["source"],
            "reply_notes": written["notes"], "reply_post_at": occasion["post_at"],
            "reply_reason": {"kind": slot["kind"], "label": slot["label"], "explanation": slot["explanation"]},
        })
        repo.save_review(review)
        queue.add(view.store_id, "post_scheduled", slot["post_at"])


def draft_negative(view: VoiceStore) -> None:
    for review in view.reviews():
        if review.get("sentiment") == "negative" and review.get("reply_status", "none") == "none":
            written = voice_reply.write(view, review, "DRAFT")
            review.update({"reply_status": "drafted", "reply_by": "donna", "reply_text": written["text"], "reply_source": written["source"]})
            repo.save_review(review)


# ── 4: 단계 응답 ──


def step_schedule(view: VoiceStore, today: dt.date) -> dict:
    events, games = _today(view.data.get("event", []), today), _today(view.data.get("game", []), today)
    reservations = _today(view.data.get("reservation", []), today)
    general = [r for r in reservations if r["party_size"] < config.GROUP_MIN_PEOPLE]
    groups = [r for r in reservations if r["party_size"] >= config.GROUP_MIN_PEOPLE]
    if not (events or games or reservations):
        return answer("오늘은 평소와 같아요", [say("오늘은 평소와 같아요.")], [], REPEAT_CHIPS)

    rows, says = [], []
    for item, kind, label, rid in ((events[:1], "event", "행사", "s_event"), (games[:1], "game", "경기", "s_game")):
        if item:
            start = parse(item[0]["starts_at"])
            value = width.fit("rows.value", f"{item[0]['name']} {speech.clock_label(start)}", item[0]["name"], label)
            rows.append({"id": rid, "kind": kind, "label": label, "value": value})
    names = [e["name"] for e in events[:1]] + [g["name"] for g in games[:1]]
    if names:
        joined = speech.josa(names[0], "과", "와") + " " + names[1] if len(names) == 2 else names[0]
        text = f"{speech.josa(joined, '이', '가')} 있어요."
        short = [n.split()[-1] for n in names]
        short_joined = speech.josa(short[0], "과", "와") + " " + short[1] if len(short) == 2 else short[0]
        caption = width.fit("caption", text, f"{speech.josa(short_joined, '이', '가')} 있어요.", "행사와 경기가 있어요.")
        says.append(say(text, caption, [r["id"] for r in rows]))
    if general:
        parts = {speech.daypart(parse(r["starts_at"]).hour) for r in general}
        value = f"{parts.pop()}에 {speech.count(len(general), '팀')}" if len(parts) == 1 else f"오늘 {speech.count(len(general), '팀')}"
        rows.append({"id": "s_resv", "kind": "reservation", "label": "일반 예약", "value": value})
        text = f"일반 예약이 {speech.count(len(general), '팀')} 있어요."
        says.append(say(text, width.fit("caption", text, f"예약이 {len(general)}팀 있어요."), ["s_resv"]))
    if groups:
        first = parse(groups[0]["starts_at"])
        people = groups[0]["party_size"]
        value = width.fit("rows.value", f"{speech.clock_label(first)}, {speech.count(people, '분')}", f"{first.hour % 12 or 12}시, {people}명")
        rows.append({"id": "s_group", "kind": "group_reservation", "label": "단체 예약", "value": value})
        text = f"{speech.clock_label(first)}에는 단체 손님 {speech.count(people, '분')}이 오세요."
        caption = width.fit("caption", f"{first.hour % 12 or 12}시에 단체 손님 {speech.count(people, '분')}이 오세요.", f"단체 손님 {people}명이 오세요.")
        says.append(say(text, caption, ["s_group"]))

    busy: dict[str, int] = {}
    for item in events + games + reservations:
        part = speech.daypart(parse(item["starts_at"]).hour)
        busy[part] = busy.get(part, 0) + 1
    part, n = max(busy.items(), key=lambda kv: kv[1])
    headline = f"오늘은 {speech.josa(part, '이', '가')} 바빠요" if n >= 2 else "오늘 일정이 있어요"
    return answer(headline, [say(f"{headline}."), *says], [{"type": "rows", "id": "schedule", "rows": rows[:4]}], REPEAT_CHIPS)


def step_reviews(waiting: list[dict]) -> dict | None:
    if not waiting:
        return None
    pos = sum(1 for r in waiting if r.get("sentiment") == "positive")
    neg = len(waiting) - pos
    total = len(waiting)
    return answer(
        f"답글 기다리는 리뷰 {total}개",
        [say(f"답글 기다리는 리뷰가 {speech.count(total, '개')} 있어요."),
         say(f"좋은 리뷰 {speech.count(pos, '개')}, 아쉬운 리뷰 {speech.count(neg, '개')}예요.",
             width.fit("caption", f"좋은 리뷰 {pos}개, 아쉬운 리뷰 {neg}개예요.", f"좋은 {pos}개, 아쉬운 {neg}개예요."), ["c_pos", "c_neg"])],
        [{"type": "counts", "id": "review_counts", "items": [
            {"id": "c_pos", "kind": "positive", "label": "좋은 리뷰", "count": pos, "unit": "개"},
            {"id": "c_neg", "kind": "negative", "label": "아쉬운 리뷰", "count": neg, "unit": "개"}]}],
        REPEAT_CHIPS,
    )


def _review_card(review: dict, variant: str, reply: dict | None) -> dict:
    return {"type": "review", "id": review["id"], "variant": variant, "rating": review["rating"],
            "text": review["summary"] if variant == "summary" else review["text"], "written_at": review["written_at"], "reply": reply}


def step_negative(view: VoiceStore, now: dt.datetime, waiting: list[dict], tip: str | None) -> tuple[dict | None, dict | None]:
    """3단계 응답과 자세히 보기. 허락 설정에 따라 갈린다 (문서 10장 '3단계의 갈림')."""
    allowed = repo.settings(view.store_id).get("negative_review_auto_reply")
    waiting_neg = [r for r in waiting if r.get("sentiment") == "negative"]
    if not waiting:  # 답글 기다리는 리뷰가 없으면 2~3단계를 함께 건너뛴다
        return None, None
    tip_card = [{"type": "tip", "id": "tip_improve", "kind": "improve", "text": tip}] if tip else []
    tip_say = [say(tip, "이렇게 고쳐 보세요.", ["tip_improve"])] if tip else []

    if allowed is None:
        if not waiting_neg:
            return None, None
        n = len(waiting_neg)
        response = answer(
            "제가 바로 답할까요?",
            [say(f"아쉬운 리뷰가 {speech.count(n, '개')} 있어요.", width.fit("caption", f"아쉬운 리뷰가 {n}개 있어요.")),
             say("앞으로 아쉬운 리뷰에는 제가 30분 안에 답글을 달까요?", "30분 안에 답글을 달까요?", ["pm_reply"]),
             say("단 답글은 브리핑 때 알려 드리고, 언제든 끌 수 있어요.", "언제든 끌 수 있어요.", ["pm_briefing", "pm_off"])],
            [{"type": "rows", "id": "permission", "rows": [
                {"id": "pm_reply", "kind": "reply", "value": "아쉬운 리뷰에 30분 안에 답글"},
                {"id": "pm_briefing", "kind": "briefing", "value": "브리핑 때 알려 드려요"},
                {"id": "pm_off", "kind": "off", "value": "언제든 끌 수 있어요"}]}],
            ["응, 그렇게 해", "아니, 내가 볼게"], kind="ask_permission",
            permission={"key": "negative_review_auto_reply"},
        )
        response["expects_reply"] = True
        return response, None

    if allowed is True:
        replied = auto_replied(view, now)
        if not replied:
            return None, None
        review = replied[0]
        minutes = review["replied_in_minutes"]
        summary_reply = {"text": review["reply_summary"], "posted_at": review["reply_posted_at"], "by": "donna"}
        response = answer(
            f"{minutes}분 만에 답했어요",
            [say(f"밤사이 아쉬운 리뷰에 제가 {minutes}분 만에 답했어요.", width.fit("caption", f"{minutes}분 만에 답글을 달았어요.")),
             say(f"{review['summary'].removesuffix('대요')}다는 리뷰였어요." if review["summary"].endswith("대요") else review["summary"],
                 review["summary"], [review["id"]]),
             say(review["reply_summary"] + ".", None, [review["id"]]),
             *tip_say],
            [_review_card(review, "summary", summary_reply), *tip_card],
            DETAIL_CHIPS,
        )
        full_reply = {"text": review["reply_text"], "posted_at": review["reply_posted_at"], "by": "donna"}
        return response, _detail(review, full_reply, "제가 올린 답글이에요.")

    # 허락을 거절함: 아쉬운 리뷰와 써 둔 초안을 보여 준다 (14장 7번 제안). 올리지는 않는다
    if not waiting_neg:
        return None, None
    review = sorted(waiting_neg, key=lambda r: r["written_at"], reverse=True)[0]
    n = len(waiting_neg)
    response = answer(
        f"아쉬운 리뷰가 {n}개 있어요",
        [say(f"아쉬운 리뷰가 {speech.count(n, '개')} 있어요.", width.fit("caption", f"아쉬운 리뷰가 {n}개예요.")),
         say(review["summary"].removesuffix(".") + ".", review["summary"], [review["id"]]),
         say("답글 초안을 써 뒀어요.", "답글 초안을 써 뒀어요.", [review["id"]]), *tip_say],
        [_review_card(review, "summary", None), *tip_card],
        DETAIL_CHIPS,
    )
    draft = {"text": review.get("reply_text") or "", "posted_at": None, "by": "donna"}
    return response, _detail(review, draft, "제가 써 둔 답글 초안이에요.")


def _detail(review: dict, reply: dict, reply_intro: str) -> dict:
    card = _review_card(review, "full", reply)
    return {
        "show": answer("리뷰와 답글이에요", [say("리뷰와 답글을 화면에 띄웠어요.", "화면에 띄웠어요.")], [card], ["읽어 줘", "돌아가기"], kind="show_detail"),
        "read": answer("리뷰와 답글이에요", [
            say("손님 리뷰예요.", "손님 리뷰예요."), say(review["text"], None, [review["id"]]),
            say(reply_intro, width.fit("caption", reply_intro, "답글이에요.")), say(reply["text"], None, [review["id"]]),
        ], [card], ["돌아가기", "다음"]),
    }


def step_positive(view: VoiceStore, now: dt.datetime) -> dict | None:
    reviews = recent_positive(view, now)
    if len(reviews) < config.POSITIVE_MIN:
        return None
    found = strengths.analyze(reviews, view.menus)
    items = found["top"]
    bars = [{"id": f"b_{n}", "label": item["label"], "count": item["count"]} for n, item in enumerate(items, 1)]
    says = [say(f"최근 일주일 좋은 리뷰가 {speech.count(found['total'], '개')}예요.",
                width.fit("caption", f"최근 7일 좋은 리뷰 {found['total']}개예요.", f"좋은 리뷰 {found['total']}개예요."))]
    if items:
        first = items[0]
        says.append(say(f"{first['label']} 얘기가 {speech.count(first['count'], '번')} 나왔어요.",
                        width.fit("caption", f"{first['label']} {first['count']}번 나왔어요.", f"{first['label']} {first['count']}번"), ["b_1"]))
    if len(items) > 1:
        rest = [f"{speech.josa(i['label'], '이', '가')} {speech.count(i['count'], '번')}" for i in items[1:]]
        says.append(say(", ".join(rest) + "이에요.", None, [b["id"] for b in bars[1:]]))
    says.append(say(found["keep_tip"] + ".", "이렇게 지켜 보세요.", ["tip_keep"]))
    return answer(
        width.fit("headline", found["headline"], "좋은 리뷰가 많아요"), says,
        [{"type": "bars", "id": "strengths", "unit": "번", "items": bars},
         {"type": "tip", "id": "tip_keep", "kind": "keep", "text": width.fit("tip", found["keep_tip"], "지금처럼 맛과 응대를 지켜 주세요")}],
        REPEAT_CHIPS,
    )


def step_scheduling(view: VoiceStore, now: dt.datetime) -> tuple[dict | None, dict | None]:
    scheduled = [r for r in view.reviews() if r.get("reply_status") == "scheduled"]
    rows = schedule.rows(scheduled, view.menus, now)
    if not rows:
        return None, None
    n = sum(len(r["review_ids"]) for r in rows)
    says = [say(f"좋은 리뷰 답글 {speech.count(n, '개')}를 예약해 뒀어요.", width.fit("caption", f"답글 {n}개를 예약해 뒀어요."))]
    for row in rows:
        caption = width.fit("caption", f"{row['day_label']}요일 {row['time_label']}에 올려요.", f"{row['day_label']}요일에 올려요.")
        says.append(say(f"{row['day_label']}요일 {row['time_label']}에 올려요.", caption, [row["id"]]))
        says.append(say(f"{row['explanation']}.", None, [row["id"]]))  # say 는 한 문장씩
    card_rows = [{k: v for k, v in row.items() if k != "explanation"} for row in rows]
    response = answer("답글은 예약해 뒀어요", says, [{"type": "scheduled", "id": "scheduled_replies", "items": card_rows}], DETAIL_CHIPS)

    by_id = {r["id"]: r for r in scheduled}
    cards, reading = [], [say("예약한 답글을 읽어 드릴게요.", "예약한 답글이에요.")]
    for row in rows:
        for review_id in row["review_ids"]:
            review = by_id[review_id]
            cards.append(_review_card(review, "full", {"text": review["reply_text"], "posted_at": None, "by": "donna"}))
            reading += [say(f"{row['day_label']}요일 {row['time_label']}에 올릴 답글이에요.",
                            width.fit("caption", f"{row['day_label']}요일 {row['time_label']} 답글이에요.", "올릴 답글이에요."), [review_id]),
                        say(review["reply_text"], None, [review_id])]
    detail = {
        "show": answer("예약한 답글이에요", [say("예약한 답글을 화면에 띄웠어요.", "화면에 띄웠어요.")], cards, ["읽어 줘", "돌아가기"], kind="show_detail"),
        "read": answer("예약한 답글이에요", reading, cards, ["돌아가기", "다음"]),
    }
    return response, detail


def plain_detail(step: dict) -> dict:
    """리뷰 카드가 없는 단계의 자세히 보기: 같은 카드를 띄우고 짧게 한 마디."""
    return {
        "show": {**step, "type": "show_detail", "say": [say("화면에 띄웠어요.", "화면에 띄웠어요.")], "suggestions": ["읽어 줘", "돌아가기"],
                 "expects_reply": False},
        "read": {**step, "type": "answer", "suggestions": ["돌아가기", "다음"], "expects_reply": False},
    }


def end_response(steps: dict, waiting: list[dict], scheduled_n: int) -> dict:
    rows = [{"id": "d_schedule", "kind": "done", "value": "오늘 일정 확인했어요"}]
    if steps["reviews"]:
        rows.append({"id": "d_reviews", "kind": "done", "value": f"리뷰 {len(waiting)}개 확인했어요"})
    if steps["positive"]:
        rows.append({"id": "d_positive", "kind": "done", "value": "좋은 리뷰 분석 확인했어요"})
    if steps["scheduling"]:
        rows.append({"id": "d_scheduling", "kind": "done", "value": f"답글 {scheduled_n}개 예약했어요"})
    return answer("브리핑은 여기까지예요", [say("오늘 일정 브리핑은 여기까지예요.")],
                  [{"type": "rows", "id": "done", "rows": rows[:4]}], ["처음부터 다시", "리뷰 보여 줘"], kind="end")


def home_rows(view: VoiceStore, today: dt.date, waiting: list[dict], scheduled_n: int) -> list[dict]:
    parts = []
    if _today(view.data.get("event", []), today):
        parts.append("행사")
    if _today(view.data.get("game", []), today):
        parts.append("경기")
    reservations = _today(view.data.get("reservation", []), today)
    if reservations:
        parts.append(f"예약 {speech.count(len(reservations), '팀')}")
    rows = [{"id": "p_schedule", "kind": "schedule", "label": "오늘 일정",
             "value": width.fit("rows.value", ", ".join(parts), "일정이 있어요") if parts else "평소와 같아요"}]
    if waiting:
        rows.append({"id": "p_reviews", "kind": "reviews", "label": "밤사이 리뷰", "value": f"{len(waiting)}개 읽고 나눠 놨어요"})
    if scheduled_n:
        rows.append({"id": "p_replies", "kind": "scheduled_replies", "label": "좋은 리뷰 답글", "value": f"{scheduled_n}개 예약해 놨어요"})
    return rows


def prepare(store_id: str) -> dict | None:
    """브리핑 묶음을 만들어 저장한다. 가게가 없으면 None."""
    view = load(store_id)
    if view is None:
        return None
    now = clock.now()
    schedule_replies(view, now)
    if repo.settings(store_id).get("negative_review_auto_reply") is False:
        draft_negative(view)
    view = load(store_id)  # 위에서 바꾼 리뷰를 다시 읽는다
    waiting = awaiting(view)
    tip = improve_tip.suggest(view, now)

    steps: dict[str, dict | None] = {"schedule": step_schedule(view, now.date()), "reviews": step_reviews(waiting)}
    steps["negative"], negative_detail = step_negative(view, now, waiting, tip["text"])
    steps["positive"] = step_positive(view, now)
    steps["scheduling"], scheduling_detail = step_scheduling(view, now)
    details = {key: plain_detail(step) for key, step in steps.items() if step and step["type"] == "answer"}
    if negative_detail:
        details["negative"] = negative_detail
    if scheduling_detail:
        details["scheduling"] = scheduling_detail
    scheduled_n = sum(len(i["review_ids"]) for i in (steps["scheduling"] or {"cards": [{"items": []}]})["cards"][0]["items"])

    briefing = {
        "store_id": store_id, "date": now.date().isoformat(), "prepared_at": iso(now),
        "home_rows": home_rows(view, now.date(), waiting, scheduled_n),
        "steps": steps, "details": details, "end": end_response(steps, waiting, scheduled_n),
        "sources": {"improve_tip": tip["source"]},
    }
    return repo.put("briefing", f"{store_id}:{briefing['date']}", store_id, briefing)


def current(store_id: str) -> dict | None:
    return repo.get("briefing", f"{store_id}:{clock.now().date().isoformat()}")
