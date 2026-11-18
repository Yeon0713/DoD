"""도나의 숫자 읽기와 CLOVA Voice 실시간 음성 합성."""
import re

import httpx

from app.core.config import settings
from voice import speech

MODEL = "clova-voice-premium"
SPEAKER = "vara"
ENABLED = settings.voice_tts
OPTIONS = {
    "speaker": SPEAKER, "speed": -2, "alpha": 1, "pitch": -1,
    "emotion": 0, "emotion-strength": 0, "format": "wav",
}


_SINO = "영일이삼사오육칠팔구"
_MONTHS = {6: "유월", 10: "시월"}


def sino(n: int) -> str:
    """한자어 수: 30 → 삼십, 128 → 백이십팔, 2026 → 이천이십육."""
    if n == 0:
        return "영"
    out = ""
    for value, name in ((1000, "천"), (100, "백"), (10, "십")):
        digit, n = divmod(n, value)
        if digit:
            out += ("" if digit == 1 else _SINO[digit]) + name
    return out + (_SINO[n] if n else "")


def _man(n: int) -> str:
    if n >= 100_000_000:
        return str(n)  # 억 단위 이상은 합성기의 숫자 읽기를 쓴다
    big, rest = divmod(n, 10000)
    return (sino(big) + "만" + (sino(rest) if rest else "")) if big else sino(n)


def spoken(text: str) -> str:
    """'낮 12시에 단체 12명' → '낮 열두 시에 단체 열두 명'. 이미 말로 쓴 숫자('열두 분')는 그대로 둔다."""
    text = re.sub(r"(\d+)\s?월", lambda m: _MONTHS.get(int(m[1]), sino(int(m[1]) % 10000) + "월"), text)
    text = re.sub(r"(\d+)\s?시(?!간)", lambda m: speech.native(int(m[1])) + " 시", text)
    text = re.sub(r"(\d+)\s?(명|개|팀|번|그릇|잔|장|분이|분께|살)", lambda m: speech.native(int(m[1])) + " " + m[2], text)
    text = re.sub(r"(\d[\d,]*)", lambda m: _man(int(m[1].replace(",", ""))), text)
    return text


def available() -> bool:
    keys = (settings.clova_voice_client_id, settings.clova_voice_client_secret)
    return ENABLED and all(re.fullmatch(r"[!-~]+", key) for key in keys)


def synthesize(text: str) -> bytes:
    response = httpx.post(
        "https://naveropenapi.apigw.ntruss.com/tts-premium/v1/tts",
        headers={
            "X-NCP-APIGW-API-KEY-ID": settings.clova_voice_client_id,
            "X-NCP-APIGW-API-KEY": settings.clova_voice_client_secret,
        },
        data={**OPTIONS, "text": text},
        timeout=5.0,
    )
    response.raise_for_status()
    return response.content
