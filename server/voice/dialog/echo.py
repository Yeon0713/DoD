"""도나가 한 말이 마이크로 다시 들어온 것 거르기 (2026-11-18).

받아 적기를 서버(Whisper, 지금은 네이버 CSR)로 바꾼 뒤, 스피커에서 나온 도나 목소리까지 또렷하게 받아 적혀 사장님 말로 들어왔다
("하린 씨에게 '…'를 보낼게요. 오늘만이에요. 맞아요?" → 알바생 시키기로 알아듣고, 브리핑 문장 → 브리핑을 다시 시작).
앱은 도나가 말하는 동안 듣지 않지만, 기기 목소리가 늦게 끝나거나 스피커가 크면 꼬리가 들어온다.

그래서 가게마다 도나가 최근(RECENT_S 초) 한 말을 기억해 두고, 들어온 말의 글자 두 개씩 묶음(바이그램) 대부분이
그 안에 있으면 도나 자신의 말로 보고 흘려듣는다. 숫자 표기("열두 분" ↔ "12분")나 받아쓰기 오타가 조금 달라도 걸린다.
짧은 대답("응", "보내 줘")과 대답 모양의 말("카카오톡으로 보내 줘", "오늘만", "쿠폰 빼고 사과만 올려", "인스타에 올리지 마")은 거르지 않는다.
"""

import threading
import time

from voice.similar import pairs as _pairs, squash as _squash

RECENT_S = 120
MIN_CHARS = 8
OVERLAP = 0.7  # "저녁 계약은 두 팀이고"(도나: "저녁 예약은 두 팀이고")처럼 일부를 잘못 받아 적은 것도 거른다

# 앱이 서버 없이 스스로 하는 말 (donna-voice/app/src/lib/conversation.tsx)
APP_LINES = ["네.", "잘 못 들었어요. 한 번 더 말씀해 주세요.", "지금은 답하기 어려워요. 조금 뒤에 다시 말씀해 주세요."]

_said: dict[str, list[tuple[float, str]]] = {}
_lock = threading.Lock()


def remember(store_id: str, texts: list[str]) -> None:
    """도나가 이번에 말한 문장들."""
    now = time.monotonic()
    with _lock:
        kept = [(t, s) for t, s in _said.get(store_id, []) if now - t <= RECENT_S]
        kept += [(now, _squash(text)) for text in texts if text]
        _said[store_id] = kept[-60:]


def _answer_shaped(text: str) -> bool:
    """도나 질문에 대한 대답 모양 ("카카오톡으로 보내 줘", "응, 진행해", "오늘만", "쿠폰 빼고 사과만 올려"). 도나 질문과 글자가 겹쳐도 사장님 말이다."""
    from voice.dialog import intent_rules as r

    n = r.normalize(text)
    return bool(r.YES_RE.search(n) or r.NO_RE.search(n) or r.STAFF_SHARE_RE.search(n) or r.STAFF_SEND_RE.search(n)
                or r.STAFF_TODAY_RE.search(n) or r.STAFF_DAILY_RE.search(n) or r.APPROVE_RE.fullmatch(n)
                or r.DROP_COMP_RE.search(n) or r.NO_CARD_RE.search(n)
                or r.INSTA_LATER_RE.search(n) or r.FEED_POST_RE.search(n) or r.STORY_POST_RE.search(n))


def is_echo(store_id: str, heard: str) -> bool:
    text = _squash(heard)
    if len(text) < MIN_CHARS or _answer_shaped(heard):
        return False
    now = time.monotonic()
    with _lock:
        recent = [s for t, s in _said.get(store_id, []) if now - t <= RECENT_S]
    pool = set().union(*(_pairs(s) for s in recent + [_squash(line) for line in APP_LINES]))
    mine = _pairs(text)
    return len(mine & pool) / len(mine) >= OVERLAP


def forget(store_id: str | None = None) -> None:
    with _lock:
        if store_id is None:
            _said.clear()
        else:
            _said.pop(store_id, None)
