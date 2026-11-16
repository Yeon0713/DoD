"""도나 v0.2.1 백엔드 목업.

계약은 docs/v0.2.0-voice-agent-handoff.md (17장 v0.2.1 화면 포맷)를 따른다. 에이전트 대신 규칙과 고정 데이터로 답한다.
화면과 문장은 Figma `v0.2.1 : 디자인개선`의 하루 시나리오(D-01 ~ D-33)와 알바생 앱(F-01 ~ F-09)을 따른다.
주소: http://localhost:8100  (기존 서버 8000 과 겹치지 않는다)
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import briefing as br
from . import requests as rq
from .data import KST, STATE, WEEKDAYS, at, clock_label, date_label, log, new_id, now, reset
from .staff import router as staff_router

app = FastAPI(title="DONNA v0.2.1 mock backend", version="0.2.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8090", "http://127.0.0.1:8090"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parents[1] / "static"), name="static")
app.include_router(staff_router)


def _store(store_id: str | None) -> None:
    if store_id and store_id != STATE["store"]["id"]:
        raise HTTPException(status_code=404, detail={"error": "store_not_found"})


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "now": now().isoformat()}


# ---------- 홈 (D-07) ----------
@app.get("/v1/home")
def get_home(store_id: str | None = None) -> dict:
    _store(store_id)
    return br.home()


# ---------- 도나 알림 (D-05, D-23) ----------
@app.get("/v1/notices")
def get_notices(store_id: str | None = None) -> dict:
    """사장님 앱이 몇 초마다 본다. 아직 안 본 알림만 준다. 도나는 소리만 내고 말하지 않는다."""
    _store(store_id)
    fresh = [n for n in STATE["notices"] if n.get("for") == "owner" and not n.get("seen")]
    for n in fresh:
        n["seen"] = True
    return {"notices": [{"id": n["id"], "kind": n["kind"], "text": n["text"], "time_label": clock_label(dt.datetime.fromisoformat(n["at"]))} for n in fresh]}


# ---------- 말 한 번에 답 한 번 ----------
def _norm(text: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", (text or "").lower())


YES = ("응", "그래", "좋아", "네", "어그", "그렇게", "해줘", "맡길게", "부탁", "올려")
NO = ("아니", "됐어", "내가볼", "싫어", "하지마", "안돼", "나중")
DOMAIN = ("도나", "리뷰", "예약", "일정", "답글", "브리핑", "매출", "손님", "알바", "인스타", "매뉴얼")
# 부르는 말. 앱이 떼고 보내지만, 붙은 채로 와도 알아듣는다.
CALL = re.compile(r"^(도나[야아]?|돈아야?|또나야)")


def classify(text: str, event: str | None, sess: dict, addressed: bool = False) -> tuple[str, str | None]:
    """(intent, 다듬은 말). 규칙만 쓴다. 에이전트가 붙으면 이 함수가 F8(뜻 알아듣기)이 된다.

    addressed: "도나야"로 불러서 한 말. 이런 말은 모르더라도 ignore 하지 않는다.
    """
    if event == "auto_next":
        return "briefing.next", None
    t = _norm(text)
    if CALL.match(t):
        addressed = True
        t = CALL.sub("", t, count=1)
    if not t:
        return ("unknown", text) if addressed else ("not_for_donna", None)
    said = re.sub(r"^\s*(도나[야아]?|돈아야?|또나야)[\s,]*", "", text).strip()
    # 브리핑 안에서 도나가 물어본 것 (허락, 인스타에 올릴까요)
    ask = sess.get("awaiting")
    if ask == "permission":
        if any(t.startswith(w) or w in t for w in NO):
            return "permission.no", "아니, 내가 볼게"
        if any(t.startswith(w) or w in t for w in YES):
            return "permission.yes", "응, 그렇게 해"
    if ask == "instagram":
        if "다음사진" in t or ("다음" in t and "사진" in t):
            return "instagram.next_photo", "다음 사진"
        if "올려" in t or t in ("응", "그래", "좋아"):
            return "instagram.post", "올려"
        if "나중" in t or t.startswith("아니"):
            return "instagram.later", "나중에"
    # 브리핑 밖의 요청 (알바생, 예약, 매뉴얼, 인스타, 설정)
    req = rq.classify(t, said, sess)
    if req:
        return req, said
    if "그만" in t or t in ("홈", "홈으로", "처음화면", "처음으로"):
        return "stop", "그만"
    if "처음부터" in t:
        return "briefing.restart", "처음부터 다시"
    if ("다시" in t and ("말" in t or "들려" in t or "얘기" in t)) or "뭐라고" in t or "못들었" in t:
        return "briefing.repeat", "다시 말해 줘"
    if "돌아가" in t or (sess.get("detail") and "됐어" in t):
        return "detail.back", "돌아가기"
    if "읽어" in t:
        return "detail.read", "읽어 줘"
    if ("화면" in t and "보여" in t) or "자세히" in t:
        return "detail.show", "화면에 보여 줘"
    if "매출" in t or "얼마팔" in t:
        return "navigate.sales", "매출 보여 줘"
    if "달력" in t or "이번주" in t or "이번달" in t:
        return "navigate.week", "이번 주 일정 보여 줘"
    if "설정" in t:
        return "navigate.settings", "설정 보여 줘"
    if "리뷰" in t and any(w in t for w in ("어때", "보여", "알려", "있어")):
        return "briefing.jump.reviews", "리뷰 보여 줘"
    if "예약" in t and "답글" in t:
        return "briefing.jump.scheduling", "예약한 답글 알려 줘"
    if t in ("다음", "다음거", "다음꺼") or "넘어가" in t or t.startswith("다음") or "계속" in t:
        return "briefing.next", "다음"
    if re.search(r"[브부프]리핑|브리빙", t) or "오늘뭐있" in t or ("오늘" in t and "일정" in t):
        return "briefing.start", "오늘 일정 브리핑해 줘"
    if addressed or any(w in t for w in DOMAIN):
        return "unknown", text
    return "not_for_donna", None


def _session(session_id: str) -> dict:
    return STATE["sessions"].setdefault(session_id, {"idx": 0, "detail": None, "awaiting": None, "current": None, "pending": None, "slide": 1})


def _enter(sess: dict, step: dict) -> dict:
    sess["idx"] = step["index"]
    sess["current"] = step
    sess["detail"] = None
    sess["awaiting"] = "permission" if step["type"] == "ask_permission" else "instagram" if step.get("ask", {}).get("key") == "instagram_post" else None
    sess["slide"] = 1
    return dict(step)


def _empty(kind: str) -> dict:
    return {"type": kind, "briefing": None, "headline": None, "say": [], "cards": [], "expects_reply": False}


def _finish(sess: dict, posted: bool = False) -> dict:
    sess.update(idx=0, current=None, detail=None, awaiting=None)
    log("owner", "오늘 일정 브리핑을 들었어요", "o_heard")
    return br.end(posted)


def _next(sess: dict, prefix: list[dict] | None = None, caption: str | None = None) -> dict:
    nxt = br.next_step(sess["idx"]) if sess["idx"] else br.build_step(1)
    out = _enter(sess, nxt) if nxt else _finish(sess)
    if prefix:
        out["say"] = prefix + list(out["say"])
    if caption:
        out["say"] = [dict(out["say"][0], caption=caption)] + list(out["say"][1:])
    return out


def handle(intent: str, sess: dict, said: str | None) -> dict:
    cur = sess.get("current")
    if intent in ("briefing.start", "briefing.restart"):
        STATE["morning_done"] = [] if intent == "briefing.restart" else STATE["morning_done"]
        return _enter(sess, br.build_step(1))
    if intent == "briefing.next":
        if sess["awaiting"] and cur:
            return dict(cur)  # 물어본 것에 대답을 못 받았으면 다시 묻는다
        return _next(sess)
    if intent == "briefing.repeat":
        if not cur:
            return _empty("not_understood")
        out = dict(cur)
        out["headline"] = "다시 말씀드릴게요"
        out["say"] = [{"text": "다시 말씀드릴게요.", "caption": None, "focus": []}] + list(cur["say"])
        return out
    if intent.startswith("briefing.jump."):
        key = intent.rsplit(".", 1)[1]
        step = br.build_step(br.STEPS.index(key) + 1)
        if step:
            return _enter(sess, step)
        out = _empty("answer")
        out.update(headline="지금은 알려 드릴 게 없어요", say=[{"text": "지금은 알려 드릴 게 없어요.", "caption": None, "focus": []}])
        return out
    if intent == "detail.show":
        d = br.detail(cur) if cur else None
        if not d:
            if not cur:
                return _empty("not_understood")
            out = dict(cur)
            out["say"] = [{"text": "이 내용은 더 보여 드릴 게 없어요.", "caption": None, "focus": []}]
            return out
        sess["detail"] = d
        return dict(d)
    if intent == "detail.read":
        d = sess.get("detail")
        if not d:
            return _empty("not_understood")
        out = dict(d)
        out.update(type="answer", say=br.read_detail(d) or d["say"])
        return out
    if intent == "detail.back":
        if not cur:
            return _empty("not_understood")
        sess["detail"] = None
        out = dict(cur)
        out["say"] = [{"text": "브리핑으로 돌아왔어요.", "caption": None, "focus": []}]
        return out
    if intent in ("permission.yes", "permission.no"):
        yes = intent == "permission.yes"
        STATE["settings"]["negative_review_auto_reply"] = yes
        sess["awaiting"] = None
        log("owner", "아쉬운 리뷰는 도나가 바로 답하게 맡겼어요" if yes else "아쉬운 리뷰는 직접 보기로 했어요", "o_perm")
        if yes:
            r = br.post_reply_now()
            if r:
                br.morning("negative")
                step = {"index": sess["idx"], "type": "answer", "briefing": cur["briefing"] if cur else None, "expects_reply": False, **br.replied_answer(r)}
                sess["current"] = step
                out = dict(step)
                out["say"] = [{"text": "네, 앞으로는 제가 바로 답할게요.", "caption": None, "focus": []}] + list(out["say"])
                return out
            return _next(sess, [{"text": "네, 앞으로는 제가 바로 답할게요.", "caption": None, "focus": []}])
        return _next(sess, [{"text": "네, 아쉬운 리뷰는 제가 답하지 않고 알려만 드릴게요.", "caption": None, "focus": []}])
    if intent == "instagram.next_photo":
        sess["slide"] = sess.get("slide", 1) % STATE["instagram"]["slides"] + 1
        d = br.insta_preview(sess["slide"])
        sess["detail"] = d
        return d
    if intent == "instagram.post":
        br.post_instagram()
        log("owner", "인스타에 인기 메뉴를 올렸어요", "o_insta")
        return _finish(sess, posted=True)
    if intent == "instagram.later":
        out = _finish(sess)
        out["say"] = [{"text": "내일 브리핑에서 다시 여쭤볼게요.", "caption": None, "focus": []}] + list(out["say"])
        return out
    if intent == "stop":
        sess.update(idx=0, current=None, detail=None, awaiting=None, pending=None)
        return _empty("stop")
    if intent.startswith("navigate."):
        tab = intent.split(".", 1)[1]
        out = _empty("navigate")
        out["tab"] = tab
        text = {"sales": get_sales()["say"], "week": get_week()["say"], "settings": "설정을 열었어요."}[tab]
        out["say"] = [{"text": text, "caption": None, "focus": []}]
        return out
    if intent == "unknown":
        return _empty("not_understood")
    if intent == "not_for_donna":
        return _empty("ignore")
    # 브리핑 밖의 요청
    out = rq.handle(intent, said or "", sess)
    if out.get("continue_briefing"):
        return _next(sess, [out["prefix"]], out["caption"])
    return out


@app.post("/v1/turn")
def post_turn(body: dict = Body(...)) -> dict:
    _store(body.get("store_id"))
    rid = body.get("request_id")
    if rid and rid in STATE["requests"]:
        return STATE["requests"][rid]  # 같은 요청이 다시 오면 같은 응답 (통신이 끊겨 다시 보낸 경우)
    sess = _session(body.get("session_id") or "default")
    utt = body.get("utterance") or {}
    intent, canon = classify(utt.get("text", ""), body.get("event"), sess, bool(utt.get("addressed")))
    out = handle(intent, sess, canon)
    STATE["turn_seq"] += 1
    said = rq.short_said(canon or "") if utt and intent not in ("pending.yes", "pending.no") else None
    resp = {"turn_id": f"t_{STATE['turn_seq']:04d}", "intent": intent, "owner_said": (said or canon) if utt else None}
    resp.update({k: v for k, v in out.items() if k not in ("detail_scheduled", "index", "focus_rest", "continue_briefing")})
    if rid:
        STATE["requests"][rid] = resp
    return resp


# ---------- 인스타 연결 (D-01, D-02) ----------
@app.post("/v1/instagram/connect")
def instagram_connect(body: dict = Body(default={})) -> dict:
    """인스타 화면에서 "허용"을 누르고 돌아왔을 때 (목업: 바로 연결됨)."""
    STATE["instagram"]["connected"] = True
    return {"connected": True, "say": "인스타를 연결했어요. 다음엔 메뉴 사진을 확인해 주세요."}


# ---------- 설정 ----------
@app.get("/v1/settings")
def get_settings(store_id: str | None = None) -> dict:
    _store(store_id)
    s = STATE["store"]
    return {
        "negative_review_auto_reply": STATE["settings"]["negative_review_auto_reply"],
        "store": {"id": s["id"], "name": s["name"]},
        "open_time_label": clock_label(dt.time(*map(int, s["open_time"].split(":")))),
        "close_time_label": clock_label(dt.time(*map(int, s["close_time"].split(":")))),
        "briefing_time_label": "오전 9시",
        "platforms": [
            {"key": "naver", "name": "네이버 플레이스", "connected": True},
            {"key": "baemin", "name": "배달의민족", "connected": True},
            {"key": "instagram", "name": "인스타그램", "connected": STATE["instagram"]["connected"]},
        ],
    }


@app.patch("/v1/settings")
def patch_settings(body: dict = Body(...)) -> dict:
    _store(body.get("store_id"))
    if "negative_review_auto_reply" in body:
        v = body["negative_review_auto_reply"]
        if v not in (None, True, False):
            raise HTTPException(status_code=400, detail={"error": "bad_value"})
        STATE["settings"]["negative_review_auto_reply"] = v
    return get_settings()


# ---------- 일정 (v0.2.0 화면이 Figma에 없어 새로 정한 것) ----------
# 일정 탭은 "바쁠 것 같다"는 추측을 보여 주지 않는다. 사장님은 자기 가게가 언제 바쁜지 이미 안다.
# 보여 주는 것은 날짜와 시각이 있는 사실(잡힌 일)과, 그래서 준비할 것 한 줄이다.
# 단체 예약은 있다는 사실만 알린다. 자리 배치 같은 매장 준비는 도나가 말하지 않는다 (2026-11-16 결정).
PLAN_LABEL = {"event": "행사", "game": "경기", "group_reservation": "단체 예약", "weather": "비"}

# 이번 주(월 ~ 일)에 잡힌 일과 준비할 것 (목업). (종류, 내용, 달력 칸에 적을 짧은 이름, 시, 분) 시가 None이면 하루 종일.
# 짧은 이름은 태블릿 달력 칸(폭 80 안팎)에 들어가게 한글 다섯 자 안팎으로 적는다.
WEEK_PLAN: dict[int, tuple[list[tuple], str | None]] = {
    0: ([], None),
    1: ([("group_reservation", "단체 손님 열두 분", "단체 12명", 12, 0), ("weather", "오후 2시부터 비", "비", 14, 0)], None),
    2: ([], None),
    3: ([("weather", "하루 종일 비", "비", None, 0)], None),
    4: ([], None),
    5: ([], None),
    6: ([], None),
}
# 이번 주 밖의 날 (목업). 월요일에서 며칠 뒤인지로 적는다.
LATER_PLAN: dict[int, tuple[list[tuple], str | None]] = {
    9: ([("group_reservation", "단체 손님 열 분", "단체 10명", 12, 0)], None),
}


def _josa(word: str, with_final: str, without_final: str) -> str:
    """받침이 있으면 with_final, 없으면 without_final (예약이 / 경기가)."""
    code = ord(word[-1]) - 0xAC00
    return with_final if 0 <= code <= 11171 and code % 28 else without_final


def _day_title(plans: list[dict], past: bool) -> str:
    """그날의 큰 한마디. 추측이 아니라 잡힌 일을 그대로 말한다."""
    labels = []
    for p in plans:
        if p["kind"] != "weather" and p["label"] not in labels:
            labels.append(p["label"])
    # 큰 한마디는 휴대폰에서도 한 줄이어야 한다. 종류가 둘 이상이면 이름을 늘어놓지 않는다 (아래 목록에 나온다).
    if len(labels) > 1:
        return "일이 여러 가지였어요" if past else "일이 여러 가지 있어요"
    if labels:
        return f"{labels[0]}{_josa(labels[0], '이', '가')} {'있었어요' if past else '있어요'}"
    if plans:
        return "비가 왔어요" if past else "비가 와요"
    return "잡힌 일이 없었어요" if past else "잡힌 일이 없어요"


def _remaining_today() -> list[dict]:
    """아직 남은 것: 못 들은 브리핑, 답을 기다리는 아쉬운 리뷰, 오늘 이 시각 뒤의 일정."""
    today = now().date()
    out = []
    if not any(a["id"] == "o_heard" for a in STATE["activity"]):
        out.append({"id": "r_brief", "kind": "briefing", "text": "오늘 일정 브리핑 듣기", "time_label": None})
    neg = [r for r in br.waiting_reviews() if r["sentiment"] == "negative"]
    if neg and STATE["settings"]["negative_review_auto_reply"] is not True:
        out.append({"id": "r_neg", "kind": "reviews", "text": f"아쉬운 리뷰 {len(neg)}개에 답글 달기", "time_label": None})
    upcoming = [("event", e["name"], e["starts_at"]) for e in STATE["events"]]
    upcoming += [("game", g["name"], g["starts_at"]) for g in STATE["games"]]
    upcoming += [("group_reservation", f"단체 손님 {br.kor(r['party_size'])} 분", r["starts_at"]) for r in STATE["reservations"] if r["kind"] == "group"]
    for kind, text, iso in sorted(upcoming, key=lambda x: x[2]):
        t = dt.datetime.fromisoformat(iso)
        if t.date() == today and t > now():
            out.append({"id": f"r_{kind}_{t.hour}{t.minute}", "kind": kind, "text": text, "time_label": br.time_label(iso)})
    return out


def _past_done(d: dt.date, yesterday: dt.date) -> list[dict]:
    """지난 날에 한 일 (목업). 어제는 저장된 기록을, 그 전은 날짜로 만든 고정 값을 쓴다."""
    if d == yesterday:
        return STATE["past"][0]["items"]
    n = d.day
    items = [{"id": f"p{n}_read", "actor": "donna", "text": f"리뷰 {3 + n % 5}개를 읽고 나눴어요"}]
    posted = (n * 7) % 4
    if posted:
        items.append({"id": f"p{n}_post", "actor": "donna", "text": f"답글 {posted}개를 올렸어요"})
    if d.weekday() != 6:
        items.append({"id": f"p{n}_heard", "actor": "owner", "text": "오늘 일정 브리핑을 들었어요"})
    return items


@app.get("/v1/week")
def get_week(store_id: str | None = None) -> dict:
    """이번 주 탭. 달력(이번 주, 이번 달)과 날짜마다의 상황을 준다.

    지난 날: 잡혔던 일, 그날 한 일 / 오늘: 한 것, 남은 것 / 앞으로: 잡힌 일, 준비할 것, 그날 올릴 답글
    """
    _store(store_id)
    today = now().date()
    monday = today - dt.timedelta(days=today.weekday())
    yesterday = today - dt.timedelta(days=1)
    first = today.replace(day=1)
    grid_start = first - dt.timedelta(days=first.weekday())
    weather = {w["date"]: w for w in STATE["weather"]}
    sched_by_day: dict[str, list[dict]] = {}
    for it in STATE["scheduled"]:
        key = dt.datetime.fromisoformat(it["post_at"]).date().isoformat()
        sched_by_day.setdefault(key, []).append({k: it[k] for k in ("id", "day_label", "time_label", "post_at", "reason", "text")})

    days = []
    for i in range(42):  # 달력 6주
        d = grid_start + dt.timedelta(days=i)
        offset = (d - monday).days
        raw, tip = WEEK_PLAN[offset] if 0 <= offset < 7 else LATER_PLAN.get(offset, ([], None))
        past = d < today
        plans = []
        for n, (kind, text, short, hour, minute) in enumerate(raw):
            starts = None if hour is None else dt.datetime(d.year, d.month, d.day, hour, minute, tzinfo=KST).isoformat()
            plans.append({"id": f"pl_{d.isoformat()}_{n}", "kind": kind, "label": PLAN_LABEL[kind], "text": text, "short": short,
                          "starts_at": starts, "time_label": br.time_label(starts) if starts else None})
        w = weather.get(d.isoformat())
        scheduled = sched_by_day.get(d.isoformat(), [])
        marks = []
        if plans:
            marks.append("plan")
        if scheduled:
            marks.append("reply")
        days.append({
            "date": d.isoformat(), "weekday_label": WEEKDAYS[d.weekday()], "day": d.day, "date_label": date_label(d),
            "in_month": d.month == today.month, "is_today": d == today, "is_past": past,
            "marks": marks,
            "title": _day_title(plans, past),
            "weather": {"label": w["label"], "temp_min": w["temp_min"], "temp_max": w["temp_max"]} if w else None,
            # 그날 잡힌 일: 행사, 경기, 단체 예약, 비. 지난 날에도 준다.
            "plans": plans,
            "tip": None if past else tip,
            "scheduled": scheduled,
            "done": _past_done(d, yesterday) if past else (
                [{"id": a["id"], "actor": a["actor"], "text": a["text"], "time_label": br.time_label(a["at"])}
                 for a in sorted(STATE["activity"], key=lambda a: a["at"])] if d == today else []),
            "remaining": _remaining_today() if d == today else [],
        })
    week_dates = [(monday + dt.timedelta(days=k)).isoformat() for k in range(7)]
    planned = [x["weekday_label"] for x in days if x["date"] in week_dates and x["plans"] and not x["is_past"]]
    say = f"이번 주는 {', '.join(planned)}요일에 일이 잡혀 있어요." if planned else "이번 주는 잡힌 일이 없어요."
    return {
        "week_label": f"{monday.month}월 {monday.day}일 ~ {(monday + dt.timedelta(days=6)).day}일",
        "month_label": f"{today.month}월",
        "today": today.isoformat(),
        "week_dates": week_dates,
        "days": days,
        "say": say,
        "scheduled": [{k: it[k] for k in ("id", "day_label", "time_label", "post_at", "reason", "text")} for it in STATE["scheduled"]],
        "past": STATE["past"],
    }


# ---------- 매출 (v0.2.0 화면이 Figma에 없어 새로 정한 것) ----------
def _won(n: int) -> str:
    """1,284,000 → 128만 원. 사장님이 한눈에 읽는 단위."""
    man = round(n / 10000)
    return f"{man:,}만 원"


@app.get("/v1/sales")
def get_sales(store_id: str | None = None) -> dict:
    _store(store_id)
    today = now().date()
    opened = now().hour >= 10
    week = [1284000, 0, 0, 0, 0, 0, 0]          # 이번 주 (월 ~ 일). 오늘(화) 이후는 아직 없음
    last_week = [1142000, 1196000, 1088000, 1251000, 1873000, 2146000, 1522000]
    today_so_far = 418000 if opened else 0
    week[today.weekday()] = today_so_far
    y = today.weekday() - 1
    diff = week[y] - last_week[y]
    primary = {
        "label": "어제",
        "amount": week[y], "amount_label": _won(week[y]),
        "compare_label": f"지난주 {WEEKDAYS[y]}요일",
        "compare_amount_label": _won(last_week[y]),
        "direction": "up" if diff >= 0 else "down",
        "compare_text": f"지난주 {WEEKDAYS[y]}요일보다 {_won(abs(diff))} {'많아요' if diff >= 0 else '적어요'}",
    }
    if opened:
        same = 372000
        d2 = today_so_far - same
        primary = {
            "label": "오늘 지금까지",
            "amount": today_so_far, "amount_label": _won(today_so_far),
            "compare_label": f"지난주 {WEEKDAYS[today.weekday()]}요일 이맘때",
            "compare_amount_label": _won(same),
            "direction": "up" if d2 >= 0 else "down",
            "compare_text": f"지난주 이맘때보다 {_won(abs(d2))} {'많아요' if d2 >= 0 else '적어요'}",
        }
    bars = []
    for i in range(7):
        d = today - dt.timedelta(days=today.weekday() - i)
        bars.append({
            "weekday_label": WEEKDAYS[i], "date": d.isoformat(),
            "amount": week[i], "amount_label": _won(week[i]) if week[i] else None,
            "last_week_amount": last_week[i], "last_week_label": _won(last_week[i]),
            "is_today": d == today, "is_future": d > today,
        })
    this_total = sum(week)
    last_total = sum(last_week[: today.weekday() + (1 if opened else 0)])
    wdiff = this_total - last_total
    headline = f"{primary['label']} {primary['amount_label']} 팔았어요" if primary["amount"] else "아직 문 열기 전이에요"
    return {
        "headline": headline,
        "say": f"{primary['label']} {primary['amount_label']} 팔았어요. {primary['compare_text']}.",
        "primary": primary,
        "week": {"bars": bars, "max_amount": max(last_week + week),
                 "total_label": _won(this_total),
                 "compare_text": f"지난주 이맘때보다 {_won(abs(wdiff))} {'많아요' if wdiff >= 0 else '적어요'}",
                 "direction": "up" if wdiff >= 0 else "down"},
        "top_menus": {"label": "어제 잘 팔린 메뉴", "unit": "개", "items": [
            {"id": "m_1", "label": "들깨옹심이메밀칼국수", "count": 38},
            {"id": "m_2", "label": "멸치옹심이메밀칼국수", "count": 27},
            {"id": "m_3", "label": "들깨옹심이", "count": 21},
        ]},
    }


# ---------- 개발용 (사장님 화면에는 없다) ----------
@app.post("/v1/dev/reviews")
def dev_review(body: dict = Body(...)) -> dict:
    rid = f"rv_{500 + len(STATE['reviews']):04d}"
    rating = int(body.get("rating", 5))
    negative = rating <= 3
    written = body.get("written_at") or now().isoformat()
    r = {
        "id": rid, "platform": body.get("platform", "naver"), "rating": rating,
        "order_channel": body.get("order_channel", "hall"), "text": body.get("text", ""), "written_at": written,
        "sentiment": "negative" if negative else "positive", "topic": body.get("topic", "other"),
        "summary": body.get("summary") or (body.get("text", "")[:15]),
        "reply_status": "none", "reply_text": None, "reply_summary": None, "reply_posted_at": None, "replied_in_minutes": None,
    }
    # 허락을 받았으면 아쉬운 리뷰에 바로 답한다 (목업: 12분 뒤에 올린 것으로 적는다). 앱에는 아무것도 알리지 않는다.
    if negative and STATE["settings"]["negative_review_auto_reply"] is True:
        posted = dt.datetime.fromisoformat(written) + dt.timedelta(minutes=12)
        r.update(reply_status="posted", reply_text="불편을 드려 죄송합니다. 말씀해 주신 부분을 바로 살펴보겠습니다.",
                 reply_summary="사과하고, 바로 살펴보겠다고 답했어요", reply_posted_at=posted.isoformat(), replied_in_minutes=12)
    STATE["reviews"].insert(0, r)
    return {"review_id": rid}


@app.post("/v1/dev/fixtures")
def dev_fixtures(body: dict = Body(default={})) -> dict:
    reset(body.get("scenario", "first_day"))
    return {"ok": True, "scenario": body.get("scenario", "first_day")}


@app.post("/v1/dev/clock")
def dev_clock(body: dict = Body(...)) -> dict:
    STATE["now"] = dt.datetime.fromisoformat(body["now"]).astimezone(KST)
    return {"now": now().isoformat()}


@app.post("/v1/dev/run")
def dev_run(body: dict = Body(default={})) -> dict:
    return {"ok": True, "job": body.get("job"), "note": "목업은 요청이 올 때마다 브리핑을 새로 만든다"}


@app.post("/v1/dev/reset")
def dev_reset() -> dict:
    reset("first_day")
    return {"ok": True}


@app.get("/v1/dev/state")
def dev_state() -> dict:
    return {
        "now": now().isoformat(),
        "settings": STATE["settings"],
        "reviews": STATE["reviews"],
        "sessions": {k: {"idx": v["idx"], "awaiting": v["awaiting"], "pending": (v.get("pending") or {}).get("kind")} for k, v in STATE["sessions"].items()},
        "tasks": STATE["tasks"],
        "staff": STATE["staff"],
        "instagram": STATE["instagram"],
        "reservations": STATE["reservations"],
    }


@app.post("/v1/dev/story")
def dev_story(body: dict = Body(default={})) -> dict:
    """손님이 스토리에 매장을 태그함 (D-21). 서비스 드리기는 사장님이 보기 전에 알바생 화면에 먼저 올라간다."""
    handle_ = body.get("handle", "namyang_foodie")
    STATE["instagram"]["story_mentions"].append({"handle": handle_, "at": now().isoformat()})
    tk = {"id": new_id("tk"), "title": "스토리 손님께 서비스 드리기", "short": "스토리 손님 서비스", "phase": "open", "repeat": "today",
          "must_confirm": False, "kind": "do", "sent_at": now().isoformat(), "owner_words": None, "to": "all",
          "done": {}, "confirmed": {}, "canceled": False, "note": "인스타 스토리에 매장을 태그한 손님"}
    STATE["tasks"].append(tk)
    STATE["notices"].append({"id": new_id("nt"), "for": "owner", "kind": "story", "at": now().isoformat(), "seen": False,
                             "text": "손님이 스토리에 올려 주셨어요"})
    return {"ok": True, "task_id": tk["id"]}


@app.post("/v1/dev/unconfirmed")
def dev_unconfirmed(body: dict = Body(default={})) -> dict:
    """"확인 필요"를 30분이 지나도 안 누른 사람 알림 (D-23)."""
    t = next((x for x in reversed(STATE["tasks"]) if x["must_confirm"] and not x["canceled"]), None)
    if not t:
        return {"ok": False}
    for s in STATE["staff"]:
        if s["joined"] and s["in_at"] and s["id"] not in t["confirmed"]:
            STATE["notices"].append({"id": new_id("nt"), "for": "owner", "kind": "unconfirmed", "at": now().isoformat(), "seen": False,
                                     "text": f"{s['call']} 씨가 {t['short'].replace(' 확인', '')} 안내를 안 봤어요"})
            return {"ok": True, "staff_id": s["id"]}
    return {"ok": False}


_ = at  # 목업 데이터에서 쓰는 도우미를 다시 내보낸다
