"""테스트 네이버 계정 (임시 네이버 로그인용). 계정과 계정마다 하는 일은 DB 표 하나로 관리한다.

DB: server/db/test_accounts.db (git 에 같이 올라간다. 팀 모두 같은 조건으로 시험한다)
    파일이 없으면 아래 DEFAULT_ACCOUNTS 로 만든다. 조건을 바꾸려면 DB 의 값을 고친다 (서버를 다시 켜지 않아도 바로 쓴다).
    목업 생성기(db/mock/generate.py)는 db/data 만 다시 만들고, 데모 초기화(/dev/reset)는 db/app_data 만 지우므로 이 파일은 그대로다.

표 test_accounts (한 줄 = 테스트 계정 하나)
  login_id      임시 네이버 로그인 아이디 (dona_test1 ...)
  password      시험용 비밀번호 (진짜 비밀번호가 아니다)
  naver_id      네이버 회원 번호 자리 (profile.id). 등록 기록(owners)의 "naver:<naver_id>" 와 이어진다
  profile_json  네이버 회원 프로필 조회 API(/v1/nid/me)가 돌려주는 모양과 같은 프로필
  find_store    1 이면 로그인할 때마다 등록 기록을 보지 않고 네이버 지도에서 가게 찾기부터 한다
  store_id      로그인하면 들어갈 가게 (예: s001). 비우면 이 계정으로 등록해 둔 가게 (등록 기록 owners 표)
  scene_at      로그인하면 서버 시계를 이 시각으로 옮긴다 (예: 2026-09-10T21:35:00+09:00. 서버를 DEV_CLOCK_ENABLED=true 로 켰을 때만)
  on_logout     reset: 로그아웃하면 그 가게의 고친 설정·계산과 서버 시계, 앱의 이 기기 기록(처음 설정, 끝낸 카드, 고쳐 쓴 답글)을
                         모두 지운다. 로그인할 때도 앱 기록을 지우고 처음부터 시작한다
                keep:  로그아웃해도 남긴다. 앱은 이 계정의 기기 기록을 따로 보관했다가 다시 로그인하면 되살린다
  scenario      임시 네이버 로그인 화면과 개발자 대시보드에 보일 설명 (어느 가게, 무엇을 시험하는 계정인지)

의도와 고른 장면은 docs/test-accounts.md 에 있다.
"""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[3] / "db" / "test_accounts.db"


def _profile(naver_id: str, login_id: str, nickname: str, name: str, gender: str, age: str, birthday: str, birthyear: str, phone: str) -> dict:
    return {
        "id": naver_id,
        "nickname": nickname,
        "name": name,
        "email": f"{login_id}@example.com",
        "gender": gender,
        "age": age,
        "birthday": birthday,
        "birthyear": birthyear,
        "mobile": phone,
        "mobile_e164": "+82" + phone.replace("-", "")[1:],
    }


# 파일이 없을 때 처음 만드는 값. 고칠 때는 DB 를 고친다.
DEFAULT_ACCOUNTS: list[dict] = [
    {
        "login_id": "dona_test1",
        "password": "dona1234",
        "naver_id": "TEST_NAVER_ID_0001",
        "profile": _profile("TEST_NAVER_ID_0001", "dona_test1", "새가게사장", "김새봄", "F", "40-49", "03-14", "1981", "010-1111-0001"),
        "find_store": 1,
        "store_id": None,
        "scene_at": None,
        "on_logout": "reset",
        "scenario": "가게 등록 시험: 로그인할 때마다 네이버 지도에서 가게 찾기 · 등록 → 처음 설정 (등록 기록을 보지 않음)",
    },
    {
        "login_id": "dona_test2",
        "password": "dona1234",
        "naver_id": "TEST_NAVER_ID_0002",
        "profile": _profile("TEST_NAVER_ID_0002", "dona_test2", "한림국수사장", "김한림", "F", "50-59", "05-02", "1971", "010-2222-0002"),
        "find_store": 0,
        "store_id": "s001",
        "scene_at": "2026-09-10T21:35:00+09:00",
        "on_logout": "reset",
        "scenario": "한림국수 (s001) · 9/10(목) 21:35 할 일 4개: 불만 리뷰 답글 2, 메뉴판 되돌리기, 포스터 · 로그아웃하면 전부 처음으로",
    },
    {
        "login_id": "dona_test3",
        "password": "dona1234",
        "naver_id": "TEST_NAVER_ID_0003",
        "profile": _profile("TEST_NAVER_ID_0003", "dona_test3", "석사돈가스사장", "이석사", "M", "40-49", "11-27", "1983", "010-3333-0003"),
        "find_store": 0,
        "store_id": "s003",
        "scene_at": "2026-09-23T20:35:00+09:00",
        "on_logout": "keep",
        "scenario": "석사돈가스 (s003) · 9/23(수) 강원대 대동제 날 20:35 할 일 4개: 불만 리뷰 답글, 행사·날씨 메뉴판 2, 포스터 · 로그아웃해도 그대로",
    },
]

COLUMNS = ("login_id", "password", "naver_id", "profile_json", "find_store", "store_id", "scene_at", "on_logout", "scenario")


def _db() -> sqlite3.Connection:
    """DB 를 연다. 파일이 없으면 표를 만들고 DEFAULT_ACCOUNTS 를 넣는다."""
    new = not DB_PATH.exists()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if new:
        with conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS test_accounts (
                    login_id TEXT PRIMARY KEY,
                    password TEXT NOT NULL,
                    naver_id TEXT NOT NULL UNIQUE,
                    profile_json TEXT NOT NULL,
                    find_store INTEGER NOT NULL DEFAULT 0 CHECK (find_store IN (0, 1)),
                    store_id TEXT,
                    scene_at TEXT,
                    on_logout TEXT NOT NULL DEFAULT 'keep' CHECK (on_logout IN ('keep', 'reset')),
                    scenario TEXT NOT NULL DEFAULT ''
                )"""
            )
            for a in DEFAULT_ACCOUNTS:
                conn.execute(
                    f"INSERT INTO test_accounts ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})",
                    (a["login_id"], a["password"], a["naver_id"], json.dumps(a["profile"], ensure_ascii=False),
                     a["find_store"], a["store_id"], a["scene_at"], a["on_logout"], a["scenario"]),
                )
    return conn


def _account(row: sqlite3.Row) -> dict:
    return {
        "login_id": row["login_id"],
        "password": row["password"],
        "profile": json.loads(row["profile_json"]),
        "find_store": bool(row["find_store"]),
        "store_id": row["store_id"] or None,
        "scene_at": row["scene_at"] or None,
        "on_logout": row["on_logout"],
        "scenario": row["scenario"],
    }


def all_accounts() -> list[dict]:
    with _db() as conn:
        return [_account(row) for row in conn.execute("SELECT * FROM test_accounts ORDER BY login_id")]


def by_login_id(login_id: str) -> dict | None:
    with _db() as conn:
        row = conn.execute("SELECT * FROM test_accounts WHERE login_id = ?", (login_id.strip(),)).fetchone()
    return _account(row) if row else None


def find_account(login_id: str, password: str) -> dict | None:
    account = by_login_id(login_id)
    return account if account and account["password"] == password else None


def where_it_goes(account: dict) -> dict:
    """이 계정으로 로그인하면 들어갈 가게와 설명 (임시 네이버 로그인 화면, 개발자 대시보드 상태 탭).

    {"store": "한림국수 (s001)" 또는 "", "scenario": DB 의 설명}
    store 는 지금 실제로 들어갈 가게다: find_store 면 없음, store_id 가 있으면 그 가게, 없으면 이 계정으로 등록해 둔 가게.
    """
    from app.data_pipeline import read_store_db

    store_id = login_store(account)
    if store_id is None or store_id not in read_store_db.list_store_ids():
        return {"store": "", "scenario": account["scenario"]}
    return {"store": f"{read_store_db.read_store(store_id)['name']} ({store_id})", "scenario": account["scenario"]}


def login_store(account: dict) -> str | None:
    """로그인하면 들어갈 가게 id. 없으면 앱이 네이버 지도에서 가게 찾기로 보낸다."""
    from app.data_pipeline import registered_stores

    if account["find_store"]:
        return None
    return account["store_id"] or registered_stores.store_for_owner(f"naver:{account['profile']['id']}")
