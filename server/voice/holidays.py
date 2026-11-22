"""쉬는 날(임시 휴무) 받기 (에이전트 조직 개편 6-3, donna-voice/docs/agent-org-plan.md).

두 곳에서 받는다 (2026-11-20 결정)
  사장님 말   "도나야, 다음 주 수요일 쉬어" → 한 번 읽어 주고 "맞아요?" → "응"이면 확정
  네이버      가게를 등록할 때 저장해 둔 네이버 플레이스 휴무 안내(closed_note)와 소식 글에서 날짜를 뽑는다 (agents/holiday_reader).
              잘못 읽으면 공지가 엉뚱한 날 올라가므로, 아침 브리핑에서 묻고 사장님이 확인해야 확정한다
저장: 가게 문서의 holidays [{date, source: owner | naver, note, confirmed, (rejected)}]. hours.on 이 확정한 날을 쉬는 날로 본다.
네이버에서 읽은 날을 사장님이 아니라고 하면 rejected 로 남겨 둔다 (다음 날 같은 글을 다시 읽어도 다시 묻지 않게).
그래서 브리핑 준비, 아쉬운 리뷰 알림 시간, 좋은 리뷰 예약 시각, 홈 가게 상태가 저절로 맞춰진다.
"""

import datetime as dt
import re

from voice import clock, repo, speech

WEEKDAYS = "월화수목금토일"
MONTH_DAY_RE = re.compile(r"(\d{1,2})월(\d{1,2})일")
DAY_RE = re.compile(r"(\d{1,2})일")
WEEKDAY_RE = re.compile(r"(이번주|다음주)?([월화수목금토일])요일")
AHEAD = dt.timedelta(days=60)
RUN_KIND = "holiday_run"  # 그날 네이버 휴무 안내를 읽었다는 표시


def items(store: dict) -> list[dict]:
    return list(store.get("holidays") or [])


def _save(store_id: str, found: list[dict]) -> None:
    store = repo.store(store_id)
    repo.put("store", store_id, store_id, {**store, "holidays": sorted(found, key=lambda h: h["date"])})


def add(store_id: str, day: str, *, source: str, note: str | None = None, confirmed: bool, rejected: bool = False) -> None:
    kept = [h for h in items(repo.store(store_id)) if h["date"] != day]
    _save(store_id, kept + [{"date": day, "source": source, "note": note, "confirmed": confirmed, **({"rejected": True} if rejected else {})}])


def remove(store_id: str, day: str) -> None:
    _save(store_id, [h for h in items(repo.store(store_id)) if h["date"] != day])


def unconfirmed(store: dict, today: dt.date) -> list[dict]:
    return [h for h in items(store) if not h["confirmed"] and not h.get("rejected") and h["date"] >= today.isoformat()]


def label(day: str) -> str:
    """'11월 26일 수요일'."""
    d = dt.date.fromisoformat(day)
    return f"{d.month}월 {d.day}일 {speech.weekday(d)}요일"


def parse_day(n: str, today: dt.date) -> dt.date | None:
    """띄어쓰기를 지운 말에서 날짜: 오늘, 내일, 모레, 11월26일, 26일, (이번주|다음주)수요일. 못 찾으면 None."""
    if "모레" in n:
        return today + dt.timedelta(days=2)
    if "내일" in n:
        return today + dt.timedelta(days=1)
    if "오늘" in n:
        return today
    found = MONTH_DAY_RE.search(n)
    if found:
        month, day = int(found.group(1)), int(found.group(2))
        try:
            when = dt.date(today.year, month, day)
        except ValueError:
            return None
        return when if when >= today else when.replace(year=today.year + 1)
    found = WEEKDAY_RE.search(n)
    if found:
        target = WEEKDAYS.index(found.group(2))
        monday = today - dt.timedelta(days=today.weekday())
        if found.group(1) == "다음주":
            return monday + dt.timedelta(days=7 + target)
        when = monday + dt.timedelta(days=target)
        return when if when >= today or found.group(1) == "이번주" else when + dt.timedelta(days=7)
    found = DAY_RE.search(n)
    if found:
        day = int(found.group(1))
        for months in range(0, 3):
            year, month = today.year + (today.month - 1 + months) // 12, (today.month - 1 + months) % 12 + 1
            try:
                when = dt.date(year, month, day)
            except ValueError:
                continue
            if when >= today:
                return when
    return None


# ── 네이버 ──


def naver_texts(store_id: str) -> list[str]:
    """등록할 때 저장해 둔 네이버 플레이스 휴무 안내와 최근 소식 글. 등록한 가게가 아니면 빈 목록."""
    from app.data_pipeline import registered_stores

    info = registered_stores.place_info(store_id)
    if info is None:
        return []
    texts = [info.closed_note] if info.closed_note else []
    texts += [" ".join(x for x in (n.title, n.body, n.period or "") if x) for n in (info.news or [])[:5]]
    return [t for t in texts if t and t.strip()]


def read_naver(view) -> list[dict]:
    """하루 한 번 네이버 휴무 안내를 읽어 확인 전 휴무로 둔다. 새로 찾은 것 [{date, quote}]."""
    from voice.agents import holiday_reader

    day = view.now.date().isoformat()
    run_id = f"{view.store_id}:{day}"
    if repo.get(RUN_KIND, run_id):
        return []
    texts = naver_texts(view.store_id)
    if not texts:
        return []
    found = holiday_reader.suggest(view, texts)
    if found is None:
        return []
    repo.put(RUN_KIND, run_id, view.store_id, {"id": run_id, "found": len(found), "at": clock.iso(clock.now())})
    known = {h["date"] for h in items(view.store)}
    fresh = [f for f in found if f["date"] not in known]
    for f in fresh:
        add(view.store_id, f["date"], source="naver", note=f["quote"], confirmed=False)
    return fresh


# ── 말로 묻고 대답 받기 ──


def ask(day: str, action: str, source: str, lead: list[str] | None = None) -> dict:
    """ask_holiday 응답. holiday 칸을 turn.handle 이 session['holiday_pending'] 에 둔다."""
    from voice.jobs.briefing import answer, say

    if action == "remove":
        says, headline = [say(f"{label(day)} 휴무를 취소할게요. 맞아요?")], "휴무를 취소할까요?"
    else:
        says, headline = [say(f"{label(day)}을 쉬는 날로 적을게요. 맞아요?")], "쉬는 날로 적을까요?"
    response = answer(headline, [say(t) for t in lead or []] + says, [], kind="ask_holiday",
                      holiday={"date": day, "action": action, "source": source})
    response["expects_reply"] = True
    return response


def from_words(view, name: str, words: str) -> dict:
    """'다음 주 수요일 쉬어' → 읽어 주고 묻는다. 날짜를 못 알아들으면 다시 묻는다."""
    from voice.dialog.intent_rules import normalize
    from voice.jobs.briefing import answer, say

    day = parse_day(normalize(words), view.now.date())
    if day is None:
        return answer("언제 쉬세요?", [say("언제 쉬시는지 날짜로 다시 말씀해 주세요.")], [])
    action = "remove" if name == "store.holiday_cancel" else "add"
    if action == "remove" and day.isoformat() not in {h["date"] for h in items(view.store) if not h.get("rejected")}:
        return answer("적힌 휴무가 없어요", [say(f"{label(day.isoformat())}은 쉬는 날로 적혀 있지 않아요.")], [])
    return ask(day.isoformat(), action, "owner")


def decide(view, name: str, session: dict) -> dict:
    """ask_holiday 뒤의 대답."""
    from voice.jobs import queue
    from voice.jobs.briefing import answer, say

    pending = session.pop("holiday_pending", None)
    if not pending:
        return answer("지금은 물어본 게 없어요", [say("지금은 여쭤본 게 없어요.")], [])
    day = pending["date"]
    if name == "holiday.no":
        if pending["source"] == "naver":  # 네이버에서 읽은 날을 아니라고 하면 아니라고 한 것으로 남긴다 (다시 묻지 않는다)
            note = next((h["note"] for h in items(repo.store(view.store_id)) if h["date"] == day), None)
            add(view.store_id, day, source="naver", note=note, confirmed=False, rejected=True)
        return answer("그대로 둘게요", [say("네, 그대로 둘게요.")], [])
    if pending["action"] == "remove":
        remove(view.store_id, day)
        text = f"네, {label(day)} 휴무를 취소했어요."
    else:
        add(view.store_id, day, source=pending["source"], note=None, confirmed=True)
        text = f"네, {label(day)}은 쉬는 날로 적었어요."
    queue.reschedule_prepare(view.store_id)  # 쉬는 날에는 브리핑을 준비하지 않는다
    return answer("쉬는 날을 적었어요" if pending["action"] == "add" else "휴무를 취소했어요", [say(text)], [])


def step(view) -> dict | None:
    """아침 브리핑: 네이버에서 읽은 확인 전 휴무가 있으면 묻는다 (가장 가까운 날 하나)."""
    waiting = unconfirmed(view.store, view.now.date())
    if not waiting:
        return None
    first = waiting[0]
    return ask(first["date"], "add", "naver", lead=[f"네이버 소식에 '{first['note']}'라고 있어요."])
