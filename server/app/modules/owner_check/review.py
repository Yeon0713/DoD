"""사장님 확인 심사 (목업). 가게를 고른 사람이 그 가게 사장님인지 확인한 뒤에만 계정과 가게를 잇는다.

순서
1. 신청 (submit): 사업자등록번호, 대표자 이름, 개업일자, 사업자등록증 사진.
   번호 자릿수·검증 숫자, 빈칸, 날짜 모양은 신청할 때 바로 거른다 (심사로 보내지 않는다).
2. 심사 중 (reviewing): REVIEW_SECONDS 동안. 진짜로는 사람이 사업자등록증을 보는 시간이다.
3. 결과 (decide, 심사 시간이 지난 뒤 처음 읽을 때 정한다)
   - 국세청 진위확인 (목업 국세청 mock_nts): 번호 + 대표자 이름 + 개업일자가 맞는지
   - 국세청 상태조회: 계속사업자인지 (휴업·폐업이면 보류)
   - 고른 가게와 사업자의 가게가 같은지 (진짜로는 사업자등록증의 상호·주소로 맞춰 본다)
   - 다른 계정이 이미 확인받은 가게가 아닌지
   모두 통과하면 승인(approved): 계정과 가게를 잇는다 (등록 기록 owners). 하나라도 걸리면 보류(held)와 까닭.
4. 탈퇴하면 그 계정의 승인을 withdrawn 으로 바꾼다 (기록은 지우지 않는다). 그 가게는 다른 계정이 다시 확인받을 수 있다.

기록: 등록 기록 DB(db/app_data/registry.db)의 owner_checks 표
"""

import datetime as dt
import secrets

from app.data_pipeline import registered_stores
from app.modules.owner_check import mock_nts

REVIEW_SECONDS = 5

# 보류 까닭: (제목, 설명). 화면에 그대로 보인다. 제목은 휴대폰 한 줄(12자 안팎)에 들어가게
REASONS: dict[str, tuple[str, str]] = {
    "NTS_NOT_FOUND": ("국세청에 없는 번호예요", "사업자등록증의 등록번호를 다시 확인해 주세요"),
    "NTS_MISMATCH": ("적은 내용이 달라요", "대표자 이름과 개업일자를 다시 확인해 주세요"),
    "CLOSED": ("폐업한 사업자예요", "지금 장사하는 가게의 사업자등록증으로 해 주세요"),
    "SUSPENDED": ("휴업 중인 사업자예요", "다시 문을 연 뒤에 해 주세요"),
    "OTHER_STORE": ("다른 가게의 사업자예요", "고른 가게가 맞는지 다시 찾아 주세요"),
    "TAKEN": ("이미 확인된 가게예요", "다른 사장님이 먼저 확인받았어요. 우리 가게가 맞다면 고객센터로 알려 주세요"),
}


class CheckInputError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _now() -> dt.datetime:
    # 심사 시간은 실제 시각으로 잰다 (시연용 서버 시계를 옮겨도 심사가 끝나게)
    return dt.datetime.now(dt.timezone.utc)


def _db():
    conn = registered_stores._db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS owner_checks (
            check_id TEXT PRIMARY KEY, owner_key TEXT NOT NULL, store_id TEXT NOT NULL,
            business_no TEXT NOT NULL, owner_name TEXT NOT NULL, opened_on TEXT NOT NULL, document TEXT NOT NULL,
            submitted_at TEXT NOT NULL, decide_at TEXT NOT NULL,
            result TEXT CHECK (result IN ('approved', 'held', 'withdrawn')), reason_code TEXT, decided_at TEXT)"""
    )
    return conn


COLUMNS = ("check_id", "owner_key", "store_id", "business_no", "owner_name", "opened_on", "document", "submitted_at", "decide_at", "result", "reason_code", "decided_at")


def _row(values) -> dict:
    return dict(zip(COLUMNS, values))


def submit(owner_key: str, store_id: str, business_no: str, owner_name: str, opened_on: str, document: str | None) -> dict:
    """심사를 신청한다. 모양이 틀리면 CheckInputError. 신청한 심사를 돌려준다 (status: reviewing)."""
    number = mock_nts.digits(business_no)
    if not mock_nts.is_valid_number(number):
        raise CheckInputError("INVALID_BUSINESS_NO", "사업자등록번호 10자리를 다시 확인해 주세요")
    if not owner_name.strip():
        raise CheckInputError("OWNER_NAME_REQUIRED", "대표자 이름을 써 주세요")
    try:
        opened = dt.date.fromisoformat(opened_on)
    except ValueError:
        raise CheckInputError("INVALID_OPENED_ON", "개업일자를 다시 확인해 주세요") from None
    if opened > _now().date():
        raise CheckInputError("INVALID_OPENED_ON", "개업일자를 다시 확인해 주세요")
    if not document:
        raise CheckInputError("DOCUMENT_REQUIRED", "사업자등록증 사진을 올려 주세요")
    if not owner_key:
        raise CheckInputError("OWNER_KEY_REQUIRED", "로그인을 다시 해 주세요")
    now = _now()
    row = {
        "check_id": "oc_" + secrets.token_urlsafe(12),
        "owner_key": owner_key,
        "store_id": store_id,
        "business_no": number,
        "owner_name": owner_name.strip(),
        "opened_on": opened.isoformat(),
        "document": document,
        "submitted_at": now.isoformat(),
        "decide_at": (now + dt.timedelta(seconds=REVIEW_SECONDS)).isoformat(),
        "result": None,
        "reason_code": None,
        "decided_at": None,
    }
    with _db() as conn:
        conn.execute(f"INSERT INTO owner_checks VALUES ({', '.join('?' * len(COLUMNS))})", [row[c] for c in COLUMNS])
    return view(row)


def _verified_owner(store_id: str) -> str | None:
    with _db() as conn:
        found = conn.execute("SELECT owner_key FROM owner_checks WHERE store_id = ? AND result = 'approved' ORDER BY decided_at LIMIT 1", (store_id,)).fetchone()
    return found[0] if found else None


def decide(row: dict) -> tuple[str, str | None]:
    """심사 결과 (approved 또는 held, 보류 까닭 코드)"""
    number = row["business_no"]
    state = mock_nts.status(number)
    if state is None:
        return "held", "NTS_NOT_FOUND"
    if not mock_nts.validate(number, row["owner_name"], row["opened_on"]):
        return "held", "NTS_MISMATCH"
    if state["status"] == "폐업자":
        return "held", "CLOSED"
    if state["status"] == "휴업자":
        return "held", "SUSPENDED"
    info = registered_stores.place_info(row["store_id"])
    if info is None or mock_nts.place_of(number) != info.place_id:
        return "held", "OTHER_STORE"
    owner = _verified_owner(row["store_id"])
    if owner and owner != row["owner_key"]:
        return "held", "TAKEN"
    return "approved", None


def get(check_id: str) -> dict | None:
    """심사 하나. 심사 시간이 지났는데 결과가 없으면 이때 결과를 정하고, 승인이면 계정과 가게를 잇는다."""
    with _db() as conn:
        found = conn.execute(f"SELECT {', '.join(COLUMNS)} FROM owner_checks WHERE check_id = ?", (check_id,)).fetchone()
    if found is None:
        return None
    row = _row(found)
    if row["result"] is None and _now() >= dt.datetime.fromisoformat(row["decide_at"]):
        result, reason = decide(row)
        row.update(result=result, reason_code=reason, decided_at=_now().isoformat())
        with _db() as conn:
            conn.execute("UPDATE owner_checks SET result = ?, reason_code = ?, decided_at = ? WHERE check_id = ?", (result, reason, row["decided_at"], check_id))
        if result == "approved":
            registered_stores.set_owner(row["owner_key"], row["store_id"])
    return view(row)


def view(row: dict) -> dict:
    """앱에 보낼 모양. 사업자등록번호는 뒷자리만 가린다."""
    status = row["result"] or "reviewing"
    title, sub = REASONS.get(row["reason_code"] or "", (None, None))
    number = row["business_no"]
    left = max(0.0, (dt.datetime.fromisoformat(row["decide_at"]) - _now()).total_seconds()) if status == "reviewing" else 0.0
    return {
        "check_id": row["check_id"],
        "store_id": row["store_id"],
        "status": status,
        "reason_code": row["reason_code"],
        "reason_title": title,
        "reason_sub": sub,
        "business_no": f"{number[:3]}-{number[3:5]}-*****",
        "seconds_left": round(left, 1),
    }


def withdraw(owner_key: str) -> int:
    """탈퇴: 그 계정의 승인을 withdrawn 으로 바꾼다 (기록은 남긴다). 바꾼 수"""
    with _db() as conn:
        return conn.execute("UPDATE owner_checks SET result = 'withdrawn' WHERE owner_key = ? AND result = 'approved'", (owner_key,)).rowcount


def sample_for(store_id: str | None) -> dict | None:
    """시험용 값: 그 가게로 통과하는 목업 사업자 정보. 없으면 None"""
    info = registered_stores.place_info(store_id) if store_id else None
    for row in mock_nts.samples():
        if info and row["place_id"] == info.place_id:
            return {"business_no": row["business_no"], "owner_name": row["owner_name"], "opened_on": row["opened_on"], "trade_name": row["trade_name"]}
    return None
