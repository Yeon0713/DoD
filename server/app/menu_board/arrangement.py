"""메뉴판 배치안: 기준 태그에 맞춰 올릴 메뉴를 골라 맨 위에 두고, 나머지는 원래 순서를 지킨다.

점수 (메뉴마다, 원래 순서에 있는 메뉴만)
- LLM 점수 = (m − r + 1) / m. m = min(MAX_CANDIDATES, 메뉴 수)이고 LLM 이 그보다 적게 골라도 그대로다.
  r 은 원래 순서에 없는 id 와 겹친 id 를 걸러 낸 뒤의 후보 안 순위(1부터)다. 후보 밖은 0.
- 데이터 점수 = max(비중 변화 %p, 0) / 매장 최댓값. 최댓값은 원래 순서의 메뉴만 보고, 0 이하면 모두 0.
  비중 변화가 없는 메뉴는 0.
- 합산 = (1 − w) · LLM + w · 데이터, w = n_eff / (n_eff + DATA_PRIOR_DAYS).
  n_eff 는 데이터 점수에 쓴 과거 날의 유효 날 수(ShareLift.n_eff). 작은 날은 하루보다 적게 세어, 작은 표본만 있으면 LLM 쪽을 더 믿는다.
  합산은 소수 9자리로 반올림해 견준다. 그보다 작은 점수는 0으로 본다.
고르기
- 합산 점수가 0보다 큰 메뉴를 점수 순서로 최대 K개 올린다. 동점이면 원래 순서에서 앞선 메뉴.
  0보다 큰 메뉴가 K개보다 적으면 그만큼만 올린다.
표시
- same_as_original: 바뀐 뒤 전체 순서가 원래 순서와 같다. 직전 영업일 배치를 모르므로 '바뀌는 것 없음'은 부르는 쪽이 정한다.
- 기준 태그가 없으면 원래 순서이고 이유는 "". 기준 태그가 있는데 점수가 모두 0이면 원래 순서이고 이유는 NO_PICK_REASON.
"""

from dataclasses import dataclass

from app.analysis.input_shapes import Menu
from app.menu_board.menu_candidates import MAX_CANDIDATES, MenuCandidates
from app.menu_board.menu_share_lift import ShareLift

DATA_PRIOR_DAYS = 5  # 데이터 비중 w = n_eff / (n_eff + DATA_PRIOR_DAYS)
NO_PICK_REASON = "추천할 메뉴를 찾지 못했어요."
_DIGITS = 9  # 점수를 견줄 때 남기는 소수 자리. 수학적으로 같은 점수가 부동소수 오차로 동점을 깨지 않게 한다


@dataclass(frozen=True)
class Arrangement:
    """raised: 맨 위로 올릴 메뉴 id(올라가는 순서). reason: 이유 한 줄(없으면 ""). order: 바뀐 뒤 전체 순서.
    same_as_original: order 가 원래 순서와 같다(기준 태그 없음, 점수가 모두 0, 올릴 메뉴가 이미 맨 위).
    """

    raised: tuple[str, ...]
    reason: str
    order: tuple[Menu, ...]
    same_as_original: bool


def arrange_menu_board(
    basis: str | None, original: list[Menu], lift: ShareLift, candidates: MenuCandidates, k: int
) -> Arrangement:
    """basis: 그날 기준 태그(근거 id). None 이면 원래 순서로 되돌린다. k: 맨 위로 올릴 메뉴 수(0 이상).

    lift 와 candidates 는 결과가 없어도 넘긴다(n=0·모두 0.0 인 ShareLift, 빈 MenuCandidates).
    """
    if k < 0:
        raise ValueError(f"올릴 메뉴 수 k 는 0 이상이어야 합니다: {k}")
    if basis is None:
        return Arrangement((), "", tuple(original), True)
    scores = _combined_scores(original, lift, candidates)
    ranked = sorted(
        (menu for menu in original if scores[menu.menu_id] > 0),
        key=lambda menu: -scores[menu.menu_id],  # sorted 는 안정 정렬이라 동점이면 원래 순서가 남는다
    )
    raised = tuple(menu.menu_id for menu in ranked[:k])
    if not raised:
        return Arrangement((), NO_PICK_REASON, tuple(original), True)
    by_id = {menu.menu_id: menu for menu in original}
    order = (*(by_id[menu_id] for menu_id in raised), *(menu for menu in original if menu.menu_id not in raised))
    return Arrangement(raised, candidates.reason, order, order == tuple(original))


def _combined_scores(original: list[Menu], lift: ShareLift, candidates: MenuCandidates) -> dict[str, float]:
    """원래 순서의 메뉴마다 합산 점수."""
    menu_ids = [menu.menu_id for menu in original]
    m = min(MAX_CANDIDATES, len(menu_ids))
    known = set(menu_ids)
    ranked_ids = list(dict.fromkeys(menu_id for menu_id in candidates.menu_ids if menu_id in known))
    llm = {menu_id: (m - rank + 1) / m for rank, menu_id in enumerate(ranked_ids[:m], start=1)}
    gains = {menu_id: max(lift.lift_pp.get(menu_id, 0.0), 0.0) for menu_id in menu_ids}
    max_gain = max(gains.values(), default=0.0)
    w = lift.n_eff / (lift.n_eff + DATA_PRIOR_DAYS)
    return {
        menu_id: round((1 - w) * llm.get(menu_id, 0.0) + w * (gains[menu_id] / max_gain if max_gain > 0 else 0.0), _DIGITS)
        for menu_id in menu_ids
    }
