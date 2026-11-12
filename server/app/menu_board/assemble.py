"""메뉴판 카드 조립: 계획 엔진의 메뉴판 카드(MENU_ORDER)마다 배치안과 '바뀌는 것 없음'을 붙인다.

1. 원본 일정으로 근거 id 마다 기간(TagPeriod)을 만든다.
   행사는 시작~끝 날짜, 경기는 당일, 계절은 날씨 기록으로 계산한 '지금 이어지는 기간' 하나다.
   계절 근거 id(season_winter)에는 연도가 없으므로, 달력에 처음 보인 날이 속한 기간만 쓰고 지난 계절은 섞지 않는다.
   한계: 달력 안에서 계절이 끊겼다 다시 시작해도 첫 기간 하나만 쓴다(근거 id 가 같아 기간을 둘로 나눌 수 없다).
   그래서 다시 시작한 기간의 영업일은 교체 이득에 세지 않고, 데이터 점수 기준일도 첫 기간의 첫날이다.
   날씨 기록이 계절 시작보다 늦게 시작하면 기간의 첫날은 기록 첫날이 된다.
   행사가 0시 정각에 끝나면 그날은 기간에 넣지 않는다(특별한 칸도 겹친 시간이 0보다 커야 잡는다).
2. 세부 종류를 알 수 없는 근거 id(행사·경기 목록에 없음)는 경고를 남기고 달력에서 그 이유만 지운다.
   그날 다른 태그가 있으면 그게 기준 태그가 된다.
3. 기준 태그(menu_board_bases)마다 배치안을 한 번만 만든다. 데이터 점수의 기준일은 그 기준 태그 기간의 첫날이고,
   LLM 후보는 세부 종류마다 한 번만 조회한다.
4. '바뀌는 것 없음' = 기준 태그가 직전 영업일과 같다(unchanged_menu_orders), 또는 직전 영업일 배치안의 전체 순서와
   그날 전체 순서가 같다. 예) 어제 축제 배치 → 오늘 점수가 모두 0(원래 순서)이면 메뉴판이 바뀌므로 '바뀌는 것 없음'이 아니다.
5. 이유 문구는 배치안 이유(LLM 이유 또는 '추천할 메뉴를 찾지 못했어요')이고, 비어 있으면 그 카드의 기존 문구(reason_line)다.
"""

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Callable, get_args

from app.analysis.input_shapes import AnalysisInputs, Menu
from app.analysis.store_calendar.season import Season, season_ref_id, seasons_between
from app.core.seoul_time import to_seoul
from app.menu_board.arrangement import Arrangement, arrange_menu_board
from app.menu_board.menu_candidates import EMPTY, MenuBoardKind, MenuCandidates
from app.menu_board.menu_share_lift import MenuBoardTag, ShareLift, menu_share_lift
from app.planner.data_shapes import CalendarCell, PlanItem, StoreSettings
from app.planner.rule_menu_order import (
    TagPeriod,
    menu_board_bases,
    previous_open_day,
    tag_periods,
    unchanged_menu_orders,
)

logger = logging.getLogger(__name__)

MAX_RAISED = 2  # K = min(2, 메뉴 수)
SEASONS: tuple[Season, ...] = get_args(Season)

Lookup = Callable[[dict, list[Menu], MenuBoardKind], MenuCandidates]  # (가게, 메뉴, 세부 종류) → LLM 후보. menu_candidates 와 같은 모양


@dataclass(frozen=True)
class MenuBoardCard:
    """plan_id: 메뉴판 카드. basis: 그날 기준 태그(None 이면 원래 순서). reason: 카드에 보일 이유 한 줄.
    unchanged: '바뀌는 것 없음'(직전 영업일과 기준 태그가 같거나 전체 순서가 같다).
    """

    plan_id: str
    basis: str | None
    arrangement: Arrangement
    reason: str
    unchanged: bool


@dataclass(frozen=True)
class _Tag:
    """근거 id 하나: 태그(EVENT, GAME, SEASON), 세부 종류, 원본 일정 기간."""

    tag: MenuBoardTag
    kind: MenuBoardKind
    period: TagPeriod


def assemble_menu_board_cards(
    calendar: list[CalendarCell],
    cards: list[PlanItem],
    inputs: AnalysisInputs,
    settings: StoreSettings | None,
    store: dict,
    original: list[Menu],
    lookup: Lookup,
) -> dict[str, MenuBoardCard]:
    """calendar: calendar_for_planner 결과(어제 칸 포함). cards: 계획 엔진 할 일(메뉴판 카드만 쓴다).
    settings: 계획 엔진 매장 설정(카드가 없으면 쓰지 않는다). store: {"store_id", "name", "category"}.
    original: 원래 메뉴 순서. lookup: LLM 후보 조회(테스트에서는 가짜, 실제로는 menu_candidates 와 같은 모양).
    돌려주는 값: 카드 plan_id → MenuBoardCard. 날짜의 기준 태그를 모르는 카드는 넣지 않는다.
    """
    cards = [item for item in cards if item.task_type == "MENU_ORDER"]
    if not cards:
        return {}
    if settings is None:
        raise ValueError("메뉴판 카드가 있는데 계획 엔진 매장 설정이 없습니다.")
    known = _known_tags(inputs, calendar)
    calendar = _without_unknown_reasons(calendar, known)
    periods = [tag.period for tag in known.values()]
    k = min(MAX_RAISED, len(original))
    bases = menu_board_bases(calendar, periods, settings, k)
    first_days = {ref_id: start for ref_id, (start, _) in tag_periods(calendar, periods).items()}

    no_data = ShareLift(0, dict.fromkeys((menu.menu_id for menu in original), 0.0))
    candidates_by_kind: dict[MenuBoardKind, MenuCandidates] = {}
    arrangements: dict[str | None, Arrangement] = {}

    def arrangement_for(basis: str | None) -> Arrangement:
        if basis not in arrangements:
            if basis is None:
                arrangements[basis] = arrange_menu_board(None, original, no_data, EMPTY, k)
            else:
                tag = known[basis]
                if tag.kind not in candidates_by_kind:
                    candidates_by_kind[tag.kind] = lookup(store, original, tag.kind)
                lift = menu_share_lift(inputs, tag.tag, tag.kind, first_days[basis])
                arrangements[basis] = arrange_menu_board(basis, original, lift, candidates_by_kind[tag.kind], k)
        return arrangements[basis]

    same_basis = unchanged_menu_orders(cards, bases, settings)
    result = {}
    for item in cards:
        day = dt.date.fromisoformat(item.basis.ref_id)  # 메뉴판 카드의 근거는 날짜다
        if day not in bases:
            logger.warning("메뉴판: %s 의 기준 태그를 정하지 못해 배치안을 만들지 않는다", item.plan_id)
            continue
        arrangement = arrangement_for(bases[day])
        previous = previous_open_day(day, settings)
        same_order = previous in bases and arrangement_for(bases[previous]).order == arrangement.order
        result[item.plan_id] = MenuBoardCard(
            plan_id=item.plan_id,
            basis=bases[day],
            arrangement=arrangement,
            reason=arrangement.reason or item.reason_line,
            unchanged=item.plan_id in same_basis or same_order,
        )
    return result


def tag_periods_from_inputs(inputs: AnalysisInputs, calendar: list[CalendarCell]) -> list[TagPeriod]:
    """달력에 보인 근거 id(날씨 제외)의 원본 일정 기간. 세부 종류를 알 수 없는 근거 id는 빠진다."""
    return [tag.period for tag in _known_tags(inputs, calendar).values()]


def _known_tags(inputs: AnalysisInputs, calendar: list[CalendarCell]) -> dict[str, _Tag]:
    """달력에 보인 근거 id 마다 태그·세부 종류·기간. 모르는 근거 id 는 경고를 남기고 뺀다."""
    first_seen: dict[str, tuple[str, dt.date]] = {}
    for cell in sorted(calendar, key=lambda c: c.date):
        for reason in cell.reasons:
            if reason.tag != "WEATHER":
                first_seen.setdefault(reason.ref_id, (reason.tag, cell.date))
    events = {event.event_id: event for event in inputs.events}
    games = {game.game_id: game for game in inputs.games}
    seasons = _seasons(inputs, calendar)
    known = {}
    for ref_id, (tag, first_day) in first_seen.items():
        if tag == "EVENT" and ref_id in events:
            event = events[ref_id]
            last_moment = event.end_at - dt.timedelta(microseconds=1)  # 0시 정각에 끝나면 전날까지
            period = TagPeriod(ref_id, to_seoul(event.start_at).date(), max(to_seoul(last_moment), to_seoul(event.start_at)).date())
            known[ref_id] = _Tag(tag, event.kind, period)
        elif tag == "GAME" and ref_id in games:
            game = games[ref_id]
            day = to_seoul(game.start_at).date()
            known[ref_id] = _Tag(tag, game.kind, TagPeriod(ref_id, day, day))
        elif tag == "SEASON" and (season := _season_of(ref_id)) is not None:
            known[ref_id] = _Tag(tag, season, _season_period(ref_id, season, first_day, seasons))
        else:
            logger.warning("메뉴판: 근거 id %r(%s)의 세부 종류를 알 수 없어 메뉴판 판단에서 뺀다", ref_id, tag)
    return known


def _season_of(ref_id: str) -> Season | None:
    return next((season for season in SEASONS if season_ref_id(season) == ref_id), None)


def _seasons(inputs: AnalysisInputs, calendar: list[CalendarCell]) -> dict[dt.date, Season | None]:
    """날씨 기록 첫날부터 달력 마지막 날까지 날짜별 계절."""
    if not calendar:
        return {}
    last_day = max(cell.date for cell in calendar)
    first_day = min([w.date for w in inputs.weather] + [min(cell.date for cell in calendar)])
    return seasons_between(inputs.weather, first_day, last_day)


def _season_period(ref_id: str, season: Season, seen_on: dt.date, seasons: dict[dt.date, Season | None]) -> TagPeriod:
    """seen_on 이 속한, 같은 계절이 이어지는 기간. 달력 마지막 날까지 이어지면 끝은 None(아직 안 끝남)."""
    one_day = dt.timedelta(days=1)
    start = seen_on
    while seasons.get(start - one_day) == season:
        start -= one_day
    end = seen_on
    while seasons.get(end + one_day) == season:
        end += one_day
    return TagPeriod(ref_id, start, None if end + one_day not in seasons else end)


def _without_unknown_reasons(calendar: list[CalendarCell], known: dict[str, _Tag]) -> list[CalendarCell]:
    """모르는 근거 id 의 이유만 지운 달력(칸은 남긴다). 날씨 이유는 그대로 둔다."""
    def keep(reason) -> bool:
        return reason.tag == "WEATHER" or reason.ref_id in known

    return [
        cell if all(keep(r) for r in cell.reasons) else cell.model_copy(update={"reasons": [r for r in cell.reasons if keep(r)]})
        for cell in calendar
    ]
