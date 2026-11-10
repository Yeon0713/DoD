"""위험 신호(risk_signal)를 열고 이어 간다.

재계산 시각(now)마다 부른다. 이전 위험 신호 목록을 받아 바뀐 전체 목록을 돌려준다.

- 분류 결과(labeled_at ≤ now)가 있고 now 이전에 쓰인 리뷰만 쓴다. 한 리뷰에 불만 유형이 여러 개면 유형마다 센다.
- 같은 유형 신호의 마지막 리뷰(last_at)가 now 기준 7일 안이면 '열려 있음'이다.
  열려 있으면 그 유형의 새 리뷰를 근거에 더하고 last_at 을 늘린다. detected_at, risk_id 는 바꾸지 않는다.
- 열려 있지 않으면, 최근 7일((now − 7일, now]) 안에 아직 어느 신호에도 쓰이지 않은 그 유형 리뷰가
  3건 이상일 때 새로 연다. detected_at 은 now 다.
- 7일 동안 같은 불만이 없으면 그 신호는 끝난 것으로 보고, 다음에 몰리면 새 신호로 연다. status 는 OPEN 으로 둔다.
- risk_id 는 이전 신호의 가장 큰 번호 + 1 이다(risk_004 형식). 한 번 붙인 id 는 바꾸지 않는다.
"""

import datetime as dt
import re
from collections import defaultdict

from app.analysis.result_shapes import ReviewLabelRow, RiskSignalRow
from app.analysis.review.complaint_groups import COMPLAINT_TYPES
from app.planner.data_shapes import Review

WINDOW = dt.timedelta(days=7)
MIN_REVIEWS = 3
RISK_ID_RE = re.compile(r"^risk_(\d+)$")


def _next_number(signals: list[RiskSignalRow]) -> int:
    numbers = [int(m.group(1)) for s in signals if (m := RISK_ID_RE.match(s.risk_id))]
    return max(numbers, default=0) + 1


def is_open(signal: RiskSignalRow, now: dt.datetime) -> bool:
    """마지막 리뷰가 now 기준 7일 안이면 열려 있다."""
    return signal.last_at >= now - WINDOW


def update_risk_signals(
    reviews: list[Review],
    labels: list[ReviewLabelRow],
    previous: list[RiskSignalRow],
    now: dt.datetime,
) -> list[RiskSignalRow]:
    usable = {label.review_id: label for label in labels if label.labeled_at <= now}
    written_at = {review.review_id: review.written_at for review in reviews if review.written_at <= now}

    # 불만 유형 → 그 유형 리뷰 (작성 시각, id) 목록
    by_type: dict[str, list[tuple[dt.datetime, str]]] = defaultdict(list)
    for review_id, label in usable.items():
        if review_id not in written_at:
            continue
        for complaint_type in label.complaint_types:
            by_type[complaint_type].append((written_at[review_id], review_id))

    signals = {signal.risk_id: signal for signal in previous}
    number = _next_number(previous)
    for complaint_type in COMPLAINT_TYPES:  # 정해진 순서로 돌아서 risk_id 가 늘 같게 붙는다
        found = sorted(by_type.get(complaint_type, []))
        if not found:
            continue
        same_type = [s for s in signals.values() if s.complaint_type == complaint_type]
        used = {review_id for s in same_type for review_id in s.review_ids}
        active = max((s for s in same_type if is_open(s, now)), key=lambda s: s.last_at, default=None)

        if active is not None:
            added = [(t, rid) for t, rid in found if rid not in used and t >= active.first_at]
            if added:
                merged = sorted([(written_at.get(rid, active.first_at), rid) for rid in active.review_ids] + added)
                signals[active.risk_id] = active.model_copy(update={
                    "review_ids": [rid for _, rid in merged],
                    "last_at": max(active.last_at, merged[-1][0]),
                })
            continue

        recent = [(t, rid) for t, rid in found if rid not in used and now - WINDOW < t]
        if len(recent) >= MIN_REVIEWS:
            risk_id = f"risk_{number:03d}"
            number += 1
            signals[risk_id] = RiskSignalRow(
                risk_id=risk_id,
                complaint_type=complaint_type,
                review_ids=[rid for _, rid in recent],
                first_at=recent[0][0],
                last_at=recent[-1][0],
                detected_at=now,
                status="OPEN",
            )
    return sorted(signals.values(), key=lambda s: s.risk_id)
