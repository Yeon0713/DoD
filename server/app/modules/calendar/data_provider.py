"""우리 매장 달력 데이터 가져오기.

DB → 태성 분석(calendar_day, 오늘부터 35일)을 기간에 맞는 칸만 골라 돌려준다.
이유 한 줄(reason_text)은 CLOVA X 로 다듬은 문장이 있으면 그것으로 바꿔 보낸다.
"""

import datetime as dt

from app.core.seoul_time import is_within_dates
from app.data_pipeline.store_snapshot_cache import get_snapshot
from app.modules.calendar.response_format import CalendarResponse
from app.sentence_polish.polish_with_clova import polished


def get_calendar(store_id: str, from_date: dt.date | None, to_date: dt.date | None) -> CalendarResponse:
    snapshot = get_snapshot(store_id)
    cells = [
        cell.model_copy(update={"reason_text": polished("calendar_reason", cell.reason_text, snapshot.store)})
        for cell in snapshot.calendar_cells
        if is_within_dates(cell.date, from_date, to_date)
    ]
    return CalendarResponse(is_example=False, cells=cells)
