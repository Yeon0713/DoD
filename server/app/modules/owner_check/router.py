"""사장님 확인 (사업자 심사, 지금은 목업). 가입할 때 가게를 고른 뒤, 그 가게 사장님인지 확인받아야 계정과 가게가 이어진다.

POST /api/owner_check                 심사 신청 (사업자등록번호, 대표자 이름, 개업일자, 사업자등록증 사진)
GET  /api/owner_check/sample?store_id= 시험용 값: 그 가게로 통과하는 목업 사업자 정보 (데모 테스트 모드의 "시험용 값 넣기")
GET  /api/owner_check/{check_id}      심사 결과 (reviewing → approved 또는 held). 승인이면 그때 계정과 가게를 잇는다

심사 규칙과 목업 국세청은 review.py, mock_nts.py. 시험용 값은 db/mock_business_registrations.json, 설명은 docs/owner-check.md
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.error_response import ApiError
from app.data_pipeline.read_store_db import list_store_ids
from app.modules.owner_check import review

router = APIRouter()


class CheckRequest(BaseModel):
    store_id: str
    owner_key: str
    business_no: str
    owner_name: str
    opened_on: str  # YYYY-MM-DD
    document: str | None = None  # 올린 사업자등록증 사진 이름 (목업: 파일은 받지 않는다)


@router.post("", summary="사장님 확인 심사 신청")
def submit(body: CheckRequest):
    if body.store_id not in list_store_ids():
        raise ApiError(404, "STORE_NOT_FOUND", "가게를 다시 골라 주세요")
    try:
        return review.submit(body.owner_key, body.store_id, body.business_no, body.owner_name, body.opened_on, body.document)
    except review.CheckInputError as error:
        raise ApiError(422, error.code, str(error))


@router.get("/sample", summary="시험용 사업자 정보 (목업)")
def sample(store_id: str | None = None):
    found = review.sample_for(store_id)
    if found is None:
        raise ApiError(404, "NO_SAMPLE", "이 가게로 통과하는 시험용 값이 없어요")
    return {**found, "document": "사업자등록증_시험용.jpg"}


@router.get("/{check_id}", summary="사장님 확인 심사 결과")
def result(check_id: str):
    found = review.get(check_id)
    if found is None:
        raise ApiError(404, "CHECK_NOT_FOUND", "심사를 다시 신청해 주세요")
    return found
