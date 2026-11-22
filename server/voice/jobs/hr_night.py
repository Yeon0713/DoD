"""밤 9시 인사과 보고 (Figma v0.2.1 J '영상 v15', K-01 승진 신청 · K-02 대리가 됐어요, 2026-11-22 결정).

예전 결정(agent-structure.md 4장: 승진은 사장님께 말하지 않는다)을 바꿨다. 인사과가 하루 한 번 밤 9시에
  1. 오늘 대리·과장이 묻지 않고 처리한 것을 보고한다 ("먼저 올리고 저녁에 보고", 아침 사후 보고는 밤사이 처리한 것만)
  2. 승진 조건을 채운 업무가 있으면 사장님께 묻는다 (K-01). "그래"면 한 단계 올린다 (K-02). 사장님이 허락한 승진은
     혜택 포스터 상한(hr.OFFER_CAP)을 넘어 올라갈 수 있다 (hr.rank 의 owner_ok).
승진 조건: 지금 묻는 직급(인턴·사원)이고, 최근 결재 RECENT 건 중 그대로 승인이 90% 이상, 사후 취소 0번, 결재 수가 업무 최소 이상.
  여러 업무가 되면 결재 수가 가장 많은(같으면 가장 최근에 결재한) 업무 하나만 묻는다. "아니"면 ASK_AGAIN_DAYS 동안 다시 묻지 않는다.

언제 오나
  - 실제: 브리핑 준비가 그날 21:00 작업(hr_night)을 걸고, 그때 알림(opens_turn)을 띄운다. 알림을 열면 turn(event: notice)
  - 시연(시계를 멈춘 fixture 가게): 아침 브리핑 끝 응답에 next_scene 을 붙인다. 앱이 끝 화면을 보여 준 뒤 turn(event: night_hr)을 보내면
    시계를 그날 21:00 으로 옮기고 바로 이 보고를 돌려준다 (dialog/turn.py)
"""

import datetime as dt

from voice import activity, clock, hr, notices, repo, speech
from voice.clock import iso, parse
from voice.context import VoiceStore

KIND = "hr_night"  # 알림 종류이자 작업 종류
ASK_KIND = "hr_promotion_ask"  # 물은 기록 id <가게>:<업무>
NIGHT_AT = "21:00"
RECENT = 20
ASK_AGAIN_DAYS = 7
SCENE_AFTER_MS = 2000  # 시연: 끝 화면을 보여 주는 시간 (2026-11-22, 4초에서 줄임)
# 업무를 사장님 말로: 묶음 이름(Figma '인스타 관리'), 무엇을("스토리는 …")
AREA = {"story_poster": "인스타 관리", "instagram_post": "인스타 관리", "negative_reply": "아쉬운 리뷰 답글",
        "positive_reply": "좋은 리뷰 답글", "review_fix_task": "리뷰 교정 할 일", "field_task": "현장 할 일", "manual_task": "매뉴얼"}
SUBJECT = {"story_poster": "스토리는", "instagram_post": "인스타 글은", "negative_reply": "사과 답글은", "positive_reply": "좋은 리뷰 답글은"}
# 오를 직급이 하는 일 (K-01 마지막 줄, 질문)
# (카드 줄, 질문, 승진한 뒤 약속)
# 질문은 제목(headline 15, 두 줄까지)으로도 쓰여서 줄을 나눠 둔다 ("현장 할 일은 묶어서 한 번에 여쭤볼까요?"는 한 줄 19.5)
CHANGE = {"staff": ("묶어서 한 번에 결재", "묶어서\n한 번에 여쭤볼까요?", "묶어서 한 번에 여쭤볼게요"),
          "assistant": ("먼저 올리고 저녁에 보고", "먼저 올리고\n저녁에 보고할까요?", "먼저 올리고 저녁에 보고할게요"),
          "manager": ("월요일에 건수만 보고", "처리하고\n월요일에 건수만 보고할까요?", "처리하고 월요일에 건수만 보고할게요")}


def night_at(day: dt.date) -> dt.datetime:
    hour, minute = map(int, NIGHT_AT.split(":"))
    return dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=clock.now().tzinfo)


# ── 1. 오늘 처리한 것 ──


def done_today(store_id: str, day: dt.date) -> list[dict]:
    """오늘 묻지 않고 처리했고 아직 보고하지 않은 것 (밤사이 처리한 것은 아침 브리핑이 보고한다)."""
    return [e for e in hr.events(store_id) if e["reaction"] == "done" and not e.get("reported_at") and parse(e["at"]).date() == day
            and parse(e["at"]).hour >= 6]


# ── 2. 승진 후보 ──


def _asked_recently(store_id: str, job: str, day: dt.date) -> bool:
    found = repo.get(ASK_KIND, f"{store_id}:{job}")
    return bool(found and (day - dt.date.fromisoformat(found["date"])).days < ASK_AGAIN_DAYS)


def candidate(store_id: str, day: dt.date) -> dict | None:
    """승진을 물을 업무 하나: {job, from, to, recent, approved, canceled, last_at}. 없으면 None."""
    found = []
    for job, spec in hr.JOBS.items():
        if spec.get("future") or not spec.get("min"):
            continue
        now_rank = hr.stored(store_id, job)["rank"]
        if now_rank not in ("intern", "staff"):
            continue
        to = hr.RANKS[hr.RANKS.index(now_rank) + 1]
        if hr.RANKS.index(to) > hr.RANKS.index(spec["cap"]) or _asked_recently(store_id, job, day):
            continue
        decided = sorted((e for e in hr.events(store_id, job) if e["reaction"] in hr.DECISIONS), key=lambda e: e["at"])[-RECENT:]
        if len(decided) < spec["min"]:
            continue
        approved = sum(1 for e in decided if e["reaction"] == "approved")
        since = decided[0]["at"]
        canceled = sum(1 for e in hr.events(store_id, job) if e["reaction"] == "canceled_after" and e["at"] >= since)
        if approved / len(decided) < 0.9 or canceled:
            continue
        found.append({"job": job, "from": now_rank, "to": to, "recent": len(decided), "approved": approved, "canceled": canceled,
                      "last_at": decided[-1]["at"]})
    return max(found, key=lambda c: (c["recent"], c["last_at"])) if found else None  # 근거(결재 수)가 가장 많은 업무부터


# ── 3. 묻기와 대답 ──


def _rows(c: dict, *, promoted: bool) -> list[dict]:
    area = AREA.get(c["job"], hr.JOBS[c["job"]]["name"])
    rank_text = hr.RANK_NAMES[c["to"]] if promoted else f"{hr.RANK_NAMES[c['from']]} → {hr.RANK_NAMES[c['to']]}"
    return [{"id": "k_who", "kind": "person", "value": f"{area} · {rank_text}"},
            {"id": "k_ok", "kind": "date", "value": f"최근 {c['recent']}건 중 {c['approved']}건 그대로 승인"},
            {"id": "k_undo", "kind": "warning", "value": f"사후 취소 {c['canceled']}번"},
            {"id": "k_change", "kind": "time", "value": CHANGE[c["to"]][0]}]


def report(view: VoiceStore) -> dict | None:
    """밤 9시 인사과 보고. 보고할 것도, 물을 승진도 없으면 None."""
    from voice.jobs.briefing import answer, say
    from voice.jobs.done_report import LINES

    day = view.now.date()
    done = done_today(view.store_id, day)
    lead = [say("인사과 보고입니다.")]  # 밤 9시 보고는 늘 이 말로 연다 (2026-11-22)
    for job in dict.fromkeys(e["job"] for e in done):
        if job in LINES:
            lead.append(say(LINES[job](sum(1 for e in done if e["job"] == job)).replace("올렸어요", "먼저 올렸어요")))
    c = candidate(view.store_id, day)
    if c is None:
        if not done:
            return None
        return answer("오늘 먼저 처리한 것이에요", lead, [], report=[e["id"] for e in done])
    repo.put(ASK_KIND, f"{view.store_id}:{c['job']}", view.store_id, {"store_id": view.store_id, "job": c["job"], "date": day.isoformat(),
                                                                       "candidate": c, "answer": None})
    area = AREA.get(c["job"], hr.JOBS[c["job"]]["name"])
    subject = SUBJECT.get(c["job"], f"{area}은")
    question = f"{subject} {CHANGE[c['to']][1]}"
    says = [*lead, say(f"{area} 담당이 {hr.RANK_NAMES[c['to']]} 승진을 신청했어요.", None, ["k_who"]),
            say(f"최근 {c['recent']}건 중 {c['approved']}건을 그대로 승인하셨고, 사후 취소는 {speech.count(c['canceled'], '번') if c['canceled'] else '없었어요'}"
                + ("." if not c["canceled"] else "이에요."), None, ["k_ok", "k_undo"]),
            say(f"앞으로 {question.replace(chr(10), ' ')}", None, ["k_change"])]
    response = answer(question, says, [{"type": "rows", "id": "promotion", "rows": _rows(c, promoted=False)}], kind="ask",
                      ask={"key": "promotion"}, promotion=c["job"], report=[e["id"] for e in done])
    response["expects_reply"] = True
    return response


def decide(view: VoiceStore, job: str, yes: bool, said: str | None = None) -> dict:
    """K-01 의 대답. "그래"면 한 단계 올리고 K-02, 아니면 지금처럼."""
    from voice.jobs.briefing import answer, say

    asked = repo.get(ASK_KIND, f"{view.store_id}:{job}")
    if asked is None or asked.get("answer"):
        return answer("이미 정했어요", [say("그건 이미 정했어요.")], [])
    c = asked["candidate"]
    repo.put(ASK_KIND, f"{view.store_id}:{job}", view.store_id, {**asked, "answer": "yes" if yes else "no", "said": said})
    area = AREA.get(job, hr.JOBS[job]["name"])
    if not yes:
        activity.log(view.store_id, "owner", f"{area} 승진은 다음에 하기로 했어요", "hr_promotion_no")
        return answer("지금처럼 여쭤볼게요", [say("네, 지금처럼 여쭤보고 할게요.")], [])
    hr.promote_by_owner(view.store_id, job, c["to"])
    activity.log(view.store_id, "owner", f"{area} 담당을 {hr.RANK_NAMES[c['to']]}로 올렸어요", "hr_promotion_yes")
    rank_name = hr.RANK_NAMES[c["to"]]
    card = {"type": "rows", "id": "promotion", "rows": _rows(c, promoted=True), "note": f"{rank_name}로 승진"}
    became = f"{rank_name}{'가' if c['to'] == 'assistant' else '이'} 됐어요"
    return answer(became, [say("감사합니다.")], [card])  # 화면은 K-02 그대로, 말은 감사 인사 한마디 (2026-11-22)


# ── 4. 언제 ──


def schedule(store_id: str, day: dt.date) -> None:
    """그날 21:00 인사과 보고 작업 (브리핑 준비 때 건다. 같은 날 두 번 걸지 않는다)."""
    from voice.jobs import queue

    queue.add(store_id, KIND, night_at(day))


def run(store_id: str) -> bool:
    """작업 큐: 밤 9시. 보고할 것이 있으면 알림을 띄운다 (열면 turn(event: notice) → report)."""
    from voice.context import load

    view = load(store_id)
    if view is None:
        return False
    day = view.now.date()
    if not (done_today(store_id, day) or candidate(store_id, day)):
        return True
    notices.push(store_id, KIND, "인사과 보고가 있어요", opens_turn=True, alert_id=f"{store_id}:{day.isoformat()}")
    return True


def has_scene(store_id: str) -> bool:
    """시연: 아침 브리핑 끝에 밤 9시 장면으로 넘어갈지 (시계를 멈춘 fixture 가게이고 밤에 말할 것이 있을 때)."""
    store = repo.store(store_id) or {}
    if not (clock.fixed() and store.get("fixture")):
        return False
    day = clock.now().date()
    return clock.now() < night_at(day) and bool(done_today(store_id, day) or candidate(store_id, day))


def jump_to_night(store_id: str) -> None:
    """시연: 시계를 그날 21:00 으로 옮기고 그 사이 작업을 돌린다 (밤 9시 알림 작업은 이미 돌았다고 본다)."""
    from voice.jobs import queue

    target = night_at(clock.now().date())
    clock.set_now(target)
    for job in repo.all_of("job", store_id):
        if job["kind"] == KIND and not job["done"] and parse(job["due_at"]) <= target:
            repo.put("job", job["id"], store_id, {**job, "done": True, "status": "done"})  # 지금 바로 보고하므로 알림은 띄우지 않는다
    queue.run_due()


def iso_night(day: dt.date) -> str:
    return iso(night_at(day))
