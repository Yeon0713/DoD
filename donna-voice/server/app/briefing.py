"""브리핑 묶음 만들기 (인수인계 문서의 F7).

저장된 데이터에서 홈 요약과 브리핑 5단계의 응답을 만든다. LLM을 부르지 않는다.
나중에 에이전트가 붙으면 이 파일이 "미리 만들어 둔 브리핑 묶음을 꺼내는 곳"이 된다.
"""
from __future__ import annotations

import datetime as dt

from .data import STATE, date_label, now

STEPS = ["schedule", "reviews", "negative", "positive", "scheduling"]
NATIVE = ["", "한", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉", "열", "열한", "열두", "열세", "열네", "열다섯"]


def kor(n: int) -> str:
    """읽는 말: 4 → 네, 12 → 열두."""
    return NATIVE[n] if 0 < n < len(NATIVE) else str(n)


def time_label(iso: str) -> str:
    t = dt.datetime.fromisoformat(iso)
    h = t.hour
    part = "오전" if h < 12 else "낮" if h == 12 else "오후" if h < 17 else "저녁" if h < 21 else "밤"
    h12 = h if h <= 12 else h - 12
    return f"{part} {h12}시" + (f" {t.minute}분" if t.minute else "")


def _today(items: list[dict]) -> list[dict]:
    d = now().date()
    return [x for x in items if dt.datetime.fromisoformat(x["starts_at"]).date() == d]


def waiting_reviews() -> list[dict]:
    return [r for r in STATE["reviews"] if r["reply_status"] != "posted"]


# ---------- 홈 (D-01) ----------
def home() -> dict:
    events, games = _today(STATE["events"]), _today(STATE["games"])
    resv = _today(STATE["reservations"])
    rows = []
    parts = []
    if events:
        parts.append("행사")
    if games:
        parts.append("경기")
    if resv:
        parts.append(f"예약 {kor(len(resv))} 팀")
    if parts:
        rows.append({"id": "p_schedule", "kind": "schedule", "label": "오늘 일정", "value": ", ".join(parts)})
    waiting = waiting_reviews()
    if waiting:
        rows.append({"id": "p_reviews", "kind": "reviews", "label": "밤사이 리뷰", "value": f"{len(waiting)}개 읽고 나눠 놨어요"})
    if STATE["scheduled"]:
        rows.append({"id": "p_replies", "kind": "scheduled_replies", "label": "좋은 리뷰 답글", "value": f"{len(STATE['scheduled'])}개 예약해 놨어요"})
    d = now().date()
    return {
        "store": {"id": STATE["store"]["id"], "name": STATE["store"]["name"]},
        "date": d.isoformat(),
        "date_label": date_label(d),
        "briefing_ready": True,
        "prepared_at": now().replace(hour=9, minute=0).isoformat(),
        "headline": "오늘 일정 브리핑 준비했어요",
        "cards": [{"type": "rows", "id": "prepared", "rows": rows}] if rows else [],
        "suggestions": ["오늘 일정 브리핑해 줘"],
    }


# ---------- 1단계: 오늘 일정 (D-03) ----------
def step_schedule() -> dict:
    events, games = _today(STATE["events"]), _today(STATE["games"])
    resv = _today(STATE["reservations"])
    general = [r for r in resv if r["kind"] == "general"]
    groups = [r for r in resv if r["kind"] == "group"]
    rows, say = [], []
    for e in events:
        rows.append({"id": "s_event", "kind": "event", "label": "행사", "value": f"{e['name']} {time_label(e['starts_at'])}"})
    for g in games:
        rows.append({"id": "s_game", "kind": "game", "label": "경기", "value": f"{g['name']} {time_label(g['starts_at'])}"})
    if general:
        rows.append({"id": "s_resv", "kind": "reservation", "label": "일반 예약", "value": f"저녁에 {kor(len(general))} 팀"})
    for g in groups:
        rows.append({"id": "s_group", "kind": "group_reservation", "label": "단체 예약", "value": f"{time_label(g['starts_at'])}, {kor(g['party_size'])} 분"})
    if not rows:
        return {"headline": "오늘은 평소와 같아요", "say": [{"text": "오늘은 행사나 예약이 없어요. 평소와 같아요.", "caption": "행사나 예약이 없어요.", "focus": []}], "cards": []}
    say.append({"text": "오늘은 저녁이 바빠요.", "caption": None, "focus": []})
    if events and games:
        say.append({"text": f"{events[0]['name']}과 {games[0]['name']}가 있어요.", "caption": "페스티벌과 한국시리즈가 있어요.", "focus": ["s_event", "s_game"]})
    elif events:
        say.append({"text": f"{events[0]['name']}이 있어요.", "caption": f"{events[0]['name']}이 있어요.", "focus": ["s_event"]})
    elif games:
        say.append({"text": f"{games[0]['name']}가 있어요.", "caption": f"{games[0]['name']}가 있어요.", "focus": ["s_game"]})
    if general:
        t = f"일반 예약이 {kor(len(general))} 팀 있어요."
        say.append({"text": t, "caption": t, "focus": ["s_resv"]})
    for g in groups:
        tl = time_label(g["starts_at"])
        say.append({
            "text": f"{tl}에는 단체 손님 {kor(g['party_size'])} 분이 오세요.",
            "caption": f"{tl.split(' ')[-1]}에 단체 손님 {kor(g['party_size'])} 분이 오세요.",
            "focus": ["s_group"],
        })
    return {"headline": "오늘은 저녁이 바빠요", "say": say, "cards": [{"type": "rows", "id": "schedule", "rows": rows[:4]}]}


# ---------- 2단계: 답글 기다리는 리뷰 (D-04) ----------
def step_reviews() -> dict | None:
    waiting = waiting_reviews()
    if not waiting:
        return None
    pos = len([r for r in waiting if r["sentiment"] == "positive"])
    neg = len(waiting) - pos
    return {
        "headline": f"답글 기다리는 리뷰 {len(waiting)}개",
        "say": [
            {"text": f"답글을 기다리는 리뷰가 {kor(len(waiting))} 개 있어요.", "caption": None, "focus": []},
            {"text": f"좋은 리뷰 {kor(pos)} 개, 아쉬운 리뷰 {kor(neg)} 개예요.", "caption": f"좋은 리뷰 {pos}개, 아쉬운 리뷰 {neg}개예요.", "focus": []},
        ],
        "cards": [{"type": "counts", "id": "review_counts", "items": [
            {"id": "c_pos", "kind": "positive", "label": "좋은 리뷰", "count": pos, "unit": "개"},
            {"id": "c_neg", "kind": "negative", "label": "아쉬운 리뷰", "count": neg, "unit": "개"},
        ]}],
    }


# ---------- 3단계: 아쉬운 리뷰 (D-05 또는 D-06) ----------
def auto_replied() -> list[dict]:
    return [r for r in STATE["reviews"] if r["sentiment"] == "negative" and r.get("reply_status") == "posted" and r.get("replied_in_minutes") is not None]


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
                {"text": "아쉬운 리뷰는 빨리 답할수록 좋아요.", "caption": "아쉬운 리뷰는 빨리 답할수록 좋아요.", "focus": []},
                {"text": "앞으로는 제가 30분 안에 사과 답글을 달고, 브리핑 때 알려 드릴까요?", "caption": "제가 바로 답하고 알려 드릴까요?", "focus": []},
            ],
            "cards": [{"type": "rows", "id": "permission", "rows": [
                {"id": "pm_reply", "kind": "reply", "value": "30분 안에 사과 답글"},
                {"id": "pm_brief", "kind": "briefing", "value": "브리핑 때 알려 드려요"},
                {"id": "pm_off", "kind": "off", "value": "언제든 말로 끌 수 있어요"},
            ]}],
            "suggestions": ["응, 그렇게 해", "아니, 내가 볼게"],
        }
    if perm is True:
        done = auto_replied()
        if not done:
            return None
        r, imp = done[0], STATE["improve"]
        return {
            "headline": f"{r['replied_in_minutes']}분 만에 답했어요",
            "say": [
                {"text": f"어젯밤 {r['summary'].replace('대요', '다는')} 리뷰가 왔어요.", "caption": "어젯밤 아쉬운 리뷰가 하나 왔어요.", "focus": [r["id"]]},
                {"text": f"{r['replied_in_minutes']}분 만에 사과하고, 다음엔 더 빨리 보내 드린다고 답했어요.", "caption": f"{r['replied_in_minutes']}분 만에 사과 답글을 달았어요.", "focus": [r["id"]]},
                {"text": imp["say"], "caption": imp["caption"], "focus": ["tip_improve"]},
            ],
            "cards": [
                {"type": "review", "id": r["id"], "variant": "summary", "rating": r["rating"], "text": r["summary"], "written_at": r["written_at"],
                 "reply": {"text": r["reply_summary"], "posted_at": r["reply_posted_at"], "by": "donna"}},
                {"type": "tip", "id": "tip_improve", "kind": "improve", "text": imp["tip"]},
            ],
            "suggestions": ["화면에 보여 줘", "다음"],
            "detail_review_id": r["id"],
        }
    # 허락하지 않은 경우: Figma에 화면이 없다 (docs/open-features.md). 아쉬운 리뷰를 줄여서 알려 주기만 한다.
    waiting = [r for r in negatives if r["reply_status"] != "posted"]
    if not waiting:
        return None
    r = waiting[0]
    return {
        "headline": f"아쉬운 리뷰가 {len(waiting)}개 있어요",
        "say": [{"text": f"아쉬운 리뷰가 {kor(len(waiting))} 개 있어요. {r['summary']}.", "caption": f"{r['summary']}.", "focus": [r["id"]]}],
        "cards": [{"type": "review", "id": r["id"], "variant": "summary", "rating": r["rating"], "text": r["summary"], "written_at": r["written_at"], "reply": None}],
        "suggestions": ["화면에 보여 줘", "다음"],
        "detail_review_id": r["id"],
    }


# ---------- 4단계: 좋은 리뷰 일주일 (D-07) ----------
def step_positive() -> dict | None:
    s = STATE["strengths"]
    if s["positive_count"] < 3:
        return None
    top = s["items"][0]
    return {
        "headline": "국물 맛을 좋아하세요",
        "say": [
            {"text": f"이번 주 좋은 리뷰 {kor(s['positive_count']) if s['positive_count'] < 16 else s['positive_count']} 개를 봤어요.", "caption": f"이번 주 좋은 리뷰 {s['positive_count']}개를 봤어요.", "focus": []},
            {"text": f"{top['label']}이 진하다는 칭찬이 가장 많았어요.", "caption": "국물이 진하다는 칭찬이 많았어요.", "focus": [top["id"]]},
            {"text": s["keep_say"], "caption": "지금처럼 매일 아침 끓여 주세요.", "focus": ["tip_keep"]},
        ],
        "cards": [
            {"type": "bars", "id": "strengths", "unit": "번", "items": s["items"][:3]},
            {"type": "tip", "id": "tip_keep", "kind": "keep", "text": s["keep"]},
        ],
    }


# ---------- 5단계: 답글 예약과 이유 (D-08) ----------
def step_scheduling() -> dict | None:
    items = STATE["scheduled"]
    if not items:
        return None
    say = [{"text": "좋은 리뷰 답글은 가장 잘 보일 때 올리려고 예약해 뒀어요.", "caption": "가장 잘 보일 때 올릴게요.", "focus": []}]
    for it in items:
        say.append({"text": it["say"], "caption": it["caption"], "focus": [it["id"]]})
    cards = [{"type": "scheduled", "id": "scheduled_replies", "items": [
        {k: it[k] for k in ("id", "day_label", "time_label", "post_at", "reason", "text", "review_ids")} for it in items[:3]
    ]}]
    return {"headline": "답글은 예약해 뒀어요", "say": say, "cards": cards, "suggestions": ["화면에 보여 줘", "다음"], "detail_scheduled": True}


BUILDERS = {"schedule": step_schedule, "reviews": step_reviews, "negative": step_negative, "positive": step_positive, "scheduling": step_scheduling}


def build_step(index: int) -> dict | None:
    """index는 1 ~ 5. 건너뛰는 단계면 None."""
    key = STEPS[index - 1]
    body = BUILDERS[key]()
    if body is None:
        return None
    out = {
        "type": body.get("type", "answer"),
        "briefing": {"step": index, "total": len(STEPS), "step_key": key},
        "headline": body["headline"],
        "say": body["say"],
        "cards": body["cards"],
        "suggestions": body.get("suggestions", ["다시 말해 줘", "다음"]),
        "expects_reply": body.get("expects_reply", False),
    }
    for k in ("permission", "detail_review_id", "detail_scheduled"):
        if k in body:
            out[k] = body[k]
    return out


def next_step(after: int) -> dict | None:
    for i in range(after + 1, len(STEPS) + 1):
        s = build_step(i)
        if s:
            return s
    return None


def end() -> dict:
    rows = [{"id": "d_schedule", "kind": "done", "value": "오늘 일정"}]
    if waiting_reviews() or auto_replied():
        rows.append({"id": "d_reviews", "kind": "done", "value": "리뷰와 답글"})
    if STATE["scheduled"]:
        rows.append({"id": "d_replies", "kind": "done", "value": "답글 예약"})
    return {
        "type": "end",
        "briefing": {"step": len(STEPS), "total": len(STEPS), "step_key": "end"},
        "headline": "브리핑은 여기까지예요",
        "say": [{"text": "오늘 일정 브리핑은 여기까지예요.", "caption": "궁금한 건 언제든 물어보세요.", "focus": []},
                {"text": "궁금한 건 언제든 물어보세요.", "caption": None, "focus": []}],
        "cards": [{"type": "rows", "id": "checked", "rows": rows}],
        "suggestions": ["처음부터 다시", "리뷰 보여 줘"],
        "expects_reply": False,
    }


# ---------- 화면으로 보기 (D-09) ----------
def detail(step: dict) -> dict | None:
    by_id = {r["id"]: r for r in STATE["reviews"]}
    cards = []
    if step.get("detail_review_id"):
        r = by_id[step["detail_review_id"]]
        cards.append(_full(r))
        headline = "리뷰와 답글이에요"
    elif step.get("detail_scheduled"):
        for it in STATE["scheduled"]:
            for rid in it["review_ids"]:
                cards.append(_full(by_id[rid], scheduled_label=f"{it['day_label']}요일 {it['time_label']}에 올릴 답글"))
        headline = "예약한 답글이에요"
    else:
        return None
    return {
        "type": "show_detail",
        "briefing": step["briefing"],
        "headline": headline,
        "say": [{"text": "화면에 띄웠어요.", "caption": "화면에 띄웠어요.", "focus": []}],
        "cards": cards,
        "suggestions": ["읽어 줘", "돌아가기"],
        "expects_reply": False,
    }


def _full(r: dict, scheduled_label: str | None = None) -> dict:
    reply = None
    if r.get("reply_text"):
        reply = {"text": r["reply_text"], "posted_at": r.get("reply_posted_at"), "by": "donna", "scheduled_label": scheduled_label}
    return {"type": "review", "id": r["id"], "variant": "full", "rating": r["rating"], "text": r["text"], "written_at": r["written_at"], "reply": reply}


def read_detail(d: dict) -> list[dict]:
    say = []
    for c in d["cards"]:
        say.append({"text": f"리뷰예요. {c['text']}", "caption": "리뷰를 읽어 드릴게요.", "focus": [c["id"]]})
        if c.get("reply"):
            say.append({"text": f"답글이에요. {c['reply']['text']}", "caption": "답글을 읽어 드릴게요.", "focus": [c["id"]]})
    return say
