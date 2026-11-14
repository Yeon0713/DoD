"""목업 국세청: 사업자등록정보 진위확인과 상태조회를 흉내 낸다 (진짜 국세청은 부르지 않는다).

진짜 서비스(공공데이터포털 "국세청_사업자등록정보 진위확인 및 상태조회 서비스")와 같은 모양으로 답한다.
  - 상태조회: 사업자등록번호만으로 사업 상태(계속사업자 / 휴업자 / 폐업자)와 과세 유형을 알려 준다. 상호·대표자·주소는 알려 주지 않는다
  - 진위확인: 사업자등록번호 + 대표자 이름 + 개업일자가 등록 정보와 맞는지만 알려 준다 (대표자 이름을 돌려주지 않는다)

자료: server/db/mock_business_registrations.json (git 에 올라간다. 시험용으로 지은 값)
"""

import json
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[3] / "db" / "mock_business_registrations.json"
_WEIGHTS = (1, 3, 7, 1, 3, 7, 1, 3, 5)


def digits(business_no: str) -> str:
    """사장님이 쓴 사업자등록번호에서 숫자만 (000-00-00000 → 0000000000)"""
    return "".join(c for c in business_no if c.isdigit())


def is_valid_number(business_no: str) -> bool:
    """10자리이고 마지막 검증 숫자가 맞는지 (국세청 사업자등록번호 규칙). 잘못 쓴 번호를 심사 전에 거른다."""
    if len(business_no) != 10 or not business_no.isdigit():
        return False
    d = [int(c) for c in business_no]
    total = sum(a * b for a, b in zip(d[:9], _WEIGHTS)) + (d[8] * 5) // 10
    return (10 - total % 10) % 10 == d[9]


@lru_cache(maxsize=1)
def _load(path: str) -> dict[str, dict]:
    with open(path, encoding="utf-8") as f:
        return {row["business_no"]: row for row in json.load(f)["registrations"]}


def _registrations() -> dict[str, dict]:
    return _load(str(DATA_PATH))


def status(business_no: str) -> dict | None:
    """상태조회. 없는 번호면 None. {"status": "계속사업자"|"휴업자"|"폐업자", "tax_type": ...}"""
    row = _registrations().get(business_no)
    return {"status": row["status"], "tax_type": row["tax_type"]} if row else None


def validate(business_no: str, owner_name: str, opened_on: str) -> bool:
    """진위확인. 번호, 대표자 이름(띄어쓰기 무시), 개업일자(YYYY-MM-DD)가 모두 맞으면 True."""
    row = _registrations().get(business_no)
    return bool(row) and row["owner_name"].replace(" ", "") == owner_name.replace(" ", "") and row["opened_on"] == opened_on


def place_of(business_no: str) -> str | None:
    """그 사업자의 가게(네이버 플레이스 id). 진짜로는 사업자등록증 사진의 상호·주소를 읽어 고른 가게와 맞춰 본다."""
    row = _registrations().get(business_no)
    return row["place_id"] if row else None


def samples() -> list[dict]:
    """시험용 값 (데모 테스트 모드의 "시험용 값 넣기", 개발 문서)"""
    return [dict(row) for row in _registrations().values()]
