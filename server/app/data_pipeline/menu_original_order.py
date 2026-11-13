"""메뉴판 원래 순서: 사장님이 정해 둔 메뉴 목록 순서. 메뉴판을 바꿀 때 맨 위 몇 자리만 바꾸고 나머지는 이 순서를 지킨다.

- 등록한 가게: 네이버 지도에서 읽어 둔 메뉴 화면 순서(registered_stores.place_info 의 menus)
- 목업 가게(네이버 가게와 연결해 등록한 목업 포함): menu_id 순서
돌려주는 메뉴는 분석 입력(AnalysisInputs.menus)과 같은 모양이다. menu_id 도 같은 문자열이다.
"""

import logging
from collections import defaultdict, deque

from app.analysis.input_shapes import Menu
from app.data_pipeline import read_store_db, registered_stores
from app.data_pipeline.db_rows_to_analysis_inputs import to_menu

logger = logging.getLogger(__name__)


def original_menu_order(store_id: str) -> list[Menu]:
    """그 가게의 원래 메뉴 순서."""
    info = None if registered_stores.is_mock_store(store_id) else registered_stores.place_info(store_id)
    names = None if info is None else [menu.name for menu in info.menus]
    return original_order(read_store_db.read_menus(store_id), names, store_id=store_id)


def original_order(db_menus: list[dict], place_menu_names: list[str] | None, *, store_id: str = "?") -> list[Menu]:
    """가게 파일의 메뉴 행(read_menus)을 원래 순서로 늘어놓는다. store_id 는 경고에 남길 가게다.

    place_menu_names
    - None: 목업 가게. menu_id 순서.
    - []: 등록한 가게인데 네이버 지도에서 메뉴를 읽지 못했다. 경고를 남기고 menu_id 순서로 대신한다.
    - 그 밖: 네이버 지도 화면 순서. 메뉴 이름(앞뒤 공백만 정리)으로 가게 파일의 메뉴와 맞춘다.
      같은 이름이 여럿이면 화면에 나온 순서와 menu_id 가 작은 순서끼리 짝짓는다(등록할 때 화면 순서로 번호를 붙였다).
      가게 파일에 없는 메뉴는 경고를 남기고 뺀다. 화면에서 사라진 메뉴(가게 파일에만 있음)는 뺀다.
    """
    by_id = sorted(db_menus, key=lambda row: row["menu_id"])
    if not place_menu_names:
        if place_menu_names is not None:
            logger.warning("%s 가게: 네이버 지도 메뉴가 비어 있어 menu_id 순서를 원래 순서로 대신 쓴다", store_id)
        return [to_menu(row) for row in by_id]

    unmatched: dict[str, deque[dict]] = defaultdict(deque)  # 이름 → 아직 짝짓지 않은 메뉴 행(menu_id 순)
    for row in by_id:
        unmatched[row["name"].strip()].append(row)
    ordered = []
    for name in place_menu_names:
        rows = unmatched.get(name.strip())
        if rows:
            ordered.append(to_menu(rows.popleft()))
        else:
            logger.warning("%s 가게: 네이버 지도 메뉴 %r 가 가게 파일에 없어 원래 순서에서 뺀다", store_id, name)
    return ordered
