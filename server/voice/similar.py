"""글자 두 개씩 묶음(바이그램)으로 두 글이 얼마나 겹치는지 잰다. LLM 없이 빠르게 후보를 고를 때 쓴다.

dialog/echo.py (도나 자신의 말 거르기)와 proposals.py (같은 할 일 찾기)가 쓴다.
"""

import re

_PUNCT = re.compile(r"[\s.,!?~…'\"“”‘’·()\[\]]+")


def squash(text: str) -> str:
    """띄어쓰기와 문장 부호를 지운다."""
    return _PUNCT.sub("", text or "")


def pairs(text: str) -> set[str]:
    return {text[i:i + 2] for i in range(len(text) - 1)}


def dice(a: str, b: str) -> float:
    """대칭 겹침 2|A∩B| / (|A|+|B|). 0 ~ 1."""
    pa, pb = pairs(squash(a)), pairs(squash(b))
    if not pa or not pb:
        return 0.0
    return 2 * len(pa & pb) / (len(pa) + len(pb))
