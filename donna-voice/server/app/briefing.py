"""브리핑 묶음 만들기 (인수인계 문서의 F7).

저장된 데이터에서 홈 요약과 브리핑 단계의 응답을 만든다. LLM을 부르지 않는다.
문장과 화면은 Figma `v0.2.1 : 디자인개선`의 D-07 ~ D-16과 그 대본을 따른다.

v0.2.1 화면 규칙
- 칩(추천 답변)이 없다. 응답에 suggestions 를 넣지 않는다.
- 카드 줄(rows)에 이름표(label)가 없다. value 는 혼자 읽혀야 하고, 숫자는 아라비아 숫자로 쓴다.
- caption 은 카드에 없는 것(이유, 되돌리는 법, 질문)일 때만 준다.
- say[].text 의 숫자는 읽는 대로("열두 분").
"""
from __future__ import annotations

import datetime as dt

from .data import STATE, clock_label, date_label, now, store_status

# 브리핑 단계. 게이지바는 다섯 칸: 일정, 리뷰, 좋은 리뷰, 인스타, 끝.
STEPS = ["schedule", "reviews", "negative", "positive", "scheduling", "instagram"]
GAUGE = {"schedule": 1, "reviews": 2, "negative": 2, "positive": 3, "scheduling": 3, "instagram": 4}
TOTAL = 5
NATIVE = ["", "한", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉", "열", "열한", "열두", "열세", "열네", "열다섯"]


def kor(n: int) -> str:
    """읽는 말: 4 → 네, 12 → 열두."""
    return NATIVE[n] if 0 < n < len(NATIVE) else str(n)


def time_label(iso: str) -> str:
    return clock_label(dt.datetime.fromisoformat(iso))


def S(text: str, focus: list[str] | None = None, caption: str | None = None) -> dict:
    return {"text": text, "caption": caption, "focus": focus or []}


def _today(items: list[dict]) -> list[dict]:
    d = now().date()
    return [x for x in items if dt.datetime.fromisoformat(x["starts_at"]).date() == d]


def _weather(d: dt.date) -> dict | None:
    return next((w for w in STATE["weather"] if w["date"] == d.isoformat()), None)


def waiting_reviews() -> list[dict]:
    return [r for r in STATE["reviews"] if r["reply_status"] != "posted"]


MORNING = {
    # 화면 글, 말할 때 쓰는 줄기 ("…했고", "…했어요"), 화면 순서
    "manual": ("매뉴얼에 배달 면 따로 담기 넣음", "배달 면 따로 담기를 매뉴얼에 넣었", 1),
    "negative": ("아쉬운 리뷰에 답글", "아쉬운 리뷰에 답했", 2),
    "scheduled": ("좋은 리뷰 답글 예약", "좋은 리뷰 답글은 예약했", 3),
    "instagram": ("인스타에 인기 메뉴 올림", "인스타에 인기 메뉴를 올렸", 4),
}


def morning(key: str) -> None:
    """브리핑 동안 한 것 (D-16 '오늘 아침에 한 것'). 같은 것은 한 번만."""
    if not any(m["key"] == key for m in STATE["morning_done"]):
        text, stem, order = MORNING[key]
        STATE["morning_done"].append({"key": key, "text": text, "stem": stem, "order": order})


def store_block() -> dict:
    s = STATE["store"]
    return {"id": s["id"], "name": s["name"], "logo_url": s["logo_url"], "open_time": s["open_time"], "close_time": s["close_time"]}


# ---------- 홈 (D-07) ----------
def home() -> dict:
    d = now().date()
    rows = []
    groups = [r for r in _today(STATE["reservations"]) if r["kind"] == "group"]
    general = [r for r in _today(STATE["reservations"]) if r["kind"] == "general"]
    w = _weather(d)
    parts = []
    if groups:
        parts.append(f"단체 {groups[0]['party_size']}명")
    elif general:
        parts.append(f"예약 {len(general)}팀")
    if w and w["label"] == "비":
        parts.append("오후 비" if w.get("rain_from", 0) >= 12 else "비")
    if parts:
        rows.append({"id": "p_schedule", "kind": "schedule", "value": ", ".join(parts)})
    waiting = waiting_reviews()
    if waiting:
        rows.append({"id": "p_reviews", "kind": "reviews", "value": f"밤사이 리뷰 {len(waiting)}개 읽어 둠"})
    ig = STATE["instagram"]
    if ig["connected"] and not ig["posted_at"] and STATE["top_menus"]:
        rows.append({"id": "p_instagram", "kind": "instagram", "value": "인기 메뉴 피드 준비"})
    if STATE["manual"] and any(s["joined"] for s in STATE["staff"]):
        rows.append({"id": "p_staff", "kind": "staff", "value": "알바생 매뉴얼 올림"})
    return {
        "store": store_block(),
        "date": d.isoformat(),
        "date_label": date_label(d),
        "store_status": store_status(),
        "now": now().isoformat(),
        "briefing_ready": True,
        "prepared_at": now().replace(hour=9, minute=0).isoformat(),
        "headline": "오늘 일정 브리핑 준비했어요",
        "cards": [{"type": "rows", "id": "prepared", "rows": rows}] if rows else [],
    }


# ---------- 1. 오늘 일정 (D-08) ----------
def step_schedule() -> dict:
    d = now().date()
    resv = _today(STATE["reservations"])
    general = [r for r in resv if r["kind"] == "general"]
    groups = [r for r in resv if r["kind"] == "group"]
    w = _weather(d)
    rows, say = [], [S("오늘 일정이에요.")]
    rain = w and w["label"] == "비"
    if rain:
        rf = w.get("rain_from")
        rows.append({"id": "s_rain", "kind": "weather", "value": f"{clock_label(dt.time(rf))}부터 비" if rf else "하루 종일 비"})
    if general:
        part = "저녁 " if all(dt.datetime.fromisoformat(r["starts_at"]).hour >= 17 for r in general) else ""
        rows.append({"id": "s_resv", "kind": "reservation", "value": f"{part}예약 {len(general)}팀"})
    for g in groups:
        rows.append({"id": "s_group", "kind": "group_reservation", "value": f"{time_label(g['starts_at'])} 단체 {g['party_size']}명"})
    if not rows:
        return {"headline": "오늘은 평소와 같아요", "say": [S("오늘은 행사나 예약이 없어요. 평소와 같아요.")], "cards": []}
    for g in groups:
        say.append(S(f"{time_label(g['starts_at'])}에 단체 손님 {kor(g['party_size'])} 분이 오세요.", ["s_group"]))
    if general:
        say.append(S(f"저녁 예약은 {kor(len(general))} 팀이고," if rain else f"저녁 예약은 {kor(len(general))} 팀이에요.", ["s_resv"]))
    if rain:
        rf = w.get("rain_from")
        say.append(S(f"{clock_label(dt.time(rf))}부터 비 소식이 있어요." if rf else "하루 종일 비 소식이 있어요.", ["s_rain"]))
    if groups:
        g = groups[0]
        headline = f"{time_label(g['starts_at'])}에 단체 {g['party_size']}명이 와요"
    elif general:
        headline = f"저녁 예약이 {len(general)}팀이에요"
    else:
        headline = "오늘은 비 소식이 있어요"
    return {"headline": headline, "say": say, "cards": [{"type": "rows", "id": "schedule", "rows": rows[:4]}]}


# ---------- 2. 답글 기다리는 리뷰 (D-09) ----------
def step_reviews() -> dict | None:
    waiting = waiting_reviews()
    if not waiting:
        return None
    pos = len([r for r in waiting if r["sentiment"] == "positive"])
    neg = len(waiting) - pos
    return {
        "headline": f"답글 기다리는 리뷰 {len(waiting)}개",
        "say": [
            S("이제 리뷰예요."),
            S(f"답글을 기다리는 리뷰가 {kor(len(waiting))} 개예요."),
            S(f"좋은 리뷰 {kor(pos)} 개, 아쉬운 리뷰 {kor(neg)} 개예요."),
        ],
        "cards": [{"type": "counts", "id": "review_counts", "items": [
            {"id": "c_pos", "kind": "positive", "label": "좋은 리뷰", "count": pos, "unit": "개"},
            {"id": "c_neg", "kind": "negative", "label": "아쉬운 리뷰", "count": neg, "unit": "개"},
        ]}],
    }


# ---------- 2. 아쉬운 리뷰 (D-10 처음 한 번 / D-11) ----------
def auto_replied() -> list[dict]:
    return [r for r in STATE["reviews"] if r["sentiment"] == "negative" and r.get("reply_status") == "posted" and r.get("replied_in_minutes") is not None]


def review_card(r: dict) -> dict:
    """화면에는 실제로 단 답글을 그대로 보여 준다. 별점은 별로만 보이고 말로 읽지 않는다 (D-11)."""
    reply = None
    if r.get("reply_text"):
        reply = {"text": r["reply_text"], "posted_at": r.get("reply_posted_at"), "by": "donna"}
    return {"type": "review", "id": r["id"], "variant": "full", "rating": r["rating"], "text": r["text"], "written_at": r["written_at"], "reply": reply}


def replied_answer(r: dict) -> dict:
    m = r["replied_in_minutes"]
    return {
        "headline": f"{m}분 만에 답했어요",
        "say": [
            S("어젯밤 배달로 드신 손님이 면이 불어서 왔다는 리뷰를 남기셨어요." if r["order_channel"] == "delivery" else f"어제 손님이 {r['summary']}."),
            S(f"{m}분 만에 사과하고, 다음엔 면을 따로 담겠다고 답했어요." if r["order_channel"] == "delivery" else f"{m}분 만에 사과 답글을 달았어요."),
        ],
        "cards": [review_card(r)],
    }


def step_negative() -> dict | None:
    perm = STATE["settings"]["negative_review_auto_reply"]
    negatives = [r for r in STATE["reviews"] if r["sentiment"] == "negative"]
    if not negatives:
        return None
    if perm is None:
        return {
            "type": "ask_permission",
            "permission": {"key": "negative_review_auto_reply"},
            "expects_reply": True,
            "headline": "제가 바로 답할까요?",
            "say": [
                S("아쉬운 리뷰는 빨리 답할수록 좋아요.", caption="아쉬운 리뷰는 빨리 답할수록 좋아요."),
                S("앞으로는 제가 30분 안에 사과 답글을 달고, 브리핑 때 알려 드릴까요?"),
            ],
            "cards": [{"type": "rows", "id": "permission", "rows": [
                {"id": "pm_reply", "kind": "reply", "value": "30분 안에 사과 답글"},
                {"id": "pm_brief", "kind": "briefing", "value": "브리핑 때 알려 드려요"},
                {"id": "pm_off", "kind": "off", "value": "언제든 말로 끌 수 있어요"},
            ]}],
        }
    if perm is True:
        done = auto_replied()
        if not done:
            return None
        morning("negative")
        return replied_answer(done[0])
    # 허락하지 않은 경우 (Figma에 화면 없음): 아쉬운 리뷰를 알려 주기만 한다.
    waiting = [r for r in negatives if r["reply_status"] != "posted"]
    if not waiting:
        return None
    r = waiting[0]
    return {
        "headline": f"아쉬운 리뷰가 {len(waiting)}개 있어요",
        "say": [S(f"아쉬운 리뷰가 {kor(len(waiting))} 개 있어요. {r['summary']}.", [r["id"]])],
        "cards": [review_card(r)],
    }


def post_reply_now() -> dict | None:
    """허락을 받자마자 밤사이 아쉬운 리뷰 하나에 답한다 (Figma D-10 → D-11 시연 흐름: 12분 만에)."""
    r = next((x for x in STATE["reviews"] if x["sentiment"] == "negative" and x["reply_status"] != "posted" and x["order_channel"] == "delivery"), None)
    if not r:
        return None
    r.update(
        reply_status="posted",
        reply_text="불어서 드시게 해 정말 죄송합니다. 다음부터 배달은 면과 국물을 따로 담아 보내 드릴게요. 다시 찾아 주시면 제대로 된 한 그릇으로 보답하겠습니다.",
        reply_summary="사과하고, 다음엔 면을 따로 담겠다고 답했어요",
        reply_posted_at=dt.datetime.fromisoformat(r["written_at"]).replace(minute=52).isoformat(),
        replied_in_minutes=12,
    )
    return r


# ---------- 3. 좋은 리뷰 일주일 (D-12) ----------
def step_positive() -> dict | None:
    s = STATE["strengths"]
    if s["positive_count"] < 3:
        return None
    n = s["positive_count"]
    return {
        "headline": "들깨 국물을 좋아하세요",
        "say": [
            S(f"이번 주 좋은 리뷰 {kor(n)} 개를 봤어요."),
            S("들깨 국물이 고소하다는 칭찬이 가장 많았어요.", [s["items"][0]["id"]]),
            S(f"{s['keep']}.", ["tip_keep"]),
        ],
        "cards": [
            {"type": "bars", "id": "strengths", "unit": "개", "items": s["items"][:3]},
            {"type": "tip", "id": "tip_keep", "kind": "keep", "text": s["keep"]},
        ],
    }


# ---------- 3. 답글 예약과 이유 (D-13) ----------
def step_scheduling() -> dict | None:
    items = STATE["scheduled"]
    if not items:
        return None
    morning("scheduled")
    say = [S("좋은 리뷰 답글은 가장 잘 보일 때 올리려고 예약해 뒀어요.")]
    for it in items:
        say.append(S(it["say"], [it["id"]]))
    cards = [{"type": "scheduled", "id": "scheduled_replies", "items": [
        {k: it[k] for k in ("id", "day_label", "time_label", "post_at", "reason", "text", "review_ids")} for it in items[:3]
    ]}]
    return {"headline": "답글은 예약해 뒀어요", "say": say, "cards": cards, "detail_scheduled": True}


# ---------- 4. 인스타에 올릴까요 (D-14, D-15) ----------
def menus_card(n: int = 3) -> dict:
    return {"type": "menus", "id": "top_menus", "title": "이번 달 가장 많이 나간 메뉴", "items": [
        {"id": m["id"], "rank": i + 1, "name": m["name"], "count_label": f"{m['month_count']}그릇", "photo_url": m["photo_url"]}
        for i, m in enumerate(STATE["top_menus"][:n])
    ]}


def step_instagram() -> dict | None:
    ig = STATE["instagram"]
    if not ig["connected"] or ig["posted_at"] or len(STATE["top_menus"]) < 3:
        return None
    names = [m["name"] for m in STATE["top_menus"][:3]]
    return {
        "type": "ask",
        "ask": {"key": "instagram_post"},
        "expects_reply": True,
        "headline": "인스타에 올릴까요?",
        "say": [
            S(f"이번 달 가장 많이 나간 메뉴는 {names[0]}, {names[1]}, {names[2]}예요.", ["top_menus"]),
            S(f"손님 리뷰 \"{ig['quote']}\"를 글에 넣었어요.", ["insta_quote"]),
            S("인스타에 올릴까요?"),
        ],
        "cards": [
            menus_card(3),
            {"type": "quote", "id": "insta_quote", "label": "글에 넣을 손님 리뷰", "text": f"“{ig['quote']}”"},
        ],
    }


def insta_post_card(slide: int) -> dict:
    ig = STATE["instagram"]
    s = STATE["store"]
    slide = max(1, min(slide, ig["slides"]))
    base = {"type": "insta_post", "id": "insta_post", "handle": ig["handle"], "logo_url": s["logo_url"], "slide": slide, "slides": ig["slides"],
            "caption": "많이 나간 메뉴 1등이에요… 더 보기"}
    if slide <= 3:
        m = STATE["top_menus"][slide - 1]
        return {**base, "photo_url": m["photo_url"], "top_label": f"이번 달 {slide}등", "title": m["name"]}
    return {**base, "photo_url": None, "top_label": s["address"], "title": s["name"]}


def insta_preview(slide: int = 1) -> dict:
    ordinal = ["", "첫", "둘째", "셋째", "넷째"][slide] if slide < 5 else f"{slide}번째"
    return {
        "type": "show_detail",
        "briefing": None,
        "headline": "이렇게 올라가요",
        "say": [S("화면에 띄웠어요. 넉 장 중 첫 장이에요." if slide == 1 else f"{ordinal} 장이에요.")],
        "cards": [insta_post_card(slide)],
        "expects_reply": True,
    }


def post_instagram() -> None:
    STATE["instagram"]["posted_at"] = now().isoformat()
    morning("instagram")


BUILDERS = {"schedule": step_schedule, "reviews": step_reviews, "negative": step_negative,
            "positive": step_positive, "scheduling": step_scheduling, "instagram": step_instagram}


def build_step(index: int) -> dict | None:
    """index 는 STEPS 의 1부터. 건너뛰는 단계면 None."""
    key = STEPS[index - 1]
    body = BUILDERS[key]()
    if body is None:
        return None
    out = {
        "index": index,
        "type": body.get("type", "answer"),
        "briefing": {"step": GAUGE[key], "total": TOTAL, "step_key": key},
        "headline": body["headline"],
        "say": body["say"],
        "cards": body["cards"],
        "expects_reply": body.get("expects_reply", False),
    }
    for k in ("permission", "ask", "detail_scheduled"):
        if k in body:
            out[k] = body[k]
    return out


def next_step(after: int) -> dict | None:
    for i in range(after + 1, len(STEPS) + 1):
        s = build_step(i)
        if s:
            return s
    return None


def end(posted: bool = False) -> dict:
    done = sorted(STATE["morning_done"], key=lambda m: m["order"])
    rows = [{"id": f"d_{i}", "kind": "done", "value": m["text"]} for i, m in enumerate(done)]
    say = ([S("인스타에 올렸어요.")] if posted else []) + [S("오늘 브리핑은 여기까지예요.")]
    # 대본 순서: 아쉬운 리뷰 → 매뉴얼 → 답글 예약 ("…했고, …했고, …했어요.")
    stems = [m["stem"] for m in sorted(done, key=lambda m: {"negative": 0, "manual": 1, "scheduled": 2}.get(m["key"], 9)) if m["key"] != "instagram"]
    if stems:
        say.append(S("".join(f"{s}고, " for s in stems[:-1]) + f"{stems[-1]}어요."))
    return {
        "type": "end",
        "briefing": {"step": TOTAL, "total": TOTAL, "step_key": "end"},
        "headline": "인스타에 올렸어요" if posted else "브리핑은 여기까지예요",
        "say": say,
        "cards": [{"type": "rows", "id": "checked", "title": "오늘 아침에 한 것", "rows": rows}] if rows else [],
        "expects_reply": False,
    }


# ---------- 화면으로 보기 ----------
def detail(step: dict) -> dict | None:
    if step.get("detail_scheduled"):
        by_id = {r["id"]: r for r in STATE["reviews"]}
        cards = []
        for it in STATE["scheduled"]:
            for rid in it["review_ids"]:
                c = review_card(by_id[rid])
                if c["reply"]:
                    c["reply"]["scheduled_label"] = f"{it['day_label']}요일 {it['time_label']}에 올릴 답글"
                cards.append(c)
        return {"type": "show_detail", "briefing": step["briefing"], "headline": "예약한 답글이에요",
                "say": [S("화면에 띄웠어요.")], "cards": cards, "expects_reply": False}
    if step.get("ask", {}).get("key") == "instagram_post":
        return insta_preview(1)
    return None


def read_detail(d: dict) -> list[dict]:
    say = []
    for c in d["cards"]:
        if c["type"] != "review":
            continue
        say.append(S(f"리뷰예요. {c['text']}", [c["id"]]))
        if c.get("reply"):
            say.append(S(f"답글이에요. {c['reply']['text']}", [c["id"]]))
    return say
