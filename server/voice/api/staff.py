"""알바생 앱 API /v1/staff/* (앱 donna-voice/app/src/app/staff/*). 하는 일은 voice/staff.py.

거절할 때는 {"error": {"code", "message"}} 로 까닭을 알려 준다 (앱 ApiFailure 가 message 를 그대로 보인다).

로그인 표시(토큰, 2026-11-18): 가입(signup)이나 로그인(login)을 하면 token 을 준다. 그 뒤의 요청은 머리글
X-Staff-Token 에 그 값을 붙인다. 서버는 토큰으로 누구인지 알고, 그 사람의 할 일만 보여 준다.
(예전처럼 staff_id 를 주소에 적는 것만으로는 남의 화면을 열 수 없다.) 없거나 끊긴 토큰은 401 not_signed_in.
"""

from fastapi import APIRouter, Body, Header
from fastapi.responses import JSONResponse

from voice import staff

router = APIRouter(prefix="/staff")


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except staff.StaffError as error:
        return JSONResponse(status_code=error.status, content={"error": {"code": error.code, "message": error.message}})


def _as_me(token: str | None, fn, *args):
    """토큰으로 알바생을 찾아 fn(…, staff_id) 를 부른다."""
    return _call(lambda: fn(*args, staff.staff_for_token(token)))


@router.post("/invite/check")
def check_code(body: dict = Body(...)):
    return _call(staff.check_code, body.get("code", ""))


@router.post("/signup")
def signup(body: dict = Body(...)):
    return _call(staff.signup, body.get("code", ""), body.get("name"), body.get("login_id"), body.get("password"))


@router.post("/login")
def login(body: dict = Body(...)):
    return _call(staff.login, body.get("login_id"), body.get("password"))


@router.post("/start")
def start(x_staff_token: str | None = Header(default=None)):
    return _as_me(x_staff_token, staff.start)


@router.get("/today")
def today(x_staff_token: str | None = Header(default=None)):
    return _as_me(x_staff_token, staff.today)


@router.get("/tasks/{task_id}")
def task_detail(task_id: str, x_staff_token: str | None = Header(default=None)):
    return _as_me(x_staff_token, staff.detail, task_id)


@router.post("/tasks/{task_id}/done")
def task_done(task_id: str, body: dict = Body(default={}), x_staff_token: str | None = Header(default=None)):
    return _call(lambda: staff.mark_done(task_id, staff.staff_for_token(x_staff_token), bool(body.get("undo"))))


@router.post("/tasks/{task_id}/confirm")
def task_confirm(task_id: str, x_staff_token: str | None = Header(default=None)):
    return _as_me(x_staff_token, staff.confirm, task_id)


@router.post("/checkout")
def checkout(x_staff_token: str | None = Header(default=None)):
    return _as_me(x_staff_token, staff.checkout)
