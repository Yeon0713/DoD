"""알바생 앱 API (Figma v0.2.1 F-02 ~ F-09).

알바생은 앱을 깔지 않고 주소(donna.app/s/choongjang)로 들어온다. 초대 코드 → 가입 → 할 일.
출근은 그날 처음 화면을 연 시각이다. 퇴근은 "퇴근하기"를 누른 시각이다 (퇴근하기 버튼은 디자인 쪽 제안, 미확정).
할 일은 사장님이 말로 보낸 것(requests.py)과 매뉴얼에서 온다. 상태는 사장님 쪽과 같은 STATE 를 쓴다.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Body, HTTPException

from .data import STATE, clock_label, date_label, hm, new_id, now

router = APIRouter(prefix="/v1/staff")

PHASES = [("before_open", "오픈 전"), ("open", "영업 중"), ("closing", "마감")]


def _staff(staff_id: str) -> dict:
    s = next((x for x in STATE["staff"] if x["id"] == staff_id), None)
    if not s:
        raise HTTPException(status_code=404, detail={"error": "staff_not_found"})
    return s


def _store() -> dict:
    s = STATE["store"]
    return {"name": s["name"], "logo_url": s["logo_url"]}


def _label(iso: str) -> str:
    return clock_label(dt.datetime.fromisoformat(iso))


def _phase_now() -> str:
    s = STATE["store"]
    t = now().timetz().replace(tzinfo=None)
    if t < hm(s["open_time"]):
        return "before_open"
    if t < hm(s["close_time"]):
        return "open"
    return "closing"


def _for(t: dict, sid: str) -> bool:
    return not t["canceled"] and t["kind"] != "rule" and t["to"] in ("all", "everyone", sid)


def _view(t: dict, sid: str) -> dict:
    mine_done = t["done"].get(sid)
    any_done = next(iter(t["done"].values()), None)
    confirmed = t["confirmed"].get(sid)
    sent = t.get("sent_at")
    fresh = bool(sent) and (now() - dt.datetime.fromisoformat(sent)) < dt.timedelta(minutes=5)
    if t["must_confirm"] and confirmed:
        sub = f"{_label(confirmed)}에 확인함"
    elif mine_done or (t["to"] != sid and any_done):
        sub = f"{_label(mine_done or any_done)}에 함"
    elif t["must_confirm"]:
        sub = "모두 확인해야 해요"
    else:
        sub = "오늘만" if t["repeat"] == "today" else "매일"
    return {
        "id": t["id"], "title": t["title"], "sub": sub, "fresh": fresh, "repeat": t["repeat"], "kind": t["kind"],
        "must_confirm": t["must_confirm"], "confirmed": bool(confirmed),
        "done": bool(mine_done or (t["to"] != sid and any_done) or (t["must_confirm"] and confirmed)), "has_words": bool(t.get("owner_words")),
    }


@router.post("/invite/check")
def check_code(body: dict = Body(...)) -> dict:
    code = "".join(ch for ch in str(body.get("code", "")) if ch.isdigit())
    sid = STATE["invites"].get(code)
    if not sid:
        return {"ok": False, "message": "코드가 맞지 않아요. 사장님에게 받은 코드를 확인해 주세요."}
    s = _staff(sid)
    return {"ok": True, "store": _store(), "staff_id": sid, "name": s["call"]}


@router.post("/signup")
def signup(body: dict = Body(...)) -> dict:
    code = "".join(ch for ch in str(body.get("code", "")) if ch.isdigit())
    sid = STATE["invites"].get(code)
    if not sid:
        raise HTTPException(status_code=400, detail={"error": "bad_code"})
    s = _staff(sid)
    name = (body.get("name") or s["call"]).strip()
    s["call"] = name
    s["login_id"] = body.get("login_id")
    return {"staff_id": sid, "store": _store(), "name": s["name"], "call": s["call"]}


@router.post("/start")
def start(body: dict = Body(...)) -> dict:
    """F-04 "시작": 사장님에게 '하린 씨가 알바생 화면에 들어왔어요' 알림 (D-05)."""
    s = _staff(body.get("staff_id", ""))
    if not s["joined"]:
        s["joined"] = True
        STATE["notices"].append({"id": new_id("nt"), "for": "owner", "kind": "staff_joined", "at": now().isoformat(),
                                 "text": f"{s['call']} 씨가 알바생 화면에 들어왔어요", "seen": False})
    return {"ok": True}


@router.get("/today")
def today(staff_id: str) -> dict:
    """F-06, F-09. 이 화면을 여는 것이 출근이다."""
    s = _staff(staff_id)
    if not s["in_at"]:
        s["in_at"] = now().isoformat()
    phase = _phase_now()
    mine = [t for t in STATE["tasks"] if _for(t, staff_id)]
    groups = []
    for key, label in PHASES:
        tasks = [t for t in mine if t["phase"] == key]
        if not tasks:
            continue
        must = [_view(t, staff_id) for t in tasks if t["must_confirm"] and not t["confirmed"].get(staff_id)]
        rest = [_view(t, staff_id) for t in tasks if not (t["must_confirm"] and not t["confirmed"].get(staff_id))]
        rest.sort(key=lambda v: (v["done"], not v["fresh"]))
        groups.append({"phase": key, "label": label, "now": key == phase, "must": must, "tasks": rest})
    order = [k for k, _ in PHASES]
    past = [g["phase"] for g in groups if order.index(g["phase"]) < order.index(phase)]
    return {
        "store": _store(),
        "date_label": date_label(now().date()),
        "staff": {"id": s["id"], "name": s["name"], "call": s["call"]},
        "attendance": {
            "state": "out" if s["out_at"] else "in",
            "label": "퇴근" if s["out_at"] else "출근",
            "detail": f"{_label(s['out_at'])}에 나갔어요" if s["out_at"] else f"{_label(s['in_at'])}에 왔어요",
        },
        "now_after": past[-1] if past else None,
        "groups": groups,
    }


@router.get("/tasks/{task_id}")
def task_detail(task_id: str, staff_id: str) -> dict:
    """F-08. 도나가 줄인 제목 아래에 사장님이 한 말을 그대로 붙인다."""
    t = next((x for x in STATE["tasks"] if x["id"] == task_id), None)
    if not t:
        raise HTTPException(status_code=404, detail={"error": "task_not_found"})
    v = _view(t, staff_id)
    words = t.get("owner_words")
    return {
        **v,
        "tag": "오늘만" if t["repeat"] == "today" else "매일",
        "owner_words": f"“{words.replace('도나야,', '').strip()}”" if words else None,
        "owner_words_label": f"사장님이 {_label(t['sent_at'])}에 한 말" if words and t.get("sent_at") else None,
        "until": "내일은 원래대로 돌아가요" if t["repeat"] == "today" else None,
    }


@router.post("/tasks/{task_id}/done")
def task_done(task_id: str, body: dict = Body(...)) -> dict:
    sid = body.get("staff_id", "")
    _staff(sid)
    t = next((x for x in STATE["tasks"] if x["id"] == task_id), None)
    if not t or t["canceled"]:
        raise HTTPException(status_code=404, detail={"error": "task_not_found"})
    if body.get("undo"):
        t["done"].pop(sid, None)
    else:
        t["done"][sid] = now().isoformat()
    return {"ok": True}


@router.post("/tasks/{task_id}/confirm")
def task_confirm(task_id: str, body: dict = Body(...)) -> dict:
    sid = body.get("staff_id", "")
    _staff(sid)
    t = next((x for x in STATE["tasks"] if x["id"] == task_id), None)
    if not t:
        raise HTTPException(status_code=404, detail={"error": "task_not_found"})
    t["confirmed"][sid] = now().isoformat()
    return {"ok": True}


@router.post("/checkout")
def checkout(body: dict = Body(...)) -> dict:
    s = _staff(body.get("staff_id", ""))
    s["out_at"] = now().isoformat()
    return {"ok": True}
