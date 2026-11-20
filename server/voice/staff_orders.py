"""사장님이 말로 알바생 일을 시키기 (2026-11-18). 뜻(staff.*)은 dialog/intent_rules.py 가 가르고, 여기서 답을 만든다.

회의 결정 (donna-voice/docs/operating-scenarios.md 2-3장)
  - 받는 사람: 이름이 없으면 오늘 나온 사람 모두(all), "모두"면 알바생 모두(everyone), "하린이한테"면 그 사람
  - 보내기 전에 한 번 읽어 주고 "맞아요?" (D-17). "응"이면 알바생 할 일 화면에 올라간다 (5초 안에 보임)
  - 오늘만 / 매일(매뉴얼) / 하지 말 것 (D-20)
  - "시킨 거 다 했대?" → 한 것과 안 한 것 (D-24). "그거 취소해" → 알바생 화면에서 지운다. 이미 했으면 그대로 둔다 (D-33)
  - 초대는 한 사람용 랜덤 6자리 코드 (D-04). 그만둔 사람은 사장님이 끊는다
  - 매뉴얼은 매장 공통 (옛 목업과 같은 세 묶음, D-06)

묻고 기다리는 것은 session["staff_pending"] 에 둔다. 그 뒤의 "응"/"아니"는 staff.yes / staff.no 로 온다 (turn.py, last_type ask_staff).
  send          할 일 보내기 확인          pick     없는 이름 → 비슷한 사람에게 보낼까요?
  invite_for    안 들어온 사람 → 초대할까요?  invite_share  초대 코드 → 카카오톡으로 보낼까요?
  remove        내보낼까요?
"""

import copy
import re
import threading
import time

from voice import activity, clock, repo, speech, staff, staff_db, width
from voice.jobs.briefing import answer, say

KEEP = "ask_staff"
# 사장님 앱이 둘 열려 있으면(시연 화면 + 다른 탭) 개발자 모드에서 보낸 말을 둘 다 듣고 각자 요청한다.
# 다른 대화(session)에서 같은 일이 이 시간 안에 또 오면 새로 하지 않고 앞의 답을 그대로 준다 (할 일·초대 코드가 두 개 생기지 않게).
# 같은 대화에서 다시 말한 것은 사장님이 정말 한 번 더 시킨 것이라 그대로 한다.
DUPLICATE_SECONDS = 10
_recent: dict[tuple, tuple[float, str, dict, dict | None]] = {}
_recent_lock = threading.Lock()
EVERYONE_WORDS = {"모두", "전부", "전원", "다", "다들", "모든사람", "다섯명", "다섯명모두"}
PRESENT_WORDS = {"알바생", "알바생들", "알바", "알바들", "직원", "직원들", "애들", "사람", "사람들", "나온사람", "오늘나온사람"}
NOT_STAFF_WORDS = {"손님", "손님들", "고객", "고객님", "어르신", "아이", "아이들", "단체"}  # "손님한테 음료 드리라고 해"는 받는 사람이 아니다
WHO_RE = re.compile(r"(?:^|\s)([가-힣]{1,5}?)(?:이)?\s*(?:한테|에게)(?=\s|$)")
ORDER_RE = re.compile(r"^(.*?)(지\s*말라고|으라고|라고)(?!.*라고)")
REASON_RE = re.compile(r"^.*?(?:니까|니깐|으니|라서)\s+")
LEAD_RE = re.compile(r"^(?:오늘은?|오늘만|앞으로는?|이제부터|매일|맨날|항상|늘|내일은?|지금|꼭|반드시|좀|그리고)\s+")
PHASE_RE = [
    (re.compile(r"마감|문\s*닫을|닫을\s*때|닫기\s*전"), "closing"),
    (re.compile(r"오픈\s*전|문\s*열기\s*전|열기\s*전|영업\s*전|장사\s*전"), "before_open"),
]
PHASE_LEAD_RE = re.compile(r"^(?:마감\s*때(?:는|에)?|마감할\s*때|문\s*닫을\s*때|닫기\s*전에?|오픈\s*전에?|문\s*열기\s*전에?|영업\s*전에?|영업\s*중에?)\s*")
DAILY_RE = re.compile(r"앞으로|매일|맨날|항상|매뉴얼|이제부터")
TODAY_RE = re.compile(r"오늘은|오늘만|오늘\s*하루|오늘까지|지금만|이번만|하루만")  # "오늘 들어온 감자가"는 이유라 빼고 본다
MUST_RE = re.compile(r"꼭|반드시|알레르기|확인\s*받")
PHASE_LABEL = {"before_open": "영업 준비", "open": "영업 중", "closing": "마감"}
DIGITS = "공일이삼사오육칠팔구"




# ── 말에서 뽑기 ──


def _clean(text: str) -> str:
    return re.sub(r"^\s*도나야[,\s]*", "", text or "").strip()


def _who_match(text: str) -> re.Match | None:
    m = WHO_RE.search(text)
    return None if m is None or m.group(1) in NOT_STAFF_WORDS else m


def recipient(text: str) -> tuple[str, str | None]:
    """('all' | 'everyone' | 'name', 들은 이름). 이름이 없으면 오늘 나온 사람 모두, "모두"면 알바생 모두."""
    t = _clean(text)
    m = _who_match(t)
    word = m.group(1) if m else None
    if word in EVERYONE_WORDS or (re.search(r"(?:^|\s)(모두|전원)(?:\s|$)", t) and (word is None or word in PRESENT_WORDS)):
        return "everyone", None
    if word is None or word in PRESENT_WORDS:
        return "all", None
    return "name", word


def parse_order(text: str, slots: dict | None = None) -> dict | None:
    """사장님 말 → {title, kind, repeat, phase, must_confirm, who, name, owner_words}. 할 일을 못 뽑으면 None."""
    t = _clean(text)
    who, name = recipient(t)
    if slots and slots.get("staff_name"):
        word = slots["staff_name"].strip()
        who, name = ("everyone", None) if word in EVERYONE_WORDS else ("all", None) if word in PRESENT_WORDS else ("name", word)
    body = t
    m = _who_match(body)
    if m:
        body = body[m.end():].strip()
    found = ORDER_RE.match(body)
    title, kind = None, "do"
    if found:
        core, ending = found.group(1).strip(), found.group(2)
        core = REASON_RE.sub("", core)
        for _ in range(3):
            core = PHASE_LEAD_RE.sub("", LEAD_RE.sub("", core)).strip()
        if core:
            kind = "dont" if "말라고" in ending else "do"
            title = f"{core.rstrip()}지 않기" if kind == "dont" else f"{core}기"
    if slots and slots.get("task_title"):
        title = slots["task_title"].strip()
        kind = slots.get("task_kind") or kind
    if not title:
        return None
    repeat = "daily" if DAILY_RE.search(t) else "today"
    # 사장님이 "오늘"이나 "매일·앞으로"를 말했는지. 말하지 않았으면 도나가 "오늘만 할까요, 매일 할까요?"라고 묻는다
    said_when = bool(DAILY_RE.search(t) or TODAY_RE.search(t))
    if slots and slots.get("task_repeat") in ("today", "daily"):
        repeat = slots["task_repeat"]
    phase = next((p for pattern, p in PHASE_RE if pattern.search(t)), "open")
    return {"title": title, "kind": kind, "repeat": repeat, "phase": phase, "must_confirm": bool(MUST_RE.search(t)),
            "who": who, "name": name, "owner_words": t, "said_when": said_when}


def name_in(text: str, slots: dict | None = None) -> str | None:
    """"하린이 초대해 줘", "정우 내보내 줘" 의 이름."""
    if slots and slots.get("staff_name"):
        return slots["staff_name"].strip()
    t = _clean(text)
    m = re.search(r"([가-힣]{1,5}?)(?:이)?\s*(?:를|을|씨|씨를|씨는)?\s*(?:초대|내보내|그만|잘라|초대를|초대는)", t)
    if not m:
        return None
    word = m.group(1)
    return None if word in EVERYONE_WORDS | PRESENT_WORDS | {"새", "새로", "알바생", "새알바"} else word


# ── 말하기 도우미 ──


def _quoted_obj(title: str) -> str:
    return f"'{title}'{'을' if speech.has_batchim(title) else '를'}"


def _to_label(store_id: str, to: str) -> str:
    if to == "all":
        return "오늘 나온 사람 모두"
    if to == "everyone":
        return f"알바생 {speech.count(staff.joined_count(store_id), '명')} 모두"
    return f"{staff.person(to)['call']} 씨"


def _to_short(store_id: str, to: str) -> str:
    return "모두" if to in ("all", "everyone") else f"{staff.person(to)['call']} 씨"


def _ask(session: dict, pending: dict, headline: str, says: list[dict], cards: list[dict] | None = None, **extra) -> dict:
    session["staff_pending"] = pending
    return {**answer(width.fit("headline", headline, "맞아요?"), says, cards or [], "ask", expects_reply=True, **extra), "keep_context": KEEP}


def _done(session: dict, headline: str, says: list[dict], cards: list[dict] | None = None, **extra) -> dict:
    session.pop("staff_pending", None)
    return answer(width.fit("headline", headline, "알겠어요"), says, cards or [], **extra)


def _spoken_code(code: str) -> str:
    spoken = "".join(DIGITS[int(ch)] for ch in code)
    return f"{spoken[:3]}, {spoken[3:]}{'예요' if code[-1] in '2459' else '이에요'}"


def _when(at: str) -> str:
    return speech.clock_label(clock.parse(at))


def _people_card(store_id: str, title: str, only_present: bool = False) -> dict:
    today = clock.now().date()
    here = {p["id"]: p for p in staff.present_today(store_id, today)}
    items = []
    for p in staff.people(store_id):
        if p["id"] in here:
            sub = f"{_when(here[p['id']]['in_at'])}에 들어옴"
        elif only_present:
            continue
        elif p["joined"]:
            sub = "오늘 아직 안 나옴"
        else:
            sub = "초대만 받음" if p["status"] == "invited" else "아직 초대 안 함"
        items.append({"id": p["id"], "name": p["name"], "sub": sub})
    return {"type": "people", "id": "staff", "title": title, "items": items}


def forget_recent() -> None:
    """처음부터 다시 할 때 (api/dev.load_fixtures)."""
    with _recent_lock:
        _recent.clear()


def _once(key: tuple, session: dict, make) -> dict:
    """한 번만 할 일(할 일 보내기, 초대 코드, 카톡 보내기, 취소, 내보내기)을 다른 앱이 방금 했으면 그 답을 그대로 준다.
    묻고 있던 것(staff_pending)도 앞의 앱과 같게 맞춘다 (그 뒤의 "응"도 한 번만 처리되게)."""
    me = session.get("id", "")
    now = time.monotonic()
    with _recent_lock:
        for old in [k for k, v in _recent.items() if now - v[0] > DUPLICATE_SECONDS]:
            del _recent[old]
        found = _recent.get(key)
        if found and found[1] != me:
            if found[3] is not None:
                session["staff_pending"] = copy.deepcopy(found[3])
            else:
                session.pop("staff_pending", None)
            return copy.deepcopy(found[2])
    response = make()
    with _recent_lock:
        _recent[key] = (now, me, copy.deepcopy(response), copy.deepcopy(session.get("staff_pending")))
    return response


# ── 뜻마다 ──


def handle(view, intent, session: dict) -> dict:
    name = intent.name.split(".", 1)[1]
    store_id = view.store_id
    if name in ("yes", "no"):
        return _answer_pending(store_id, session, name == "yes")
    if name == "daily":  # "오늘만 할까요, 매일 할까요?" 에 "매일"
        return _answer_pending(store_id, session, True, daily=True)
    session.pop("staff_pending", None)  # 다른 말을 했으면 묻던 것은 접는다
    return {
        "order": lambda: order(store_id, session, intent),
        "status": lambda: status(store_id),
        "cancel": lambda: cancel(store_id, session, intent.owner_said),
        "invite": lambda: invite_by_name(store_id, session, name_in(intent.owner_said, intent.slots)),
        "remove": lambda: remove(store_id, session, name_in(intent.owner_said, intent.slots)),
        "share": lambda: share(store_id, session, None),
        "list": lambda: staff_list(store_id, intent.owner_said),
        "manual": lambda: manual(store_id),
    }[name]()


def order(store_id: str, session: dict, intent) -> dict:
    found = parse_order(intent.owner_said, intent.slots)
    if found is None:
        return _done(session, "무엇을 시킬까요?", [say("무엇을 시킬지 다시 말해 주세요."), say("'하린이한테 테이블 닦으라고 해'처럼요.")])
    if found["who"] in ("all", "everyone"):
        return confirm_send(store_id, session, found, found["who"])
    person = staff.find_by_name(store_id, found["name"])
    if person is None:
        near = staff.similar_name(store_id, found["name"])
        heard = found["name"].rstrip("이") if len(found["name"]) > 2 else found["name"]
        if near:
            return _ask(session, {"kind": "pick", "order": found, "to": near["id"]}, f"{heard} 씨는 없어요",
                        [say(f"{heard} 씨는 없어요."), say(f"비슷한 이름은 {near['call']} 씨예요."),
                         say(f"{near['call']} 씨에게 보낼까요?", f"{near['call']} 씨에게 보낼까요?")],
                        [_people_card(store_id, "알바생")])
        return _done(session, f"{heard} 씨는 없어요", [say(f"{heard} 씨는 알바생 명단에 없어요.")], [_people_card(store_id, "알바생")])
    if not person["joined"]:
        return _ask(session, {"kind": "invite_for", "staff_id": person["id"]}, f"{person['call']} 씨는 아직이에요",
                    [say(f"{person['call']} 씨는 아직 알바생 화면에 안 들어왔어요."),
                     say("들어와야 할 일을 볼 수 있어요.", "들어와야 할 일을 볼 수 있어요."), say("초대할까요?")])
    return confirm_send(store_id, session, found, person["id"])


def confirm_send(store_id: str, session: dict, found: dict, to: str) -> dict:
    """보내기 전에 읽어 주고 묻는다 (D-17, D-19, D-20)."""
    to_label = _to_label(store_id, to)
    title = found["title"]
    rows = [{"id": "cf_to", "kind": "person", "value": to_label},
            {"id": "cf_task", "kind": "ban" if found["kind"] == "dont" else "warning" if found["must_confirm"] else "task", "value": title},
            {"id": "cf_when", "kind": "time", "value": "매일" if found["repeat"] == "daily" else "오늘만"}]
    card = {"type": "rows", "id": "confirm", "rows": rows}
    if found["repeat"] == "daily":
        says = [say(f"매뉴얼 {PHASE_LABEL[found['phase']]}에 {_quoted_obj(title)} 넣을까요?", None, ["cf_task"])]
        if found["must_confirm"]:
            says.append(say("모두 확인을 받게 할게요."))
        headline = "매뉴얼에 넣을까요?"
    elif not found.get("said_when", True):
        # 오늘만인지 매일인지 사장님이 말하지 않았다: 정해 버리지 않고 묻는다 ("오늘만" / "매일")
        says = [say(f"{to_label}에게 {_quoted_obj(title)} 보낼게요.", None, ["cf_task"]),
                say("오늘만 할까요, 매일 할까요?", "오늘만 할까요, 매일 할까요?", ["cf_when"])]
        headline = "오늘만 할까요, 매일 할까요?"
    else:
        says = [say(f"{to_label}에게 오늘 하루만 {_quoted_obj(title)} 보낼까요?", None, ["cf_task", "cf_when"])]
        if found["kind"] == "dont":
            says.append(say("내일은 원래대로 돌아가요.", "내일은 원래대로 돌아가요."))
        headline = "오늘만 보낼까요?"
    return _ask(session, {"kind": "send", "order": found, "to": to}, headline, says, [card])


def send(store_id: str, session: dict, found: dict, to: str) -> dict:
    return _once(("send", store_id, found["title"], to, found["repeat"]), session, lambda: _send(store_id, session, found, to))


def _send(store_id: str, session: dict, found: dict, to: str) -> dict:
    task = staff.add_task(store_id, found["title"], found["phase"], repeat=found["repeat"], must_confirm=found["must_confirm"],
                          owner_words=found["owner_words"], kind=found["kind"], to=to, origin="owner", sent_at=clock.now())
    session["staff_last_sent"] = task["id"]
    to_label = _to_label(store_id, to)
    activity.log(store_id, "owner", f"{to_label}에게 {_quoted_obj(found['title'])} 보냈어요", f"staff:{task['id']}")
    card = {"type": "checklist", "id": "sent", "title": "알바생에게 시킨 것",
            "items": [{"id": task["id"], "title": task["title"], "sub": f"{_to_short(store_id, to)}에게 보냄", "state": "todo"}]}
    head = "매뉴얼에 넣었어요" if found["repeat"] == "daily" else "보냈어요"
    return _done(session, head, [say(f"{to_label}에게 보냈어요." if found["repeat"] != "daily" else "매뉴얼에 넣었어요."),
                                 say("알바생 화면에 바로 떠요.", "알바생 화면에 바로 떠요.")], [card])


NOT_UNDERSTOOD = {"type": "not_understood", "headline": None, "say": [], "cards": [], "expects_reply": False}


def _answer_pending(store_id: str, session: dict, yes: bool, daily: bool = False) -> dict:
    pending = session.get("staff_pending")
    if not pending:
        return dict(NOT_UNDERSTOOD)
    kind = pending["kind"]
    if daily and kind in ("send", "pick"):  # 매일 → 매뉴얼에 넣는다
        pending = {**pending, "order": {**pending["order"], "repeat": "daily", "said_when": True}}
    if not yes:
        session.pop("staff_pending", None)
        line = {"send": "안 보냈어요.", "pick": "안 보냈어요.", "invite_for": "초대하지 않았어요.",
                "invite_share": "나중에 보내 주세요. 코드는 그대로예요.", "remove": "그대로 뒀어요."}[kind]
        return _done(session, line.rstrip("."), [say(line)])
    if kind in ("send", "pick"):
        if kind == "pick":
            return confirm_send(store_id, session, pending["order"], pending["to"])
        return send(store_id, session, pending["order"], pending["to"])
    if kind == "invite_for":
        return invite_person(store_id, session, staff.person(pending["staff_id"]))
    if kind == "invite_share":
        return share(store_id, session, pending["code"])
    if kind == "remove":
        return _once(("remove", store_id, pending["staff_id"]), session, lambda: _remove_now(store_id, session, pending["staff_id"]))
    return dict(NOT_UNDERSTOOD)


def _remove_now(store_id: str, session: dict, staff_id: str) -> dict:
    person = staff.remove(staff_id)
    activity.log(store_id, "owner", f"{person['call']} 씨를 알바생 화면에서 내보냈어요", f"staff_remove:{person['id']}")
    return _done(session, "내보냈어요", [say(f"{person['call']} 씨를 내보냈어요."),
                                      say("이제 알바생 화면에 못 들어와요.", "이제 알바생 화면에 못 들어와요.")])


# ── 시킨 일 확인하기, 취소하기 ──


def _sent_today(store_id: str) -> list[dict]:
    """오늘 보이는, 사장님이 시킨 일과 교정 카드, 이벤트 카드 (매뉴얼은 빼고). 오래된 것부터."""
    today = clock.now().date().isoformat()
    return [t for t in staff.store_tasks(store_id)
            if not t["canceled"] and t["origin"] in ("owner", "review", "story_event", "field_variable") and t["repeat"] == "today" and t["date"] <= today <= t["until"]]


def status(store_id: str) -> dict:
    """D-24 "시킨 거 다 했대?"."""
    today = clock.now().date()
    tasks = _sent_today(store_id)
    if not tasks:
        return answer("오늘 시킨 일이 없어요", [say("오늘 알바생에게 시킨 일은 없어요.")], [])
    left, done = [], []
    for t in tasks:
        finished = staff.finished_by(t, today)
        (done if finished else left).append((t, finished))
    items = []
    for t, _ in left:
        items.append({"id": t["id"], "title": t["title"], "sub": f"{_to_short(store_id, t['to'])}에게 보냄", "state": "todo",
                      **({"tone": "urgent"} if t["urgent"] else {})})
    for t, (staff_id, at) in done:
        word = "확인함" if t["must_confirm"] else "함"
        items.append({"id": t["id"], "title": t["title"], "sub": f"{staff.person(staff_id)['call']} 씨가 {_when(at)}에 {word}", "state": "done"})
    card = {"type": "checklist", "id": "sent", "title": "알바생에게 시킨 것", "items": items}
    if not left:
        return answer("다 했어요", [say("시킨 건 다 했어요.")], [card])
    if len(left) == 1:
        head, first = f"{left[0][0]['title']}만 남았어요", f"'{left[0][0]['title']}'만 남았어요."
    else:
        head, first = "아직 안 한 게 있어요", f"아직 안 한 게 {speech.count(len(left), '개')} 있어요."
    says = [say(first)]
    if done:
        names = ", ".join(t["title"] for t, _ in done[:2])
        says.append(say(f"{speech.josa(names, '은', '는')} 했어요."))
    return answer(width.fit("headline", head, "아직 안 한 게 있어요"), says, [card])


def _words(text: str) -> list[str]:
    stop = {"그거", "그것", "아까", "방금", "시킨", "보낸", "거", "것", "일", "취소", "취소해", "취소해줘", "해줘", "해", "좀", "없던", "걸로", "지워줘", "도나야"}
    return [w for w in re.findall(r"[가-힣]{2,}", text) if w not in stop and not w.startswith("취소")]


def cancel(store_id: str, session: dict, text: str) -> dict:
    """D-33 "그거 취소해". 말한 낱말이 들어간 오늘 일, 없으면 방금 보낸 일. (두 앱이 같이 들어도 하나만 취소한다)"""
    return _once(("cancel", store_id, re.sub(r"\s+", "", _clean(text))), session, lambda: _cancel(store_id, session, text))


def _cancel(store_id: str, session: dict, text: str) -> dict:
    tasks = [t for t in _sent_today(store_id) if t["origin"] == "owner"]
    words = _words(_clean(text))
    target = None
    if words:
        target = next((t for t in reversed(tasks) if any(w.rstrip("은는이가을를") in t["title"] for w in words)), None)
    if target is None:
        last = session.get("staff_last_sent")
        target = next((t for t in tasks if t["id"] == last), None) or (tasks[-1] if tasks else None)
    if target is None:
        return answer("취소할 게 없어요", [say("오늘 보낸 일 중에 취소할 게 없어요.")], [])
    finished = staff.finished_by(target, clock.now().date())
    if finished:
        who = staff.person(finished[0])["call"]
        return answer("벌써 했어요", [say(f"{who} 씨가 벌써 했어요."), say("취소하지 않았어요.")], [])
    staff.cancel(target["id"])
    activity.log(store_id, "owner", f"{_quoted_obj(target['title'])} 취소했어요", f"staff_cancel:{target['id']}")
    card = {"type": "checklist", "id": "canceled", "title": "알바생에게 시킨 것",
            "items": [{"id": target["id"], "title": target["title"], "sub": f"{_when(clock.iso(clock.now()))}에 취소함", "state": "canceled"}]}
    return answer("취소했어요", [say(f"{_quoted_obj(target['title'])} 취소했어요."),
                                say("알바생 화면에서 지웠어요.", "알바생 화면에서 지웠어요.")], [card])


# ── 초대, 내보내기 ──


def invite_by_name(store_id: str, session: dict, word: str | None) -> dict:
    if not word:
        return _done(session, "누구를 초대할까요?", [say("누구를 초대할지 이름을 말해 주세요."), say("'하린이 초대해 줘'처럼요.")])
    person = staff.ensure_person(store_id, word)
    if person["joined"]:
        return _done(session, f"{person['call']} 씨는 들어와 있어요", [say(f"{person['call']} 씨는 벌써 알바생 화면에 들어와 있어요.")])
    return invite_person(store_id, session, person)


def invite_person(store_id: str, session: dict, person: dict) -> dict:
    """D-04. 새 코드를 만들고, 보낼 글을 보여 주고, 카카오톡으로 보낼지 묻는다. (두 앱이 같이 들어도 코드는 하나)"""
    return _once(("invite", store_id, person["id"]), session, lambda: _invite_person(store_id, session, person))


def _invite_person(store_id: str, session: dict, person: dict) -> dict:
    code = staff.invite(store_id, person["id"])["code"]
    store = repo.store(store_id) or {}
    activity.log(store_id, "owner", f"{person['call']} 씨 초대 코드를 만들었어요", f"staff_invite:{code}")
    card = {"type": "invite", "id": "invite",
            "message": f"{store.get('name', '')} 알바생 할 일 페이지예요.\n아래 주소로 들어와서\n초대 코드를 넣어 주세요.",
            "url": invite_url(store), "code": f"{code[:3]} {code[3:]}"}
    return _ask(session, {"kind": "invite_share", "code": code, "staff_id": person["id"]}, f"{person['call']} 씨 초대 코드예요",
                [say(f"{person['call']} 씨 초대 코드를 만들었어요."), say(f"{_spoken_code(code)}."),
                 say("카카오톡으로 보낼까요?", "카카오톡으로 보낼까요?")], [card])


def invite_url(store: dict) -> str:
    return f"donna.app/s/{store.get('slug') or store.get('id', '')}"


def share(store_id: str, session: dict, code: str | None) -> dict:
    """"카카오톡으로 보내 줘". 받을 사람은 사장님이 카카오톡에서 직접 고른다 (도나가 문자를 대신 보내지 않는다)."""
    return _once(("share", store_id, code or "latest"), session, lambda: _share(store_id, session, code))


def _share(store_id: str, session: dict, code: str | None) -> dict:
    if code is None:
        waiting = [i for i in staff_db.store_invites(store_id) if not i["used_at"] and not i["revoked_at"]]
        code = waiting[0]["code"] if waiting else None
    if code is None:
        return _done(session, "보낼 초대 코드가 없어요", [say("보낼 초대 코드가 없어요."), say("'하린이 초대해 줘'라고 먼저 말해 주세요.")])
    staff.share_invite(code)
    return _done(session, "카카오톡을 열게요", [say("카카오톡을 열게요."), say("받을 사람은 직접 골라 주세요.", "받을 사람은 직접 골라 주세요.")],
                 open="kakao_share")


def remove(store_id: str, session: dict, word: str | None) -> dict:
    person = staff.find_by_name(store_id, word) if word else None
    if person is None:
        return _done(session, "누구를 내보낼까요?", [say("누구를 내보낼지 이름을 말해 주세요.")], [_people_card(store_id, "알바생")])
    return _ask(session, {"kind": "remove", "staff_id": person["id"]}, f"{person['call']} 씨를 내보낼까요?",
                [say(f"{person['call']} 씨를 알바생 화면에서 내보낼까요?"),
                 say("초대 코드도 못 쓰게 돼요.", "초대 코드도 못 쓰게 돼요.")])


# ── 알바생 목록, 매뉴얼 ──


def staff_list(store_id: str, text: str) -> dict:
    """D-30. "알바생 누구 있어?" / "오늘 누구 나왔어?"."""
    today = clock.now().date()
    joined = [p for p in staff.people(store_id) if p["joined"]]
    here = staff.present_today(store_id, today)
    if re.search(r"나왔|출근|오늘", text or ""):
        says = [say(f"오늘 나온 사람은 {speech.count(len(here), '명')}이에요." if here else "오늘 나온 사람은 아직 없어요.")]
        if here:
            says.append(say(", ".join(f"{p['call']} 씨" for p in here[:4]) + "예요."))
        return answer(f"오늘 {speech.count(len(here), '명')} 나왔어요" if here else "아직 아무도 안 나왔어요", says,
                      [_people_card(store_id, "오늘 나온 알바생", only_present=True)])
    says = [say(f"알바생은 {speech.count(len(joined), '명')}이에요."),
            say(f"오늘 나온 사람은 {speech.count(len(here), '명')}이에요." if here else "오늘 나온 사람은 아직 없어요.")]
    return answer(f"알바생 {len(joined)}명이에요", says, [_people_card(store_id, "알바생")])


def manual(store_id: str) -> dict:
    """D-06. 매장 공통 매뉴얼 세 묶음 (옛 목업과 같은 모양). 더할 것은 "앞으로 …하라고 해"로 말한다."""
    tasks = [t for t in staff.store_tasks(store_id) if t["repeat"] == "daily" and not t["canceled"]]
    groups = []
    for kind, label in PHASE_LABEL.items():
        titles = [t["title"] for t in tasks if t["phase"] == kind]
        if titles:
            groups.append({"id": f"mn_{kind}", "kind": kind, "label": label, "text": ", ".join(titles)})
    if not groups:
        return answer("매뉴얼이 아직 없어요", [say("알바생 매뉴얼이 아직 없어요.")], [])
    return answer("알바생 매뉴얼이에요",
                  [say(f"{', '.join(g['label'] for g in groups)} {speech.count(len(groups), '묶음')}이에요."),
                   say("더할 건 '앞으로 마감 때 냉장고 온도 적으라고 해'처럼 말하면 돼요.")],
                  [{"type": "manual", "id": "manual", "groups": groups}])
