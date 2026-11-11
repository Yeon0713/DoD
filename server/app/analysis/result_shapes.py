"""분석 결과 테이블 여섯 개의 한 줄 모양과 고정 샘플 읽기.

테이블 정의 문서는 contracts/schema.md 이다.
계획 엔진(app/planner/data_shapes.py)에 같은 모양이 있는 테이블은 그 모델을 그대로 쓰고,
없는 두 테이블만 여기서 정의한다.
- SalesDailyRow: 하루 × 시간대 매출과 매출에서 빠지는 항목.
- ReviewLabelRow: 리뷰 분류. 계획 엔진에서는 Review.label 안에 들어가고, 테이블에서는 review_id 를 붙여 따로 둔다.

시간대 코드값은 MORNING(오픈~11시), LUNCH(11~17시), DINNER(17시~마감)이다.
계획 엔진은 아직 LUNCH, DINNER, NIGHT 만 받으므로, 바뀌기 전까지 분석 결과의 시간대에는 NIGHT 도 허용한다.

고정 샘플은 contracts/fixtures/analysis/<테이블>.example.json 이고 load_fixture() 로 읽는다.
"""

import datetime as dt
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, model_validator

from app.planner.data_shapes import (
    CalendarCell,
    CustomerCycle,
    ReviewLabel,
    RiskSignal,
    SalesAnomaly,
)

# server/app/analysis/ 에서 세 단계 위가 저장소 맨 위
FIXTURES_DIR = Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "analysis"


# 분석 결과의 시간대. NIGHT 는 계획 엔진이 새 코드값으로 바뀔 때까지만 허용한다.
AnalysisDaypart = Literal["MORNING", "LUNCH", "DINNER", "NIGHT"]
DAYPART_ORDER: tuple[str, ...] = ("MORNING", "LUNCH", "DINNER", "NIGHT")

# 매출에서 빠지는 항목. 값을 가져올 데이터가 없으면 None 이다.
DEDUCTION_FIELDS: tuple[str, ...] = ("food_cost", "labor_cost", "platform_fee", "delivery_fee", "payment_fee")


class SalesDailyRow(BaseModel):
    """sales_daily 한 줄. 키는 (date, daypart). 금액은 원 단위 정수."""

    date: dt.date
    daypart: AnalysisDaypart
    sales_amount: int  # 매출
    qty: int  # 판매 수량 합
    food_cost: int | None = None  # 메뉴 원가 합 (수량 × 원가). 메뉴 원가가 없으면 None
    labor_cost: int | None = None  # 그 시간대와 겹치는 근무 시간 × 시급. 근무표가 없으면 None
    platform_fee: int | None = None  # 배달앱 중개수수료
    delivery_fee: int | None = None  # 사장님이 내는 배달비
    payment_fee: int | None = None  # 결제수수료
    profit: int  # 매출 - 값이 있는 빠지는 항목의 합

    @model_validator(mode="after")
    def _profit_matches(self):
        deducted = sum(getattr(self, name) or 0 for name in DEDUCTION_FIELDS)
        if self.profit != self.sales_amount - deducted:
            raise ValueError("profit 은 sales_amount 에서 값이 있는 빠지는 항목을 뺀 값과 같아야 합니다.")
        return self


class ReviewLabelRow(ReviewLabel):
    """review_label 한 줄. 키는 review_id."""

    review_id: str

    def to_label(self) -> ReviewLabel:
        """계획 엔진의 Review.label 에 넣을 모양으로 바꾼다."""
        return ReviewLabel.model_validate(self.model_dump(exclude={"review_id"}))


class CalendarDayRow(CalendarCell):
    """calendar_day 한 줄. 키는 (date, daypart, computed_at). 시간대만 분석 결과 코드값으로 받는다."""

    daypart: AnalysisDaypart


class CustomerCycleRow(CustomerCycle):
    """customer_cycle 한 줄. 키는 (customer_key, computed_at)."""

    expected_daypart: AnalysisDaypart | None = None


RiskSignalRow = RiskSignal  # risk_signal. 키는 risk_id


class SalesAnomalyRow(SalesAnomaly):
    """sales_anomaly 한 줄. 키는 (date, daypart)."""

    daypart: AnalysisDaypart


# 테이블 이름 → 한 줄 모양
RESULT_TABLES: dict[str, type[BaseModel]] = {
    "sales_daily": SalesDailyRow,
    "calendar_day": CalendarDayRow,
    "customer_cycle": CustomerCycleRow,
    "review_label": ReviewLabelRow,
    "risk_signal": RiskSignalRow,
    "sales_anomaly": SalesAnomalyRow,
}


def load_fixture_raw(table: str) -> list[dict]:
    """고정 샘플 JSON 의 rows 를 dict 그대로 읽는다. 파일 맨 위의 "_설명" 은 읽지 않는다."""
    data = json.loads((FIXTURES_DIR / f"{table}.example.json").read_text(encoding="utf-8"))
    return data["rows"]


def load_fixture(table: str) -> list[BaseModel]:
    """고정 샘플을 그 테이블의 모양으로 읽는다. 모양이 틀리면 pydantic 오류가 난다."""
    model = RESULT_TABLES[table]
    return [model.model_validate(row) for row in load_fixture_raw(table)]
