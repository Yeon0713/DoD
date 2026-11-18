"""알바생 할 일 (Figma v0.2.1 F-02 ~ F-09). 옛 목업 donna-voice/server/app/staff.py 를 저장소에 옮긴 것.

알바생은 앱을 깔지 않고 사장님이 보낸 초대 코드로 들어온다. 그날 할 일 화면을 처음 연 시각이 출근이다 (근무표는 받지 않는다).
할 일 종류
  매뉴얼  repeat=daily: 날마다 올라온다. 누른 기록은 그날만 센다
  오늘만  repeat=today: date 하루만
  교정    urgent=True (2026-11-18 팀 개선안): 아쉬운 리뷰에서 나온 일. 넣은 날과 다음 날 맨 위에 따로 뜨고,
          저마다 "확인"을 눌러야 내려간다. 확인하지 않으면 퇴근하기가 막힌다.
저장소 종류: staff (id = 알바생 id), invite (id = 코드), task (id = tk_0001 …). 알바생 id 는 가게마다 따로 두지 않았다 (시연 가게 하나).
"""

import datetime as dt

from voice import clock, hours, notices, repo, speech
from voice.clock import iso, parse

PHASES = [("before_open", "오픈 전"), ("open", "영업 중"), ("closing", "마감")]
FRESH = dt.timedelta(minutes=5)


class StaffError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


# ── 넣기 ──


def seed(store_id: str, payload: dict) -> None:
    """픽스처의 staff, invites, manual 을 넣는다 (가게 데이터를 새로 넣을 때)."""
    for person in payload.get("staff", []):
        repo.put("staff", person["id"], store_id, {**person, "store_id": store_id, "days": {}})
    for code, staff_id in payload.get("invites", {}).items():
        repo.put("invite", code, store_id, {"code": code, "store_id": store_id, "staff_id": staff_id})
    for item in payload.get("manual", []):
        add_task(store_id, item["title"], item["phase"], repeat="daily", sent_at=None)


def add_task(store_id: str, title: str, phase: str, *, repeat: str = "today", must_confirm: bool = False, urgent: bool = False,
             detail: str | None = None, source: dict | None = None, owner_words: str | None = None,
             sent_at: dt.datetime | None = None, days: int = 1) -> dict:
    """할 일 하나를 넣는다. 오늘만이면 오늘부터 days 일 동안 보인다."""
    now = clock.now()
    task_id = f"tk_{repo.next_number(f'task:{store_id}'):04d}"
    return repo.put("task", task_id, store_id, {
        "id": task_id, "store_id": store_id, "title": title, "phase": phase, "repeat": repeat, "kind": "do",
        "must_confirm": must_confirm or urgent, "urgent": urgent, "detail": detail, "source": source, "owner_words": owner_words,
        "date": now.date().isoformat(), "until": (now.date() + dt.timedelta(days=days - 1)).isoformat(),
        "sent_at": iso(sent_at if sent_at is not None else now) if repeat != "daily" or sent_at else None,
        "to": "all", "done": {}, "confirmed": {}, "canceled": False,
    })


# ── 읽기 ──


def person(staff_id: str) -> dict:
    found = repo.get("staff", staff_id)
    if not found:
        raise StaffError(404, "staff_not_found", "알바생을 찾지 못했어요.")
    return found


def joined_count(store_id: str) -> int:
    return sum(1 for s in repo.all_of("staff", store_id) if s.get("joined"))


def _label(text: str) -> str:
    return speech.clock_label(parse(text))


def _today_of(text: str | None, day: dt.date) -> bool:
    return bool(text) and parse(text).date() == day


def visible(task: dict, staff_id: str, day: dt.date) -> bool:
    if task["canceled"] or task["to"] not in ("all", staff_id):
        return False
    return task["repeat"] == "daily" or task["date"] <= day.isoformat() <= task["until"]


def _done_at(task: dict, staff_id: str, day: dt.date) -> str | None:
    """이 알바생에게 '했음'으로 보일 시각. 매뉴얼은 그날 누른 것만, 오늘만 일은 누가 눌러도."""
    marks = task["done"]
    mine = marks.get(staff_id)
    if task["repeat"] == "daily":
        return mine if _today_of(mine, day) else None
    return mine or next(iter(marks.values()), None)


def _confirmed_at(task: dict, staff_id: str, day: dt.date) -> str | None:
    at = task["confirmed"].get(staff_id)
    if task["repeat"] == "daily":
        return at if _today_of(at, day) else None
    return at


def task_view(task: dict, staff_id: str, now: dt.datetime) -> dict:
    day = now.date()
    done = _done_at(task, staff_id, day)
    confirmed = _confirmed_at(task, staff_id, day)
    fresh = bool(task.get("sent_at")) and now - parse(task["sent_at"]) < FRESH
    if task["must_confirm"] and confirmed:
        sub = f"{_label(confirmed)}에 확인함"
    elif done:
        sub = f"{_label(done)}에 함"
    elif task["urgent"]:
        sub = "리뷰에서 나온 일"
    elif task["must_confirm"]:
        sub = "모두 확인해야 해요"
    else:
        sub = "오늘만" if task["repeat"] == "today" else "매일"
    return {
        "id": task["id"], "title": task["title"], "sub": sub, "fresh": fresh, "repeat": task["repeat"], "kind": task["kind"],
        "must_confirm": task["must_confirm"], "confirmed": bool(confirmed), "done": bool(done or (task["must_confirm"] and confirmed)),
        "has_words": bool(task.get("owner_words") or task.get("detail")), "urgent": task["urgent"], "detail": task.get("detail"),
    }


def _phase_now(store: dict, now: dt.datetime) -> str:
    today = hours.on(store, now.date())
    if today is None:
        return "closing"
    t = now.strftime("%H:%M")
    if t < today["open"]:
        return "before_open"
    return "open" if t < today["close"] else "closing"


def unconfirmed_urgent(store_id: str, staff_id: str, now: dt.datetime) -> list[dict]:
    return [t for t in repo.all_of("task", store_id)
            if t["urgent"] and visible(t, staff_id, now.date()) and not t["confirmed"].get(staff_id)]


def today(staff_id: str) -> dict:
    """F-06, F-09. 이 화면을 여는 것이 출근이다."""
    me = person(staff_id)
    store_id = me["store_id"]
    store = repo.store(store_id)
    now = clock.now()
    key = now.date().isoformat()
    days = dict(me.get("days") or {})
    if key not in days:
        days[key] = {"in_at": iso(now), "out_at": None}
        me = repo.put("staff", staff_id, store_id, {**me, "days": days})
    mine = [t for t in repo.all_of("task", store_id) if visible(t, staff_id, now.date())]
    urgent = sorted((t for t in mine if t["urgent"] and not t["confirmed"].get(staff_id)), key=lambda t: t["sent_at"] or "", reverse=True)
    phase = _phase_now(store, now)
    groups = []
    for phase_key, label in PHASES:
        tasks = [t for t in mine if t["phase"] == phase_key and t not in urgent]
        if not tasks:
            continue
        must = [task_view(t, staff_id, now) for t in tasks if t["must_confirm"] and not _confirmed_at(t, staff_id, now.date())]
        rest = [task_view(t, staff_id, now) for t in tasks if not (t["must_confirm"] and not _confirmed_at(t, staff_id, now.date()))]
        rest.sort(key=lambda v: (v["done"], not v["fresh"]))
        groups.append({"phase": phase_key, "label": label, "now": phase_key == phase, "must": must, "tasks": rest})
    order = [k for k, _ in PHASES]
    past = [g["phase"] for g in groups if order.index(g["phase"]) < order.index(phase)]
    day = days[key]
    return {
        "store": {"name": store["name"], "logo_url": store.get("logo_url")},
        "date_label": f"{now.month}월 {now.day}일 {speech.weekday(now.date())}요일",
        "staff": {"id": me["id"], "name": me["name"], "call": me["call"]},
        "attendance": {
            "state": "out" if day["out_at"] else "in",
            "label": "퇴근" if day["out_at"] else "출근",
            "detail": f"{_label(day['out_at'])}에 나갔어요" if day["out_at"] else f"{_label(day['in_at'])}에 왔어요",
        },
        "now_after": past[-1] if past else None,
        "urgent": [task_view(t, staff_id, now) for t in urgent],
        "groups": groups,
    }


def detail(task_id: str, staff_id: str) -> dict:
    """F-08. 사장님이 한 말, 또는 도나가 리뷰를 보고 넣은 일의 자세한 말."""
    task = _task(task_id)
    now = clock.now()
    view = task_view(task, staff_id, now)
    if task["urgent"]:
        return {**view, "tag": "긴급", "owner_words": task.get("detail"), "owner_words_label": "도나가 리뷰를 보고 넣은 일",
                "until": "내일까지 맨 위에 보여요"}
    words = task.get("owner_words")
    return {**view, "tag": "오늘만" if task["repeat"] == "today" else "매일",
            "owner_words": f"“{words.replace('도나야,', '').strip()}”" if words else None,
            "owner_words_label": f"사장님이 {_label(task['sent_at'])}에 한 말" if words and task.get("sent_at") else None,
            "until": "내일은 원래대로 돌아가요" if task["repeat"] == "today" else None}


def _task(task_id: str) -> dict:
    task = repo.get("task", task_id)
    if not task or task["canceled"]:
        raise StaffError(404, "task_not_found", "할 일을 찾지 못했어요.")
    return task


# ── 알바생이 누르는 것 ──


def check_code(code: str) -> dict:
    invite = repo.get("invite", "".join(ch for ch in str(code) if ch.isdigit()))
    if not invite:
        return {"ok": False, "message": "코드가 맞지 않아요. 사장님에게 받은 코드를 확인해 주세요."}
    me = person(invite["staff_id"])
    store = repo.store(invite["store_id"])
    return {"ok": True, "store": {"name": store["name"], "logo_url": store.get("logo_url")}, "staff_id": me["id"], "name": me["call"]}


def signup(code: str, name: str | None, login_id: str | None) -> dict:
    invite = repo.get("invite", "".join(ch for ch in str(code) if ch.isdigit()))
    if not invite:
        raise StaffError(400, "bad_code", "코드가 맞지 않아요. 사장님에게 받은 코드를 확인해 주세요.")
    me = person(invite["staff_id"])
    me = repo.put("staff", me["id"], me["store_id"], {**me, "call": (name or me["call"]).strip(), "login_id": login_id})
    store = repo.store(me["store_id"])
    return {"staff_id": me["id"], "store": {"name": store["name"], "logo_url": store.get("logo_url")}, "name": me["name"], "call": me["call"]}


def start(staff_id: str) -> dict:
    """F-04 "시작": 사장님에게 '하린 씨가 알바생 화면에 들어왔어요' 알림 (D-05)."""
    me = person(staff_id)
    if not me.get("joined"):
        repo.put("staff", staff_id, me["store_id"], {**me, "joined": True})
        notices.push(me["store_id"], "staff_joined", f"{me['call']} 씨가 알바생 화면에 들어왔어요")
    return {"ok": True}


def mark_done(task_id: str, staff_id: str, undo: bool = False) -> dict:
    person(staff_id)
    task = _task(task_id)
    done = dict(task["done"])
    if undo:
        done.pop(staff_id, None)
    else:
        done[staff_id] = iso(clock.now())
    repo.put("task", task_id, task["store_id"], {**task, "done": done})
    return {"ok": True}


def confirm(task_id: str, staff_id: str) -> dict:
    me = person(staff_id)
    task = _task(task_id)
    first = not task["confirmed"]
    task = repo.put("task", task_id, task["store_id"], {**task, "confirmed": {**task["confirmed"], staff_id: iso(clock.now())}})
    if task["urgent"] and first:
        from voice.jobs import review_loop

        review_loop.on_staff_confirm(task, me)
    return {"ok": True}


def checkout(staff_id: str) -> dict:
    me = person(staff_id)
    now = clock.now()
    left = unconfirmed_urgent(me["store_id"], staff_id, now)
    if left:
        raise StaffError(409, "urgent_unconfirmed", f"{left[0]['title']}{'을' if speech.has_batchim(left[0]['title']) else '를'} 먼저 확인해 주세요.")
    key = now.date().isoformat()
    days = dict(me.get("days") or {})
    days[key] = {**(days.get(key) or {"in_at": iso(now)}), "out_at": iso(now)}
    repo.put("staff", staff_id, me["store_id"], {**me, "days": days})
    return {"ok": True}
