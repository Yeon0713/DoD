"""알바생 표 읽고 쓰기 (repo.STAFF_TABLES). 알바생 기능(voice/staff.py, voice/staff_orders.py)은 이 파일로만 표를 만진다.

표 다섯 + 로그인 표시
  staff_members     알바생 한 명 (아이디, 비밀번호 해시, 상태)
  staff_invites     초대 코드 (한 사람용, 랜덤 6자리)
  staff_tasks       할 일 (매뉴얼, 사장님이 말로 시킨 일, 교정 카드)
  staff_task_marks  누가 어느 날 했는지·확인했는지
  staff_attendance  출퇴근
  staff_sessions    로그인 표시(토큰)

비밀번호는 그대로 두지 않고 PBKDF2(SHA-256) 해시로 둔다. 같은 비밀번호도 사람마다 소금(salt)이 달라 해시가 다르다.
"""

import hashlib
import hmac
import json
import secrets

from voice import repo

PASSWORD_ROUNDS = 120_000
CODE_DIGITS = 6


# ── 비밀번호와 토큰 ──


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ROUNDS)
    return f"pbkdf2${PASSWORD_ROUNDS}${salt.hex()}${digest.hex()}"


def password_matches(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _, rounds, salt, digest = stored.split("$")
    except ValueError:
        return False
    again = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
    return hmac.compare_digest(again.hex(), digest)


def new_token() -> str:
    return secrets.token_urlsafe(32)


# ── 공통 ──


def _rows(sql: str, params: tuple = ()) -> list[dict]:
    with repo.lock(), repo.connect() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _row(sql: str, params: tuple = ()) -> dict | None:
    found = _rows(sql, params)
    return found[0] if found else None


def _write(sql: str, params: tuple = ()) -> None:
    with repo.lock(), repo.connect() as conn:
        conn.execute(sql, params)


# ── 알바생 ──


def add_member(member: dict) -> dict:
    columns = ("staff_id", "store_id", "name", "call", "login_id", "password_hash", "status",
               "signed_up_at", "started_at", "removed_at", "created_at")
    row = {column: member.get(column) for column in columns}
    _write(f"INSERT OR REPLACE INTO staff_members ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
           tuple(row[c] for c in columns))
    return row


def member(staff_id: str) -> dict | None:
    return _row("SELECT * FROM staff_members WHERE staff_id = ?", (staff_id,))


def members(store_id: str) -> list[dict]:
    return _rows("SELECT * FROM staff_members WHERE store_id = ? ORDER BY created_at, rowid", (store_id,))


def member_by_login(login_id: str) -> dict | None:
    return _row("SELECT * FROM staff_members WHERE lower(login_id) = lower(?)", (login_id.strip(),))


def update_member(staff_id: str, **fields) -> dict | None:
    if fields:
        sets = ", ".join(f"{name} = ?" for name in fields)
        _write(f"UPDATE staff_members SET {sets} WHERE staff_id = ?", (*fields.values(), staff_id))
    return member(staff_id)


# ── 초대 코드 ──


def new_invite(store_id: str, staff_id: str, now_iso: str) -> dict:
    """겹치지 않는 랜덤 6자리 코드를 만든다. 이 사람의 예전 코드는 못 쓰게 한다 (코드는 한 사람에 하나)."""
    with repo.lock(), repo.connect() as conn:
        conn.execute("UPDATE staff_invites SET revoked_at = ? WHERE staff_id = ? AND revoked_at IS NULL AND used_at IS NULL",
                     (now_iso, staff_id))
        while True:
            code = f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"
            if code[0] != "0" and not conn.execute("SELECT 1 FROM staff_invites WHERE code = ?", (code,)).fetchone():
                break
        conn.execute("INSERT INTO staff_invites (code, store_id, staff_id, created_at) VALUES (?, ?, ?, ?)",
                     (code, store_id, staff_id, now_iso))
    return invite(code)


def add_invite(code: str, store_id: str, staff_id: str, now_iso: str) -> None:
    _write("INSERT OR REPLACE INTO staff_invites (code, store_id, staff_id, created_at) VALUES (?, ?, ?, ?)", (code, store_id, staff_id, now_iso))


def invite(code: str) -> dict | None:
    return _row("SELECT * FROM staff_invites WHERE code = ?", (code,))


def invites_of(staff_id: str) -> list[dict]:
    return _rows("SELECT * FROM staff_invites WHERE staff_id = ? ORDER BY created_at DESC, rowid DESC", (staff_id,))


def store_invites(store_id: str) -> list[dict]:
    return _rows("SELECT * FROM staff_invites WHERE store_id = ? ORDER BY created_at DESC, rowid DESC", (store_id,))


def update_invite(code: str, **fields) -> None:
    sets = ", ".join(f"{name} = ?" for name in fields)
    _write(f"UPDATE staff_invites SET {sets} WHERE code = ?", (*fields.values(), code))


def revoke_invites(staff_id: str, now_iso: str) -> None:
    _write("UPDATE staff_invites SET revoked_at = ? WHERE staff_id = ? AND revoked_at IS NULL", (now_iso, staff_id))


# ── 할 일 ──

TASK_COLUMNS = ("task_id", "store_id", "title", "phase", "repeat", "kind", "must_confirm", "urgent", "to_staff", "origin",
                "detail", "owner_words", "source", "start_date", "end_date", "sent_at", "canceled_at", "created_at")


def add_task(task: dict) -> None:
    row = {**task, "source": json.dumps(task["source"], ensure_ascii=False) if task.get("source") is not None else None,
           "must_confirm": int(bool(task["must_confirm"])), "urgent": int(bool(task["urgent"]))}
    _write(f"INSERT INTO staff_tasks ({', '.join(TASK_COLUMNS)}) VALUES ({', '.join('?' for _ in TASK_COLUMNS)})",
           tuple(row.get(c) for c in TASK_COLUMNS))


def _task_out(row: dict) -> dict:
    return {**row, "source": json.loads(row["source"]) if row.get("source") else None,
            "must_confirm": bool(row["must_confirm"]), "urgent": bool(row["urgent"])}


def task(task_id: str) -> dict | None:
    row = _row("SELECT * FROM staff_tasks WHERE task_id = ?", (task_id,))
    return _task_out(row) if row else None


def tasks(store_id: str) -> list[dict]:
    return [_task_out(row) for row in _rows("SELECT * FROM staff_tasks WHERE store_id = ? ORDER BY created_at, rowid", (store_id,))]


def update_task_source(task_id: str, source: dict) -> None:
    """출처 기록을 고친다 (같은 일로 묶인 제안 merged, 매뉴얼로 올린 promoted_at)."""
    _write("UPDATE staff_tasks SET source = ? WHERE task_id = ?", (json.dumps(source, ensure_ascii=False), task_id))


def cancel_task(task_id: str, now_iso: str) -> None:
    _write("UPDATE staff_tasks SET canceled_at = ? WHERE task_id = ?", (now_iso, task_id))


# ── 한 일 기록 ──


def marks_of_task(task_id: str) -> list[dict]:
    return _rows("SELECT * FROM staff_task_marks WHERE task_id = ? ORDER BY day, rowid", (task_id,))


def marks_of_store(store_id: str) -> list[dict]:
    return _rows("SELECT * FROM staff_task_marks WHERE store_id = ? ORDER BY day, rowid", (store_id,))


def set_mark(task_id: str, staff_id: str, day: str, store_id: str, **fields) -> None:
    """fields: done_at, confirmed_at (None 이면 지운다)."""
    with repo.lock(), repo.connect() as conn:
        conn.execute("INSERT OR IGNORE INTO staff_task_marks (task_id, staff_id, day, store_id) VALUES (?, ?, ?, ?)",
                     (task_id, staff_id, day, store_id))
        sets = ", ".join(f"{name} = ?" for name in fields)
        conn.execute(f"UPDATE staff_task_marks SET {sets} WHERE task_id = ? AND staff_id = ? AND day = ?",
                     (*fields.values(), task_id, staff_id, day))


def clear_done(task_id: str, staff_id: str) -> None:
    _write("UPDATE staff_task_marks SET done_at = NULL WHERE task_id = ? AND staff_id = ?", (task_id, staff_id))


# ── 출퇴근 ──


def attendance(staff_id: str, day: str) -> dict | None:
    return _row("SELECT * FROM staff_attendance WHERE staff_id = ? AND day = ?", (staff_id, day))


def attendance_on(store_id: str, day: str) -> list[dict]:
    return _rows("SELECT * FROM staff_attendance WHERE store_id = ? AND day = ? ORDER BY in_at", (store_id, day))


def check_in(staff_id: str, day: str, store_id: str, now_iso: str) -> dict:
    _write("INSERT OR IGNORE INTO staff_attendance (staff_id, day, store_id, in_at) VALUES (?, ?, ?, ?)",
           (staff_id, day, store_id, now_iso))
    return attendance(staff_id, day)


def check_out(staff_id: str, day: str, now_iso: str) -> None:
    _write("UPDATE staff_attendance SET out_at = ? WHERE staff_id = ? AND day = ?", (now_iso, staff_id, day))


# ── 로그인 표시 ──


def add_session(staff_id: str, store_id: str, now_iso: str) -> str:
    token = new_token()
    _write("INSERT INTO staff_sessions (token, staff_id, store_id, created_at) VALUES (?, ?, ?, ?)", (token, staff_id, store_id, now_iso))
    return token


def session(token: str) -> dict | None:
    return _row("SELECT * FROM staff_sessions WHERE token = ?", (token,))


def end_sessions(staff_id: str) -> None:
    _write("DELETE FROM staff_sessions WHERE staff_id = ?", (staff_id,))
