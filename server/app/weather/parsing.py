"""여러 모듈이 같이 쓰는 값 읽기와 발표 시각 계산."""

import datetime as dt
import re
from collections.abc import Iterable

from app.core.seoul_time import SEOUL
from app.weather.client import KmaResponseError

MISSING_ABS = 900  # 단기예보 활용가이드: +900 이상, -900 이하 값은 결측


def number(value) -> float | None:
    """예보·실황 값을 숫자로. 빈 값, 숫자가 아닌 값, ±900 넘는 결측값은 None."""
    if value is None:
        return None
    try:
        result = float(str(value).strip())
    except ValueError:
        return None
    return None if abs(result) >= MISSING_ABS else result


def issue_times(now: dt.datetime, hours: Iterable[int], delay: dt.timedelta, count: int) -> list[dt.datetime]:
    """now 기준 받을 수 있는 가장 최근 발표 시각부터 직전 발표 시각들까지 count 개 (서울 시각, 정시).

    delay: 발표 뒤 API 에 자료가 올라오기까지 기다리는 시간. 그래도 없으면 부르는 쪽이 다음 시각으로 넘어간다.
    """
    hours = set(hours)
    t = (now.astimezone(SEOUL) - delay).replace(minute=0, second=0, microsecond=0)
    result = []
    for _ in range(24 * 3):
        if t.hour in hours:
            result.append(t)
            if len(result) == count:
                break
        t -= dt.timedelta(hours=1)
    return result


_NUMBERED_HELP = re.compile(r"^#\s*(\d+)\.\s*([A-Z][A-Z0-9_]*)\b")


def typ01_rows(text: str, required: Iterable[str], skip_mismatched: bool = False, rest_in_last: bool = False) -> list[dict[str, str]]:
    """typ01 글자 응답(help=1)을 칸 이름 → 값 dict 목록으로.

    칸 순서는 응답 안에서 읽는다 (문서 표의 순서로 짐작하지 않는다. 문서 표와 실제 출력 순서가 다르다).
    - "#  1. TM : 관측일" 같은 번호 붙은 설명 줄이 있으면 그 번호 순서
    - 없으면 칸 이름이 나란히 적힌 주석 줄. 바로 아래 주석 줄에 대문자 낱말이 있으면 이어 붙인다
      (실제 지점정보 응답: "# STN  LON  LAT … STN STN_KO …" 아래 "#  ID degee degree …  AD …" → STN_ID, STN_AD)
    칸 이름 줄을 못 찾으면 오류. 값은 쉼표(disp=1) 또는 빈칸(disp=0)으로 나뉜다.
    skip_mismatched: 칸 수가 다른 줄을 오류 대신 건너뛴다.
    rest_in_last: 값이 칸보다 많으면 남는 값을 마지막 칸에 빈칸으로 이어 붙인다 (마지막 칸이 주소처럼 빈칸 있는 글일 때).
    """
    required = list(required)
    lines = text.splitlines()
    columns = _header_columns(lines, required)
    if not columns:
        raise KmaResponseError(f"응답에서 칸 이름({', '.join(required)})을 찾지 못했어요")
    rows = []
    for line in lines:
        if not line.strip() or line.startswith("#"):
            continue
        values = _split(line)
        if rest_in_last and len(values) > len(columns):
            values = values[: len(columns) - 1] + [" ".join(values[len(columns) - 1 :])]
        if len(values) != len(columns):
            if skip_mismatched:
                continue
            raise KmaResponseError(f"칸 수가 달라요 (이름 {len(columns)}개, 값 {len(values)}개)")
        rows.append(dict(zip(columns, values)))
    return rows


def _header_columns(lines: list[str], required: list[str]) -> list[str]:
    numbered = sorted((int(m.group(1)), m.group(2)) for line in lines if (m := _NUMBERED_HELP.match(line)))
    columns = [name for _, name in numbered]
    if all(name in columns for name in required):
        return columns
    comments = [_split(line.lstrip("#")) for line in lines if line.startswith("#")]
    for i, tokens in enumerate(comments):
        below = comments[i + 1] if i + 1 < len(comments) else []
        if len(below) == len(tokens):
            joined = [f"{a}_{b}" if b.isalpha() and b.isupper() else a for a, b in zip(tokens, below)]
            if all(name in joined for name in required):
                return joined
        if all(name in tokens for name in required):
            return tokens
    return []


def _split(line: str) -> list[str]:
    line = line.strip().rstrip("=").strip().rstrip(",")  # 줄 끝에 = 나 쉼표가 붙어 오는 때가 있다
    parts = line.split(",") if "," in line else line.split()
    return [p.strip() for p in parts]
