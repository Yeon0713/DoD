"""근거 장부와 근거 대조.

제출물에 나온 숫자, 메뉴 이름, 행사·경기 이름, 시각은 입력 사실이나 이번 실행의 도구 결과에 글자 그대로 있어야 한다.
문장 다듬기의 must_keep 검사를 거꾸로 쓴 것이다. 비율처럼 계산이 필요한 숫자는 도구가 계산해서 돌려주므로,
모델이 직접 계산한 숫자는 장부에 없어서 걸린다.
"""

import json
import re
from collections.abc import Iterable

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


class Evidence:
    """이번 실행에서 모델이 본 것: 입력 사실(user 메시지 등)과 도구 결과."""

    def __init__(self, facts: Iterable[str] = ()):
        self.entries: list[dict] = [{"source": "input", "text": text} for text in facts if text]

    def add(self, source: str, result: object) -> None:
        text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
        self.entries.append({"source": source, "text": text})

    def sources(self) -> list[str]:
        return [entry["source"] for entry in self.entries]

    @property
    def corpus(self) -> str:
        return "\n".join(entry["text"] for entry in self.entries)

    def numbers(self) -> set[str]:
        return set(NUMBER_RE.findall(self.corpus))


def ungrounded_numbers(text: str, evidence: Evidence) -> list[str]:
    """글에 나온 숫자 중 근거 장부에 없는 것."""
    known = evidence.numbers()
    return [number for number in NUMBER_RE.findall(text) if number not in known]


def ungrounded_terms(terms: Iterable[str], evidence: Evidence) -> list[str]:
    """이름 목록 중 근거 장부에 글자 그대로 없는 것."""
    corpus = evidence.corpus
    return [term for term in terms if term and term not in corpus]
