"""달력 칸의 이유 한 줄(reason_text)을 만든다. 1차는 템플릿 문장이고, 나중에 N7에서 바꾼다.

- 이유가 없으면 "평소와 비슷할 것 같아요"
- 있으면 "{이유} 영향으로 평소보다 {n}% 많을(적을) 것 같아요". 이유는 효과의 절댓값이 큰 순서로 " · " 로 잇는다
- 이유가 있어도 ratio 가 1.00 이면 "{이유} 영향이 있지만 평소와 비슷할 것 같아요"
- 기준선이 없는 칸(ratio 없음)은 이유도 없어야 한다. 이유가 같이 오면 ValueError
- 이유 이름은 부르는 쪽이 붙인다(행사·경기는 title, 날씨는 비·폭염·한파, 계절은 겨울·여름)
"""

from dataclasses import dataclass

USUAL_TEXT = "평소와 비슷할 것 같아요"


@dataclass(frozen=True)
class NamedReason:
    name: str  # 행사·경기 title, 날씨·계절 이름. 예) "지역 축제", "비", "겨울"
    effect: float  # 0.35 이면 +35%


def reason_text(reasons: list[NamedReason], ratio: float | None) -> str:
    """이유와 비율(ratio)로 카드에 보일 한 줄. 퍼센트는 ratio 에서 계산한다(1.35 → 35%)."""
    if ratio is None:
        if reasons:
            raise ValueError("기준선이 없는 칸(ratio 없음)에는 이유가 없어야 합니다.")
        return USUAL_TEXT
    if not reasons:
        return USUAL_TEXT
    ordered = sorted(reasons, key=lambda r: abs(r.effect), reverse=True)  # 안정 정렬: 크기가 같으면 받은 순서
    names = " · ".join(r.name for r in ordered)
    ratio = round(ratio, 2)  # 달력의 ratio 는 소수 둘째 자리다. 덜 반올림된 값이 와도 같은 문장이 나오게 한다
    percent = round(abs(ratio - 1) * 100)  # 소수 오차만 정리한다(1.15 → 15)
    if percent == 0:  # 이유끼리 상쇄돼 ratio 가 1.00 이면 "0% 많을" 대신
        return f"{names} 영향이 있지만 {USUAL_TEXT}"
    direction = "많을" if ratio > 1 else "적을"  # 방향은 ratio 로 정한다. 맨 앞 이유가 반대 방향일 수 있다
    return f"{names} 영향으로 평소보다 {percent}% {direction} 것 같아요"
