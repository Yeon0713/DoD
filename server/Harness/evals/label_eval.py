"""label 스위트: 리뷰 분류가 맞는가 (질문 1). A/B 가 같은 분류를 쓰므로 시스템 대신 분류기를 비교한다.

분류기 (CLASSIFIERS, 기존 함수를 그대로 부른다. 켜거나 고치지 않는다)
  rule   키워드 규칙 app/analysis/review/keyword_rules.classify_by_keywords. CLOVA 를 부르지 않는다
  hcx    HCX 분류기 app/analysis/review/hcx_classifier.classify_with_hcx (운영에서는 꺼져 있다).
         clova.ask 를 거치지 않고 직접 부르므로 post 를 CountingPost 로 감싸 호출 수와 토큰을 센다. 실제 CLOVA 를 부른다
  voice  음성 라벨 voice/jobs/label.classify (규칙을 음성 체계 positive/negative + 주제 하나로 바꾼 것, 별점 2 이하는 negative)

세트: balanced 64건(대표 값)과 전체 864건(참고 값). 둘 다 적는다. 지표 줄마다 set 에 balanced / full 을 적는다.
--scope balanced 면 balanced 만 분류한다 (hcx 를 짧게 확인할 때).

지표 (분모는 요청한 전체. 답을 못 받은 것(None)도 넣고 실패로 센다)
  negative_recall          정답 NEGATIVE·MIXED 중 아쉬운 리뷰로 잡은 비율. 아쉬운 리뷰 = rule·hcx 는 감정이 POSITIVE 가 아님
                           (불만 유형이 있으면 POSITIVE 가 될 수 없다), voice 는 negative
  negative_precision       아쉬운 리뷰로 잡은 것 중 정답 NEGATIVE·MIXED 비율
  sentiment_macro_f1       감정 F1 평균. rule·hcx 는 3종, voice 는 2종(positive / negative = NEGATIVE·MIXED)
  sentiment_macro_f1_2way  모두 2종으로 맞춰 본 값 (voice 와 나란히 비교하려고)
  complaint_type_f1        불만 유형 micro F1 (사례 × 유형 쌍). voice 는 주제 하나를 유형 하나로 바꿔 센다(other 는 유형 없음).
                           정답 유형이 TYPE_MIN_GOLD 건 이상인 유형만 complaint_type_f1:<유형> 을 따로 적고, 나머지는 note 에 건수만
  hcx_failed               hcx 가 답을 못 준 비율 (낮을수록 좋다)
불만 유형 정답은 사람이 확인하기 전에는 초안이다. config.gold_verified 가 false 면 complaint_type_f1 은 참고 값이다.

result.json 에 더 남기는 것
  cases   틀린 사례 전부 (감정이 다름, 불만 유형이 다름, 아쉬운 리뷰 판정이 다름, 답 없음). 맞은 사례는 남기지 않는다
  tables  혼동 행렬 confusion[<set>][<분류기>][<정답 감정>][<예측 감정 또는 "답 없음">] = 건수
"""

import argparse
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from app.analysis.review import hcx_classifier
from app.analysis.review.complaint_groups import COMPLAINT_TYPES, sort_types
from app.analysis.review.keyword_rules import classify_by_keywords
from app.core.config import settings
from Harness.evals import derive, gold, metrics, report
from voice.jobs import label as voice_label

QUESTION = 1
CLASSIFIERS = ("rule", "hcx", "voice")
DEFAULT_CLASSIFIERS = ("rule", "voice")  # 실제 CLOVA 를 부르지 않는 것만
NEEDS_CLOVA = {"hcx"}
SCOPES = ("full", "balanced")
TYPE_MIN_GOLD = 5  # 정답 유형이 이보다 적으면 유형별 F1 을 따로 적지 않는다
GOLD_VERIFIED = False  # 불만 유형 초안을 사람이 확인하면 True 로 바꾸고 다시 잰다

VOICE_TOPIC_TYPES = {"delivery": "DELIVERY_DELAY", "taste": "TASTE", "portion": "PORTION", "service": "SERVICE",
                     "hygiene": "HYGIENE"}
NO_ANSWER = "답 없음"
HCX_PROMPT = Path(hcx_classifier.__file__).parent / "prompts" / "review_label.txt"


class ClassifierUnavailable(ValueError):
    """모르는 분류기 이름."""


@dataclass
class Prediction:
    """분류기 하나의 답. 답을 못 받았으면 sentiment, types, negative 가 None 이다."""

    sentiment: str | None  # rule·hcx: POSITIVE|NEGATIVE|MIXED, voice: positive|negative
    types: list[str] | None
    negative: bool | None  # 아쉬운 리뷰로 잡았는지
    calls: int = 0
    tokens: tuple[int, int] = (0, 0)
    seconds: float = 0.0
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.sentiment is None


def parse_classifiers(text: str) -> list[str]:
    names = [part.strip() for part in text.split(",") if part.strip()]
    unknown = [name for name in names if name not in CLASSIFIERS]
    if unknown or not names:
        raise ClassifierUnavailable(f"분류기는 {', '.join(CLASSIFIERS)} 중에서 골라요 (받은 값: {text!r})")
    return list(dict.fromkeys(names))


def predict_rule(case: dict) -> Prediction:
    sentiment, types = classify_by_keywords(case["text"])
    return Prediction(sentiment, sort_types(types), sentiment != "POSITIVE")


def predict_voice(case: dict) -> Prediction:
    sentiment, topic = voice_label.classify(case["text"], int(case["rating"] or 0))
    negative = sentiment == "negative"
    types = [VOICE_TOPIC_TYPES[topic]] if negative and topic in VOICE_TOPIC_TYPES else []
    return Prediction(sentiment, types, negative)


def predict_hcx(case: dict, post=None) -> Prediction:
    counting = report.CountingPost(post) if post is not None else report.CountingPost()
    started = time.perf_counter()
    error = None
    try:
        answer = hcx_classifier.classify_with_hcx(case["text"], post=counting)
    except Exception as exc:  # 한 건이 터져도 나머지는 계속 잰다
        answer, error = None, f"{type(exc).__name__}: {exc}"
    seconds = round(time.perf_counter() - started, 3)
    if answer is None:
        return Prediction(None, None, None, counting.calls, tuple(counting.tokens), seconds, error or "답을 못 받음")
    sentiment, types = answer
    return Prediction(sentiment, sort_types(types), sentiment != "POSITIVE", counting.calls, tuple(counting.tokens), seconds)


PREDICTORS: dict[str, Callable[..., Prediction]] = {"rule": predict_rule, "hcx": predict_hcx, "voice": predict_voice}


def classify_all(name: str, cases: list[dict], *, workers: int = 1, post=None) -> dict[str, Prediction]:
    """case_id → Prediction. hcx 만 여러 개를 함께 부른다 (workers, 기본 1)."""
    predictor = PREDICTORS[name]
    if name != "hcx":
        return {case["case_id"]: predictor(case) for case in cases}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        answers = list(pool.map(lambda case: predictor(case, post), cases))
    return {case["case_id"]: answer for case, answer in zip(cases, answers)}


# ── 채점 (순수 함수) ──


def gold_negative(case: dict) -> bool:
    return case["gold"]["sentiment"] != "POSITIVE"


def two_way(sentiment: str | None) -> str | None:
    if sentiment is None:
        return None
    return "positive" if sentiment in ("POSITIVE", "positive") else "negative"


def type_counts(cases: list[dict], predictions: dict[str, Prediction]) -> dict[str, dict[str, int]]:
    """유형별 tp, fp, fn 과 정답 건수(gold). 답을 못 받은 사례의 정답 유형은 놓친 것(fn)이다."""
    counts = {t: {"tp": 0, "fp": 0, "fn": 0, "gold": 0} for t in COMPLAINT_TYPES}
    for case in cases:
        expected = set(case["gold"]["complaint_types"])
        got = set(predictions[case["case_id"]].types or [])
        for t in COMPLAINT_TYPES:
            counts[t]["gold"] += t in expected
            if t in expected and t in got:
                counts[t]["tp"] += 1
            elif t in got:
                counts[t]["fp"] += 1
            elif t in expected:
                counts[t]["fn"] += 1
    return counts


def micro_f1(counts: list[dict[str, int]]) -> tuple[float | None, int, int, int]:
    tp, fp, fn = (sum(c[key] for c in counts) for key in ("tp", "fp", "fn"))
    return (None if tp + fp + fn == 0 else 2 * tp / (2 * tp + fp + fn)), tp, fp, fn


def confusion(cases: list[dict], predictions: dict[str, Prediction]) -> dict[str, dict[str, int]]:
    table: dict[str, dict[str, int]] = {}
    for case in cases:
        got = predictions[case["case_id"]].sentiment or NO_ANSWER
        row = table.setdefault(case["gold"]["sentiment"], {})
        row[got] = row.get(got, 0) + 1
    return table


def _with_set(row: dict, set_name: str) -> dict:
    return {**row, "set": set_name}


def _f1_note(per_label: dict) -> str:
    return ", ".join(f"{label} {'-' if f1 is None else f'{f1:.3f}'}" for label, f1 in per_label.items())


def score(name: str, set_name: str, cases: list[dict], predictions: dict[str, Prediction]) -> list[dict]:
    """분류기 하나, 세트 하나의 지표 줄들."""
    rows = []
    gold_bin = [gold_negative(case) for case in cases]
    pred_bin = [predictions[case["case_id"]].negative for case in cases]
    pr = metrics.precision_recall_f1(gold_bin, pred_bin, True)
    rows.append(metrics.metric("negative_recall", "아쉬운 리뷰 재현율", question=QUESTION, system=name,
                               numerator=pr["tp"], denominator=pr["tp"] + pr["fn"]))
    rows.append(metrics.metric("negative_precision", "아쉬운 리뷰 정밀도", question=QUESTION, system=name,
                               numerator=pr["tp"], denominator=pr["tp"] + pr["fp"]))

    if name == "voice":
        gold_sent = [two_way(case["gold"]["sentiment"]) for case in cases]
        pred_sent = [predictions[case["case_id"]].sentiment for case in cases]
        labels, note_prefix = ("positive", "negative"), "2종 (음성 체계). "
    else:
        gold_sent = [case["gold"]["sentiment"] for case in cases]
        pred_sent = [predictions[case["case_id"]].sentiment for case in cases]
        labels, note_prefix = ("POSITIVE", "NEGATIVE", "MIXED"), ""
    macro = metrics.macro_f1(gold_sent, pred_sent, labels)
    rows.append(metrics.value_metric("sentiment_macro_f1", "감정 Macro-F1", question=QUESTION, system=name,
                                     value=macro["value"], unit="f1", higher_is_better=True,
                                     note=note_prefix + _f1_note(macro["per_label"])))
    macro2 = metrics.macro_f1([two_way(case["gold"]["sentiment"]) for case in cases],
                              [two_way(predictions[case["case_id"]].sentiment) for case in cases], ("positive", "negative"))
    rows.append(metrics.value_metric("sentiment_macro_f1_2way", "감정 Macro-F1 (2종으로 맞춤)", question=QUESTION,
                                     system=name, value=macro2["value"], unit="f1", higher_is_better=True,
                                     note=_f1_note(macro2["per_label"])))

    counts = type_counts(cases, predictions)
    value, tp, fp, fn = micro_f1(list(counts.values()))
    small = [f"{t} {c['gold']}" for t, c in counts.items() if 0 < c["gold"] < TYPE_MIN_GOLD]
    draft = "" if GOLD_VERIFIED else "정답 유형은 사람 확인 전 초안. "
    voice_note = "음성은 주제 하나만 유형으로 센다. " if name == "voice" else ""
    rows.append(metrics.value_metric(
        "complaint_type_f1", "불만 유형 F1 (micro)", question=QUESTION, system=name, value=value, unit="f1",
        higher_is_better=True,
        note=f"{draft}{voice_note}tp {tp}, fp {fp}, fn {fn}" + (f". 정답 {TYPE_MIN_GOLD}건 미만(전체 값에만 들어감): {', '.join(small)}" if small else "")))
    for t, c in counts.items():
        if c["gold"] >= TYPE_MIN_GOLD:
            f1, *_ = micro_f1([c])
            rows.append(metrics.value_metric(
                f"complaint_type_f1:{t}", f"불만 유형 F1 ({t})", question=QUESTION, system=name, value=f1, unit="f1",
                higher_is_better=True, note=f"{draft}정답 {c['gold']}건, tp {c['tp']}, fp {c['fp']}, fn {c['fn']}"))

    if name == "hcx":
        failed = sum(1 for case in cases if predictions[case["case_id"]].failed)
        rows.append(metrics.metric("hcx_failed", "HCX 분류기 답 없음 비율", question=QUESTION, system=name,
                                   numerator=failed, denominator=len(cases), higher_is_better=False))
    return [_with_set(row, set_name) for row in rows]


def wrong_reasons(case: dict, prediction: Prediction) -> list[str]:
    if prediction.failed:
        return ["failed"]
    reasons = []
    expected_sentiment = case["gold"]["sentiment"]
    if prediction.sentiment in ("positive", "negative"):
        if prediction.sentiment != two_way(expected_sentiment):
            reasons.append("sentiment")
    elif prediction.sentiment != expected_sentiment:
        reasons.append("sentiment")
    if sort_types(prediction.types or []) != sort_types(case["gold"]["complaint_types"]):
        reasons.append("types")
    if prediction.negative != gold_negative(case):
        reasons.append("negative")
    return reasons


def case_row(name: str, case: dict, prediction: Prediction, sets: list[str], reasons: list[str]) -> dict:
    return {
        "case_id": case["case_id"], "system": name, "run": 1, "run_id": None, "source": None, "sets": sets,
        "text": case["text"], "rating": case["rating"], "platform": case["platform"],
        "gold": {"sentiment": case["gold"]["sentiment"], "complaint_types": sort_types(case["gold"]["complaint_types"])},
        "predicted": {"sentiment": prediction.sentiment, "complaint_types": prediction.types, "negative": prediction.negative},
        "output": NO_ANSWER if prediction.failed else f"{prediction.sentiment} {prediction.types}",
        "wrong": reasons, "fit": False, "calls": prediction.calls, "tokens": list(prediction.tokens),
        "seconds": prediction.seconds, "error": prediction.error,
    }


def evaluate(cases: list[dict], names: list[str], *, scope: str = "full", workers: int = 1, post=None,
             on_done: Callable[[str, float], None] | None = None) -> dict:
    """분류하고 채점한다. {"metrics", "cases", "confusion", "sets"} 를 돌려준다 (결과 파일은 쓰지 않는다)."""
    sets = derive.build_sets(cases)
    chosen = {"balanced": sets["label_balanced"]} if scope == "balanced" else {"balanced": sets["label_balanced"], "full": sets["label_full"]}
    target = chosen.get("full", chosen["balanced"])
    balanced_ids = {case["case_id"] for case in chosen["balanced"]}
    rows, wrong, table = [], [], {set_name: {} for set_name in chosen}
    for name in names:
        started = time.perf_counter()
        predictions = classify_all(name, target, workers=workers, post=post)
        for set_name, set_cases in chosen.items():
            rows.extend(score(name, set_name, set_cases, predictions))
            table[set_name][name] = confusion(set_cases, predictions)
        for case in target:
            reasons = wrong_reasons(case, predictions[case["case_id"]])
            if reasons:
                in_sets = (["balanced"] if case["case_id"] in balanced_ids else []) + (["full"] if "full" in chosen else [])
                wrong.append(case_row(name, case, predictions[case["case_id"]], in_sets, reasons))
        if on_done:
            on_done(name, time.perf_counter() - started)
    return {"metrics": rows, "cases": wrong, "confusion": table, "sets": {f"label_{k}": v for k, v in chosen.items()}}


def run(args: argparse.Namespace):
    """python -m Harness.evals label --systems rule,hcx,voice [--scope balanced]"""
    path, sha, cases = gold.from_args(args)
    if args.ids:
        wanted = {part for part in args.ids.split(",") if part}
        cases = [case for case in cases if case["case_id"] in wanted]
    names = args.system_names
    if args.runs != 1:
        print("[알림] label 스위트는 한 번만 돌려요 (--runs 무시)", file=sys.stderr)
    config = {"model": settings.clova_studio_model if "hcx" in names else None, "scope": args.scope,
              "gold_verified": GOLD_VERIFIED, "concurrency": args.concurrency}
    if "hcx" in names:
        config["prompts"] = report.prompt_hashes([HCX_PROMPT])
    eval_run = report.start("label", config=config, systems=names)
    print(f"결과 폴더: {eval_run.out}")
    result = evaluate(cases, names, scope=args.scope, workers=args.concurrency,
                      on_done=lambda name, seconds: print(f"  {name}: {seconds:.1f}초"))
    hashes = {name: derive.write_set(eval_run.out, name, rows) for name, rows in result["sets"].items()}
    eval_run.config["gold"] = gold.config_entry(path, sha, hashes)
    for row in result["metrics"]:
        eval_run.add_metric(row)
    for row in result["cases"]:
        eval_run.add_case(row)
    eval_run.tables["confusion"] = result["confusion"]
    out = eval_run.finish()
    print(f"result.json: {out}")
    return out
