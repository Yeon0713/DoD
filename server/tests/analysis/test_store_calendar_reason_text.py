"""달력 칸의 이유 한 줄 (app/analysis/store_calendar/reason_text.py). 1차는 템플릿 문장이다."""

import pytest

from app.analysis.store_calendar.reason_text import NamedReason, reason_text


def test_no_reason_reads_as_usual():
    assert reason_text([], 1.0) == "평소와 비슷할 것 같아요"
    assert reason_text([], None) == "평소와 비슷할 것 같아요"  # 기준선이 없는 칸


def test_one_reason_with_percent_from_ratio():
    game = NamedReason(name="국가대표 축구 경기", effect=0.351)
    assert reason_text([game], 1.35) == "국가대표 축구 경기 영향으로 평소보다 35% 많을 것 같아요"
    rain = NamedReason(name="비", effect=-0.132)
    assert reason_text([rain], 0.87) == "비 영향으로 평소보다 13% 적을 것 같아요"


def test_several_reasons_in_order_of_effect_size():
    reasons = [NamedReason("겨울", 0.05), NamedReason("비", -0.132), NamedReason("지역 축제", 0.493)]
    assert reason_text(reasons, 1.41) == "지역 축제 · 비 · 겨울 영향으로 평소보다 41% 많을 것 같아요"
    tie = [NamedReason("대학 축제", 0.15), NamedReason("야구 경기", -0.15), NamedReason("겨울", 0.05)]
    assert reason_text(tie, 1.05) == "대학 축제 · 야구 경기 · 겨울 영향으로 평소보다 5% 많을 것 같아요"  # 크기가 같으면 받은 순서


def test_reasons_that_cancel_out_read_as_usual_with_the_reasons():
    reasons = [NamedReason("플리마켓", 0.10), NamedReason("비", -0.10)]
    assert reason_text(reasons, 1.0) == "플리마켓 · 비 영향이 있지만 평소와 비슷할 것 같아요"



def test_reasons_without_a_ratio_are_rejected():
    """기준선이 없는 칸(ratio 없음)은 이유도 비어 있어야 한다. 둘이 같이 오면 부르는 쪽의 잘못이다."""
    with pytest.raises(ValueError):
        reason_text([NamedReason("지역 축제", 0.49)], None)


def test_percent_survives_float_noise_and_large_ratios():
    festival = [NamedReason("지역 축제", 0.15)]
    assert reason_text(festival, 1.15) == "지역 축제 영향으로 평소보다 15% 많을 것 같아요"  # 1.15 − 1 = 0.1499…
    assert reason_text([NamedReason("비", -0.15)], 0.85) == "비 영향으로 평소보다 15% 적을 것 같아요"
    morning = [NamedReason("지역 축제", 1.643), NamedReason("겨울", 0.05)]
    assert reason_text(morning, 2.69) == "지역 축제 · 겨울 영향으로 평소보다 169% 많을 것 같아요"


def test_direction_follows_the_ratio_even_if_the_first_reason_points_the_other_way():
    reasons = [NamedReason("지역 축제", 0.20), NamedReason("비", -0.50)]
    assert reason_text(reasons, 1.15) == "비 · 지역 축제 영향으로 평소보다 15% 많을 것 같아요"
