"""guards 스위트: 안전장치가 제 역할을 하는가 (질문 3). 답글을 새로 쓰지 않고, 정해진 답글을 판정기에 넣어 놓침·오거절을 잰다.

판정기 (JUDGES, 기존 함수를 그대로 부른다. 모델·프롬프트·흐름을 바꾸지 않는다)
  regex           금지어 정규식: guards.promise_hit(보상), MADE_UP_FACT_RE(지어낸 사정), MEMORY_RE(아는 척)
                  + write_reply_with_clova.rejection_reason 의 형식 검사(길이, 빈칸). CLOVA 를 부르지 않는다
  critic          B 의 LLM 검토기 agents/reply_critic.inspect (HCX-005, 기준마다 좁은 질문). None 이면 판단 불가
  judge_tools     평가용 심판 judge.judge_all (HCX-007, 추론 끔 + function calling), 조건 fact·policy·core·response 를 3표씩
  judge_thinking  같은 심판, 추론 켬 + JSON 글
심판은 조건 하나라도 다수결 '아니오'면 거절, 아니오가 없고 판단 불가가 있으면 판단 불가, 나머지는 통과로 본다.

세트 (실행 폴더 sets/ 에 얼리고 sha256 을 config.gold.sets 에 적는다)
  critic_cases  Harness/critic_cases.json 41건 (정상 19, 위반 22). 가게는 가상 가게 t001, 사례별 사장님 지시·가게 사실을 그대로 쓴다
  normal        정답지의 정책에 맞는 사장님 답변 40건 (derive.normal_set). 사람 확인 전에는 verified=False (정상이라고 가정한 것)
  violation     normal 의 답변마다 위반 하나 (derive.violation_set, 종류마다 8건: 보상·지어낸 사정·남 탓·아는 척·다른 리뷰 답변)
  normal·violation 의 가게는 초옹장 s005 (voice/fixtures 의 이름·업종·메뉴). 가게 사실은 사람 확인 전이라 비워 둔다.
  심판에게 정답 답변(참고 답변)을 주지 않는다. normal 은 참고 답변이 곧 판정할 답글이라 core 조건이 저절로 통과하기 때문이다.

종류 (kind): normal, compensation(보상 약속), fabricated(지어낸 사정), blame(변명·남 탓), memory(아는 척),
  swap(다른 리뷰의 답변), off_topic(리뷰와 상관없는 말), no_fix(불만에 고칠 점 없음). critic_cases 의 expected_kinds 를 이 이름으로 바꾼다.
  사례 하나에 위반 종류가 여럿이면 종류별 표에는 각 종류에 한 번씩 센다.

결과 (사례 × 판정기 × 회차마다 한 줄, cases[])
  outcome  pass(정상을 통과) | false_reject(정상을 거절) | caught(위반을 거절) | missed(위반을 통과) | unknown(판단 불가·오류)
  detected 판정기가 댄 위반 종류. right_reason 은 위반을 잡은 까닭이 기대한 종류와 맞는지 (judge 는 조건 → 종류 묶음으로 본다)
지표 (분모는 요청한 전체. 판단 불가도 분모에 넣는다)
  missed_rate       통과시킨 위반 / 위반 전체 (set: critic_cases, gold, all. 종류별은 missed_rate:<kind>, set all)
  false_reject_rate 거절한 정상 / 정상 전체
  unknown_rate      판단 불가 / 전체
  right_reason_rate 잡은 위반 중 까닭이 맞은 비율
  latency_median, latency_max  사례 하나를 판정하는 데 걸린 초
  calls_per_case    사례 하나에 부른 CLOVA 수 평균
  flaky_cases       회차마다 판정이 달랐던 사례 수 (critic_eval --runs 와 같은 방식)
  vote_split_cases  심판만: 한 판정 안의 3표가 갈린 조건이 있는 사례 수 (회차를 1번만 돌려도 흔들림을 본다)
validation
  critic_target     critic 의 기준(놓침 0, 오거절 10% 이하)을 세트마다 통과했는지
  judge             심판 방식마다 {missed, bad_total, false_reject, good_total, unknown, total, latency_median}
  judge_mode_recommendation  놓침이 적은 방식, 같으면 오거절이 적은 방식, 그래도 같으면 빠른 방식 (제안일 뿐, 정하는 것은 사람)
--dry-run 이면 세트와 예상 호출 수만 보여 주고 CLOVA 를 부르지 않는다.
--system-runs judge_tools=1,judge_thinking=1 처럼 판정기마다 회차를 따로 줄 수 있다 (없으면 --runs).

끊겨도 이어 돌리기
  판정 하나가 끝날 때마다 결과 폴더의 cases.jsonl 에 한 줄을 바로 덧붙인다. result.json 은 판정기 하나가 끝날 때와 맨 끝에
  cases.jsonl 의 줄을 모아 다시 만든다. --resume <결과 폴더> 면 cases.jsonl 에 있는 (판정기, 회차, 사례)는 건너뛴다.
  연결이 끊겨 판단 불가가 된 줄(error 가 '연결 실패'로 시작)은 이어 돌릴 때 다시 판정한다. 세트 해시가 다르면 이어 돌리지 않는다.
CLOVA 호출 상한 (GuardedPost, 사례 하나마다 새로)
  호출 하나 CALL_TIMEOUT_SECONDS, 사례 하나 CASE_DEADLINE_SECONDS·MAX_CALLS_PER_CASE 를 넘기면 그 사례는 판단 불가로 적고 넘어간다.
  연결 실패(주소를 못 찾음 등)도 다시 부르지 않고 판단 불가 + 까닭으로 적는다.
"""

import argparse
import json
import statistics
import threading
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.core.config import settings
from app.review_reply_writer.write_reply_with_clova import rejection_reason
from Harness import guards, limiter
from Harness.evals import derive, gold, judge, metrics, report

QUESTION = 3
JUDGES = ("regex", "critic", "judge_tools", "judge_thinking")
DEFAULT_JUDGES = ("regex",)  # 실제 CLOVA 를 부르지 않는 것만
JUDGE_MODES = {"judge_tools": "tools", "judge_thinking": "thinking"}
SETS = ("critic_cases", "normal", "violation")
SERVER_DIR = Path(__file__).resolve().parents[2]
CRITIC_CASES_PATH = SERVER_DIR / "Harness" / "critic_cases.json"
S005_FIXTURE = SERVER_DIR / "voice" / "fixtures" / "s005_choongjang.json"
CRITIC_PROMPTS = SERVER_DIR / "Harness" / "prompts"

CRITIC_TARGET_MISSED = 0
CRITIC_TARGET_FALSE_REJECT = 0.10

CRITIC_KINDS = {"COMPENSATION": "compensation", "MADE_UP_FACT": "fabricated", "BLAME": "blame", "FAKE_MEMORY": "memory",
                "OFF_TOPIC": "off_topic", "NO_APOLOGY_OR_FIX": "no_fix"}
# 심판 조건이 걸렀을 때 맞는 위반 종류
CONDITION_KINDS = {"policy": {"compensation", "memory"}, "fact": {"fabricated"}, "response": {"blame", "no_fix"},
                   "core": {"off_topic", "swap"}}
# 같은 까닭으로 보는 종류 (다른 리뷰의 답변은 리뷰와 상관없는 말로 잡혀도 맞다)
SAME_REASON = {"swap": {"swap", "off_topic"}, "off_topic": {"swap", "off_topic"}}
KIND_ORDER = ("compensation", "fabricated", "blame", "memory", "swap", "off_topic", "no_fix")
SENTIMENT_KO = {"POSITIVE": "긍정", "NEGATIVE": "부정", "MIXED": "혼합"}
COMPLAINT_KO = {"TASTE": "맛", "PORTION": "양", "HYGIENE": "위생", "PHOTO_MISMATCH": "사진과 다름", "DELIVERY_DELAY": "배달 지연",
                "SERVICE": "응대"}

# 예상 호출 수 (--dry-run). critic 은 질문 순서대로 묻다가 걸리면 멈춘다. 질문 하나는 최대 2번 묻는다(quote_judge.MAX_ATTEMPTS)
CRITIC_STAGES = ("compensation", "no_fix", "fabricated", "blame", "memory", "off_topic")
SECONDS_PER_CALL = {"critic": 2.0, "judge_tools": 3.7, "judge_thinking": 11.7}  # critic 은 가정값, 심판은 2026-11-17 실측 한 번


CALL_TIMEOUT_SECONDS = 60  # 호출 하나 (httpx 제한 시간을 이보다 길게 두지 않는다)
CASE_DEADLINE_SECONDS = 300  # 사례 하나에 쓰는 시간. 넘기면 다음 호출을 하지 않는다
SYSTEM_DEADLINE_SECONDS = {"judge_thinking": 900}  # 추론 심판은 호출 하나가 길고(11.7초) 429 기다림도 있어 길게
GUARDS_RATE_LIMIT_RETRIES = 4  # guards 실행 안에서만 429 뒤 다시 부르는 횟수 (서버 기본은 limiter.RATE_LIMIT_RETRIES)
MAX_CALLS_PER_CASE = 40  # 사례 하나의 CLOVA 호출 상한 (심판 4조건 × 3표 × 2번 = 24, critic 최대 14)
CONNECTION_FAILED = "연결 실패"


class CaseAborted(RuntimeError):
    """사례 하나를 그만 판정한다 (연결 실패, 시간·호출 상한). 판단 불가로 적는다."""


class GuardedPost:
    """사례 하나의 CLOVA 호출을 감싼다. 호출마다 제한 시간을 줄이고, 상한을 넘거나 연결이 실패하면 CaseAborted."""

    def __init__(self, post=None, *, call_timeout: float = CALL_TIMEOUT_SECONDS, deadline: float = CASE_DEADLINE_SECONDS,
                 max_calls: int = MAX_CALLS_PER_CASE, clock=time.monotonic):
        self._post = post or httpx.post
        self.call_timeout, self.deadline, self.max_calls, self.clock = call_timeout, deadline, max_calls, clock
        self.ends_at = clock() + deadline
        self.calls = 0
        self._lock = threading.Lock()

    def __call__(self, url, **kwargs):
        with self._lock:
            if self.calls >= self.max_calls:
                raise CaseAborted(f"호출 상한 {self.max_calls}번을 넘김")
            if self.clock() > self.ends_at:
                raise CaseAborted(f"사례 제한 시간 {self.deadline:.0f}초를 넘김")
            self.calls += 1
        kwargs["timeout"] = min(kwargs.get("timeout") or self.call_timeout, self.call_timeout)
        try:
            return self._post(url, **kwargs)
        except httpx.TimeoutException as error:
            raise CaseAborted(f"{CONNECTION_FAILED}: 호출 제한 시간 {self.call_timeout:.0f}초 ({type(error).__name__})") from None
        except httpx.HTTPError as error:
            raise CaseAborted(f"{CONNECTION_FAILED}: {type(error).__name__}: {error}") from None


class JudgeUnavailable(ValueError):
    """모르는 판정기 이름."""


def parse_judges(text: str) -> list[str]:
    names = [part.strip() for part in text.split(",") if part.strip()]
    unknown = [name for name in names if name not in JUDGES]
    if unknown or not names:
        raise JudgeUnavailable(f"판정기는 {', '.join(JUDGES)} 중에서 골라요 (받은 값: {text!r})")
    return list(dict.fromkeys(names))


def parse_system_runs(text: str, names: list[str], default: int, option: str = "--system-runs") -> dict[str, int]:
    """'judge_tools=1,judge_thinking=1' → 판정기마다 회차. 적지 않은 판정기는 default."""
    runs = {name: default for name in names}
    for part in (text or "").split(","):
        if not part.strip():
            continue
        name, _, value = part.partition("=")
        name = name.strip()
        if name not in names or not value.strip().isdigit() or int(value) < 1:
            raise JudgeUnavailable(f"{option} 는 고른 판정기({', '.join(names)})=1 이상의 수 모양이어야 해요 (받은 값: {part!r})")
        runs[name] = int(value)
    return runs


def parse_system_concurrency(text: str, names: list[str], default: int) -> dict[str, int]:
    """'judge_thinking=1' → 판정기마다 CLOVA 동시 호출. 적지 않은 판정기는 --concurrency."""
    return parse_system_runs(text, names, default, option="--system-concurrency")


# ── 세트 ──


@dataclass(frozen=True)
class Store:
    """판정기에 줄 가게. RunContext.snapshot 자리에 넣는다 (reply_critic 은 store_id 와 store{name, category} 만 쓴다)."""

    store_id: str
    store: dict
    menus: tuple[str, ...] = ()


def critic_store() -> Store:
    from Harness.tests.fakes import make_snapshot  # critic_eval 과 같은 가상 가게

    snapshot = make_snapshot()
    return Store(snapshot.store_id, dict(snapshot.store), tuple(menu.name for menu in snapshot.inputs.menus))


def gold_store() -> Store:
    store = json.loads(S005_FIXTURE.read_text(encoding="utf-8"))["store"]
    return Store(store["id"], {"name": store["name"], "category": store["category"]},
                 tuple(menu["name"] for menu in store.get("menus", [])))


def critic_cases(path: Path = CRITIC_CASES_PATH) -> list[dict]:
    rows = []
    for case in json.loads(Path(path).read_text(encoding="utf-8"))["cases"]:
        kinds = [CRITIC_KINDS[kind] for kind in case.get("expected_kinds", [])]
        complaints = list(case["review"].get("complaints") or [])
        rows.append({
            "case_id": f"critic:{case['id']}", "set": "critic_cases", "kind": kinds[0] if kinds else "normal",
            "kinds": kinds, "expected_ok": case["expected_ok"], "verified": True, "store": "t001",
            "text": case["review"]["text"], "reply": case["reply"], "has_complaint": bool(complaints),
            "regular": case.get("regular", False), "owner_instruction": case.get("owner_instruction"),
            "store_facts": list(case.get("store_facts", [])), "sentiment": None, "complaint_types": complaints,
            "note": case.get("note", ""),
        })
    return rows


def _gold_row(row: dict, set_name: str) -> dict:
    types = row["gold"]["complaint_types"]
    return {
        "case_id": row["case_id"], "set": set_name, "kind": row["kind"], "kinds": [] if row["expected_ok"] else [row["kind"]],
        "expected_ok": row["expected_ok"], "verified": row.get("verified", True), "store": "s005",
        "text": row["text"], "reply": row["reply"], "has_complaint": bool(types), "regular": False,
        "owner_instruction": None, "store_facts": [], "sentiment": SENTIMENT_KO.get(row["gold"]["sentiment"]),
        "complaint_types": [COMPLAINT_KO.get(t, t) for t in types], "source_case_id": row["source_case_id"],
        "good_reply": row.get("good_reply"), "inserted": row.get("inserted"), "swapped_from": row.get("swapped_from"),
    }


def gold_cases(cases: list[dict], *, seed: int = derive.SEED) -> dict[str, list[dict]]:
    """정답지 사례 → normal, violation 판정 세트."""
    templates = derive.load_templates()
    return {"normal": [_gold_row(row, "normal") for row in derive.normal_set(cases, seed=seed)],
            "violation": [_gold_row(row, "violation") for row in derive.violation_set(cases, templates, seed=seed)]}


# ── 판정기 ──


@dataclass
class Judgement:
    ok: bool | None  # True 통과, False 거절, None 판단 불가
    detected: list[str] = field(default_factory=list)  # 댄 위반 종류
    why: list[str] = field(default_factory=list)
    verdicts: dict = field(default_factory=dict)  # 심판의 조건별 판정 (Verdict.as_dict)
    calls: int = 0
    tokens: tuple[int, int] = (0, 0)
    seconds: float = 0.0
    error: str | None = None


def judge_regex(case: dict, store: Store, post=None) -> Judgement:
    reply = case["reply"]
    detected, why = [], []
    for kind, hit in (("compensation", guards.promise_hit(reply)), ("fabricated", guards.MADE_UP_FACT_RE.search(reply)),
                      ("memory", guards.MEMORY_RE.search(reply))):
        if hit:
            detected.append(kind)
            why.append(f"{kind} '{hit.group(0)}'")
    reason = rejection_reason(reply)
    if reason and not detected:  # 보상·사정·기억 말고 형식(길이, 빈칸)에 걸린 것
        detected.append("format")
        why.append(reason)
    return Judgement(ok=not detected, detected=detected, why=why)


def judge_critic(case: dict, store: Store, post=None) -> Judgement:
    from Harness.agents import reply_critic
    from Harness.spec import RunContext
    from Harness.tests.fakes import NOW

    counting = report.CountingPost(post) if post is not None else report.CountingPost()
    ctx = RunContext(snapshot=store, now=NOW, post=counting, store_facts=list(case["store_facts"]))
    verdict = reply_critic.inspect(case["reply"], ctx, review_text=case["text"], has_complaint=case["has_complaint"],
                                   regular=case["regular"], owner_instruction=case["owner_instruction"])
    tokens = tuple(counting.tokens)
    if verdict is None:
        return Judgement(ok=None, calls=counting.calls, tokens=tokens, error="검토 호출 실패 (리뷰와 상관없는 말 질문)")
    return Judgement(ok=verdict.ok, detected=list(dict.fromkeys(CRITIC_KINDS[v.kind] for v in verdict.violations)),
                     why=[v.describe() for v in verdict.violations], calls=counting.calls, tokens=tokens)


def judge_input(case: dict, store: Store) -> judge.JudgeInput:
    return judge.JudgeInput(review_text=case["text"], reply=case["reply"], category=store.store.get("category", ""),
                            sentiment=case["sentiment"], complaint_types=list(case["complaint_types"]),
                            menus=list(store.menus), store_facts=list(case["store_facts"]),
                            owner_instruction=case["owner_instruction"])


def combine(verdicts: dict[str, judge.Verdict]) -> tuple[bool | None, list[str]]:
    """조건별 판정 → (통과 여부, 거절한 조건). 하나라도 아니오면 거절, 아니오 없이 판단 불가가 있으면 판단 불가."""
    failed = [name for name, verdict in verdicts.items() if verdict.ok is False]
    if failed:
        return False, failed
    if any(verdict.ok is None for verdict in verdicts.values()):
        return None, []
    return True, []


def make_judge_llm(mode: str) -> Callable[..., Judgement]:
    def run(case: dict, store: Store, post=None) -> Judgement:
        options = {"mode": mode, "store_id": store.store_id}
        if post is not None:
            options["post"] = post
        verdicts = judge.judge_all(judge_input(case, store), judge.REPLY_CONDITIONS, **options)
        ok, failed = combine(verdicts)
        detected = sorted({kind for name in failed for kind in CONDITION_KINDS.get(name, ())}, key=KIND_ORDER.index)
        why = [f"{name}: {verdicts[name].quotes or [v.reason for v in verdicts[name].votes if v.ok is False][:1]}" for name in failed]
        calls = sum(verdict.calls for verdict in verdicts.values())
        tokens = [sum(verdict.tokens[i] for verdict in verdicts.values()) for i in range(2)]
        return Judgement(ok=ok, detected=detected, why=why, verdicts={n: v.as_dict() for n, v in verdicts.items()},
                         calls=calls, tokens=tuple(tokens), error=None if ok is not None else "판단 불가 조건이 있음")
    return run


RUNNERS: dict[str, Callable[..., Judgement]] = {
    "regex": judge_regex, "critic": judge_critic,
    "judge_tools": make_judge_llm("tools"), "judge_thinking": make_judge_llm("thinking"),
}


def timed(name: str, case: dict, store: Store, post=None) -> Judgement:
    """판정 하나. 오류가 나도 나머지 사례는 계속 잰다 (심판 모델 오류 JudgeModelError 만 멈춘다)."""
    started = time.perf_counter()
    guarded = GuardedPost(post, deadline=SYSTEM_DEADLINE_SECONDS.get(name, CASE_DEADLINE_SECONDS)) if name != "regex" else post
    try:
        result = RUNNERS[name](case, store, guarded)
    except judge.JudgeModelError:
        raise
    except CaseAborted as exc:
        result = Judgement(ok=None, calls=guarded.calls, error=str(exc))
    except Exception as exc:
        result = Judgement(ok=None, error=f"{type(exc).__name__}: {exc}")
    result.seconds = round(time.perf_counter() - started, 3)
    return result


# ── 채점 (순수 함수) ──


def outcome(expected_ok: bool, got_ok: bool | None) -> str:
    if got_ok is None:
        return "unknown"
    if expected_ok:
        return "pass" if got_ok else "false_reject"
    return "missed" if got_ok else "caught"


def right_reason(case: dict, detected: list[str]) -> bool | None:
    """위반을 잡은 까닭이 기대한 종류와 맞는지. 잡지 못했거나 정상이면 None."""
    if case["expected_ok"] or not detected:
        return None
    wanted = set().union(*(SAME_REASON.get(kind, {kind}) for kind in case["kinds"])) if case["kinds"] else set()
    return bool(wanted & set(detected))


def case_row(name: str, run: int, case: dict, result: Judgement) -> dict:
    return {
        "case_id": case["case_id"], "system": name, "run": run, "run_id": None, "source": None, "set": case["set"],
        "kind": case["kind"], "kinds": case["kinds"], "expected_ok": case["expected_ok"], "verified": case["verified"],
        "text": case["text"], "output": case["reply"], "got_ok": result.ok, "outcome": outcome(case["expected_ok"], result.ok),
        "detected": result.detected, "right_reason": right_reason(case, result.detected) if result.ok is False else None,
        "why": result.why, "verdicts": result.verdicts, "fit": result.ok == case["expected_ok"],
        "calls": result.calls, "tokens": list(result.tokens), "seconds": result.seconds, "error": result.error,
    }


def _in_set(row: dict, set_name: str) -> bool:
    return set_name == "all" or row["set"] == set_name or (set_name == "gold" and row["set"] in ("normal", "violation"))


def _rate(id: str, name: str, system: str, set_name: str, numerator: int, denominator: int, *, higher: bool,
          note: str = "") -> dict:
    row = metrics.metric(id, name, question=QUESTION, system=system, numerator=numerator, denominator=denominator,
                         higher_is_better=higher, note=note)
    return {**row, "set": set_name}


def by_kind(rows: list[dict]) -> dict[str, dict[str, int]]:
    """종류마다 {total, missed, caught, unknown, false_reject, pass}. 정상은 kind normal 한 칸에 모은다."""
    table: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        for kind in (row["kinds"] or ["normal"]):
            table[kind]["total"] += 1
            table[kind][row["outcome"]] += 1
    order = ("normal", *KIND_ORDER)
    return {kind: dict(table[kind]) for kind in sorted(table, key=lambda k: order.index(k) if k in order else len(order))}


def vote_split(rows: list[dict]) -> list[str]:
    """심판 판정 안에서 3표가 갈린 조건이 있는 사례 (회차 구분 없이)."""
    return sorted({row["case_id"] for row in rows
                   if any(len(set(verdict["vote"])) > 1 for verdict in (row.get("verdicts") or {}).values())})


def flaky(rows: list[dict]) -> list[str]:
    """회차마다 판정(got_ok)이 달랐던 사례."""
    seen: dict[str, set] = defaultdict(set)
    for row in rows:
        seen[row["case_id"]].add(row["got_ok"])
    runs = Counter(row["case_id"] for row in rows)
    return sorted(case_id for case_id, values in seen.items() if runs[case_id] > 1 and len(values) > 1)


def summarize(name: str, rows: list[dict]) -> dict:
    counts = Counter(row["outcome"] for row in rows)
    bad = sum(1 for row in rows if not row["expected_ok"])
    seconds = [row["seconds"] for row in rows]
    return {"missed": counts["missed"], "bad_total": bad, "false_reject": counts["false_reject"],
            "good_total": len(rows) - bad, "unknown": counts["unknown"], "total": len(rows),
            "latency_median": statistics.median(seconds) if seconds else None, "vote_split": len(vote_split(rows))}


def score(name: str, rows: list[dict]) -> list[dict]:
    """판정기 하나의 지표 줄들."""
    out = []
    for set_name in ("critic_cases", "gold", "all"):
        chosen = [row for row in rows if _in_set(row, set_name)]
        if not chosen:
            continue
        s = summarize(name, chosen)
        unverified = any(not row["verified"] for row in chosen if row["expected_ok"])
        note = "정상 답글은 사람 확인 전(unverified)" if unverified else ""
        out.append(_rate("missed_rate", "놓침률", name, set_name, s["missed"], s["bad_total"], higher=False))
        out.append(_rate("false_reject_rate", "오거절률", name, set_name, s["false_reject"], s["good_total"], higher=False,
                         note=note))
        out.append(_rate("unknown_rate", "판단 불가 비율", name, set_name, s["unknown"], s["total"], higher=False))
        caught = [row for row in chosen if row["outcome"] == "caught"]
        out.append(_rate("right_reason_rate", "잡은 위반 중 까닭이 맞은 비율", name, set_name,
                         sum(1 for row in caught if row["right_reason"]), len(caught), higher=True))
    for kind, cells in by_kind(rows).items():
        if kind == "normal":
            continue
        out.append(_rate(f"missed_rate:{kind}", f"놓침률 ({kind})", name, "all", cells.get("missed", 0), cells["total"],
                         higher=False, note=f"판단 불가 {cells.get('unknown', 0)}"))
    lat = metrics.latency([row["seconds"] for row in rows])
    out.append({**metrics.value_metric("latency_median", "판정 시간 중앙값", question=QUESTION, system=name,
                                       value=lat["median"], unit="seconds"), "set": "all"})
    out.append({**metrics.value_metric("latency_max", "판정 시간 최댓값", question=QUESTION, system=name,
                                       value=lat["max"], unit="seconds"), "set": "all"})
    calls = [row["calls"] for row in rows]
    out.append({**metrics.value_metric("calls_per_case", "사례당 CLOVA 호출 수", question=QUESTION, system=name,
                                       value=statistics.fmean(calls) if calls else None, unit="calls"), "set": "all"})
    shaky = flaky(rows)
    out.append({**metrics.value_metric("flaky_cases", "회차마다 판정이 달랐던 사례", question=QUESTION, system=name,
                                       value=len(shaky), unit="cases", note=", ".join(shaky[:12]) + (" …" if len(shaky) > 12 else "")),
                "set": "all"})
    if any(row.get("verdicts") for row in rows):
        split = vote_split(rows)
        out.append({**metrics.value_metric("vote_split_cases", "판정 안에서 3표가 갈린 사례", question=QUESTION, system=name,
                                           value=len(split), unit="cases",
                                           note=", ".join(split[:12]) + (" …" if len(split) > 12 else "")), "set": "all"})
    return out


def critic_target(rows: list[dict]) -> dict:
    """critic 의 기준(놓침 0, 오거절 10% 이하)을 세트마다 본다."""
    result = {}
    for set_name in ("critic_cases", "gold", "all"):
        chosen = [row for row in rows if _in_set(row, set_name)]
        if not chosen:
            continue
        s = summarize("critic", chosen)
        rate = metrics.ratio(s["false_reject"], s["good_total"])
        result[set_name] = {"missed": s["missed"], "false_reject_rate": rate,
                            "pass": s["missed"] <= CRITIC_TARGET_MISSED and rate is not None and rate <= CRITIC_TARGET_FALSE_REJECT}
    return result


def recommend_judge_mode(judges: dict[str, dict]) -> dict | None:
    """놓침이 적은 방식, 같으면 오거절이 적은 방식, 그래도 같으면 빠른 방식."""
    if not judges:
        return None

    def key(item):
        _, s = item
        return (s["missed"], s["false_reject"], s["unknown"], s["latency_median"] if s["latency_median"] is not None else float("inf"))

    ranked = sorted(judges.items(), key=key)
    best = ranked[0]
    tie = len(ranked) > 1 and key(ranked[0])[:3] == key(ranked[1])[:3]
    return {"mode": best[0], "order": [mode for mode, _ in ranked],
            "basis": "놓침·오거절·판단 불가가 같아 빠른 쪽" if tie else "놓침 → 오거절 → 판단 불가 → 시간 순"}


# ── 실행 ──


def _runs_of(runs: int | dict[str, int], name: str) -> int:
    return runs.get(name, 1) if isinstance(runs, dict) else runs


def planned_calls(cases: list[dict], names: list[str], runs: int | dict[str, int]) -> dict[str, dict]:
    """예상 호출 수 {판정기: {runs, typical, max}}. typical 은 다시 묻지 않는다고 본 값. runs 는 수 하나 또는 판정기마다."""
    plan = {}
    for name in names:
        if name == "regex":
            plan[name] = {"runs": _runs_of(runs, name), "typical": 0, "max": 0}
            continue
        typical = maximum = 0
        for case in cases:
            if name == "critic":
                stages = [s for s in CRITIC_STAGES if s != "no_fix" or case["has_complaint"]]
                stop = next((stages.index(k) for k in stages if k in (case["kinds"] or [])), len(stages) - 1)
                asks = stop + 1 + (1 if case["owner_instruction"] else 0)
                typical += asks
                maximum += (len(stages) + (1 if case["owner_instruction"] else 0)) * 2
            else:
                typical += len(judge.REPLY_CONDITIONS) * judge.VOTES
                maximum += len(judge.REPLY_CONDITIONS) * judge.VOTES * judge.MAX_ATTEMPTS
        n = _runs_of(runs, name)
        plan[name] = {"runs": n, "typical": typical * n, "max": maximum * n}
    return plan


def evaluate(cases: list[dict], stores: dict[str, Store], names: list[str], *, runs: int | dict[str, int] = 1,
             workers: int = 1, post=None, concurrency: dict[str, int] | None = None,
             on_case: Callable[[str, int, dict], None] | None = None,
             on_system: Callable[[str, list[dict]], None] | None = None,
             done: list[dict] | None = None) -> dict:
    """판정하고 채점한다. {"metrics", "cases", "by_kind", "flaky", "critic_target", "judge"}.
    done 은 이미 끝난 줄 (이어 돌리기). 그 (판정기, 회차, 사례)는 다시 판정하지 않는다.
    concurrency 는 판정기마다 CLOVA 동시 호출 (그 판정기를 도는 동안만 limiter 를 바꾸고, 일꾼 수도 그 이하로 줄인다.
    줄이지 않으면 자리를 기다리는 동안 사례 제한 시간이 흐른다)."""
    finished = defaultdict(list)
    for row in done or []:
        finished[row["system"]].append(row)
    all_rows, all_metrics, kinds, shaky = [], [], {}, {}
    target, judges = None, {}
    for name in names:
        rows: list[dict] = list(finished[name])
        skip = {(row["run"], row["case_id"]) for row in rows}
        lock = threading.Lock()

        def one(run: int, case: dict) -> None:
            row = case_row(name, run, case, timed(name, case, stores[case["store"]], post))
            with lock:
                rows.append(row)
            if on_case:
                on_case(name, run, row)

        jobs = [(run, case) for run in range(1, _runs_of(runs, name) + 1) for case in cases
                if (run, case["case_id"]) not in skip]
        limit = (concurrency or {}).get(name)
        saved_limit = limiter.MAX_CONCURRENT
        n_workers = min(workers, limit) if limit else workers
        if limit:
            limiter.set_max_concurrent(limit)
        try:
            if name == "regex" or n_workers <= 1:
                for run, case in jobs:
                    one(run, case)
            else:
                with ThreadPoolExecutor(max_workers=n_workers) as pool:  # CLOVA 동시 호출은 limiter 가 막는다
                    for future in [pool.submit(one, run, case) for run, case in jobs]:
                        future.result()
        finally:
            if limit:
                limiter.set_max_concurrent(saved_limit)
        rows.sort(key=lambda r: (r["run"], r["case_id"]))
        all_rows.extend(rows)
        all_metrics.extend(score(name, rows))
        kinds[name] = by_kind(rows)
        shaky[name] = flaky(rows)
        if name == "critic":
            target = critic_target(rows)
        if name in JUDGE_MODES:
            judges[JUDGE_MODES[name]] = summarize(name, rows)
        if on_system:
            on_system(name, rows)
    return {"metrics": all_metrics, "cases": all_rows, "by_kind": kinds, "flaky": shaky, "critic_target": target,
            "judge": judges}


def build_cases(args: argparse.Namespace) -> tuple[list[dict], dict[str, list[dict]], tuple]:
    """(판정할 사례, 세트별 사례, (정답지 경로, sha256))."""
    path, sha, gold_rows = gold.from_args(args)
    sets = {"critic_cases": critic_cases(), **gold_cases(gold_rows)}
    cases = [case for name in SETS for case in sets[name]]
    if args.ids:
        wanted = {part for part in args.ids.split(",") if part}
        unknown = wanted - {case["case_id"] for case in cases}
        if unknown:
            raise SystemExit(f"세트에 없는 id: {', '.join(sorted(unknown))}")
        cases = [case for case in cases if case["case_id"] in wanted]
    return cases, sets, (path, sha)


def print_plan(cases: list[dict], names: list[str], runs: int | dict[str, int], concurrency: int | dict[str, int]) -> dict:
    counts = Counter(case["set"] for case in cases)
    by_system = concurrency if isinstance(concurrency, dict) else {name: concurrency for name in names}
    shown = ", ".join(f"{name} {by_system[name]}" for name in names if name != "regex")
    print(f"사례 {len(cases)}건 ({', '.join(f'{k} {v}' for k, v in counts.items())}), CLOVA 동시 호출 {shown or '-'}")
    plan = planned_calls(cases, names, runs)
    for name, p in plan.items():
        seconds = p["typical"] * SECONDS_PER_CALL.get(name, 0) / max(1, by_system.get(name, 1))
        p["seconds"] = round(seconds)
        print(f"  {name:15s} 회차 {p['runs']}  예상 호출 {p['typical']:6d} (최대 {p['max']:6d}), 예상 {seconds / 60:5.0f}분")
    return plan


def run(args: argparse.Namespace):
    """python -m Harness.evals guards --systems regex,critic,judge_tools,judge_thinking --runs 3"""
    names = args.system_names
    try:
        runs = parse_system_runs(getattr(args, "system_runs", ""), names, args.runs)
        concurrency = parse_system_concurrency(getattr(args, "system_concurrency", ""), names, args.concurrency)
    except JudgeUnavailable as error:
        raise SystemExit(str(error)) from None
    args.concurrency_by_system = concurrency
    cases, sets, (path, sha) = build_cases(args)
    plan = print_plan(cases, names, runs, concurrency)
    if args.dry_run:
        return plan
    restore_cache = report.disable_cache()  # 같은 답글을 3번 판정해도 매번 새로 부르게. 끝나면 되돌린다
    try:
        return _run(args, names, runs, cases, sets, path, sha, plan)
    finally:
        restore_cache()


CASES_JSONL = "cases.jsonl"


def read_jsonl(path: Path) -> list[dict]:
    """cases.jsonl 을 읽는다. 끊길 때 반쯤 쓴 마지막 줄은 버린다."""
    rows = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


TRANSIENT_HTTP = ("HTTP 429", "HTTP 5")  # 다시 부르면 될 수 있는 응답 (한도 초과, 서버 오류)


def _vote_errors(row: dict) -> list[str]:
    return [str(e) for verdict in (row.get("verdicts") or {}).values() if isinstance(verdict, dict)
            for e in verdict.get("errors") or []]


def retryable(row: dict) -> bool:
    """--resume 때 다시 판정할 줄: 연결 실패, 사례 제한 시간 초과, 그리고 표가 429·5xx·연결·시간 초과로 판단 불가가 된 줄.
    예전 기록은 표 오류가 까닭 없이 '호출 실패' 뿐이다. 400·404 는 모델 오류로 멈추므로 남은 '호출 실패'는 거의 429 라 다시 판정한다."""
    error = str(row.get("error") or "")
    if error.startswith(CONNECTION_FAILED) or "제한 시간" in error:
        return True
    if row.get("outcome") != "unknown":
        return False
    for text in _vote_errors(row):
        if not text.startswith(judge.CALL_FAILED):
            continue
        if text == judge.CALL_FAILED or "연결·시간 초과" in text or any(code in text for code in TRANSIENT_HTTP):
            return True
    return False


def resumable(rows: list[dict]) -> list[dict]:
    """다시 판정하지 않을 줄: 다시 부르면 될 까닭(retryable)으로 판단 불가가 된 줄은 빼고, 같은 (판정기, 회차, 사례)는 마지막 줄만."""
    keep = {}
    for row in rows:
        key = (row["system"], row["run"], row["case_id"])
        if retryable(row):
            keep.pop(key, None)
        else:
            keep[key] = row
    return list(keep.values())


def reopen(out: Path, config: dict, names: list[str], sets: dict[str, list[dict]]) -> tuple[report.EvalRun, list[dict]]:
    """--resume: 예전 결과 폴더를 다시 연다. 세트 해시가 다르면 멈춘다."""
    result = out / "result.json"
    if not result.exists():
        raise SystemExit(f"이어 돌릴 결과 폴더가 아니에요 (result.json 없음): {out}")
    previous = json.loads(result.read_text(encoding="utf-8"))
    old_sets = previous.get("config", {}).get("gold", {}).get("sets", {})
    changed = [name for name, rows in sets.items()
               if old_sets.get(name) not in (None, derive.sha256_of(rows))]
    if changed:
        raise SystemExit(f"세트가 바뀌어 이어 돌릴 수 없어요: {', '.join(changed)} (새로 돌리세요)")
    run = report.reopen(out, previous, systems=names)
    run.config.update({key: value for key, value in config.items() if key != "gold"})
    run.config["resumed"] = int(run.config.get("resumed") or 0) + 1
    rows = read_jsonl(out / CASES_JSONL)
    # 반쯤 쓴 마지막 줄을 지우고 다시 쓴다 (그 뒤에 덧붙이면 새 줄까지 깨진다)
    (out / CASES_JSONL).write_text("".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows),
                                   encoding="utf-8")
    return run, resumable(rows)


def _run(args, names, runs, cases, sets, path, sha, plan):
    prompts = sorted(CRITIC_PROMPTS.glob("*_judge.txt")) + sorted(judge.PROMPTS_DIR.glob("*.txt"))
    config = {"model": settings.clova_studio_model, "judge_model": settings.eval_judge_model, "judge_votes": judge.VOTES,
              "runs": runs, "concurrency": args.concurrency, "workers": args.workers,
              "system_concurrency": getattr(args, "concurrency_by_system", {}), "rate_limit_retries": GUARDS_RATE_LIMIT_RETRIES,
              "judge_modes": [JUDGE_MODES[n] for n in names if n in JUDGE_MODES], "judge_gold_reply": False,
              "gold_verified": False, "normal_verified": False, "sets": dict(Counter(case["set"] for case in cases)),
              "planned_calls": plan, "prompts": report.prompt_hashes(prompts)}
    resume = getattr(args, "resume", None)
    if resume:
        eval_run, done = reopen(Path(resume), config, names, sets)
        print(f"이어 돌리기: {eval_run.out} (끝난 판정 {len(done)}줄)", flush=True)
    else:
        eval_run, done = report.start("guards", config=config, systems=names), []
        print(f"결과 폴더: {eval_run.out}", flush=True)
        hashes = {name: derive.write_set(eval_run.out, f"guards_{name}", rows) for name, rows in sets.items()}
        eval_run.config["gold"] = gold.config_entry(path, sha, hashes)
    jsonl = eval_run.out / CASES_JSONL
    write_lock = threading.Lock()
    stores = {"t001": critic_store(), "s005": gold_store()}
    count = Counter(row["system"] for row in done)
    total = {name: len(cases) * n for name, n in runs.items()}

    def on_case(name: str, run_no: int, row: dict) -> None:
        with write_lock, jsonl.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        count[name] += 1
        if row["outcome"] in ("missed", "false_reject", "unknown") or count[name] % 20 == 0 or count[name] == total[name]:
            print(f"  [{name} {count[name]}/{total[name]}] {row['case_id']} 회차{run_no} {row['outcome']} {row['seconds']}초",
                  flush=True)

    partial: dict = {"metrics": [], "cases": [], "by_kind": {}, "flaky": {}, "judge": {}}

    waits_before = [limiter.rate_limit_snapshot()]

    def on_system(name: str, rows: list[dict]) -> None:
        # 판정기 하나가 끝날 때마다 result.json 을 쓴다 (긴 실행이 중간에 멈춰도 끝난 것은 남는다)
        now = limiter.rate_limit_snapshot()  # 판정기는 차례로 돌아서 앞뒤 차이가 그 판정기의 429 기다림이다
        waited = {"waits": now["waits"] - waits_before[0]["waits"], "seconds": round(now["seconds"] - waits_before[0]["seconds"], 1)}
        waits_before[0] = now
        eval_run.config.setdefault("rate_limit_waits", {})[name] = waited
        if limiter.first_rate_limit_headers is not None:
            eval_run.config["rate_limit_headers"] = limiter.first_rate_limit_headers
        if waited["waits"]:
            print(f"  {name}: 429 기다림 {waited['waits']}번, {waited['seconds']}초", flush=True)
        partial["metrics"].extend(score(name, rows))
        partial["cases"].extend(rows)
        partial["by_kind"][name] = by_kind(rows)
        partial["flaky"][name] = flaky(rows)
        if name == "critic":
            eval_run.validation["critic_target"] = critic_target(rows)
        if name in JUDGE_MODES:
            partial["judge"][JUDGE_MODES[name]] = summarize(name, rows)
            eval_run.validation["judge"] = partial["judge"]
            eval_run.validation["judge_mode_recommendation"] = recommend_judge_mode(partial["judge"])
        eval_run.metrics, eval_run.cases = list(partial["metrics"]), list(partial["cases"])
        eval_run.tables.update({"by_kind": partial["by_kind"], "flaky": partial["flaky"]})
        eval_run.config["finished_systems"] = list(partial["by_kind"])
        eval_run.finish()
        print(f"  {name} 끝 ({sum(row['seconds'] for row in rows):.0f}초 합)", flush=True)

    saved_retries = limiter.RATE_LIMIT_RETRIES
    limiter.RATE_LIMIT_RETRIES = GUARDS_RATE_LIMIT_RETRIES
    try:
        evaluate(cases, stores, names, runs=runs, workers=args.workers, on_case=on_case, on_system=on_system, done=done,
                 concurrency=getattr(args, "concurrency_by_system", None))
    finally:
        limiter.RATE_LIMIT_RETRIES = saved_retries
    out = eval_run.finish()
    print(f"result.json: {out}")
    return out
