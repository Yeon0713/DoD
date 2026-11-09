"""키워드 규칙 리뷰 분류. 모델 호출이 실패했을 때 대신 쓴다.

- 불만 유형마다 정규식 목록을 두고, 하나라도 맞으면 그 유형을 붙인다.
- 불만을 놓치지 않는 쪽으로 넓게 잡았다. 그래서 가끔 불만이 아닌 리뷰를 불만으로 볼 수 있다.
- 키워드 바로 뒤에 "지 않" 이 오면 그 키워드는 맞지 않은 것으로 본다. 예) "양이 적지 않아요"
"""

import re

from app.analysis.review.complaint_groups import sort_types

KEYWORDS: dict[str, list[str]] = {
    "TASTE": [
        r"짜요", r"짰", r"짜서", r"싱거", r"싱겁", r"비린", r"비려", r"너무\s?달[아고았]", r"달아서",
        r"맛이\s?(없|이상|달라|별로|변했)", r"맛없", r"덜\s?익", r"퍼져서", r"퍼졌", r"식감이\s?별로",
        r"너무\s?매[워웠]",
    ],
    "PORTION": [
        r"양[이도]\s?(너무\s?|좀\s?|많이\s?)?(적|작)", r"가격\s?대비\s?양", r"양이\s?(줄|부족|아쉬)",
    ],
    "HYGIENE": [
        r"머리카락", r"이물질", r"벌레", r"비위생", r"위생이\s?(별로|엉망|안\s?좋)", r"상했", r"쉰\s?냄새",
    ],
    "PHOTO_MISMATCH": [
        r"사진(이랑|과|하고)\s?(너무\s?|많이\s?|완전\s?)?(달라|다르|다름|딴판)", r"사진\s?보고\s?시켰는데",
    ],
    "DELIVERY_DELAY": [
        r"늦[게어었는고]", r"\d+\s?분\s?(넘게|이상|가까이)", r"한\s?시간", r"\d+\s?시간\s?(넘게|이상|가까이)",
        r"오래\s?걸", r"기다렸", r"불어서", r"불었", r"식어서", r"식었", r"미지근", r"예상\s?시간보다",
        r"시간\s?안내가?\s?틀",
    ],
    "SERVICE": [
        r"불친절", r"(응대|태도)가?\s?(별로|불쾌|엉망|최악)", r"누락",
        r"(김밥|만두|음료|수저|젓가락|반찬|메뉴)[이가을]?\s?(빠졌|빠져|안\s?왔)", r"전화를?\s?안\s?받",
    ],
}
PATTERNS = {kind: [re.compile(p) for p in patterns] for kind, patterns in KEYWORDS.items()}

NEGATION_AFTER = re.compile(r"^.{0,2}지\s?(는\s?|도\s?)?않")  # 키워드 뒤에 바로 오는 "지 않"
PRAISE = re.compile(r"맛있|맛나|맛은\s?(괜찮|좋)|좋아|좋았|좋네|좋은데|최고|(?<!불)친절|추천|괜찮|만족|또\s?(시킬|먹|올|주문)")
CONTRAST = re.compile(r"지만|다만|아쉽|아쉬")  # 칭찬 뒤에 붙는 아쉬움


def _matches(pattern: re.Pattern, text: str) -> bool:
    return any(not NEGATION_AFTER.match(text[m.end():]) for m in pattern.finditer(text))


def complaint_types_by_keywords(text: str) -> list[str]:
    """맞는 키워드가 있는 불만 유형 목록."""
    return sort_types(kind for kind, patterns in PATTERNS.items() if any(_matches(p, text) for p in patterns))


def classify_by_keywords(text: str) -> tuple[str, list[str]]:
    """리뷰 본문 → (감정, 불만 유형 목록).

    - 불만 유형이 있고 칭찬도 있으면 MIXED, 칭찬이 없으면 NEGATIVE
    - 불만 유형이 없으면 POSITIVE. 단, 칭찬 뒤에 "지만", "아쉬워요" 같은 아쉬움이 붙으면 MIXED
    """
    types = complaint_types_by_keywords(text)
    praised = PRAISE.search(text) is not None
    if types:
        return ("MIXED" if praised else "NEGATIVE"), types
    if praised and CONTRAST.search(text):
        return "MIXED", types
    return "POSITIVE", types
