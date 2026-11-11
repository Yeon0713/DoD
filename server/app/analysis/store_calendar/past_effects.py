"""과거 효과를 구한다.

효과는 같은 묶음(행사 종류·경기 종류·날씨 종류)의 과거 특별한 칸에서 실제 매출이 기준선과 달랐던 비율의 평균이다.
- 칸 하나의 효과 = 실제 매출 ÷ 그날 기준선 − 1. 기준선은 그날 직전 8주로 구하고 특별한 칸은 뺀다.
  같은 요일 기준선이 없으면 직전 8주 같은 시간대의 모든 날 중앙값을 대신 쓴다 [가정, 임시 규칙].
  이 대체 기준선은 과거 효과에서만 쓴다. 그래도 없거나 기준선이 0원이면(비율을 구할 수 없다) 그 칸은 평균에 넣지 않는다.
- 묶음 × 시간대별로 칸의 효과를 평균한다.
- 한 칸에 이유가 둘 이상이면 그 칸의 효과를 각 묶음에 모두 넣는다(원인을 나눌 수 없다).
- 효과가 ±10% 안이면 태그를 붙이지 않는다(tagged_effect).
"""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from app.analysis.input_shapes import AnalysisInputs, require_aware
from app.analysis.pattern.baseline import Cell, baseline_for, median_before
from app.analysis.result_shapes import AnalysisDaypart, SalesDailyRow
from app.analysis.special_cells import SpecialKind, SpecialTag, cell_keys, find_special_cells
from app.core.seoul_time import to_seoul

EffectGroup = tuple[SpecialTag, SpecialKind]  # (태그, 종류). 예) ("EVENT", "LOCAL_FESTIVAL"), ("WEATHER", "RAIN")
EffectKey = tuple[EffectGroup, AnalysisDaypart]

TAG_THRESHOLD = 0.10  # |효과| 가 이 값 이상이면 태그를 붙인다(같으면 붙인다)
FALLBACK_MIN_DAYS = 4  # 대체 기준선에 필요한 날 수
FLOAT_TOLERANCE = 1e-9  # 110 / 100 − 1 같은 계산의 소수 오차. 정확히 10% 인 효과가 태그를 잃지 않게 한다


@dataclass(frozen=True)
class PastEffect:
    effect: float  # 칸 평균. 0.351 이면 +35.1%
    cell_count: int  # 평균에 들어간 칸 수


def build_past_effects(
    inputs: AnalysisInputs,
    rows: list[SalesDailyRow],
    now: dt.datetime,
) -> dict[EffectKey, PastEffect]:
    """now 이전의 특별한 칸으로 묶음 × 시간대별 과거 효과. 쓸 수 있는 칸이 없는 묶음은 없다.

    rows 는 sales_daily 행이다(마감이 지난 날만 있다). now 의 날짜 뒤 행은 쓰지 않고,
    매출 행이 없는 특별한 칸도 쓰지 않는다. sales_daily 를 거치지 않은 행을 넘기면 마감 전 당일도 들어갈 수 있다.
    """
    require_aware(now)
    rows = [r for r in rows if r.date <= to_seoul(now).date()]
    if not rows:
        return {}
    sales = {(r.date, r.daypart): r.sales_amount for r in rows}
    cells = find_special_cells(inputs, min(sales)[0], max(sales)[0])
    excluded = cell_keys(cells)

    groups_by_cell = defaultdict(set)
    for cell in cells:
        groups_by_cell[(cell.date, cell.daypart)].add((cell.tag, cell.kind))

    effects_by_key = defaultdict(list)
    for (day, daypart), groups in groups_by_cell.items():
        if (day, daypart) not in sales:
            continue
        baseline = baseline_for(rows, excluded, day, daypart)
        if baseline is None:
            baseline = _all_days_baseline(rows, excluded, day, daypart)
        if not baseline:  # 기준선이 없거나 0원이면 비율을 구할 수 없다
            continue
        effect = sales[(day, daypart)] / baseline - 1
        for group in groups:
            effects_by_key[(group, daypart)].append(effect)

    return {key: PastEffect(effect=sum(values) / len(values), cell_count=len(values)) for key, values in effects_by_key.items()}


def tagged_effect(effects: dict[EffectKey, PastEffect], group: EffectGroup, daypart: AnalysisDaypart) -> float | None:
    """태그를 붙일 효과. 사례가 없거나 |효과| < 10% 면 None."""
    past = effects.get((group, daypart))
    if past is None or abs(past.effect) < TAG_THRESHOLD - FLOAT_TOLERANCE:
        return None
    return past.effect


def _all_days_baseline(
    rows: list[SalesDailyRow],
    excluded: set[Cell],
    day: dt.date,
    daypart: AnalysisDaypart,
) -> int | None:
    """대체 기준선 [가정, 임시 규칙]: day 직전 8주 같은 시간대의 모든 날(특별한 칸 제외) 매출 중앙값."""
    return median_before(rows, excluded, day, daypart, same_weekday=False, minimum=FALLBACK_MIN_DAYS)

