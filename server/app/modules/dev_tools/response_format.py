"""개발자 대시보드 API 요청 모양. 응답은 화면(dev/app.js)이 바로 그리는 dict 라서 따로 모델을 두지 않는다."""

import datetime as dt

from pydantic import BaseModel


class PolishSwitch(BaseModel):
    enabled: bool  # 카드 문장을 CLOVA X 로 다듬을지 (서버를 다시 켜면 .env 값으로 돌아간다)


class DemoGo(BaseModel):
    store_id: str
    at: dt.datetime  # 서버 시계를 둘 시각 (시연 단계의 at)


class UiTextEdit(BaseModel):
    file: str
    line: int
    func: str
    original: str
    edited: str  # 바꿀 글


class UiTextEdits(BaseModel):
    edits: dict[str, UiTextEdit]  # 글 id(파일::함수::해시::순서) → 수정
