"""메뉴판 배치안 테스트. server/ 폴더에서 `python -m pytest` 로 실행한다.

원래 순서: 1 국수, 2 비빔국수, 3 만두, 4 전, 5 수육. m = min(5, 메뉴 수) = 5.
"""

import pytest

from app.analysis.input_shapes import Menu
from app.menu_board.arrangement import NO_PICK_REASON, arrange_menu_board
from app.menu_board.menu_candidates import EMPTY, MenuCandidates
from app.menu_board.menu_share_lift import ShareLift

ORIGINAL = [Menu(menu_id=m, name=n, category="MAIN", price=9000) for m, n in [("1", "국수"), ("2", "비빔국수"), ("3", "만두"), ("4", "전"), ("5", "수육")]]
WINTER = "season_winter"
K = 2


def lift(n: int, **pp: float) -> ShareLift:
    """lift(5, m3=6.0) → n=5(n_eff 도 5), 메뉴 3 의 비중 변화 +6%p, 나머지 0.0"""
    values = dict.fromkeys([menu.menu_id for menu in ORIGINAL], 0.0)
    values.update({key.removeprefix("m"): value for key, value in pp.items()})
    return ShareLift(n, float(n), values)


NO_DATA = lift(0)


def ids(menus) -> list[str]:
    return [menu.menu_id for menu in menus]


def test_winter_raises_suyuk_and_mandu():
    candidates = MenuCandidates(("5", "3"), "추운 날엔 따뜻한 수육과 만두가 잘 어울려요")  # LLM: 수육 1.0, 만두 0.8
    data = lift(5, m5=6.0, m3=3.0, m4=1.0, m1=-4.0)  # w = 5/10 = 0.5. 데이터: 수육 1.0, 만두 0.5, 전 0.17
    result = arrange_menu_board(WINTER, ORIGINAL, data, candidates, K)
    # 합산: 수육 0.5·1.0 + 0.5·1.0 = 1.0, 만두 0.5·0.8 + 0.5·0.5 = 0.65, 전 0.5·0.17 = 0.08
    assert result.raised == ("5", "3")
    assert ids(result.order) == ["5", "3", "1", "2", "4"]  # 나머지는 원래 순서 그대로
    assert result.reason == "추운 날엔 따뜻한 수육과 만두가 잘 어울려요"
    assert result.same_as_original is False


def test_new_store_without_sales_history_uses_llm_only():
    candidates = MenuCandidates(("3", "5"), "만두와 수육이 어울려요")
    result = arrange_menu_board(WINTER, ORIGINAL, NO_DATA, candidates, K)  # n=0 → w=0
    assert result.raised == ("3", "5")


def test_empty_llm_candidates_use_data_only():
    result = arrange_menu_board(WINTER, ORIGINAL, lift(5, m4=2.0, m2=8.0), EMPTY, K)
    assert result.raised == ("2", "4")
    assert result.reason == ""  # LLM 이유가 없으면 빈 값 그대로. 문구는 부르는 쪽이 정한다


def test_menu_outside_llm_candidates_can_rise_with_data():
    candidates = MenuCandidates(("5",), "수육이 어울려요")
    data = lift(20, m4=10.0, m5=1.0)  # w = 0.8. 전: 0.8·1.0 = 0.8, 수육: 0.2·1.0 + 0.8·0.1 = 0.28
    assert arrange_menu_board(WINTER, ORIGINAL, data, candidates, K).raised == ("4", "5")


def test_data_weight_uses_effective_days_not_day_count():
    # 작은 날 여럿이라 n = 20 이어도 유효 날 수 n_eff = 1 이면 w = 1/(1 + 5) = 1/6
    data = ShareLift(20, 1.0, {menu.menu_id: 0.0 for menu in ORIGINAL} | {"4": 10.0})
    candidates = MenuCandidates(("5",), "수육이 어울려요")
    # 수육 (5/6)·1.0 ≈ 0.83, 전 (1/6)·1.0 ≈ 0.17. n 으로 w(= 0.8)를 정했다면 전 0.8, 수육 0.2 로 뒤집힌다
    assert arrange_menu_board(WINTER, ORIGINAL, data, candidates, K).raised == ("5", "4")


def test_ties_keep_original_order():
    assert arrange_menu_board(WINTER, ORIGINAL, lift(5, m5=5.0, m3=5.0), EMPTY, K).raised == ("3", "5")


def test_ties_survive_floating_point_noise():
    six = [*ORIGINAL, Menu(menu_id="6", name="보쌈", category="MAIN", price=9000)]
    candidates = MenuCandidates(("1", "2", "3", "4", "6"), "")  # 보쌈은 LLM 5위: (5/6)·(1/5) = 1/6
    data = ShareLift(1, 1.0, {"5": 4.0})  # w = 1/6. 수육은 데이터 최댓값: (1/6)·1 = 1/6
    result = arrange_menu_board(WINTER, six, data, candidates, k=6)
    assert result.raised[-2:] == ("5", "6")  # 같은 점수라 원래 순서에서 앞선 수육이 먼저


def test_all_zero_scores_keep_original_order_with_no_pick_reason():
    result = arrange_menu_board(WINTER, ORIGINAL, lift(5, m1=-3.0, m2=-1.0), EMPTY, K)
    assert result.raised == ()
    assert ids(result.order) == ["1", "2", "3", "4", "5"]
    assert result.same_as_original is True
    assert result.reason == NO_PICK_REASON == "추천할 메뉴를 찾지 못했어요."


def test_menus_already_on_top_are_same_as_original():
    candidates = MenuCandidates(("1", "2"), "국수가 어울려요")
    result = arrange_menu_board(WINTER, ORIGINAL, NO_DATA, candidates, K)
    assert result.raised == ("1", "2")
    assert result.same_as_original is True
    assert result.reason == "국수가 어울려요"


def test_no_basis_returns_original_order_without_reason():
    candidates = MenuCandidates(("5", "3"), "수육과 만두가 어울려요")
    result = arrange_menu_board(None, ORIGINAL, lift(5, m5=6.0), candidates, K)  # 기준 태그가 없으면 점수는 보지 않는다
    assert result.raised == ()
    assert ids(result.order) == ["1", "2", "3", "4", "5"]
    assert result.same_as_original is True
    assert result.reason == ""  # 점수가 모두 0인 날의 문구와 다르다
    assert result.reason != NO_PICK_REASON


def test_fewer_positive_menus_than_k_raise_only_those():
    result = arrange_menu_board(WINTER, ORIGINAL, NO_DATA, MenuCandidates(("5",), "수육이 어울려요"), K)
    assert result.raised == ("5",)
    assert ids(result.order) == ["5", "1", "2", "3", "4"]


def test_ids_outside_original_order_are_ignored_and_missing_lift_counts_as_zero():
    candidates = MenuCandidates(("9", "5"), "")  # 9 는 원래 순서에 없는 메뉴. 걸러 낸 뒤 순위를 매겨 수육이 1위(1.0)
    data = ShareLift(5, 5.0, {"9": 50.0, "3": 10.0, "4": 9.0})  # 9 는 최댓값 계산에서도 빠진다. 1·2·5 는 lift_pp 에 없다
    result = arrange_menu_board(WINTER, ORIGINAL, data, candidates, K)
    # 만두 0.5·1.0 = 0.5, 수육 0.5·1.0 = 0.5, 전 0.5·0.9 = 0.45.
    # 9 가 자리를 차지했다면 수육은 0.5·0.8 = 0.4 로 전에 밀리고, 9 가 최댓값이었다면 만두는 0.1
    assert result.raised == ("3", "5")
    assert "9" not in ids(result.order)


def test_duplicate_candidate_keeps_its_first_rank():
    result = arrange_menu_board(WINTER, ORIGINAL, NO_DATA, MenuCandidates(("5", "3", "5"), ""), K)
    assert result.raised == ("5", "3")  # 수육 1위(1.0). 뒤 자리(0.6)로 덮어쓰면 만두(0.8)에 밀린다


def test_negative_k_is_rejected():
    with pytest.raises(ValueError):
        arrange_menu_board(WINTER, ORIGINAL, NO_DATA, MenuCandidates(("5",), ""), -1)


def test_llm_rank_score_uses_m_even_when_llm_picks_fewer():
    candidates = MenuCandidates(("5", "3"), "")  # LLM 이 2개만 골라도 m = 5: 수육 1.0, 만두 0.8 (m 이 2 였다면 0.5)
    data = lift(5, m1=5.0, m4=3.0)  # 데이터: 국수 1.0, 전 0.6
    result = arrange_menu_board(WINTER, ORIGINAL, data, candidates, k=3)
    # 국수 0.5, 수육 0.5, 만두 0.4, 전 0.3. 국수와 수육은 동점이라 원래 순서
    assert result.raised == ("1", "5", "3")


def test_negative_share_change_counts_as_zero_not_a_penalty():
    data = lift(5, m5=-5.0, m4=5.0)  # 수육은 그날 덜 팔렸지만 데이터 점수는 0 이지 마이너스가 아니다
    result = arrange_menu_board(WINTER, ORIGINAL, data, MenuCandidates(("5",), ""), K)
    assert result.raised == ("4", "5")  # 전 0.5, 수육 0.5·1.0 = 0.5. 동점이라 원래 순서
