"""도나 목소리 (TTS). Qwen3-TTS CustomVoice 의 Sohee 에 '도나 목소리 설계'(INSTRUCT)를 얹어 이 컴퓨터에서 만든다 (MLX).

- 무겁다: M1 에서 문장 길이의 약 3배 시간이 걸린다. 그래서 브리핑을 준비할 때 도나가 할 말을 미리 만들어
  디스크(db/app_data/voice_tts/)에 둔다 (prewarm). 한 번 만든 문장은 다시 만들지 않는다.
- GET /v1/tts?text= : 만들어 둔 것이 있으면 wav 를 준다. 없으면 204 를 주고 맨 앞 차례로 만든다.
  앱은 204 면 그 문장만 기기 목소리로 읽는다.
- mlx-audio 가 없거나 GPU(Metal)를 못 쓰면 꺼진다. VOICE_TTS=false 로도 끈다. 그때 앱은 기기 목소리로 읽는다.
- 모든 생성은 스레드 하나에서 차례로 한다 (모델은 한 번만 올린다).

도나 목소리 설계 (docs/donna-voice-design.md)
  사장님 곁에서 몇 년째 가게를 같이 본 30대 초반 실장. 아침마다 그날 일을 짧게 알려 준다.
  보통보다 조금 느리게, 숫자와 시각은 또박또박. 차분하고 다정하지만 들뜨거나 광고 같지 않다.
"""

import hashlib
import heapq
import itertools
import logging
import os
import re
import threading
import wave
from pathlib import Path

from voice import config, speech

logger = logging.getLogger(__name__)

MODEL = os.environ.get("VOICE_TTS_MODEL", "mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit")
SPEAKER = os.environ.get("VOICE_TTS_SPEAKER", "sohee")
INSTRUCT = os.environ.get(
    "VOICE_TTS_INSTRUCT",
    "A calm, warm Korean woman in her early thirties who has run this small restaurant with the owner for years, "
    "giving him his morning briefing. Slightly slower than normal, unhurried pace with clear, crisp pronunciation, "
    "especially for numbers and times. Gentle, polite and reassuring; friendly but never bubbly or salesy. "
    "Steady mid-to-low pitch, short natural pauses at commas. A trusted colleague, not an announcer or a robot.",
)
ENABLED = os.environ.get("VOICE_TTS", "true").lower() != "false"
LIVE, PREWARM = 0, 1  # 차례: 사장님이 지금 들을 문장이 먼저

# 앱이 서버 없이도 늘 하는 말 (src/lib/conversation.tsx). 켤 때 미리 만든다.
FIXED = ["네.", "잘 못 들었어요. 한 번 더 말씀해 주세요.", "지금은 답하기 어려워요. 조금 뒤에 다시 말씀해 주세요."]


def cache_dir() -> Path:
    return config.DB_PATH.parent / "voice_tts"


# ── 읽는 글로 바꾸기: 화면 글의 숫자를 소리 내는 말로 ──

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
    big, rest = divmod(n, 10000)
    return (sino(big) + "만" + (sino(rest) if rest else "")) if big else sino(n)


def spoken(text: str) -> str:
    """'낮 12시에 단체 12명' → '낮 열두 시에 단체 열두 명'. 이미 말로 쓴 숫자('열두 분')는 그대로 둔다."""
    text = re.sub(r"(\d+)\s?월", lambda m: _MONTHS.get(int(m[1]), sino(int(m[1]) % 10000) + "월"), text)
    text = re.sub(r"(\d+)\s?시(?!간)", lambda m: speech.native(int(m[1])) + " 시", text)
    text = re.sub(r"(\d+)\s?(명|개|팀|번|그릇|잔|장|분이|분께|살)", lambda m: speech.native(int(m[1])) + " " + m[2], text)
    text = re.sub(r"(\d[\d,]*)", lambda m: _man(int(m[1].replace(",", ""))), text)
    return text


def key(text: str) -> str:
    return hashlib.sha1(f"{MODEL}|{SPEAKER}|{INSTRUCT}|{spoken(text)}".encode()).hexdigest()


def cached(text: str) -> Path | None:
    path = cache_dir() / f"{key(text)}.wav"
    return path if path.exists() else None


# ── 만드는 스레드 ──


class _Worker:
    def __init__(self):
        self.queue: list[tuple[int, int, str, str]] = []  # (차례, 순번, key, 글)
        self.queued: dict[str, int] = {}
        self.seq = itertools.count()
        self.cond = threading.Condition()
        self.thread: threading.Thread | None = None
        self.model = None
        self.error: str | None = None
        self.made = 0

    def add(self, text: str, priority: int) -> None:
        if not ENABLED or self.error or cached(text):
            return
        k = key(text)
        with self.cond:
            if self.queued.get(k, 99) <= priority:
                return
            self.queued[k] = priority
            heapq.heappush(self.queue, (priority, next(self.seq), k, text))
            if self.thread is None:
                self.thread = threading.Thread(target=self.run, daemon=True, name="voice-tts")
                self.thread.start()
            self.cond.notify()

    def run(self) -> None:
        while True:
            with self.cond:
                while not self.queue:
                    self.cond.wait()
                priority, _, k, text = heapq.heappop(self.queue)
                if self.queued.get(k) != priority:  # 더 앞 차례로 다시 들어온 것
                    continue
                self.queued.pop(k, None)
            if cached(text):
                continue
            try:
                self.make(text)
            except Exception as error:  # 모델을 못 올리면 끈다. 앱은 기기 목소리로 읽는다
                logger.exception("도나 목소리를 만들지 못했어요")
                if self.model is None:
                    self.error = str(error)
                    with self.cond:
                        self.queue.clear()
                        self.queued.clear()

    def make(self, text: str) -> None:
        import numpy as np

        if self.model is None:
            from mlx_audio.tts.utils import load_model

            self.model = load_model(MODEL)
        results = list(self.model.generate(text=spoken(text), voice=SPEAKER, instruct=INSTRUCT, lang_code="korean"))
        audio = np.concatenate([np.array(r.audio, dtype=np.float32).reshape(-1) for r in results])
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
        folder = cache_dir()
        folder.mkdir(parents=True, exist_ok=True)
        part = folder / f"{key(text)}.part"
        with wave.open(str(part), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(self.model.sample_rate)
            out.writeframes(pcm.tobytes())
        part.rename(folder / f"{key(text)}.wav")
        self.made += 1


_worker = _Worker()


def available() -> bool:
    if not ENABLED or _worker.error:
        return False
    try:
        import mlx_audio  # noqa: F401
    except ImportError:
        return False
    return True


def request(text: str) -> None:
    """지금 들을 문장. 맨 앞 차례로 만든다."""
    if available():
        _worker.add(text, LIVE)


def prewarm(texts: list[str]) -> None:
    """미리 만들어 둘 문장 (브리핑 준비 때). 뒤 차례로 만든다."""
    if available():
        for text in texts:
            _worker.add(text, PREWARM)


def status() -> dict:
    folder = cache_dir()
    return {"available": available(), "model": MODEL, "speaker": SPEAKER, "loaded": _worker.model is not None,
            "waiting": len(_worker.queued), "made": _worker.made, "cached": len(list(folder.glob("*.wav"))) if folder.exists() else 0,
            "error": _worker.error}
