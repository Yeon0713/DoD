"""불만 유형을 불만 묶음으로 바꾸고 빠른 응대(is_quick) 여부를 정한다.

묶음이 하나라도 있으면 별점과 관계없이 빠른 응대 대상이다.
"""

from collections.abc import Iterable

from app.planner.data_shapes import ComplaintGroup, ComplaintType

# 불만 유형 → 불만 묶음. 이 순서가 결과 목록의 순서다.
GROUP_OF: dict[ComplaintType, ComplaintGroup] = {
    "TASTE": "FOOD",
    "PORTION": "FOOD",
    "HYGIENE": "FOOD",
    "PHOTO_MISMATCH": "FOOD",
    "DELIVERY_DELAY": "DELIVERY",
    "SERVICE": "SERVICE",
}
COMPLAINT_TYPES: tuple[ComplaintType, ...] = tuple(GROUP_OF)
GROUP_ORDER: tuple[ComplaintGroup, ...] = ("FOOD", "DELIVERY", "SERVICE")


def sort_types(types: Iterable[str]) -> list[ComplaintType]:
    """중복을 빼고 COMPLAINT_TYPES 순서로 정렬한다."""
    unique = set(types)
    return [t for t in COMPLAINT_TYPES if t in unique]


def groups_of(types: Iterable[str]) -> list[ComplaintGroup]:
    """불만 유형 목록 → 불만 묶음 목록 (중복 없이 GROUP_ORDER 순서)."""
    groups = {GROUP_OF[t] for t in types}
    return [g for g in GROUP_ORDER if g in groups]


def is_quick(groups: Iterable[str]) -> bool:
    """불만 묶음이 하나라도 있으면 빠른 응대 대상이다."""
    return any(True for _ in groups)
