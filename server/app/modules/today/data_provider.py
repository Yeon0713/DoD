"""오늘의 카드 데이터 가져오기.

지금은 응답 예시(today_response.example.json)를 그대로 돌려준다.
계획 엔진을 연결하면 make_plan 결과에서 오늘 묶음만 골라 돌려준다.
"""

from app.core.sample_response_loader import load_sample_response
from app.modules.today.response_format import TodayResponse


def get_today() -> TodayResponse:
    return TodayResponse.model_validate(load_sample_response("today"))
