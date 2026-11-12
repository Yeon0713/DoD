"""메뉴판 데이터 점수: 세부 종류별로 그 태그가 붙은 날 메뉴 판매 비중이 평소보다 얼마나 달라졌는지(%p).

- 비중은 판매 수량으로 센다(메뉴 수량 ÷ 그 칸들의 전체 수량). 영업시간 밖 주문은 넣지 않는다.
- EVENT·GAME: 과거에 그 세부 종류(EventKind, GameKind)의 특별한 칸이 있던 날마다, 그 칸의 시간대들을 합산한다.
  평소는 그날 이전 8주의 같은 시간대들을 합산한다(특별한 칸 제외).
- SEASON: 그 계절(WINTER, SUMMER)에 속한 날마다, 행사·경기 특별한 칸을 뺀 시간대들을 합산한다.
  평소는 그 계절 기간이 시작되기 전 8주의 같은 시간대들을 합산한다(특별한 칸 제외).
  그날 직전 8주도 같은 계절이면 변화가 0에 가깝게 나오기 때문이다.
  첫 주문 날보다 먼저 시작한 계절은 첫 주문 날을 시작일로 본다. 그 앞 8주에는 주문이 없어 그 계절 날은 쓰이지 않는다.
- 현재 메뉴 목록에 없는 메뉴의 판매도 전체 수량(비중의 분모)에는 들어간다.
- 평소 구간은 기준점(EVENT·GAME 은 그날, SEASON 은 계절 시작일)부터 7일씩 거슬러 1~8주로 나눈다.
  특별한 칸을 빼고 남은 칸에 주문이 있는 주가 4주 미만이면 그날은 쓰지 않는다.
- 날마다 (그날 비중 − 평소 비중)을 구해 쓴 날 수(n)로 평균한다.
"""

import datetime as dt
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Literal

from app.analysis.input_shapes import AnalysisInputs
from app.analysis.pattern.daypart_time import business_date, daypart_at, dayparts_of, is_closed_day
from app.analysis.special_cells import SpecialCell, cell_keys, find_special_cells
from app.analysis.store_calendar.season import seasons_between

USUAL_WEEKS = 8
MIN_USUAL_WEEKS = 4

MenuBoardTag = Literal["EVENT", "GAME", "SEASON"]
Cell = tuple[dt.date, str]  # (영업일, 시간대)


@dataclass(frozen=True)
class ShareLift:
    """n: 쓴 과거 날 수. lift_pp: 메뉴 id(문자열) → 비중 변화. 단위는 %p 이다(6.0 = 6%p, 0.06 이 아니다).

    매장의 현재 메뉴(inputs.menus)는 빠짐없이 들어간다. 그때 안 팔렸거나 없던 메뉴, n 이 0 일 때는 0.0 이다.
    """

    n: int
    lift_pp: dict[str, float]


@dataclass(frozen=True)
class _Sample:
    """과거 날 하나: 그날 볼 칸, 평소 구간의 기준점(이 날 전 8주), 평소에 볼 시간대."""

    cells: list[Cell]
    anchor: dt.date
    dayparts: list[str]


def menu_share_lift(inputs: AnalysisInputs, tag: MenuBoardTag, kind: str, as_of: dt.date) -> ShareLift:
    """as_of(기준 태그 기간의 첫날)보다 앞선 날만 쓴 그 세부 종류의 메뉴 비중 변화."""
    menu_ids = [menu.menu_id for menu in inputs.menus]
    qty = _quantities(inputs)
    if not qty:
        return ShareLift(0, dict.fromkeys(menu_ids, 0.0))
    first_day = min(day for day, _ in qty)
    specials = find_special_cells(inputs, first_day, as_of - dt.timedelta(days=1))  # as_of 앞선 날만
    special_keys = cell_keys(specials)
    if tag == "SEASON":
        samples = _season_samples(inputs, kind, first_day, as_of, specials)
    else:
        samples = _tagged_samples(specials, tag, kind)

    lifts = []
    for sample in samples:
        tagged = _total(qty, sample.cells)
        if not tagged:
            continue
        usual_cells = _usual_cells(sample, special_keys, inputs)
        if len(_weeks_with_orders(usual_cells, sample.anchor, qty)) < MIN_USUAL_WEEKS:
            continue
        usual = _total(qty, usual_cells)
        lifts.append({m: (_share(tagged, m) - _share(usual, m)) * 100 for m in menu_ids})
    n = len(lifts)
    return ShareLift(n, {m: sum(lift[m] for lift in lifts) / n if n else 0.0 for m in menu_ids})


def _quantities(inputs: AnalysisInputs) -> dict[Cell, Counter]:
    """칸마다 메뉴별 판매 수량."""
    ranges = dayparts_of(inputs.store)
    cell_of = {}
    for order in inputs.orders:
        daypart = daypart_at(order.ordered_at, ranges)
        if daypart is not None:
            cell_of[order.order_id] = (business_date(order.ordered_at, inputs.store), daypart)
    qty: dict[Cell, Counter] = defaultdict(Counter)
    for item in inputs.order_items:
        if item.order_id in cell_of:
            qty[cell_of[item.order_id]][item.menu_id] += item.quantity
    return qty


def _tagged_samples(specials: list[SpecialCell], tag: MenuBoardTag, kind: str) -> list[_Sample]:
    dayparts_by_day: dict[dt.date, set[str]] = defaultdict(set)
    for cell in specials:
        if cell.tag == tag and cell.kind == kind:
            dayparts_by_day[cell.date].add(cell.daypart)
    return [
        _Sample([(day, p) for p in sorted(parts)], day, sorted(parts))
        for day, parts in sorted(dayparts_by_day.items())
    ]


def _season_samples(
    inputs: AnalysisInputs, kind: str, first_day: dt.date, as_of: dt.date, specials: list[SpecialCell]
) -> list[_Sample]:
    all_parts = [r.daypart for r in dayparts_of(inputs.store)]
    event_or_game = {(c.date, c.daypart) for c in specials if c.tag in ("EVENT", "GAME")}
    samples, season_start, previous = [], None, None
    for day, season in sorted(seasons_between(inputs.weather, first_day, as_of - dt.timedelta(days=1)).items()):
        if season != previous:
            season_start, previous = day, season
        if season != kind or is_closed_day(day, inputs.store):
            continue
        parts = [p for p in all_parts if (day, p) not in event_or_game]
        samples.append(_Sample([(day, p) for p in parts], season_start, parts))
    return samples


def _usual_cells(sample: _Sample, special_keys: set[Cell], inputs: AnalysisInputs) -> list[Cell]:
    """기준점 전 8주의 같은 시간대 칸. 쉬는 날과 특별한 칸은 뺀다."""
    cells = []
    for back in range(1, USUAL_WEEKS * 7 + 1):
        day = sample.anchor - dt.timedelta(days=back)
        if not is_closed_day(day, inputs.store):
            cells += [(day, p) for p in sample.dayparts if (day, p) not in special_keys]
    return cells


def _weeks_with_orders(cells: list[Cell], anchor: dt.date, qty: dict[Cell, Counter]) -> set[int]:
    """주문이 있는 칸이 하나라도 남은 주(기준점 전 1~7일이 0번 주)."""
    return {((anchor - day).days - 1) // 7 for day, part in cells if sum(qty.get((day, part), Counter()).values())}


def _total(qty: dict[Cell, Counter], cells: list[Cell]) -> Counter:
    total = Counter()
    for cell in cells:
        total.update(qty.get(cell, Counter()))
    return total


def _share(total: Counter, menu_id: str) -> float:
    return total[menu_id] / sum(total.values())
