"""평가 지표 계산. 모두 순수 함수다 (CLOVA, 파일을 건드리지 않는다).

지키는 규칙
  - 비율의 분모는 요청한 전체다. 못 만든 것, 시간 초과, 오류(None)도 분모에 넣고 실패로 센다.
  - 분모가 0 이면 값은 None(result.json 에서 null)이고 note 에 까닭을 적는다.
  - 지표 하나는 metric() 이 만드는 dict 하나다. result.json 의 metrics 와 대시보드 표가 이 모양을 쓴다.
"""

import math
import statistics
from collections.abc import Hashable, Iterable, Sequence

ZERO_DENOMINATOR_NOTE = "분모 0 (잴 사례 없음)"


def ratio(numerator: int, denominator: int) -> float | None:
    """분자/분모. 분모가 0 이면 None."""
    return None if denominator == 0 else numerator / denominator


def metric(
    id: str, name: str, *, question: int, system: str | None, numerator: int, denominator: int,
    higher_is_better: bool = True, note: str = "",
) -> dict:
    """비율 지표 한 줄."""
    value = ratio(numerator, denominator)
    if value is None and not note:
        note = ZERO_DENOMINATOR_NOTE
    return {"id": id, "question": question, "name": name, "system": system, "value": value,
            "numerator": numerator, "denominator": denominator, "unit": "ratio",
            "higher_is_better": higher_is_better, "note": note}


def value_metric(
    id: str, name: str, *, question: int, system: str | None, value: float | None, unit: str,
    higher_is_better: bool = False, note: str = "",
) -> dict:
    """비율이 아닌 지표 한 줄 (초, 호출 수, 토큰 수). 분자·분모는 없다."""
    if value is None and not note:
        note = ZERO_DENOMINATOR_NOTE
    return {"id": id, "question": question, "name": name, "system": system, "value": value,
            "numerator": None, "denominator": None, "unit": unit, "higher_is_better": higher_is_better, "note": note}


def precision_recall_f1(gold: Sequence[Hashable], predicted: Sequence[Hashable | None], positive: Hashable) -> dict:
    """positive 하나에 대한 정밀도·재현율·F1.

    predicted 의 None 은 '분류하지 못함'이다. 정답이 positive 인데 None 이면 놓친 것(fn)으로 센다.
    분모가 0 인 값은 None.
    """
    if len(gold) != len(predicted):
        raise ValueError("gold 와 predicted 의 길이가 달라요")
    tp = sum(1 for g, p in zip(gold, predicted) if g == positive and p == positive)
    fp = sum(1 for g, p in zip(gold, predicted) if g != positive and p == positive)
    fn = sum(1 for g, p in zip(gold, predicted) if g == positive and p != positive)
    precision = ratio(tp, tp + fp)
    recall = ratio(tp, tp + fn)
    if precision is None or recall is None:
        f1 = None if tp + fp + fn == 0 else 0.0
    else:
        f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def macro_f1(gold: Sequence[Hashable], predicted: Sequence[Hashable | None], labels: Iterable[Hashable]) -> dict:
    """라벨별 F1 의 평균. 정답에도 예측에도 없는 라벨(F1 None)은 평균에서 뺀다.

    돌려주는 값: {"value": 평균 또는 None, "per_label": {라벨: F1 또는 None}}
    """
    per_label = {label: precision_recall_f1(gold, predicted, label)["f1"] for label in labels}
    counted = [f1 for f1 in per_label.values() if f1 is not None]
    return {"value": statistics.fmean(counted) if counted else None, "per_label": per_label}


def all_pass(results: dict[str, Sequence[bool | None]], k: int = 3) -> tuple[int, int]:
    """pass^k (τ-bench). 같은 사례를 k 번 이상 돌려 모두 통과(True)한 사례 수와 전체 사례 수.

    k 번보다 적게 돈 사례, None(실패·오류)이 하나라도 있는 사례는 통과가 아니다.
    k 번보다 많이 돌렸으면 돌린 것 전부가 통과해야 한다 (runs 를 k 로 맞춰 돌리는 것을 기본으로 한다).
    """
    passed = sum(1 for runs in results.values() if len(runs) >= k and all(run is True for run in runs))
    return passed, len(results)


def latency(seconds: Sequence[float | None], budget: float | None = None) -> dict:
    """준비 시간 요약. None 은 시간 초과·오류로 끝난 것이다.

    median, max 는 잰 값(None 이 아닌 것)으로만 낸다. 예산 안 비율의 분모는 요청한 전체(None 포함)다.
    """
    measured = [s for s in seconds if s is not None]
    within = None if budget is None else sum(1 for s in measured if s <= budget)
    return {
        "median": statistics.median(measured) if measured else None,
        "max": max(measured) if measured else None,
        "within_budget": within,
        "total": len(seconds),
        "within_budget_rate": None if within is None else ratio(within, len(seconds)),
    }


def wilson_interval(numerator: int, denominator: int, z: float = 1.96) -> tuple[float, float] | None:
    """비율의 95% 신뢰 구간 (Wilson). 분모가 0 이면 None. 0/n, n/n 에서도 구간이 0~1 을 넘지 않는다."""
    if denominator == 0:
        return None
    p = numerator / denominator
    z2 = z * z
    centre = (p + z2 / (2 * denominator)) / (1 + z2 / denominator)
    half = z * math.sqrt(p * (1 - p) / denominator + z2 / (4 * denominator * denominator)) / (1 + z2 / denominator)
    return max(0.0, centre - half), min(1.0, centre + half)


def percentile(values: Sequence[float], q: float) -> float | None:
    """q(0~100) 백분위수. 가장 가까운 순위(nearest-rank) 방식이라 늘 잰 값 중 하나다. 값이 없으면 None."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def per_fit(total: float, fit_count: int) -> float | None:
    """적합 결과 1건당 값 (호출 수, 토큰). 적합 결과가 0 건이면 None."""
    return None if fit_count == 0 else total / fit_count
