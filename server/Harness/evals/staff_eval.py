"""알바생 할 일 평가 (에이전트 조직 개편 8단계, donna-voice/docs/agent-org-plan.md 8-1). 실제 CLOVA 를 부른다.

fixcard  부정 리뷰 사원(voice/agents/fix_card.py): 조치 가능 판정의 정밀도·재현율, 카드에 알바생이 할 수 없는 일이 들어간 비율,
         에이전트가 끝내지 못하고 템플릿으로 물러난 비율. 세트 Harness/evals/data/fix_cases.json
dedupe   같은 할 일 묶기(voice/proposals.py + agents/same_task.py): 정확도, 잘못 묶음(교정이 사라짐), 놓침(하나 더 뜸).
         세트 Harness/evals/data/dedupe_cases.json. --systems dice 는 바이그램만(CLOVA 없음), dice+judge 는 좁은 LLM 질문까지
프롬프트에 예시를 늘리는 대신 이 세트를 늘려 판정을 잰다 (2026-11-20 결정: 하드코딩·빡센 프롬프트 예시 금지).
세트의 정답은 처음 만든 사람이 붙인 초안이다 (verified_by). 팀이 검토해 고친다.
"""

import argparse
import json
import time
from pathlib import Path

from Harness.evals import metrics, report

DATA = Path(__file__).parent / "data"
FIX_DATA = DATA / "fix_cases.json"
DEDUPE_DATA = DATA / "dedupe_cases.json"
DEDUPE_SYSTEMS = ("dice", "dice+judge")
STORE = {"name": "평가 가게", "category": "칼국수", "menus": [
    {"id": "m_1", "name": "들깨칼국수", "price": 11000, "photo_url": "x.png"},
    {"id": "m_2", "name": "만두", "price": 6000, "photo_url": "y.png"}]}


def _load(path: Path, ids: str | None) -> tuple[dict, list[dict]]:
    body = json.loads(path.read_text(encoding="utf-8"))
    cases = body["cases"]
    if ids:
        wanted = {part for part in ids.split(",") if part}
        cases = [c for c in cases if c["id"] in wanted]
    return body, cases


def _view(review: dict | None = None):
    from voice import clock
    from voice.context import VoiceStore

    now = clock.now()
    data = {"review": [review]} if review else {}
    return VoiceStore("eval", {**STORE, "id": "eval"}, data, now)


def _isolate(out: Path) -> None:
    """평가가 운영 음성 DB 를 건드리지 않게 결과 폴더의 빈 DB 를 쓴다."""
    from voice import config

    config.DB_PATH = out / "voice.db"


def run_fixcard(args: argparse.Namespace):
    """python -m Harness.evals fixcard [--ids …]"""
    from voice import config as voice_config
    from voice.agents import fix_card

    body, cases = _load(FIX_DATA, args.ids)
    print(f"교정 카드 {len(cases)}건", flush=True)
    if getattr(args, "dry_run", False):
        print(f"--dry-run: 예상 CLOVA 호출 약 {len(cases) * 2}회 (카드 + 할 수 없는 일 질문)")
        return None
    eval_run = report.start("fixcard", config={"data": {"file": FIX_DATA.name, "sha256": report.file_sha256(FIX_DATA),
                                                         "verified_by": body.get("verified_by")}}, systems=["fixcard"])
    _isolate(eval_run.out)
    voice_config.agent_on = lambda name: name == "fixcard"  # 이 프로세스 안에서만
    gold, predicted, scope_bad, fell_back, seconds = [], [], 0, 0, []
    for case in cases:
        review = {"id": case["id"], "store_id": "eval", "text": case["text"], "rating": case.get("rating", 2), "sentiment": "negative",
                  "written_at": "2026-01-01T00:00:00+09:00", "order_channel": case.get("channel", "delivery")}
        started = time.monotonic()
        got = fix_card.suggest(_view(review), review)
        seconds.append(time.monotonic() - started)
        if got is None:
            fell_back += 1
        actionable = None if got is None else got["actionable"]
        card_text = "" if not got or not got["actionable"] else f"{got['title']} {got['detail']}"
        bad = [w for w in case.get("must_not", []) if w in card_text]
        scope_bad += bool(bad)
        gold.append(case["actionable"])
        predicted.append(actionable)
        eval_run.add_case({"id": case["id"], "gold": case["actionable"], "predicted": actionable, "card": card_text or None,
                           "must_not_found": bad, "seconds": round(seconds[-1], 2)})
        print(f"  {case['id']}: 정답 {case['actionable']} / 판정 {actionable} {card_text}", flush=True)
    prf = metrics.precision_recall_f1(gold, predicted, True)
    done = [p for p in predicted if p is not None]
    eval_run.metrics = [
        metrics.metric("fixcard.accuracy", "조치 가능 판정 정확도", question=2, system="fixcard",
                       numerator=sum(1 for g, p in zip(gold, predicted) if p is not None and g == p), denominator=len(done)),
        metrics.value_metric("fixcard.precision", "조치 가능 정밀도 (넣자고 한 것 중 맞은 것)", question=2, system="fixcard",
                             value=prf.get("precision"), unit="ratio", higher_is_better=True),
        metrics.value_metric("fixcard.recall", "조치 가능 재현율", question=2, system="fixcard", value=prf.get("recall"), unit="ratio",
                             higher_is_better=True),
        metrics.metric("fixcard.scope_violation", "카드에 알바생이 할 수 없는 일이 들어간 비율", question=3, system="fixcard",
                       numerator=scope_bad, denominator=len(cases), higher_is_better=False),
        metrics.metric("fixcard.fallback", "템플릿으로 물러난 비율", question=2, system="fixcard",
                       numerator=fell_back, denominator=len(cases), higher_is_better=False),
        metrics.value_metric("fixcard.seconds_median", "카드 쓰는 시간 중앙값", question=5, system="fixcard",
                             value=metrics.latency(seconds)["median"], unit="seconds"),
    ]
    out = eval_run.finish()
    print(f"result.json: {out}")
    return out


def parse_dedupe_systems(text: str) -> list[str]:
    names = [part for part in text.split(",") if part]
    unknown = [n for n in names if n not in DEDUPE_SYSTEMS]
    if unknown:
        raise ValueError(f"dedupe 시스템은 {', '.join(DEDUPE_SYSTEMS)} 중에서: {', '.join(unknown)}")
    return names


def run_dedupe(args: argparse.Namespace):
    """python -m Harness.evals dedupe [--systems dice,dice+judge]"""
    from voice import config as voice_config
    from voice import proposals
    from voice.agents import same_task
    from voice.similar import dice

    names = args.system_names
    body, cases = _load(DEDUPE_DATA, args.ids)
    print(f"같은 할 일 {len(cases)}쌍, 시스템 {', '.join(names)}", flush=True)
    if getattr(args, "dry_run", False):
        print("--dry-run: dice+judge 는 겹침이 기준 이상인 쌍만 CLOVA 를 부른다")
        return None
    eval_run = report.start("dedupe", config={"data": {"file": DEDUPE_DATA.name, "sha256": report.file_sha256(DEDUPE_DATA),
                                                        "verified_by": body.get("verified_by")},
                                              "same_score": proposals.SAME_SCORE, "same_text": proposals.SAME_TEXT}, systems=names)
    _isolate(eval_run.out)
    voice_config.agent_on = lambda name: name == "same"
    rows = []
    for name in names:
        right = wrong_merge = missed = 0
        for case in cases:
            a = f"{case['a']['title']} {case['a'].get('detail', '')}"
            b = f"{case['b']['title']} {case['b'].get('detail', '')}"
            score = dice(a, b)
            if score >= proposals.SAME_TEXT:
                same = True
            elif score < proposals.SAME_SCORE or name == "dice":
                same = False
            else:
                same = same_task.judge(_view(), a, [{"id": "t_1", "text": b}]) == "t_1"
            right += same == case["same"]
            wrong_merge += same and not case["same"]
            missed += case["same"] and not same
            eval_run.add_case({"id": case["id"], "system": name, "gold": case["same"], "predicted": same, "dice": round(score, 3)})
        rows += [
            metrics.metric("dedupe.accuracy", "같은 할 일 판정 정확도", question=2, system=name, numerator=right, denominator=len(cases)),
            metrics.metric("dedupe.wrong_merge", "다른 일을 같은 일로 묶음 (교정이 사라짐)", question=3, system=name,
                           numerator=wrong_merge, denominator=len(cases), higher_is_better=False),
            metrics.metric("dedupe.missed", "같은 일을 놓침 (할 일이 하나 더 뜸)", question=2, system=name,
                           numerator=missed, denominator=len(cases), higher_is_better=False),
        ]
        print(f"  {name}: 정확 {right}/{len(cases)}, 잘못 묶음 {wrong_merge}, 놓침 {missed}", flush=True)
    eval_run.metrics = rows
    out = eval_run.finish()
    print(f"result.json: {out}")
    return out
