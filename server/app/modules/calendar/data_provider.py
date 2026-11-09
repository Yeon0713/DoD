"""우리 매장 달력 데이터 가져오기.

지금은 응답 예시(calendar_response.example.json)에서 기간에 맞는 칸만 골라 돌려준다.
태성의 분석 결과(calendar_day)가 나오면 그걸 읽도록 바꾼다.
"""

import datetime as dt

from app.core.sample_response_loader import load_sample_response
from app.core.seoul_time import is_within_dates
from app.modules.calendar.response_format import CalendarResponse


def get_calendar(from_date: dt.date | None, to_date: dt.date | None) -> CalendarResponse:
    calendar = CalendarResponse.model_validate(load_sample_response("calendar"))
    cells = [cell for cell in calendar.cells if is_within_dates(cell.date, from_date, to_date)]
    return calendar.model_copy(update={"cells": cells})
