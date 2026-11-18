"""알바생 앱 API /v1/staff/* (앱 donna-voice/app/src/app/staff/*). 하는 일은 voice/staff.py.

거절할 때는 {"error": {"code", "message"}} 로 까닭을 알려 준다 (앱 ApiFailure 가 message 를 그대로 보인다).
"""

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from voice import staff

router = APIRouter(prefix="/staff")


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except staff.StaffError as error:
        return JSONResponse(status_code=error.status, content={"error": {"code": error.code, "message": error.message}})


@router.post("/invite/check")
def check_code(body: dict = Body(...)):
    return _call(staff.check_code, body.get("code", ""))


@router.post("/signup")
def signup(body: dict = Body(...)):
    return _call(staff.signup, body.get("code", ""), body.get("name"), body.get("login_id"))


@router.post("/start")
def start(body: dict = Body(...)):
    return _call(staff.start, body.get("staff_id", ""))


@router.get("/today")
def today(staff_id: str):
    return _call(staff.today, staff_id)


@router.get("/tasks/{task_id}")
def task_detail(task_id: str, staff_id: str):
    return _call(staff.detail, task_id, staff_id)


@router.post("/tasks/{task_id}/done")
def task_done(task_id: str, body: dict = Body(...)):
    return _call(staff.mark_done, task_id, body.get("staff_id", ""), bool(body.get("undo")))


@router.post("/tasks/{task_id}/confirm")
def task_confirm(task_id: str, body: dict = Body(...)):
    return _call(staff.confirm, task_id, body.get("staff_id", ""))


@router.post("/checkout")
def checkout(body: dict = Body(...)):
    return _call(staff.checkout, body.get("staff_id", ""))
