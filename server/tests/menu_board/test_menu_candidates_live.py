"""실제 HyperCLOVA X 로 메뉴 후보를 받아 본다. CLOVA 키가 없으면 건너뛴다(키 없는 환경에서도 실패하지 않는다).

LLM 답은 매번 달라지므로 순위는 보지 않는다. 메뉴 목록 안의 id 만 오는지, 이유 한 줄이 검사를 통과하는지만 본다.
server/ 폴더에서 `python -m pytest` 로 실행한다.
"""

import pytest

from app.core.config import settings
from app.data_pipeline import read_store_db
from app.data_pipeline.menu_original_order import original_menu_order
from app.menu_board import menu_candidates as module
from app.menu_board.menu_candidates import MAX_REASON_LENGTH, menu_candidates


ATTEMPTS = 3  # 이유 한 줄은 가끔 검사에 걸려 빈 값이 된다(그때 카드는 기준 태그 문구를 쓴다). 몇 번 받아 한 번이라도 통과하면 된다


@pytest.mark.parametrize("kind", ["WINTER", "UNIV_FESTIVAL"])
def test_live_clova_returns_listed_menu_ids_and_a_usable_reason(kind):
    if not settings.clova_studio_api_key:
        pytest.skip("CLOVA 키가 없어 실제 호출을 건너뛴다")
    menus = original_menu_order("s001")
    row = read_store_db.read_store("s001")
    store = {"store_id": "s001", "name": row["name"], "category": row["category"]}
    listed = {menu.menu_id for menu in menus}
    reasons = []
    for _ in range(ATTEMPTS):
        module.forget_all()
        result = menu_candidates(store, menus, kind)
        assert set(result.menu_ids) <= listed  # 목록 밖 id 는 매번 없어야 한다
        if result.menu_ids and result.reason:
            reasons.append(result.reason)
            break
    module.forget_all()
    assert reasons, f"{ATTEMPTS}번 받아도 후보와 검사를 통과한 이유 한 줄이 없었다"
    assert len(reasons[0]) <= MAX_REASON_LENGTH
