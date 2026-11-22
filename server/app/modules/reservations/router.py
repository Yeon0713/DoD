"""예약·단체 주문 (네이버 예약 동기화는 목업 + 사장님이 직접 적기). 확정한 것은 이번 주 바쁨 계산에 들어간다.

GET    /api/reservations?store_id=&from=&to=     예약 목록 (네이버 예약에서 새로 들어온 것을 먼저 가져온다)
POST   /api/reservations                        사장님이 직접 적기 {"at", "people", "kind", "name", "memo"} (바로 확정)
POST   /api/reservations/{id}/confirm           예약 문의 받기
POST   /api/reservations/{id}/decline           예약 문의에 어렵다고 답하기
DELETE /api/reservations/{id}                   지우기 (사장님이 적은 것만)

예약이 바뀌면 그 가게 계산 결과를 지워 이번 주가 바로 다시 계산되게 한다. 설명: app/data_pipeline/reservations.py
"""

import datetime as dt

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.error_response import ApiError
from app.data_pipeline import reservations, store_snapshot_cache
from app.data_pipeline.store_selection import store_id_param

router = APIRouter()

SOURCE_KO = {"NAVER": "네이버 예약", "OWNER": "직접 적음"}


def _view(row: dict) -> dict:
    return {
        "reservation_id": row["reservation_id"],
        "source": row["source"],
        "source_label": SOURCE_KO[row["source"]],
        "kind": row["kind"],
        "at": row["at"].isoformat(timespec="minutes"),
        "people": row["people"],
        "name": row["name"],
        "memo": row["memo"],
        "status": row["status"],
    }


def _fail(error: reservations.ReservationError):
    status = 404 if error.code == "NOT_FOUND" else 422
    raise ApiError(status, error.code, str(error))


@router.get("", summary="예약·단체 주문 목록")
def list_all(
    store_id: str = Depends(store_id_param),
    from_date: dt.date | None = Query(None, alias="from"),
    to_date: dt.date | None = Query(None, alias="to"),
):
    return {"reservations": [_view(r) for r in reservations.list_reservations(store_id, from_date, to_date)]}


class NewReservation(BaseModel):
    at: dt.datetime
    people: int
    kind: str = "RESERVATION"
    name: str = ""
    memo: str = ""


@router.post("", summary="예약·단체 주문 직접 적기")
def add(body: NewReservation, store_id: str = Depends(store_id_param)):
    try:
        row = reservations.add(store_id, body.at, body.people, body.kind, body.name, body.memo)
    except reservations.ReservationError as error:
        _fail(error)
    store_snapshot_cache.forget(store_id)
    return _view(row)


def _change(reservation_id: int, store_id: str, status: str, owner_only: bool = False) -> dict:
    row = reservations.get(reservation_id)
    if row is None or row["store_id"] != store_id:  # 다른 가게 예약은 있는지도 알려 주지 않는다
        raise ApiError(404, "NOT_FOUND", "예약을 찾지 못했어요")
    if owner_only and row["source"] != "OWNER":
        raise ApiError(400, "NAVER_RESERVATION", "네이버 예약은 받기·어렵다고 답하기로 정해 주세요")
    try:
        row = reservations.set_status(reservation_id, status)
    except reservations.ReservationError as error:
        _fail(error)
    store_snapshot_cache.forget(row["store_id"])
    return _view(row)


@router.post("/{reservation_id}/confirm", summary="예약 문의 받기")
def confirm(reservation_id: int, store_id: str = Depends(store_id_param)):
    return _change(reservation_id, store_id, "CONFIRMED")


@router.post("/{reservation_id}/decline", summary="예약 문의에 어렵다고 답하기")
def decline(reservation_id: int, store_id: str = Depends(store_id_param)):
    return _change(reservation_id, store_id, "DECLINED")


@router.delete("/{reservation_id}", summary="직접 적은 예약 지우기")
def remove(reservation_id: int, store_id: str = Depends(store_id_param)):
    return _change(reservation_id, store_id, "CANCELED", owner_only=True)
