"""noise 스위트: 모의 받아쓰기 오류 강도별 뜻 판정. 오디오는 쓰지 않는다.

뜻 판정 세트(intent 스위트와 같은 Harness/evals/data/intents_v1.json)의 말마다 받아쓰기 오류를 규칙으로 넣고,
강도 0/1/2/3 에서 intent 스위트와 같은 채점(intent_eval.score)을 한다. 강도 k 는 오류 k 개다.
같은 말의 강도 k 글자는 강도 k-1 글자에 오류 하나를 더한 것이라(같은 seed) 강도가 오를수록 글자가 더 망가진다.
앞 강도의 글자로 되돌아가는 바꿈(띄어쓰기를 넣었다가 다시 지우기 등)은 고르지 않는다.
결과를 보일 때는 실제 소음 음성이 아니라 "모의 받아쓰기 오류"라고 밝힌다.

오류 종류 (corrupt_once 가 쓸 수 있는 것 중 하나를 고른다)
  jamo       글자 하나의 자모를 비슷한 소리로 바꿈 (ㅂ↔ㅃ↔ㅍ, ㅐ↔ㅔ, ㅓ↔ㅗ, 받침 빠짐·ㄴ↔ㅇ 등)
  spacing    띄어쓰기 하나를 지우거나 한글 두 글자 사이에 하나 넣음
  ending     낱말 끝 조사·어미 한 글자를 뺌 ("보여 줘요" → "보여 줘")
  sound      비슷한 소리 낱말로 바꿈 (브리핑→부리핑, 다음→다은, 도나→또나 같은 호출어 변형 포함)

시스템은 intent 스위트와 같다 (rule, rule+judge). 지표 줄마다 noise(강도)를 붙인다.
--levels 0,1,2,3 (기본), --dry-run 이면 강도마다 판정 에이전트를 부를 말 수(예상 CLOVA 호출 수)만 보여 준다.
"""

import argparse
import hashlib
import random

from app.core.config import settings
from Harness.evals import intent_eval, report

SEED = 14
LEVELS = (0, 1, 2, 3)

CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = ("", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ",
        "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ")
CHO_GROUPS = ("ㄱㄲㅋ", "ㄷㄸㅌ", "ㅂㅃㅍ", "ㅈㅉㅊ", "ㅅㅆ")
JUNG_GROUPS = ("ㅐㅔ", "ㅓㅗ", "ㅡㅜ", "ㅢㅣ", "ㅚㅙㅞ", "ㅕㅛ", "ㅒㅖ")
JONG_SWAPS = {"ㄴ": "ㅇ", "ㅇ": "ㄴ", "ㅁ": "ㅇ"}
ENDINGS = set("요줘은는이가을를에도")
SOUND_ALIKE = {
    "브리핑": ("부리핑", "뿌리핑", "브리펑"), "다음": ("다은", "따음"), "리뷰": ("이뷰", "리부"), "매출": ("매추", "메출"),
    "예약": ("얘약", "예야"), "해 줘": ("해조", "해죠"), "해줘": ("해조", "해죠"), "그만": ("금만", "그마"),
    "처음부터": ("첨부터", "처음부더"), "다시": ("다쉬", "타시"), "설정": ("설증", "설쩡"), "화면": ("화멘", "하면"),
    "읽어": ("일거", "익어"), "날씨": ("날시", "랄씨"), "도나": ("돈아", "또나", "토나"), "아쉬운": ("아수운", "아쉰"),
    "자세히": ("자세이", "자쎄히"), "테이블": ("테블", "테이브"), "손님": ("손니", "송님"), "그렇게": ("그러케", "그렇개"),
    "넘어가": ("너머가", "넘가"),
}


def _is_syllable(ch: str) -> bool:
    return "가" <= ch <= "힣"


def _split(ch: str) -> tuple[int, int, int]:
    code = ord(ch) - 0xAC00
    return code // 588, (code % 588) // 28, code % 28


def _join(cho: int, jung: int, jong: int) -> str:
    return chr(0xAC00 + cho * 588 + jung * 28 + jong)


def _jamo_choices(ch: str) -> list[str]:
    """글자 하나를 비슷한 소리로 바꾼 후보들."""
    cho, jung, jong = _split(ch)
    out = []
    for group in CHO_GROUPS:
        if CHO[cho] in group:
            out += [_join(CHO.index(c), jung, jong) for c in group if c != CHO[cho]]
    for group in JUNG_GROUPS:
        if JUNG[jung] in group:
            out += [_join(cho, JUNG.index(v), jong) for v in group if v != JUNG[jung]]
    if jong:
        out.append(_join(cho, jung, 0))
        if JONG[jong] in JONG_SWAPS:
            out.append(_join(cho, jung, JONG.index(JONG_SWAPS[JONG[jong]])))
    return out


def _jamo(text: str, rng: random.Random) -> str | None:
    spots = [i for i, ch in enumerate(text) if _is_syllable(ch) and _jamo_choices(ch)]
    if not spots:
        return None
    i = rng.choice(spots)
    return text[:i] + rng.choice(_jamo_choices(text[i])) + text[i + 1:]


def _spacing(text: str, rng: random.Random) -> str | None:
    spaces = [i for i, ch in enumerate(text) if ch == " "]
    joins = [i for i in range(1, len(text)) if _is_syllable(text[i - 1]) and _is_syllable(text[i])]
    choices = [("drop", i) for i in spaces] + [("add", i) for i in joins]
    if not choices:
        return None
    kind, i = rng.choice(choices)
    return text[:i] + text[i + 1:] if kind == "drop" else text[:i] + " " + text[i:]


def _ending(text: str, rng: random.Random) -> str | None:
    words = text.split(" ")
    spots = [i for i, word in enumerate(words) if len(word) > 1 and word[-1] in ENDINGS]
    if not spots:
        return None
    i = rng.choice(spots)
    words[i] = words[i][:-1]
    return " ".join(words)


def _sound(text: str, rng: random.Random) -> str | None:
    found = [word for word in SOUND_ALIKE if word in text]
    if not found:
        return None
    word = rng.choice(found)
    return text.replace(word, rng.choice(SOUND_ALIKE[word]), 1)


KINDS = {"jamo": _jamo, "spacing": _spacing, "ending": _ending, "sound": _sound}


ATTEMPTS = 8  # 오류 하나를 고르려고 해 보는 횟수


def corrupt_once(text: str, rng: random.Random, seen: set[str] = frozenset()) -> tuple[str, str | None]:
    """(바뀐 글자, 오류 종류). seen(앞 강도의 글자)으로 되돌아가는 바꿈은 고르지 않는다. 못 넣으면 (그대로, None)."""
    for _ in range(ATTEMPTS):
        for kind in rng.sample(list(KINDS), len(KINDS)):
            changed = KINDS[kind](text, rng)
            if changed and changed.strip() and changed != text and changed not in seen:
                return changed, kind
    return text, None


def corrupt_levels(text: str, key: str, levels: int = max(LEVELS), seed: int = SEED) -> list[tuple[str, list[str]]]:
    """강도 0..levels 의 (글자, 지금까지 넣은 오류 종류들). key(사례 id)와 seed 가 같으면 늘 같다."""
    rng = random.Random(int(hashlib.sha256(f"{seed}:{key}".encode("utf-8")).hexdigest()[:16], 16))
    out = [(text, [])]
    for _ in range(levels):
        previous, kinds = out[-1]
        changed, kind = corrupt_once(previous, rng, {text for text, _ in out})
        out.append((changed, kinds + ([kind] if kind else [])))
    return out


def noisy_cases(cases: list[dict], level: int, seed: int = SEED) -> list[dict]:
    """사례마다 강도 level 의 글자로 바꾼 사본. 원래 글자는 clean_text, 넣은 오류는 noise_kinds 에 남긴다."""
    out = []
    for case in cases:
        text, kinds = corrupt_levels(case["text"], case["id"], level, seed)[level]
        out.append({**case, "text": text, "clean_text": case["text"], "noise": level, "noise_kinds": kinds})
    return out


def parse_levels(text: str) -> list[int]:
    try:
        levels = sorted({int(part) for part in text.split(",") if part.strip()})
    except ValueError:
        levels = []
    if not levels or any(level not in LEVELS for level in levels):
        raise SystemExit(f"--levels 는 {','.join(map(str, LEVELS))} 중에서 쉼표로 골라요 (받은 값: {text!r})")
    return levels


def evaluate(cases: list[dict], names: list[str], levels: list[int], *, runs: int = 1, seed: int = SEED, post=None) -> dict:
    """강도마다 intent_eval.evaluate 를 돌리고 지표·줄에 noise 를 붙인다."""
    rows, out, calls = [], [], 0
    for level in levels:
        noisy = noisy_cases(cases, level, seed)
        by_id = {case["id"]: case for case in noisy}
        result = intent_eval.evaluate(noisy, names, runs=runs, post=post)
        calls += result["calls"]
        for row in result["cases"]:
            case = by_id[row["case_id"]]
            rows.append({**row, "noise": level, "clean_text": case["clean_text"], "noise_kinds": case["noise_kinds"]})
        out += [{**metric, "noise": level, "name": f"{metric['name']} (모의 받아쓰기 오류 강도 {level})"}
                for metric in result["metrics"]]
    return {"metrics": out, "cases": rows, "calls": calls}


def planned_calls(cases: list[dict], names: list[str], levels: list[int], runs: int, seed: int = SEED) -> dict:
    """{강도: {시스템: {typical, max}}}. 강도가 오를수록 규칙이 못 가르는 말이 늘어 호출이 는다."""
    return {level: intent_eval.planned_calls(noisy_cases(cases, level, seed), names, runs) for level in levels}


def run(args: argparse.Namespace):
    """python -m Harness.evals noise [--systems rule,rule+judge] [--levels 0,1,2,3] [--runs 1] [--dry-run]"""
    names = args.system_names
    levels = parse_levels(getattr(args, "levels", None) or ",".join(map(str, LEVELS)))
    body, cases = intent_eval.load_cases()
    if args.ids:
        wanted = {part for part in args.ids.split(",") if part}
        cases = [case for case in cases if case["id"] in wanted]
    print(f"모의 받아쓰기 오류: 뜻 판정 {len(cases)}건 × 강도 {levels}, 시스템 {', '.join(names)}, 회차 {args.runs}", flush=True)
    plan = planned_calls(cases, names, levels, args.runs)
    for level, per_system in plan.items():
        print(f"  강도 {level}: " + ", ".join(f"{name} 예상 호출 {calls['typical']}회 (최대 {calls['max']})"
                                            for name, calls in per_system.items()), flush=True)
    total = sum(calls["typical"] for per_system in plan.values() for calls in per_system.values())
    print(f"  합계 예상 CLOVA 호출 {total}회", flush=True)
    if getattr(args, "dry_run", False):
        print("--dry-run: CLOVA 를 부르지 않고 끝냅니다", flush=True)
        return plan
    config = {"model": settings.clova_studio_model if "rule+judge" in names else None, "runs": args.runs,
              "levels": levels, "seed": SEED, "kinds": list(KINDS), "label": "모의 받아쓰기 오류 (오디오·STT 아님)",
              "data": {"file": intent_eval.DATA.name, "version": body.get("version"),
                       "sha256": report.file_sha256(intent_eval.DATA), "verified_by": body.get("verified_by")},
              "switches": dict(intent_eval.SWITCHES) if "rule+judge" in names else {},
              "judge_budget_seconds": intent_eval.JUDGE_BUDGET_SECONDS, "planned_calls": plan}
    eval_run = report.start("noise", config=config, systems=names)
    print(f"결과 폴더: {eval_run.out}", flush=True)
    result = evaluate(cases, names, levels, runs=args.runs)
    eval_run.metrics, eval_run.cases = result["metrics"], result["cases"]
    eval_run.config["agent_calls"] = result["calls"]
    out = eval_run.finish()
    print(f"result.json: {out}")
    return out
