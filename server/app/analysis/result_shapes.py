"""분석 결과 테이블 여섯 개의 한 줄 모양과 고정 샘플 읽기.

테이블 정의 문서는 contracts/schema.md 이다.
계획 엔진(app/planner/data_shapes.py)에 같은 모양이 있는 테이블은 그 모델을 그대로 쓰고,
없는 두 테이블만 여기서 정의한다.
- SalesDailyRow: 하루 × 시간대 매출. /api/sales 의 SalesRow(grain=day)와 같은 값이다.
- ReviewLabelRow: 리뷰 분류. 계획 엔진에서는 Review.label 안에 들어가고, 테이블에서는 review_id 를 붙여 따로 둔다.

고정 샘플은 contracts/fixtures/analysis/<테이블>.example.json 이고 load_fixture() 로 읽는다.
"""

import datetime as dt
import json
from pathlib import Path

from pydantic import BaseModel, model_validator

from app.planner.data_shapes import (
    CalendarCell,
    CustomerCycle,
    Daypart,
    ReviewLabel,
    RiskSignal,
    SalesAnomaly,
)

# server/app/analysis/ 에서 세 단계 위가 저장소 맨 위
FIXTURES_DIR = Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "analysis"


class SalesDailyRow(BaseModel):
    """sales_daily 한 줄. 키는 (date, daypart). 금액은 원 단위 정수."""

    date: dt.date
    daypart: Daypart
    sales_amount: int  # 매출
    qty: int  # 판매 수량 합
    food_cost: int  # 메뉴 원가 합 (수량 × 원가)
    labor_cost: int  # 그 시간대와 겹치는 근무 시간 × 시급
    profit: int  # 매출 - 메뉴 원가 - 인건비

    @model_validator(mode="after")
    def _profit_matches(self):
        if self.profit != self.sales_amount - self.food_cost - self.labor_cost:
            raise ValueError("profit 은 sales_amount - food_cost - labor_cost 와 같아야 합니다.")
        return self


class ReviewLabelRow(ReviewLabel):
    """review_label 한 줄. 키는 review_id."""

    review_id: str

    def to_label(self) -> ReviewLabel:
        """계획 엔진의 Review.label 에 넣을 모양으로 바꾼다."""
        return ReviewLabel.model_validate(self.model_dump(exclude={"review_id"}))


CalendarDayRow = CalendarCell  # calendar_day. 키는 (date, daypart, computed_at)
CustomerCycleRow = CustomerCycle  # customer_cycle. 키는 (customer_key, computed_at)
RiskSignalRow = RiskSignal  # risk_signal. 키는 risk_id
SalesAnomalyRow = SalesAnomaly  # sales_anomaly. 키는 (date, daypart)

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
