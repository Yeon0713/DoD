"""인사과: 담당 × 업무의 직급 (2026-11-21 결정, donna-voice/docs/agent-structure.md 4장, 9장 2단계).

인사과는 일을 만들지 않고 직급만 관리한다. 기록·평가·승진·강등은 모두 코드다 (같은 기록이면 늘 같은 결과).
사장님께는 승진·강등·평가를 말하지 않는다.

직급 (결재 없이 처리할 수 있는 범위)
  intern     인턴: 건마다 묻는다                      asks → "each"
  staff      사원: 같은 업무를 묶어 한 번에 묻는다      asks → "batch"
  assistant  대리: 묻지 않고 처리, 다음 날 아침 사후 보고  asks → None
  manager    과장: 묻지 않고 처리, 월요일 아침 건수 보고    asks → None
업무마다 오를 수 있는 가장 높은 직급(상한)이 있다 (JOBS). 결재하는 곳은 asks 만 본다.

저장 (voice.db docs, 표를 더하지 않음)
  hr_rank    id <가게>:<업무>   {store_id, job, agent, rank, cap, since, changed_by: start | promote | demote, history[]}
  hr_event   id hr_<가게>_<번호> {id, store_id, job, agent, rank_at, ref, reaction, said, at, reported_at}
             reaction: approved(그대로 승인) | edited(조금 수정) | rejected(반려) | done(묻지 않고 처리) | canceled_after(사후 취소)
  hr_review  id <가게>:<평가일> {store_id, date, period, per_job: [{job, count, approved, canceled, before, after}], at}

평가 (4-5): HR_EPOCH(2026-11-30 월)부터 14일마다, 그날(또는 그 뒤) 첫 브리핑 준비 때 한 번. 평가일 앞 14일의 기록만 본다.
  인턴 → 사원, 사원 → 대리: 결재(approved + edited + rejected)가 최소 건수 이상이고 그대로 승인이 90% 이상
  대리 → 과장: done 이 최소 건수 이상이고 사후 취소 0
  한 번에 한 단계, 상한을 넘지 않는다. 못 미치면 그대로 (낮은 승인 비율로는 내리지 않는다)
강등 (4-6): 사후 취소 1건이면 그 자리에서 한 단계 (대리 → 사원, 과장 → 대리). 높은 위험 업무의 사고는 인턴으로.
스위치 VOICE_HR=false 면 기록·평가·강등을 멈춘다. 직급은 저장된 그대로 읽는다 (9-0 r).
"""

import datetime as dt
import sys

from voice import audit, clock, config, repo
from voice.clock import iso, parse

RANK_KIND = "hr_rank"
EVENT_KIND = "hr_event"
REVIEW_KIND = "hr_review"

RANKS = ("intern", "staff", "assistant", "manager")
RANK_NAMES = {"intern": "인턴", "staff": "사원", "assistant": "대리", "manager": "과장"}
DECISIONS = ("approved", "edited", "rejected")  # 결재 한 건의 반응. 뒤로 갈수록 무겁다 (한 건에 하나만 남긴다)
REACTIONS = DECISIONS + ("done", "canceled_after")

# 4-2 업무 표. agent 는 업무 수첩(7단계)의 담당 칸 이름이다. future: 앞으로 생길 업무 (아직 결재하는 곳이 없다)
JOBS: dict[str, dict] = {
    "positive_reply": {"name": "칭찬 리뷰 답글", "agent": "revisit", "risk": "low", "cap": "manager", "min": 20},
    "negative_reply": {"name": "부정 리뷰 답글", "agent": "negative_review", "risk": "mid", "cap": "assistant", "min": 20},
    "instagram_post": {"name": "인스타 게시", "agent": "marketing", "risk": "mid", "cap": "assistant", "min": 5},
    "story_poster": {"name": "포스터", "agent": "story_event", "risk": "mid", "cap": "assistant", "min": 5},
    "review_fix_task": {"name": "리뷰 교정 할 일", "agent": "negative_review", "risk": "staff_task", "cap": "staff", "min": 5},
    "field_task": {"name": "현장 변수 할 일", "agent": "field_variable", "risk": "staff_task", "cap": "staff", "min": 5},
    "manual_task": {"name": "매뉴얼화 제안", "agent": "manual_coach", "risk": "staff_task", "cap": "staff", "min": 5},
    "holiday_notice": {"name": "휴무 공지", "agent": "holiday", "risk": "low", "cap": "manager", "min": 5, "future": True},
    "price_notice": {"name": "가격·할인 안내", "agent": None, "risk": "high", "cap": "staff", "min": None, "future": True},
    "allergy_notice": {"name": "알레르기 안내", "agent": None, "risk": "high", "cap": "staff", "min": None, "future": True},
}
OFFER_CAP = "staff"  # 혜택(할인·사은품·서비스)이 들어간 포스터는 늘 결재 (4-3)
# 알바생 할 일 proposal 의 by → 업무
JOB_OF_PROPOSAL = {"negative_review": "review_fix_task", "field_variable": "field_task", "manual_coach": "manual_task"}


def _lower(a: str, b: str) -> str:
    return a if RANKS.index(a) <= RANKS.index(b) else b


def cap_of(job: str, *, offer: bool = False) -> str:
    cap = JOBS[job]["cap"]
    return _lower(cap, OFFER_CAP) if offer else cap


def rank_id(store_id: str, job: str) -> str:
    return f"{store_id}:{job}"


def _start(store_id: str, job: str, rank: str) -> dict:
    now = iso(clock.now())
    return repo.put(RANK_KIND, rank_id(store_id, job), store_id, {
        "store_id": store_id, "job": job, "agent": JOBS[job]["agent"], "rank": rank, "cap": JOBS[job]["cap"],
        "since": now, "changed_by": "start", "history": [{"at": now, "from": None, "to": rank, "by": "start"}]})


def set_ranks(store_id: str, ranks: dict[str, str]) -> None:
    """직급을 그대로 적는다 (시나리오 파일의 hr 칸, 개발자 API /v1/dev/hr). 평가·강등이 아니라 출발 직급이다."""
    for job, rank_ in ranks.items():
        if job not in JOBS or rank_ not in RANKS:
            raise ValueError(f"모르는 업무나 직급: {job}={rank_}")
        _start(store_id, job, rank_)


def seed_history(store_id: str, history: list[dict]) -> int:
    """시나리오 파일의 지난 반응 기록 (시연 가게, 9-2의 1): [{job, from, to, approved, edited, rejected, done}].
    기간 안 날짜에 고르게 나눠 hr_event 로 넣는다 (ref hist_<업무>_<번호>). 스위치와 상관없이 넣는다. 넣은 수."""
    count = 0
    for row in history:
        start, end = dt.date.fromisoformat(row["from"]), dt.date.fromisoformat(row["to"])
        days = (end - start).days + 1
        reactions = [r for r in REACTIONS for _ in range(row.get(r, 0))]
        for n, reaction in enumerate(reactions):
            day = start + dt.timedelta(days=n * days // max(len(reactions), 1))
            eid = f"hr_{store_id}_{repo.next_number(f'hr_event:{store_id}'):04d}"
            repo.put(EVENT_KIND, eid, store_id, {
                "id": eid, "store_id": store_id, "job": row["job"], "agent": JOBS[row["job"]]["agent"], "rank_at": stored(store_id, row["job"])["rank"],
                "ref": f"hist_{row['job']}_{n + 1}", "reaction": reaction, "said": None, "at": f"{day.isoformat()}T12:00:00+09:00",
                "reported_at": f"{day.isoformat()}T12:00:00+09:00" if reaction == "done" else None})
            count += 1
    return count


def stored(store_id: str, job: str) -> dict:
    """저장된 직급 문서. 없으면 인턴으로 만든다 (새 가게, 4-9)."""
    return repo.get(RANK_KIND, rank_id(store_id, job)) or _start(store_id, job, "intern")


def rank(store_id: str, job: str, *, offer: bool = False) -> str:
    """지금 직급 (상한을 적용한 것). 사장님이 밤 9시 승진을 허락한 업무(owner_ok)는 혜택 포스터 상한을 넘을 수 있다 (jobs/hr_night.py)."""
    found = stored(store_id, job)
    return _lower(found["rank"], cap_of(job, offer=offer and not found.get("owner_ok")))


def promote_by_owner(store_id: str, job: str, to: str) -> dict:
    """사장님이 밤 9시 인사과 보고에서 "그래"라고 한 승진 (K-02). 업무 상한까지만, 혜택 상한은 풀린다."""
    found = stored(store_id, job)
    if RANKS.index(to) > RANKS.index(JOBS[job]["cap"]):
        raise ValueError(f"{job} 은 {to} 까지 오를 수 없어요")
    return _change({**found, "owner_ok": True}, to, "owner")


def asks(store_id: str, job: str, **kw) -> str | None:
    """직급을 동작으로: 인턴 "each"(건마다 묻기), 사원 "batch"(묶어 묻기), 대리·과장 None(묻지 않고 처리)."""
    return {"intern": "each", "staff": "batch"}.get(rank(store_id, job, **kw))


def _change(found: dict, to: str, by: str, **extra) -> dict:
    now = iso(clock.now())
    history = found["history"] + [{"at": now, "from": found["rank"], "to": to, "by": by, **extra}]
    return repo.put(RANK_KIND, rank_id(found["store_id"], found["job"]), found["store_id"],
                    {**found, "rank": to, "since": now, "changed_by": by, "history": history})


# ── 반응 기록 (4-4) ──


def events(store_id: str, job: str | None = None) -> list[dict]:
    return [e for e in repo.all_of(EVENT_KIND, store_id) if job in (None, e["job"])]


def record(store_id: str, job: str, ref: str, reaction: str, said: str | None = None) -> dict | None:
    """반응 한 건을 남긴다. 결재 반응(approved·edited·rejected)은 업무 × ref 마다 하나만 남기고, 더 무거운 반응이 오면 바꾼다
    (예: "좀 더 부드럽게"로 고친 뒤 승인하면 edited 로 남는다). done·canceled_after 도 업무 × ref 마다 하나."""
    if not config.hr_on():
        return None
    if reaction not in REACTIONS:
        raise ValueError(f"모르는 반응: {reaction}")
    if audit.held(store_id, job, ref):  # 감사 보류 건은 직급에 반영하지 않는다 (감사팀 결정 8, 가정 e)
        return None
    kinds = DECISIONS if reaction in DECISIONS else (reaction,)
    with repo.lock():
        same = next((e for e in events(store_id, job) if e["ref"] == ref and e["reaction"] in kinds), None)
        if same is not None:
            if reaction in DECISIONS and DECISIONS.index(reaction) > DECISIONS.index(same["reaction"]):
                _notebook(store_id, job, reaction, said)
                return repo.put(EVENT_KIND, same["id"], store_id, {**same, "reaction": reaction, "said": said or same["said"],
                                                                   "at": iso(clock.now())})
            if reaction == "edited" and said and said != same["said"]:  # 같은 글을 두 번 고쳤다: 두 번째 지시도 수첩 판정
                _notebook(store_id, job, reaction, said)
            return same
        _notebook(store_id, job, reaction, said)
        eid = f"hr_{store_id}_{repo.next_number(f'hr_event:{store_id}'):04d}"  # repo 키는 가게를 가리지 않으므로 가게 id 를 넣는다
        return repo.put(EVENT_KIND, eid, store_id, {
            "id": eid, "store_id": store_id, "job": job, "agent": JOBS[job]["agent"], "rank_at": stored(store_id, job)["rank"],
            "ref": ref, "reaction": reaction, "said": said, "at": iso(clock.now()), "reported_at": None})


def _notebook(store_id: str, job: str, reaction: str, said: str | None) -> None:
    """고침·반려에 사장님 말이 있으면 업무 수첩 규칙인지 뒤에서 판정한다 (voice/notebook.py, 9장 7단계)."""
    if reaction in ("edited", "rejected") and said:
        from voice import notebook

        notebook.judge_later(store_id, job, said)


# ── 평가 (4-5) ──


def review_day(day: dt.date) -> dt.date | None:
    """그날 기준 가장 최근 평가일 (HR_EPOCH 부터 HR_PERIOD 마다). 첫 평가일 전이면 None."""
    if day < config.HR_EPOCH:
        return None
    return config.HR_EPOCH + config.HR_PERIOD * ((day - config.HR_EPOCH) // config.HR_PERIOD)


def _judge(job: str, current: str, found: list[dict]) -> tuple[str, dict]:
    count = {r: sum(1 for e in found if e["reaction"] == r) for r in REACTIONS}
    decided = sum(count[r] for r in DECISIONS)
    minimum = JOBS[job]["min"]
    after = current
    if current in ("intern", "staff"):
        if minimum and decided >= minimum and count["approved"] / decided >= config.HR_PROMOTE_RATIO:
            after = RANKS[RANKS.index(current) + 1]
        row = {"count": decided, "approved": count["approved"], "canceled": count["canceled_after"]}
    else:
        if current == "assistant" and minimum and count["done"] >= minimum and count["canceled_after"] == 0:
            after = "manager"
        row = {"count": count["done"], "approved": count["approved"], "canceled": count["canceled_after"]}
    return _lower(after, JOBS[job]["cap"]), row


def evaluate(store_id: str, day: dt.date) -> dict | None:
    """평가일이면 한 번만 평가한다 (hr_review id 로 막음). 평가한 기록 또는 None."""
    when = review_day(day)
    if when is None or not config.hr_on():
        return None
    rid = f"{store_id}:{when.isoformat()}"
    with repo.lock():
        if repo.get(REVIEW_KIND, rid):
            return None
        start = when - config.HR_PERIOD
        found = [e for e in events(store_id) if start <= parse(e["at"]).date() < when]
        per_job = []
        for job, spec in JOBS.items():
            if spec.get("future"):
                continue
            before = stored(store_id, job)
            after, row = _judge(job, before["rank"], [e for e in found if e["job"] == job])
            if after != before["rank"]:
                _change(before, after, "promote", review=rid)
            per_job.append({"job": job, **row, "before": before["rank"], "after": after})
        return repo.put(REVIEW_KIND, rid, store_id, {
            "store_id": store_id, "date": when.isoformat(), "period": [start.isoformat(), when.isoformat()],
            "per_job": per_job, "at": iso(clock.now())})


# ── 강등 (4-6) ──


def demote(store_id: str, job: str, ref: str, *, offer: bool = False) -> str | None:
    """사후 취소·사고면 내린다. 높은 위험 업무(또는 혜택 포스터)는 인턴으로, 대리·과장은 한 단계. 바뀐 직급 또는 None."""
    if not config.hr_on():
        return None
    with repo.lock():
        found = stored(store_id, job)
        if JOBS[job]["risk"] == "high" or offer:
            to = "intern"
        elif found["rank"] in ("assistant", "manager"):
            to = RANKS[RANKS.index(found["rank"]) - 1]
        else:
            return None  # 인턴·사원은 늘 결재를 받으므로 강등이 없다
        if to == found["rank"]:
            return None
        _change(found, to, "demote", ref=ref)
        return to


# ── 사후 보고 (4-7, 9장 5단계) ──


def report_items(store_id: str, now: dt.datetime) -> list[dict]:
    """아침 브리핑에서 알릴 것 (아직 보고하지 않은 done). 대리가 처리한 것은 오늘 전 것을 건별로,
    과장이 처리한 것은 이번 주 월요일 전 것을 건수로 (월요일에 지난주 것. 듣지 못한 보고는 다음 브리핑에 이어 붙는다).
    순서: 업무 표 순서 → 처리한 때."""
    monday = now.date() - dt.timedelta(days=now.weekday())
    found = []
    for e in events(store_id):
        if e["reaction"] != "done" or e.get("reported_at"):
            continue
        day = parse(e["at"]).date()
        if (day < monday) if e["rank_at"] == "manager" else (day < now.date()):
            found.append(e)
    order = list(JOBS)
    return sorted(found, key=lambda e: (e["rank_at"] == "manager", order.index(e["job"]), e["at"]))


def mark_reported(store_id: str, ids: list[str]) -> None:
    """보고를 앱에 보냈다 (9-0 h). 다음 보고에 다시 넣지 않고, 사후 취소 기간을 이날로 센다."""
    now = iso(clock.now())
    with repo.lock():
        for e in events(store_id):
            if e["id"] in ids and not e.get("reported_at"):
                repo.put(EVENT_KIND, e["id"], store_id, {**e, "reported_at": now})


def reported_on(store_id: str, day: dt.date) -> list[dict]:
    """그날 보고한 대리 건 (보고한 순서). "두 번째 거 취소해"의 번호가 가리키는 목록."""
    found = [e for e in events(store_id) if e["reaction"] == "done" and e["rank_at"] != "manager"
             and e.get("reported_at") and parse(e["reported_at"]).date() == day]
    order = list(JOBS)
    return sorted(found, key=lambda e: (order.index(e["job"]), e["at"]))


def undo(store_id: str, event: dict, in_time: bool, said: str | None = None) -> str | None:
    """사후 취소: 보고를 들은 날 영업이 끝나기 전이면 기록하고 강등한다 (4-6·4-7). 지났으면 아무것도 하지 않는다 (지우기만)."""
    if not in_time:
        return None
    record(store_id, event["job"], event["ref"], "canceled_after", said)
    return demote(store_id, event["job"], event["ref"])


# ── 이관 (4-9, 9-0 j) ──


def start_ranks(store_id: str) -> dict[str, str]:
    """인사과를 넣을 때 이미 쓰고 있는 가게의 출발 직급 (지금 동작에 맞춤)."""
    auto = repo.settings(store_id).get("negative_review_auto_reply") is True
    ranks = {job: "intern" for job, spec in JOBS.items() if not spec.get("future")}
    ranks.update(positive_reply="manager", negative_reply="assistant" if auto else "intern",
                 review_fix_task="staff", field_task="staff", manual_task="staff")
    return ranks


def migrate() -> dict[str, dict[str, str]]:
    """그때 있는 가게를 모두 이미 쓰는 가게로 채운다. 이미 직급이 있는 업무는 두지 않는다. {가게: {업무: 직급}} (새로 쓴 것만)."""
    done: dict[str, dict[str, str]] = {}
    for store_id in repo.store_ids():
        for job, rank_ in start_ranks(store_id).items():
            if repo.get(RANK_KIND, rank_id(store_id, job)) is None:
                _start(store_id, job, rank_)
                done.setdefault(store_id, {})[job] = rank_
    return done


if __name__ == "__main__":
    if sys.argv[1:] != ["migrate"]:
        sys.exit("쓰는 법: python -m voice.hr migrate")
    for store, ranks in migrate().items():
        print(store, ", ".join(f"{job}={RANK_NAMES[r]}" for job, r in ranks.items()))
