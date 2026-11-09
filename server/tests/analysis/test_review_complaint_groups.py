"""불만 묶음과 빠른 응대 판정 (app/analysis/review/complaint_groups.py)."""

from app.analysis.review.complaint_groups import COMPLAINT_TYPES, groups_of, is_quick, sort_types


def test_every_complaint_type_has_a_group():
    assert groups_of(COMPLAINT_TYPES) == ["FOOD", "DELIVERY", "SERVICE"]


def test_food_types_share_one_group():
    assert groups_of(["TASTE", "PORTION", "HYGIENE", "PHOTO_MISMATCH"]) == ["FOOD"]


def test_groups_keep_fixed_order():
    assert groups_of(["SERVICE", "DELIVERY_DELAY", "TASTE"]) == ["FOOD", "DELIVERY", "SERVICE"]


def test_sort_types_removes_duplicates_and_orders():
    assert sort_types(["SERVICE", "TASTE", "SERVICE"]) == ["TASTE", "SERVICE"]


def test_quick_when_any_group():
    assert is_quick(["DELIVERY"]) is True
    assert is_quick([]) is False
