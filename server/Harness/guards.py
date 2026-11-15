"""규칙 검사. 지금 파일마다 흩어진 검사를 이름 붙은 함수로 모은다. 기존 정규식은 가져다 쓰고 고치지 않는다.

함수마다 써도 되면 None, 안 되면 거절 이유 문자열을 돌려준다. 이유는 모델에게 그대로 돌려주므로
무엇을 고쳐야 하는지 알 수 있게 쓴다.

리뷰 답글에서는 지어낸 사정·기억하는 척 정규식을 바로 거절에 쓰지 않고, LLM 검토에 "확인할 표현"으로 넘긴다 (hint_phrases).
보상 약속은 리뷰와 답글을 주고 보상 제안이 있는지만 LLM 에게 따로 묻는다 (agents/quote_judge). 보상 정규식은 "환불은 어렵다"도 거르고,
"한 그릇 더 드릴게요"는 놓치기 때문이다. LLM 을 부를 수 없을 때만 예전처럼 정규식을 바로 거절에 쓴다.
"""

import re
from collections.abc import Iterable

from app.menu_board.menu_candidates import BANNED_REASON_WORDS
from app.review_reply_writer.write_reply_with_clova import (
    MADE_UP_FACT_RE,
    MEMORY_RE,
    PLACEHOLDER_RE,
    PROMISE_RE,
    keeps_numbers,
)

PRICE_RE = re.compile(r"\d[\d,]*\s?(원|%|％|퍼센트)|할인|반값|\d+\s?\+\s?\d+")
# 기존 PROMISE_RE 가 놓치는 보상 말투 ("만두 서비스 드린다고", "음료 서비스로 드려요", "하나 더 넣어 드릴게요")
EXTRA_PROMISE_RE = re.compile(r"서비스\s?(로\s?)?(드[리릴린려]|챙겨|넣어)|더\s?(넣어|챙겨|얹어)\s?드[리릴]|공짜로|무료로")


def promise_hit(text: str) -> re.Match | None:
    """보상 말투가 있는지 (기존 정규식 + 하네스에서 더한 정규식)."""
    return PROMISE_RE.search(text) or EXTRA_PROMISE_RE.search(text)


def length(text: str, low: int, high: int, what: str = "글") -> str | None:
    if len(text) < low:
        return f"{what}이 너무 짧거나 비었어요 ({low}자 이상)"
    if len(text) > high:
        return f"{what}이 너무 길어요 ({len(text)}자, {high}자 이하로)"
    return None


def placeholder(text: str) -> str | None:
    match = PLACEHOLDER_RE.search(text)
    return f"빈칸이 남았어요('{match.group(0)}'). 채우거나 빼세요" if match else None


def promise(text: str) -> str | None:
    match = PROMISE_RE.search(text)
    return f"보상 약속('{match.group(0)}')은 사장님이 정할 일이라 쓰면 안 돼요" if match else None


def memory(text: str) -> str | None:
    match = MEMORY_RE.search(text)
    return f"손님을 기억하는 척('{match.group(0)}')하면 안 돼요" if match else None


def made_up_fact(text: str) -> str | None:
    match = MADE_UP_FACT_RE.search(text)
    return f"가게가 알려 준 적 없는 사정('{match.group(0)}')을 쓰면 안 돼요" if match else None


def price_or_discount(text: str) -> str | None:
    match = PRICE_RE.search(text)
    return f"가격·할인('{match.group(0)}')을 지어내면 안 돼요" if match else None


def numbers_kept(original: str, rewritten: str) -> str | None:
    return None if keeps_numbers(original, rewritten) else "사장님이 쓴 숫자(날짜, 시각, 전화번호, 가격)가 바뀌거나 빠졌어요"


def sales_claim_words(text: str) -> list[str]:
    return [word for word in BANNED_REASON_WORDS if word in text]


def not_in(names: Iterable[str], allowed: Iterable[str], what: str) -> str | None:
    allowed = set(allowed)
    unknown = [name for name in names if name not in allowed]
    return f"목록에 없는 {what}: {', '.join(map(str, unknown))}" if unknown else None


def hint_phrases(text: str) -> list[str]:
    """금지어 정규식에 걸린 표현들. LLM 검토에 '확인할 표현'으로 넘긴다. 보상은 따로 판별하므로(quote_judge) 넣지 않는다."""
    return [match.group(0) for regex in (MEMORY_RE, MADE_UP_FACT_RE) for match in regex.finditer(text)]


def first(*reasons: str | None) -> str | None:
    """여러 검사 중 처음 걸린 이유."""
    return next((reason for reason in reasons if reason), None)
