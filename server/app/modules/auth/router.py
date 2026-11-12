"""네이버 아이디로 로그인.

GET  /api/auth/naver/start?back=<앱 주소>     네이버 로그인 창으로 보낸다
GET  /api/auth/naver/callback                 네이버가 돌려보내는 곳. 프로필을 받아 앱(back)으로 돌려보낸다
GET  /api/auth/naver/result/{ticket}          앱이 네이버에서 받은 정보와 이 계정의 가게를 읽는다 (30분 안)
POST /api/auth/naver/result/{ticket}/unlink   이 앱과 네이버 계정 연결을 끊는다

진짜 네이버: server/.env 에 NAVER_LOGIN_CLIENT_ID / SECRET 이 있으면 nid.naver.com 으로 보낸다.
임시 네이버: 키가 없으면(도메인을 받아 앱을 등록하기 전) 이 서버가 그리는 임시 로그인 화면과 동의 화면으로 보낸다.
  테스트 아이디와 비밀번호(test_accounts.py)로 로그인하면 동의 화면 없이 바로 앱으로 돌아간다.
  흐름(start → 로그인 → callback → 앱)이 진짜 네이버와 같아서, 키를 넣으면 앱을 고치지 않고 진짜로 바뀐다.
접근 토큰은 서버 메모리에만 두고 앱에는 보내지 않는다. 서버를 다시 켜면 모두 사라진다.
"""

import datetime as dt
import html
import secrets
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.config import settings
from app.core.error_response import ApiError
from app.data_pipeline import registered_stores
from app.data_pipeline.read_store_db import list_store_ids, read_store
from app.modules.auth.test_accounts import TEST_ACCOUNTS, find_account

router = APIRouter()

AUTHORIZE_URL = "https://nid.naver.com/oauth2.0/authorize"
TOKEN_URL = "https://nid.naver.com/oauth2.0/token"
PROFILE_URL = "https://openapi.naver.com/v1/nid/me"
KEEP = dt.timedelta(minutes=30)

# 네이버 회원 프로필 조회 API 가 줄 수 있는 항목. 사장님이 동의한 것만 온다.
PROFILE_FIELDS = ["id", "nickname", "name", "email", "gender", "age", "birthday", "birthyear", "profile_image", "mobile", "mobile_e164"]

_pending: dict[str, tuple[str, dt.datetime]] = {}  # state → (돌아갈 앱 주소, 만든 때)
_results: dict[str, dict] = {}  # ticket → 받은 정보
_mock_codes: dict[str, str] = {}  # 임시 네이버가 준 code → 테스트 아이디


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _real_naver() -> bool:
    return bool(settings.naver_login_client_id and settings.naver_login_client_secret)


def _forget_old() -> None:
    cutoff = _now() - KEEP
    for state in [k for k, (_, at) in _pending.items() if at < cutoff]:
        _pending.pop(state, None)
    for ticket in [k for k, v in _results.items() if v["_at"] < cutoff]:
        _results.pop(ticket, None)


def _allowed_back(back: str) -> bool:
    """앱 주소로만 돌려보낸다 (아무 주소로나 보내는 통로가 되지 않게). CORS 에 적은 앱 주소와 같은 곳만."""
    parsed = urlparse(back)
    return f"{parsed.scheme}://{parsed.netloc}" in settings.cors_origins


def _back_with(back: str, **params: str) -> RedirectResponse:
    joiner = "&" if urlparse(back).query else "?"
    return RedirectResponse(back + joiner + urlencode(params), status_code=302)


def _callback_url(**params: str) -> str:
    return "/api/auth/naver/callback?" + urlencode(params)


@router.get("/naver/start", summary="네이버 로그인 창으로 보내기")
def naver_start(back: str):
    if not _allowed_back(back):
        raise ApiError(400, "BAD_BACK_URL", "돌아갈 앱 주소가 허용 목록에 없어요")
    _forget_old()
    state = secrets.token_urlsafe(24)
    _pending[state] = (back, _now())
    if not _real_naver():
        return RedirectResponse("/api/auth/naver/mock/login?" + urlencode({"state": state}), status_code=302)
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.naver_login_client_id,
            "redirect_uri": settings.naver_login_callback_url,
            "state": state,
        }
    )
    return RedirectResponse(f"{AUTHORIZE_URL}?{query}", status_code=302)


@router.get("/naver/callback", summary="네이버가 돌려보내는 곳")
def naver_callback(
    state: str = "",
    code: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    pending = _pending.pop(state, None)
    if pending is None:
        raise ApiError(400, "BAD_STATE", "로그인을 처음부터 다시 해 주세요")
    back, _ = pending
    if error or not code:
        # 사장님이 동의 화면에서 취소했거나 네이버가 거절했다
        return _back_with(back, error=error or "NO_CODE", detail=error_description or "")

    test_login_id = _mock_codes.pop(code, None)
    if test_login_id is not None:
        account = next(a for a in TEST_ACCOUNTS if a["login_id"] == test_login_id)
        profile, access_token, expires_in = dict(account["profile"]), None, 3600
    else:
        try:
            token = httpx.get(
                TOKEN_URL,
                params={
                    "grant_type": "authorization_code",
                    "client_id": settings.naver_login_client_id,
                    "client_secret": settings.naver_login_client_secret,
                    "code": code,
                    "state": state,
                },
                timeout=10,
            ).json()
            access_token = token.get("access_token")
            if not access_token:
                return _back_with(back, error=token.get("error", "NO_TOKEN"), detail=token.get("error_description", ""))
            answer = httpx.get(PROFILE_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=10).json()
        except httpx.HTTPError:
            return _back_with(back, error="NAVER_UNREACHABLE")
        if answer.get("resultcode") != "00":
            return _back_with(back, error="PROFILE_FAILED", detail=answer.get("message", ""))
        profile, expires_in = answer.get("response", {}), int(token.get("expires_in", 0) or 0)
    # 네이버 로그인은 어느 가게 사장님인지 알려 주지 않는다. 이 계정으로 등록해 둔 가게가 있으면 그 가게로 들어온다
    store_id = registered_stores.store_for_owner(f"naver:{profile.get('id')}")

    ticket = secrets.token_urlsafe(24)
    _results[ticket] = {
        "_at": _now(),
        "_access_token": access_token,
        "profile": profile,
        "token_expires_in": expires_in,
        "store_id": store_id,
        "test": test_login_id is not None,
    }
    return _back_with(back, ticket=ticket)


@router.get("/naver/result/{ticket}", summary="네이버에서 받은 정보")
def naver_result(ticket: str):
    _forget_old()
    result = _results.get(ticket)
    if result is None:
        raise ApiError(404, "TICKET_NOT_FOUND", "로그인한 지 오래됐어요. 다시 로그인해 주세요")
    profile = result["profile"]
    store_id = result["store_id"] if result["store_id"] in list_store_ids() else None
    return {
        "received": dict(profile),
        "missing": [field for field in PROFILE_FIELDS if field not in profile],
        "token_expires_in": result["token_expires_in"],
        "received_at": result["_at"].isoformat(),
        "test": result["test"],
        # 이 네이버 계정으로 등록해 둔 가게. 없으면 앱이 가게 등록(네이버 지도에서 찾기)으로 보낸다
        "store_id": store_id,
        "store_name": read_store(store_id)["name"] if store_id else None,
    }


@router.post("/naver/result/{ticket}/unlink", summary="네이버 계정 연결 끊기")
def naver_unlink(ticket: str):
    result = _results.pop(ticket, None)
    if result is None:
        raise ApiError(404, "TICKET_NOT_FOUND", "로그인한 지 오래됐어요")
    if result["test"]:
        return {"unlinked": True}
    try:
        answer = httpx.get(
            TOKEN_URL,
            params={
                "grant_type": "delete",
                "client_id": settings.naver_login_client_id,
                "client_secret": settings.naver_login_client_secret,
                "access_token": result["_access_token"],
                "service_provider": "NAVER",
            },
            timeout=10,
        ).json()
    except httpx.HTTPError:
        raise ApiError(502, "NAVER_UNREACHABLE", "네이버에 닿지 않아요")
    return {"unlinked": answer.get("result") == "success"}


# ---------------------------------------------------------------------------
# 임시 네이버 로그인 화면 (진짜 네이버 키가 없을 때만). 팀이 시험할 때 쓰는 화면이다.


async def _form(request: Request) -> dict[str, str]:
    body = (await request.body()).decode("utf-8")
    return {key: values[0] for key, values in parse_qs(body, keep_blank_values=True).items()}


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
*{{box-sizing:border-box}} body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;background:#f5f6f7;color:#222}}
.wrap{{max-width:420px;margin:0 auto;padding:28px 20px 40px}}
.logo{{display:flex;align-items:center;gap:8px;justify-content:center;margin:12px 0 24px;font-weight:800;font-size:22px;color:#03c75a}}
.logo b{{display:inline-flex;width:34px;height:34px;border-radius:8px;background:#03c75a;color:#fff;align-items:center;justify-content:center;font-size:20px}}
.card{{background:#fff;border:1px solid #dadada;border-radius:10px;padding:20px}}
input{{width:100%;height:50px;border:1px solid #dadada;border-radius:6px;padding:0 14px;font-size:16px;margin-bottom:10px}}
button{{width:100%;height:52px;border:0;border-radius:6px;font-size:17px;font-weight:700;cursor:pointer}}
.go{{background:#03c75a;color:#fff}}
.err{{color:#e02020;font-size:14px;margin:4px 0 12px}}
details{{margin-top:18px;font-size:14px;color:#555}} summary{{cursor:pointer}}
table{{width:100%;border-collapse:collapse;margin-top:8px;font-size:13px}} td{{padding:6px 4px;border-top:1px solid #eee;vertical-align:top}}
.fill{{color:#03a04a;cursor:pointer;text-decoration:underline;background:none;border:0;width:auto;height:auto;font-size:13px;font-weight:600;padding:0;white-space:nowrap}}
</style></head><body><div class="wrap">{body}</div></body></html>"""
    )


def _login_page(state: str, login_id: str = "", error: str = "") -> HTMLResponse:
    rows = "".join(
        f"<tr><td><b>{html.escape(a['login_id'])}</b><br>{html.escape(a['password'])}</td><td>{html.escape(a['scenario'])}</td>"
        f"<td><button type=button class=fill onclick=\"fill('{html.escape(a['login_id'])}','{html.escape(a['password'])}')\">넣기</button></td></tr>"
        for a in TEST_ACCOUNTS
    )
    return _page(
        "네이버 로그인 (테스트)",
        f"""<div class="logo"><b>N</b>NAVER 로그인 <span style="color:#999;font-size:14px;font-weight:600">테스트</span></div>
<form class="card" method="post" action="/api/auth/naver/mock/login">
<input type="hidden" name="state" value="{html.escape(state)}">
<input name="login_id" placeholder="아이디" autocomplete="off" value="{html.escape(login_id)}">
<input name="password" type="password" placeholder="비밀번호" autocomplete="off">
{f'<div class="err">{html.escape(error)}</div>' if error else ''}
<button class="go" type="submit">로그인</button>
</form>
<details><summary>테스트 계정 보기</summary><table>{rows}</table></details>
<script>function fill(i,p){{document.querySelector('[name=login_id]').value=i;document.querySelector('[name=password]').value=p;}}</script>""",
    )


@router.get("/naver/mock/login", response_class=HTMLResponse, include_in_schema=False)
def mock_login_page(state: str = ""):
    if state not in _pending:
        return _page("로그인", "<p>로그인을 앱에서 처음부터 다시 해 주세요.</p>")
    return _login_page(state)


@router.post("/naver/mock/login", include_in_schema=False)
async def mock_login(request: Request):
    form = await _form(request)
    state = form.get("state", "")
    if state not in _pending:
        return _page("로그인", "<p>로그인을 앱에서 처음부터 다시 해 주세요.</p>")
    account = find_account(form.get("login_id", ""), form.get("password", ""))
    if account is None:
        return _login_page(state, form.get("login_id", ""), "아이디 또는 비밀번호를 잘못 입력했어요. 다시 확인해 주세요.")
    # 동의 화면 없이 바로 앱으로 돌려보낸다 (팀 시험용)
    code = "mock_" + secrets.token_urlsafe(24)
    _mock_codes[code] = account["login_id"]
    return RedirectResponse(_callback_url(state=state, code=code), status_code=303)
