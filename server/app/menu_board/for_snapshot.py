"""스냅샷 계산(store_snapshot_cache)에 메뉴판 배치안을 붙인다.

- LLM 후보는 뒤에서 부른다(candidates_in_background). 아직 결과가 없으면 데이터 점수만으로 배치안을 만들고,
  다음 계산 때 LLM 후보가 반영된다. 스냅샷 계산은 CLOVA 를 기다리지 않는다.
- 배치안 계산이 실패해도 달력·할 일 같은 나머지 화면은 그대로 나와야 하므로, 오류는 기록하고 빈 배치안을 돌려준다.
  로그 문구로 '실패해서 비어 있음', '계획이 없어서 비어 있음', '카드가 없어서 비어 있음'을 구분한다.
"""

import logging

from app.analysis.input_shapes import AnalysisInputs
from app.data_pipeline.menu_original_order import original_menu_order
from app.menu_board.assemble import MenuBoardCard, assemble_menu_board_cards
from app.menu_board.menu_candidates import candidates_in_background
from app.planner.data_shapes import CalendarCell, PlanResult, StoreSettings

logger = logging.getLogger(__name__)


def snapshot_menu_boards(
    store_id: str,
    store_row: dict,
    inputs: AnalysisInputs,
    settings: StoreSettings | None,
    plan: PlanResult | None,
    calendar: list[CalendarCell],
) -> dict[str, MenuBoardCard]:
    """메뉴판 카드 plan_id → 배치안. store_row: DB 가게 정보 한 줄. calendar: calendar_for_planner 결과."""
    if plan is None:
        logger.info("%s 가게: 계획 엔진 결과가 없어 메뉴판 배치안을 만들지 않았다", store_id)
        return {}
    cards = [item for item in plan.plan_items if item.task_type == "MENU_ORDER"]
    if not cards:
        logger.info("%s 가게: 메뉴판 카드가 없어 배치안을 만들지 않았다", store_id)
        return {}
    try:
        store = {"store_id": store_id, "name": store_row["name"], "category": store_row["category"]}
        original = original_menu_order(store_id)
        return assemble_menu_board_cards(calendar, cards, inputs, settings, store, original, candidates_in_background)
    except Exception:
        logger.exception("%s 가게: 메뉴판 배치안 계산이 실패해 배치안을 비워 둔다", store_id)
        return {}
