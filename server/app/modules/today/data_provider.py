"""오늘의 카드 데이터 가져오기.

DB → 태성 분석 → 계획 엔진 결과(store_snapshot_cache)에서 오늘 날짜의 알림 묶음만 골라 돌려준다.
묶음 안의 각 줄은 plan_id / notice_id 만 가리키고, 카드 문구는 /api/plan 에 있다.
"""

from app.core.seoul_time import to_seoul
from app.data_pipeline.store_snapshot_cache import get_snapshot
from app.modules.today.response_format import TodayResponse


def get_today(store_id: str) -> TodayResponse:
    snapshot = get_snapshot(store_id)
    plan = snapshot.require_plan()
    today = snapshot.computed_at.date()
    batches = [batch for batch in plan.batches if to_seoul(batch.slot_at).date() == today]
    return TodayResponse(is_example=False, date=today, batches=batches)
