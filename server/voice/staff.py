"""알바생 할 일 (Figma v0.2.1 F-02 ~ F-09). 옛 목업 donna-voice/server/app/staff.py 를 저장소에 옮긴 것.

알바생은 앱을 깔지 않고 사장님이 보낸 초대 코드로 들어온다. 그날 할 일 화면을 처음 연 시각이 출근이다 (근무표는 받지 않는다).
할 일 종류
  매뉴얼  repeat=daily: 날마다 올라온다. 누른 기록은 그날만 센다
  오늘만  repeat=today: start_date ~ end_date 동안만
  교정    origin=review, must_confirm (2026-11-18 팀 개선안, 2026-11-20 긴급에서 내림): 아쉬운 리뷰에서 나온 일.
          넣은 날과 다음 날 "확인 필요"에 뜨고, 저마다 "확인"을 눌러야 내려간다. 퇴근은 막지 않는다.
  긴급    urgent=True: 오늘 안 하면 손님이 바로 겪는 일 (비 오는 날 이벤트 카드). 맨 위에 따로 뜨고,
          확인하지 않으면 퇴근하기가 막힌다.
  하지 말 것  kind=dont: "오늘은 장칼국수 주문 받지 마" (D-20)

저장은 voice/staff_db.py 의 알바생 표에 한다. 화면이 받는 모양(today, detail)은 표로 옮기기 전과 같다.

들어오기 (2026-11-18)
  1. 사장님이 "하린이 초대해 줘" → 랜덤 6자리 코드 (staff_orders.invite)
  2. 알바생이 코드를 넣고(check_code) 이름·아이디·비밀번호로 가입(signup) → 로그인 표시(토큰)를 받는다
  3. 그 뒤로는 요청마다 토큰을 보낸다 (X-Staff-Token). 다른 기기에서는 아이디·비밀번호로 다시 들어온다(login)
  4. 사장님이 "정우 내보내 줘" → 코드와 토큰을 지운다 (remove)
"""

import datetime as dt

from voice import clock, hours, notices, speech, staff_db
from voice.clock import iso, parse

PHASES = [("before_open", "오픈 전"), ("open", "영업 중"), ("closing", "마감")]
FRESH = dt.timedelta(minutes=5)
ORIGINS = ("manual", "owner", "review", "story_event", "field_variable")
# 도나가 넣은 일: origin → (목록 줄 아래 글, 자세히의 설명). 처음 확인하면 사장님께 알린다 (review_loop.on_staff_confirm)
FROM_DONNA = {"review": ("리뷰에서 나온 일", "도나가 리뷰를 보고 넣은 일"),
              "story_event": ("오늘 이벤트", "도나가 이벤트를 올리고 넣은 일"),
              "field_variable": ("오늘 날씨·예약", "도나가 오늘 날씨·예약을 보고 넣은 일")}
LOGIN_ID_MIN, PASSWORD_MIN = 3, 8
BAD_CODE = "코드가 맞지 않아요. 사장님에게 받은 코드를 확인해 주세요."


class StaffError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _now_iso() -> str:
    return iso(clock.now())


def _digits(code: str) -> str:
    return "".join(ch for ch in str(code) if ch.isdigit())


# ── 넣기 ──


def seed(store_id: str, payload: dict) -> None:
    """픽스처의 staff, invites, manual 을 넣는다 (가게 데이터를 새로 넣을 때).
    joined 인 사람은 이미 가입해 자기 휴대폰으로 쓰고 있는 알바생이다 (시연 데이터. 비밀번호가 없어 이 기기에서는 로그인하지 않는다)."""
    now = _now_iso()
    for person_ in payload.get("staff", []):
        joined = bool(person_.get("joined"))
        staff_db.add_member({
            "staff_id": person_["id"], "store_id": store_id, "name": person_["name"], "call": person_["call"],
            "login_id": person_.get("login_id"), "status": "joined" if joined else "listed",
            "signed_up_at": now if joined else None, "started_at": now if joined else None, "created_at": now,
        })
    for code, staff_id in payload.get("invites", {}).items():  # 미리 정한 코드 (시험용. 시연 데이터에는 없다)
        staff_db.update_member(staff_id, status="invited")
        staff_db.add_invite(code, store_id, staff_id, now)
    for item in payload.get("manual", []):
        add_task(store_id, item["title"], item["phase"], repeat="daily", sent_at=None, origin="manual")


def add_task(store_id: str, title: str, phase: str, *, repeat: str = "today", must_confirm: bool = False, urgent: bool = False,
             detail: str | None = None, source: dict | None = None, owner_words: str | None = None,
             sent_at: dt.datetime | None = None, days: int = 1, kind: str = "do", to: str = "all",
             origin: str | None = None) -> dict:
    """할 일 하나를 넣는다. 오늘만이면 오늘부터 days 일 동안 보인다.
    origin(누가 넣었나)은 넣는 쪽이 꼭 밝힌다: manual | owner | review | story_event | field_variable. 화면 문구와 확인 뒤 처리가 이것을 본다."""
    if origin not in ORIGINS:
        raise ValueError(f"할 일 origin 이 필요해요: {origin!r}")
    now = clock.now()
    task_id = f"tk_{store_id}_{_next_task_number(store_id):04d}"  # 표 키 task_id 는 가게를 가리지 않으므로 가게 id 를 넣는다
    staff_db.add_task({
        "task_id": task_id, "store_id": store_id, "title": title, "phase": phase, "repeat": repeat, "kind": kind,
        "must_confirm": must_confirm or urgent, "urgent": urgent, "to_staff": to,
        "origin": origin,
        "detail": detail, "owner_words": owner_words, "source": source,
        "start_date": now.date().isoformat(), "end_date": (now.date() + dt.timedelta(days=days - 1)).isoformat(),
        "sent_at": iso(sent_at if sent_at is not None else now) if repeat != "daily" or sent_at or owner_words else None,
        "created_at": iso(now),
    })
    return _task(task_id)


def _next_task_number(store_id: str) -> int:
    from voice import repo

    return repo.next_number(f"task:{store_id}")


# ── 읽기 ──


def _person_out(row: dict) -> dict:
    return {"id": row["staff_id"], "store_id": row["store_id"], "name": row["name"], "call": row["call"],
            "status": row["status"], "joined": row["status"] == "joined", "started": bool(row.get("started_at")),
            "login_id": row.get("login_id"), "signed_up_at": row.get("signed_up_at")}


def person(staff_id: str) -> dict:
    found = staff_db.member(staff_id)
    if not found:
        raise StaffError(404, "staff_not_found", "알바생을 찾지 못했어요.")
    return _person_out(found)


def people(store_id: str, *, include_removed: bool = False) -> list[dict]:
    return [_person_out(row) for row in staff_db.members(store_id) if include_removed or row["status"] != "removed"]


def joined_count(store_id: str) -> int:
    return sum(1 for p in people(store_id) if p["joined"])


def find_by_name(store_id: str, word: str) -> dict | None:
    """"하린", "하린이", "문하린" → 하린. 내보낸 사람은 찾지 않는다."""
    word = word.strip()
    if not word:
        return None
    candidates = [word, word[:-1] if len(word) > 1 and word.endswith("이") else word]
    for p in people(store_id):
        if p["call"] in candidates or p["name"] in candidates or any(len(c) >= 2 and p["name"].endswith(c) for c in candidates):
            return p
    return None


def similar_name(store_id: str, word: str) -> dict | None:
    """"하림" → 하린처럼 첫 글자가 같은 가입한 알바생."""
    word = word.strip().rstrip("이")
    return next((p for p in people(store_id) if p["joined"] and word and (p["call"].startswith(word[:1]) or word.startswith(p["call"][:1]))), None)


def _label(text: str) -> str:
    return speech.clock_label(parse(text))


def _task(task_id: str) -> dict:
    found = staff_db.task(task_id)
    if not found or found["canceled_at"]:
        raise StaffError(404, "task_not_found", "할 일을 찾지 못했어요.")
    return _shape(found)


def _shape(row: dict) -> dict:
    """표의 한 줄 → 이 파일과 jobs/review_loop.py 가 쓰는 모양."""
    return {"id": row["task_id"], "store_id": row["store_id"], "title": row["title"], "phase": row["phase"], "repeat": row["repeat"],
            "kind": row["kind"], "must_confirm": row["must_confirm"], "urgent": row["urgent"], "to": row["to_staff"],
            "origin": row["origin"], "detail": row["detail"], "owner_words": row["owner_words"], "source": row["source"],
            "date": row["start_date"], "until": row["end_date"], "sent_at": row["sent_at"], "canceled_at": row["canceled_at"],
            "canceled": bool(row["canceled_at"]), "created_at": row["created_at"]}


def store_tasks(store_id: str) -> list[dict]:
    return [_shape(row) for row in staff_db.tasks(store_id)]


def visible(task: dict, staff_id: str, day: dt.date) -> bool:
    if task["canceled"] or task["to"] not in ("all", "everyone", staff_id):
        return False
    return task["repeat"] == "daily" or task["date"] <= day.isoformat() <= task["until"]


def _marks(task_id: str) -> list[dict]:
    return staff_db.marks_of_task(task_id)


def _done_at(task: dict, staff_id: str, day: dt.date, marks: list[dict] | None = None) -> str | None:
    """이 알바생에게 '했음'으로 보일 시각. 매뉴얼은 그날 누른 것만, 오늘만 일은 누가 눌러도."""
    marks = _marks(task["id"]) if marks is None else marks
    if task["repeat"] == "daily":
        return next((m["done_at"] for m in marks if m["staff_id"] == staff_id and m["day"] == day.isoformat() and m["done_at"]), None)
    mine = next((m["done_at"] for m in marks if m["staff_id"] == staff_id and m["done_at"]), None)
    return mine or next((m["done_at"] for m in marks if m["done_at"]), None)


def _confirmed_at(task: dict, staff_id: str, day: dt.date, marks: list[dict] | None = None) -> str | None:
    marks = _marks(task["id"]) if marks is None else marks
    if task["repeat"] == "daily":
        return next((m["confirmed_at"] for m in marks if m["staff_id"] == staff_id and m["day"] == day.isoformat() and m["confirmed_at"]), None)
    return next((m["confirmed_at"] for m in marks if m["staff_id"] == staff_id and m["confirmed_at"]), None)


def finished_by(task: dict, day: dt.date) -> tuple[str, str] | None:
    """사장님이 묻는 "다 했대?"의 답: (누가, 언제). 꼭 확인할 일은 확인, 아니면 완료를 누른 사람 중 처음."""
    marks = _marks(task["id"])
    if task["repeat"] == "daily":
        marks = [m for m in marks if m["day"] == day.isoformat()]
    key = "confirmed_at" if task["must_confirm"] else "done_at"
    found = sorted((m[key], m["staff_id"]) for m in marks if m[key])
    return (found[0][1], found[0][0]) if found else None


def task_view(task: dict, staff_id: str, now: dt.datetime, marks: list[dict] | None = None) -> dict:
    day = now.date()
    marks = _marks(task["id"]) if marks is None else marks
    done = _done_at(task, staff_id, day, marks)
    confirmed = _confirmed_at(task, staff_id, day, marks)
    fresh = bool(task.get("sent_at")) and now - parse(task["sent_at"]) < FRESH
    if task["must_confirm"] and confirmed:
        sub = f"{_label(confirmed)}에 확인함"
    elif done:
        sub = f"{_label(done)}에 함"
    elif task["origin"] in FROM_DONNA:
        sub = FROM_DONNA[task["origin"]][0]
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
    found = hours.business_day(store, now)  # 자정 넘김 가게의 새벽은 어제 영업
    if found is None:
        return "closing"
    return "before_open" if now < hours.open_at(*found) else "open"


def unconfirmed_urgent(store_id: str, staff_id: str, now: dt.datetime) -> list[dict]:
    return [t for t in store_tasks(store_id)
            if t["urgent"] and visible(t, staff_id, now.date()) and not _confirmed_at(t, staff_id, now.date())]


def present_today(store_id: str, day: dt.date) -> list[dict]:
    """오늘 나온 사람 (그날 할 일 화면을 연 사람). [{person..., in_at, out_at}]"""
    found = []
    for row in staff_db.attendance_on(store_id, day.isoformat()):
        member = staff_db.member(row["staff_id"])
        if member and member["status"] == "joined":
            found.append({**_person_out(member), "in_at": row["in_at"], "out_at": row["out_at"]})
    return found


def today(staff_id: str) -> dict:
    """F-06, F-09. 이 화면을 여는 것이 출근이다."""
    from voice import repo

    me = person(staff_id)
    store_id = me["store_id"]
    store = repo.store(store_id)
    now = clock.now()
    key = now.date().isoformat()
    day = staff_db.check_in(staff_id, key, store_id, iso(now))
    marks: dict[str, list[dict]] = {}
    for mark in staff_db.marks_of_store(store_id):
        marks.setdefault(mark["task_id"], []).append(mark)
    mine = [t for t in store_tasks(store_id) if visible(t, staff_id, now.date())]
    urgent = sorted((t for t in mine if t["urgent"] and not _confirmed_at(t, staff_id, now.date(), marks.get(t["id"], []))),
                    key=lambda t: t["sent_at"] or "", reverse=True)
    phase = _phase_now(store, now)
    groups = []
    for phase_key, label in PHASES:
        tasks = [t for t in mine if t["phase"] == phase_key and t not in urgent]
        if not tasks:
            continue
        waiting = [t for t in tasks if t["must_confirm"] and not _confirmed_at(t, staff_id, now.date(), marks.get(t["id"], []))]
        must = [task_view(t, staff_id, now, marks.get(t["id"], [])) for t in waiting]
        rest = [task_view(t, staff_id, now, marks.get(t["id"], [])) for t in tasks if t not in waiting]
        rest.sort(key=lambda v: (v["done"], not v["fresh"]))
        groups.append({"phase": phase_key, "label": label, "now": phase_key == phase, "must": must, "tasks": rest})
    order = [k for k, _ in PHASES]
    past = [g["phase"] for g in groups if order.index(g["phase"]) < order.index(phase)]
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
        "urgent": [task_view(t, staff_id, now, marks.get(t["id"], [])) for t in urgent],
        "groups": groups,
    }


def detail(task_id: str, staff_id: str) -> dict:
    """F-08. 사장님이 한 말, 또는 도나가 리뷰·이벤트를 보고 넣은 일의 자세한 말."""
    task = _task(task_id)
    now = clock.now()
    view = task_view(task, staff_id, now)
    if task["origin"] in FROM_DONNA:
        return {**view, "tag": "긴급" if task["urgent"] else "확인 필요", "owner_words": task.get("detail"),
                "owner_words_label": FROM_DONNA[task["origin"]][1],
                "until": "내일까지 보여요" if task["until"] > now.date().isoformat() else "오늘만 보여요"}
    words = task.get("owner_words")
    return {**view, "tag": "오늘만" if task["repeat"] == "today" else "매일",
            "owner_words": f"“{words.replace('도나야,', '').strip()}”" if words else None,
            "owner_words_label": f"사장님이 {_label(task['sent_at'])}에 한 말" if words and task.get("sent_at") else None,
            "until": "내일은 원래대로 돌아가요" if task["repeat"] == "today" else None}


# ── 알바생이 들어오기 ──


def _usable_invite(code: str) -> dict:
    found = staff_db.invite(_digits(code))
    if not found or found["revoked_at"]:
        raise StaffError(400, "bad_code", BAD_CODE)
    if found["used_at"]:
        raise StaffError(400, "code_used", "이미 가입에 쓴 코드예요. 아이디와 비밀번호로 들어와 주세요.")
    member = staff_db.member(found["staff_id"])
    if not member or member["status"] == "removed":
        raise StaffError(400, "bad_code", BAD_CODE)
    return found


def _store_head(store_id: str) -> dict:
    from voice import repo

    store = repo.store(store_id) or {}
    return {"name": store.get("name", ""), "logo_url": store.get("logo_url")}


def check_code(code: str) -> dict:
    try:
        found = _usable_invite(code)
    except StaffError as error:
        return {"ok": False, "message": error.message}
    me = person(found["staff_id"])
    return {"ok": True, "store": _store_head(found["store_id"]), "staff_id": me["id"], "name": me["call"]}


def _signed_in(member: dict) -> dict:
    token = staff_db.add_session(member["staff_id"], member["store_id"], _now_iso())
    return {"token": token, "staff_id": member["staff_id"], "store": _store_head(member["store_id"]),
            "name": member["name"], "call": member["call"]}


def signup(code: str, name: str | None, login_id: str | None, password: str | None) -> dict:
    """F-03. 이름은 사장님이 부르는 이름(call)이 된다. 아이디는 겹치면 안 되고, 비밀번호는 해시로만 둔다."""
    found = _usable_invite(code)
    name = (name or "").strip()
    login_id = (login_id or "").strip()
    password = password or ""
    if not name:
        raise StaffError(400, "name_missing", "이름을 적어 주세요.")
    if len(login_id) < LOGIN_ID_MIN:
        raise StaffError(400, "login_id_short", f"아이디는 {LOGIN_ID_MIN}자 이상으로 정해 주세요.")
    if len(password) < PASSWORD_MIN:
        raise StaffError(400, "password_short", f"비밀번호는 {PASSWORD_MIN}자 이상으로 정해 주세요.")
    taken = staff_db.member_by_login(login_id)
    if taken and taken["staff_id"] != found["staff_id"]:
        raise StaffError(409, "login_id_taken", "이미 쓰는 아이디예요. 다른 아이디를 정해 주세요.")
    now = _now_iso()
    member = staff_db.update_member(found["staff_id"], call=name, login_id=login_id, password_hash=staff_db.hash_password(password),
                                    status="joined", signed_up_at=now)
    staff_db.update_invite(found["code"], used_at=now)
    return _signed_in(member)


def login(login_id: str | None, password: str | None) -> dict:
    """가입한 알바생이 다른 기기나 브라우저에서 다시 들어온다."""
    member = staff_db.member_by_login(login_id or "") if login_id else None
    if not member or member["status"] != "joined" or not staff_db.password_matches(password or "", member["password_hash"]):
        raise StaffError(401, "bad_login", "아이디나 비밀번호가 맞지 않아요.")
    return _signed_in(member)


def staff_for_token(token: str | None) -> str:
    """요청에 붙은 로그인 표시 → 알바생 번호. 없거나 끊겼으면 다시 들어오라고 한다."""
    found = staff_db.session(token) if token else None
    member = staff_db.member(found["staff_id"]) if found else None
    if not member or member["status"] != "joined":
        raise StaffError(401, "not_signed_in", "다시 들어와 주세요.")
    return member["staff_id"]


def issue_token(staff_id: str) -> str:
    """시험과 개발자 모드용: 가입한 알바생에게 로그인 표시를 바로 준다."""
    member = staff_db.member(staff_id)
    if not member or member["status"] != "joined":
        raise StaffError(404, "staff_not_found", "가입한 알바생이 아니에요.")
    return staff_db.add_session(staff_id, member["store_id"], _now_iso())


def start(staff_id: str) -> dict:
    """F-04 "시작": 사장님에게 '하린 씨가 알바생 화면에 들어왔어요' 알림 (D-05)."""
    me = person(staff_id)
    if not me["started"]:
        staff_db.update_member(staff_id, started_at=_now_iso())
        notices.push(me["store_id"], "staff_joined", f"{me['call']} 씨가 알바생 화면에 들어왔어요")
    return {"ok": True}


# ── 사장님이 하는 것 (voice/staff_orders.py 가 부른다) ──


def ensure_person(store_id: str, word: str) -> dict:
    """초대할 사람. 명단에 없으면 새로 만든다 (부르는 이름 = 들은 이름)."""
    found = find_by_name(store_id, word)
    if found:
        return found
    call = word.strip().rstrip("이") if len(word.strip()) > 2 and word.strip().endswith("이") else word.strip()
    from voice import repo

    staff_id = f"st_{store_id}_{repo.next_number(f'staff:{store_id}'):03d}"  # 표 키 staff_id 는 가게를 가리지 않으므로 가게 id 를 넣는다
    staff_db.add_member({"staff_id": staff_id, "store_id": store_id, "name": call, "call": call, "status": "listed", "created_at": _now_iso()})
    return person(staff_id)


def invite(store_id: str, staff_id: str) -> dict:
    """새 초대 코드. 예전에 받은 코드는 못 쓰게 된다."""
    code = staff_db.new_invite(store_id, staff_id, _now_iso())
    staff_db.update_member(staff_id, status="invited")
    return code


def share_invite(code: str) -> None:
    staff_db.update_invite(code, shared_at=_now_iso())


def remove(staff_id: str) -> dict:
    """그만둔 알바생: 코드와 로그인 표시를 지우고 내보낸다 (알레르기 같은 손님 정보가 할 일에 들어가므로)."""
    now = _now_iso()
    staff_db.revoke_invites(staff_id, now)
    staff_db.end_sessions(staff_id)
    staff_db.update_member(staff_id, status="removed", removed_at=now, login_id=None)
    return person(staff_id)


def cancel(task_id: str) -> dict:
    staff_db.cancel_task(task_id, _now_iso())
    return _shape(staff_db.task(task_id))


# ── 알바생이 누르는 것 ──


def mark_done(task_id: str, staff_id: str, undo: bool = False) -> dict:
    me = person(staff_id)
    task = _task(task_id)
    if undo:
        staff_db.clear_done(task_id, staff_id)
    else:
        staff_db.set_mark(task_id, staff_id, clock.now().date().isoformat(), me["store_id"], done_at=_now_iso())
    return {"ok": True}


def confirm(task_id: str, staff_id: str) -> dict:
    me = person(staff_id)
    task = _task(task_id)
    first = not any(m["confirmed_at"] for m in _marks(task_id))
    staff_db.set_mark(task_id, staff_id, clock.now().date().isoformat(), me["store_id"], confirmed_at=_now_iso())
    if task["origin"] in FROM_DONNA and first:  # 도나가 넣은 일은 처음 확인하면 사장님께 알린다
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
    staff_db.check_in(staff_id, key, me["store_id"], iso(now))
    staff_db.check_out(staff_id, key, iso(now))
    return {"ok": True}
