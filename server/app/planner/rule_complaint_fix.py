"""④ 반복 불만 개선 규칙.

같은 불만이 7일 안에 3건 쌓여 위험 신호가 열리면, 발견 뒤 첫 14:00(같은 시각 포함)에
개선 체크리스트 승인을 요청한다. 실행 시각은 없다(체크리스트를 마치는 것이 실행). 기한은 2차에서 정한다.
"""

from app.planner.data_shapes import Basis, PlanItem, RiskSignal, StoreSettings
from app.planner.notification_time_helpers import next_named_slot

COMPLAINT_NAMES = {
    "TASTE": "맛",
    "PORTION": "양",
    "HYGIENE": "위생",
    "PHOTO_MISMATCH": "사진과 다름",
    "DELIVERY_DELAY": "배달 지연",
    "SERVICE": "응대",
}


def plan_complaint_fixes(risk_signals: list[RiskSignal], store: StoreSettings) -> list[PlanItem]:
    items = []
    for risk in risk_signals:
        if risk.status != "OPEN":
            continue
        approval_at = next_named_slot(risk.detected_at, "AFTERNOON", store, include_same_time=True)
        items.append(
            PlanItem(
                plan_id=f"REVIEW_FIX:{risk.risk_id}:{approval_at.date()}",
                task_type="REVIEW_FIX",
                basis=Basis(kind="RISK_SIGNAL", ref_id=risk.risk_id),
                target_date=approval_at.date(),
                approval_request_at=approval_at,
                reason_line=(
                    f"최근 7일 동안 {COMPLAINT_NAMES[risk.complaint_type]} 불만이 "
                    f"{len(risk.review_ids)}건 들어왔어요."
                ),
                planned_at=risk.detected_at,
            )
        )
    return items
