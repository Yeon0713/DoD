"""화면 글자 폭 한도 (문서 6장). 한도를 넘으면 앱 화면에서 줄이 넘어가 깨진다.

폭: 한글 한 글자 = 1, 숫자·공백·문장 부호·영문 한 글자 = 0.5.
violations(응답) 는 넘은 칸을 모두 돌려준다. 테스트(D4)와 브리핑을 만들 때(fit) 같이 쓴다.
"""

LIMITS = {
    "headline": 15,
    "caption": 18,
    "owner_said": 36,
    "suggestions": 16,  # 둘을 합친 폭
    "rows.label": 10,
    "rows.value": 14,
    "counts.label": 8,
    "review.summary": 17,
    "reply.summary": 32,
    "tip": 34,
    "bars.label": 12,
    "scheduled.text": 13,
    "reason.label": 8,
    "time_label": 6,  # v0.2.1 예약 카드는 '오전 10시 반'까지 들어간다 (D-13)
    "day_label": 1,
    "staff.title": 16,  # 알바생 할 일 제목 (에이전트가 쓰는 교정·현장 변수·매뉴얼)
    "staff.detail": 48,  # 알바생 할 일 무엇을 어떻게 (한 문장)
}
MAX_ITEMS = {"rows": 4, "bars": 3, "scheduled": 3, "suggestions": 2}


def width(text: str | None) -> float:
    if not text:
        return 0
    return sum(1 if _wide(ch) else 0.5 for ch in text)


def _wide(ch: str) -> bool:
    code = ord(ch)
    return 0xAC00 <= code <= 0xD7A3 or 0x1100 <= code <= 0x11FF or 0x3130 <= code <= 0x318F or 0x4E00 <= code <= 0x9FFF


def fits(text: str | None, field: str) -> bool:
    return width(text) <= LIMITS[field]


def fit(field: str, *choices: str) -> str:
    """한도 안에 들어가는 첫 문장. 모두 넘으면 마지막(가장 짧게 준비한) 문장."""
    for choice in choices:
        if fits(choice, field):
            return choice
    return choices[-1]


def _over(field: str, text: str | None, where: str, found: list[str]) -> None:
    if text is not None and not fits(text, field):
        found.append(f"{where}: '{text}' 폭 {width(text)} > {LIMITS[field]}")


def violations(response: dict) -> list[str]:
    """응답(home 또는 turn) 안에서 한도를 넘은 칸."""
    found: list[str] = []
    _over("headline", response.get("headline"), "headline", found)
    _over("owner_said", response.get("owner_said"), "owner_said", found)
    for number, say in enumerate(response.get("say") or []):
        _over("caption", say.get("caption"), f"say[{number}].caption", found)
    suggestions = response.get("suggestions") or []
    if len(suggestions) > MAX_ITEMS["suggestions"]:
        found.append(f"suggestions {len(suggestions)}개 > 2")
    if sum(width(s) for s in suggestions) > LIMITS["suggestions"]:
        found.append(f"suggestions 합친 폭 {sum(width(s) for s in suggestions)} > 16: {suggestions}")
    for card in response.get("cards") or []:
        _card(card, found)
    return found


def _card(card: dict, found: list[str]) -> None:
    kind, cid = card["type"], card.get("id")
    if kind == "rows":
        if len(card["rows"]) > MAX_ITEMS["rows"]:
            found.append(f"{cid}: rows {len(card['rows'])}줄 > 4")
        for row in card["rows"]:
            _over("rows.label", row.get("label"), f"{cid}.{row['id']}.label", found)
            _over("rows.value", row.get("value"), f"{cid}.{row['id']}.value", found)
    elif kind == "counts":
        if len(card["items"]) != 2:
            found.append(f"{cid}: counts {len(card['items'])}칸 (정확히 2)")
        for item in card["items"]:
            _over("counts.label", item.get("label"), f"{cid}.{item['id']}.label", found)
    elif kind == "review":
        if card.get("variant") == "summary":
            _over("review.summary", card.get("text"), f"{cid}.text", found)
            if card.get("reply"):
                _over("reply.summary", card["reply"].get("text"), f"{cid}.reply.text", found)
    elif kind == "tip":
        _over("tip", card.get("text"), f"{cid}.text", found)
    elif kind == "bars":
        if len(card["items"]) > MAX_ITEMS["bars"]:
            found.append(f"{cid}: bars {len(card['items'])}줄 > 3")
        for item in card["items"]:
            _over("bars.label", item.get("label"), f"{cid}.{item['id']}.label", found)
    elif kind == "scheduled":
        if len(card["items"]) > MAX_ITEMS["scheduled"]:
            found.append(f"{cid}: scheduled {len(card['items'])}줄 > 3")
        for item in card["items"]:
            _over("scheduled.text", item.get("text"), f"{cid}.{item['id']}.text", found)
            _over("reason.label", item["reason"].get("label"), f"{cid}.{item['id']}.reason", found)
            _over("time_label", item.get("time_label"), f"{cid}.{item['id']}.time_label", found)
            _over("day_label", item.get("day_label"), f"{cid}.{item['id']}.day_label", found)
