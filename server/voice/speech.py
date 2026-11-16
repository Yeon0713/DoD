"""말할 문장 도구: 숫자를 읽는 대로("열두 분"), 시각 표기("저녁 7시"), 받침에 맞는 조사.

say[].text 에서는 수를 읽는 대로 쓰고, 화면 글(caption, 카드)에서는 숫자를 쓴다 (문서 12장).
"""

import datetime as dt

WEEKDAYS = "월화수목금토일"
_ONES = ["", "한", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉"]
_TENS = ["", "열", "스물", "서른", "마흔", "쉰", "예순", "일흔", "여든", "아흔"]


def native(n: int) -> str:
    """수 + 단위 앞에 쓰는 고유어 수. 1 → 한, 12 → 열두, 20 → 스무. 100 이상은 숫자 그대로."""
    if not 0 < n < 100:
        return str(n)
    tens, ones = divmod(n, 10)
    if ones == 0:
        return "스무" if tens == 2 else _TENS[tens]
    return _TENS[tens] + _ONES[ones]


def count(n: int, unit: str) -> str:
    """'열두 분', '세 개'."""
    return f"{native(n)} {unit}"


def daypart(hour: int) -> str:
    if 5 <= hour < 10:
        return "아침"
    if 10 <= hour < 12:
        return "오전"
    if hour == 12:
        return "낮"
    if 13 <= hour < 18:
        return "오후"
    if 18 <= hour < 22:
        return "저녁"
    return "밤"


def clock_label(moment: dt.datetime) -> str:
    """'저녁 6시', '저녁 6시 반', '오전 11시 15분'. 30분은 사장님이 말하는 대로 '반'이라고 쓴다 (Figma v0.2.1)."""
    hour = moment.hour % 12 or 12
    text = f"{daypart(moment.hour)} {hour}시"
    if moment.minute == 30:
        return f"{text} 반"
    return f"{text} {moment.minute}분" if moment.minute else text


def weekday(day: dt.date) -> str:
    return WEEKDAYS[day.weekday()]


def has_batchim(word: str) -> bool:
    last = word.strip()[-1:] if word.strip() else ""
    if not last:
        return False
    if "0" <= last <= "9":
        return last in "013678"
    code = ord(last) - 0xAC00
    return 0 <= code <= 11171 and code % 28 != 0


def josa(word: str, with_batchim: str, without: str) -> str:
    """josa('강남 페스티벌', '과', '와') → '강남 페스티벌과'."""
    return word + (with_batchim if has_batchim(word) else without)
