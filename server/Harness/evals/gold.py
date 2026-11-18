"""정답지(review_gold_*.xlsx) 읽기. 행 하나를 평가 사례 dict 하나로 바꾼다.

정답지는 사용자만 갖는다. 저장소에 복사하거나 커밋하지 않는다. 경로와 sha256 은 실행할 때 받는다.
  경로    --gold <경로>       또는 환경 변수 DONA_EVAL_GOLD
  sha256  --gold-sha <해시>   또는 환경 변수 DONA_EVAL_GOLD_SHA256
파일의 sha256 이 주어진 값과 다르면 멈춘다(GoldError). 정답지 판이 바뀌면 처음부터 다시 재야 하기 때문이다.

시트 gold 의 열 → 사례
  case_id                      case_id
  플랫폼                        platform   네이버플레이스 NAVER, 쿠팡이츠 COUPANG, 배달의민족 BAEMIN
  배달상황키워드, 플랫폼, 리뷰    order_channel  배달상황키워드가 있거나, 배달 플랫폼(쿠팡이츠·배달의민족)이거나,
                                               리뷰 글에 배달 말(DELIVERY_TEXT_RE: 배달, 라이더, 배송)이 있으면 delivery, 아니면 hall
  별점                          rating     없으면 None
  주문일                        written_at YYYY-MM-DD
  손님 리뷰                      text       그대로 둔다. 모델에 보낼 때 mask_personal_info 를 거친다
  방문상황키워드, 배달상황키워드    visit_keywords, delivery_keywords (없으면 "")
  sentiment                    gold.sentiment       POSITIVE | NEGATIVE | MIXED
  complaint_types (JSON 글)     gold.complaint_types
  사장님 답변                    gold.reply   없거나 flags 에 reply_equals_review(리뷰를 그대로 복사한 답)가 있으면 None
  flags (쉼표로 구분)            flags
  eval_set, split              eval_set (balanced | full_only), split (tune | holdout | "")
가게는 모두 s005(초옹장)다. 작성자, 사장님 답변일, complaint_note 는 사례에 넣지 않는다.

사용 (server/ 에서, CLOVA 를 부르지 않는다):
  python -m Harness.evals.gold --gold <경로> --gold-sha <해시>     행 수와 세트별 개수를 보여 준다
"""

import argparse
import datetime as dt
import json
import os
import re
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

from Harness.evals.report import file_sha256

SHEET = "gold"
STORE_ID = "s005"
GOLD_ENV = "DONA_EVAL_GOLD"
SHA_ENV = "DONA_EVAL_GOLD_SHA256"

PLATFORMS = {"네이버플레이스": "NAVER", "쿠팡이츠": "COUPANG", "배달의민족": "BAEMIN"}
DELIVERY_PLATFORMS = {"COUPANG", "BAEMIN"}
DELIVERY_TEXT_RE = re.compile(r"배달|라이더|배송")  # 포장은 가져가는 손님도 써서 넣지 않는다
SENTIMENTS = ("POSITIVE", "NEGATIVE", "MIXED")
EVAL_SETS = ("balanced", "full_only")
SPLITS = ("tune", "holdout", "")
REPLY_COPY_FLAG = "reply_equals_review"

COLUMNS = ("case_id", "별점", "방문상황키워드", "배달상황키워드", "주문일", "손님 리뷰", "사장님 답변", "플랫폼",
           "sentiment", "complaint_types", "eval_set", "split", "flags")


class GoldError(RuntimeError):
    """정답지를 쓸 수 없다 (경로·해시가 없음, 해시가 다름, 열이나 값이 틀림)."""


def resolve_source(gold: str | None = None, sha256: str | None = None,
                   env: Mapping[str, str] | None = None) -> tuple[Path, str]:
    """인자 → 환경 변수 순으로 정답지 경로와 sha256 을 정한다. 없으면 GoldError."""
    env = os.environ if env is None else env
    path = gold or env.get(GOLD_ENV)
    if not path:
        raise GoldError(f"정답지 경로를 주세요 (--gold <경로> 또는 환경 변수 {GOLD_ENV})")
    expected = sha256 or env.get(SHA_ENV)
    if not expected:
        raise GoldError(f"정답지 sha256 을 주세요 (--gold-sha <해시> 또는 환경 변수 {SHA_ENV})")
    return Path(path), expected.strip().lower()


def check_sha256(path: Path, expected_sha256: str) -> str:
    """파일 해시가 기대값과 같으면 그 해시를, 다르면 GoldError."""
    path = Path(path)
    if not path.is_file():
        raise GoldError(f"정답지 파일이 없어요: {path}")
    actual = file_sha256(path)
    if actual != expected_sha256.strip().lower():
        raise GoldError(f"정답지 sha256 이 달라요 (기대 {expected_sha256[:12]}…, 실제 {actual[:12]}…). "
                        "정답지 판이 바뀌었으면 처음부터 다시 재야 해요")
    return actual


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _date(value: object) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value).strip()[:10]


def _rating(value: object, case_id: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise GoldError(f"{case_id}: 별점을 숫자로 읽을 수 없어요 ({value!r})") from None


def _complaint_types(value: object, case_id: str) -> list[str]:
    raw = _text(value) or "[]"
    try:
        types = json.loads(raw)
    except ValueError:
        raise GoldError(f"{case_id}: complaint_types 가 JSON 이 아니에요 ({raw!r})") from None
    if not isinstance(types, list) or not all(isinstance(t, str) for t in types):
        raise GoldError(f"{case_id}: complaint_types 는 글자 목록이어야 해요 ({raw!r})")
    return types


def _one_of(value: str, allowed: tuple[str, ...], column: str, case_id: str) -> str:
    if value not in allowed:
        raise GoldError(f"{case_id}: {column} 값 {value!r} 은 {', '.join(repr(a) for a in allowed)} 중 하나여야 해요")
    return value


def row_to_case(row: Mapping[str, object]) -> dict:
    """정답지 행 하나(열 이름 → 값) → 사례 dict."""
    case_id = _text(row["case_id"])
    if not case_id:
        raise GoldError("case_id 가 빈 행이 있어요")
    platform_name = _text(row["플랫폼"])
    platform = PLATFORMS.get(platform_name)
    if platform is None:
        raise GoldError(f"{case_id}: 모르는 플랫폼 {platform_name!r}")
    delivery_keywords = _text(row["배달상황키워드"])
    flags = [flag.strip() for flag in _text(row["flags"]).split(",") if flag.strip()]
    reply = _text(row["사장님 답변"]) or None
    if REPLY_COPY_FLAG in flags:
        reply = None
    return {
        "case_id": case_id,
        "store": STORE_ID,
        "platform": platform,
        "order_channel": ("delivery" if delivery_keywords or platform in DELIVERY_PLATFORMS
                          or DELIVERY_TEXT_RE.search(_text(row["손님 리뷰"])) else "hall"),
        "rating": _rating(row["별점"], case_id),
        "written_at": _date(row["주문일"]),
        "text": _text(row["손님 리뷰"]),
        "visit_keywords": _text(row["방문상황키워드"]),
        "delivery_keywords": delivery_keywords,
        "gold": {
            "sentiment": _one_of(_text(row["sentiment"]), SENTIMENTS, "sentiment", case_id),
            "complaint_types": _complaint_types(row["complaint_types"], case_id),
            "reply": reply,
        },
        "flags": flags,
        "eval_set": _one_of(_text(row["eval_set"]), EVAL_SETS, "eval_set", case_id),
        "split": _one_of(_text(row["split"]), SPLITS, "split", case_id),
    }


def read_rows(path: Path) -> list[dict]:
    """시트 gold 의 행들(열 이름 → 값). 열이 모자라면 GoldError."""
    import openpyxl  # 평가할 때만 필요하다

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if SHEET not in workbook.sheetnames:
            raise GoldError(f"정답지에 시트 {SHEET!r} 가 없어요")
        rows = workbook[SHEET].iter_rows(values_only=True)
        header = [_text(name) for name in next(rows, ())]
        missing = [name for name in COLUMNS if name not in header]
        if missing:
            raise GoldError(f"정답지에 열이 없어요: {', '.join(missing)}")
        return [dict(zip(header, values)) for values in rows if any(v is not None for v in values)]
    finally:
        workbook.close()


def load_gold(path: Path | str, expected_sha256: str) -> list[dict]:
    """해시를 확인하고 정답지를 사례 목록으로 읽는다. case_id 가 겹치면 GoldError."""
    path = Path(path)
    check_sha256(path, expected_sha256)
    cases = [row_to_case(row) for row in read_rows(path)]
    repeated = [case_id for case_id, n in Counter(case["case_id"] for case in cases).items() if n > 1]
    if repeated:
        raise GoldError(f"case_id 가 겹쳐요: {', '.join(repeated[:5])}")
    return cases


def config_entry(path: Path, sha256: str, sets: Mapping[str, str] | None = None) -> dict:
    """result.json config.gold 에 넣을 값. 파일 이름만 적는다 (경로에는 사용자 폴더 이름이 들어간다)."""
    return {"file": Path(path).name, "sha256": sha256, "sets": dict(sets or {})}


def summary(cases: list[dict]) -> dict:
    """행 수와 세트별 개수. 정답지를 바르게 읽었는지 사람이 볼 때 쓴다."""
    balanced = [case for case in cases if case["eval_set"] == "balanced"]
    return {
        "rows": len(cases),
        "balanced": len(balanced),
        "tune": sum(1 for case in balanced if case["split"] == "tune"),
        "holdout": sum(1 for case in balanced if case["split"] == "holdout"),
        "sentiment": dict(Counter(case["gold"]["sentiment"] for case in cases)),
        "order_channel": dict(Counter(case["order_channel"] for case in cases)),
        "with_reply": sum(1 for case in cases if case["gold"]["reply"]),
    }


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--gold", default=None, help=f"정답지 xlsx 경로 (없으면 환경 변수 {GOLD_ENV})")
    parser.add_argument("--gold-sha", default=None, help=f"정답지 sha256 (없으면 환경 변수 {SHA_ENV})")


def from_args(args: argparse.Namespace) -> tuple[Path, str, list[dict]]:
    """argparse 결과로 정답지를 읽는다. (경로, sha256, 사례 목록)."""
    path, expected = resolve_source(getattr(args, "gold", None), getattr(args, "gold_sha", None))
    return path, expected, load_gold(path, expected)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m Harness.evals.gold", description="정답지를 읽어 행 수와 세트별 개수를 보여 준다")
    add_arguments(parser)
    try:
        _, _, cases = from_args(parser.parse_args(argv))
    except GoldError as error:
        raise SystemExit(f"멈춤: {error}") from None
    print(json.dumps(summary(cases), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
