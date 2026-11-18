"""사장님 말 받아 적기 (STT, 2026-11-18): Faster-Whisper large-v3-turbo + Silero VAD. 이 컴퓨터에서 돈다.

앱이 마이크 소리(16kHz, 16비트, 모노)를 WebSocket /v1/stt/stream 으로 계속 보내면
  1. Silero VAD (faster-whisper 에 들어 있는 silero_vad_v6.onnx) 가 32ms 마다 말소리인지 본다
  2. 말이 시작되면 {"type": "speech_start"} → 앱은 "듣고 있어요…"
  3. 말이 SILENCE_MS 동안 끊기면 그 구간을 Whisper 로 받아 적어 {"type": "final", "text": "…"} 를 보낸다
     ("도나야"로 시작하는지는 지금처럼 앱이 본다. 받아 적는 것은 여기, 도나에게 한 말인지는 앱)
  4. 너무 길면 MAX_SPEECH_S 에서 끊어 받아 적는다

모델: Whisper 는 맥 GPU(MPS, CTranslate2 실험 기능)로 먼저 올리고 안 되면 CPU(int8)로. 6초 말에 MPS 2.4초, CPU 5.4초 (M2, 2026-11-18).
모델 파일은 처음 한 번 Hugging Face 에서 받는다 (약 1.6GB, ~/.cache/huggingface).
끄기: VOICE_STT=false (앱은 예전처럼 브라우저 음성 인식으로 듣는다).
"""

import logging
import os
import threading
import time
from collections.abc import Callable

import numpy as np

logger = logging.getLogger(__name__)

ENABLED = os.environ.get("VOICE_STT", "true").lower() != "false"
MODEL_NAME = os.environ.get("VOICE_STT_MODEL", "large-v3-turbo")
DEVICE = os.environ.get("VOICE_STT_DEVICE", "mps")  # mps | cpu
RATE = 16000
CHUNK = 512  # Silero VAD 한 칸 (32ms)
START_PROB, END_PROB = 0.5, 0.35  # 이보다 크면 말, 작으면 조용
START_CHUNKS = 3  # 말로 보려면 연속 3칸 (약 0.1초)
SILENCE_MS = 700  # 이만큼 조용하면 말이 끝난 것
PREROLL_MS = 300  # 말 시작 앞을 이만큼 더 붙인다 (첫 소리가 잘리지 않게)
MAX_SPEECH_S = 15
VAD_CONTEXT = 32  # VAD 를 돌릴 때 앞의 몇 칸을 같이 넣을지 (약 1초. 모델이 앞뒤를 보고 판단한다)


# ── 모델 ──


class _Models:
    def __init__(self):
        self.whisper = None
        self.vad = None
        self.device: str | None = None
        self.error: str | None = None
        self.lock = threading.Lock()
        self.load_lock = threading.Lock()

    def load(self) -> None:
        with self.load_lock:
            if self.whisper is not None or self.error:
                return
            try:
                from faster_whisper import WhisperModel
                from faster_whisper.vad import get_vad_model

                started = time.perf_counter()
                self.vad = get_vad_model()
                for device, compute in ((DEVICE, "float16" if DEVICE == "mps" else "int8"), ("cpu", "int8")):
                    try:
                        self.whisper = WhisperModel(MODEL_NAME, device=device, compute_type=compute, cpu_threads=8)
                        self.device = device
                        break
                    except Exception:  # MPS 가 안 되면 CPU 로
                        logger.exception("Whisper 를 %s 로 올리지 못했어요", device)
                if self.whisper is None:
                    raise RuntimeError("Whisper 를 올리지 못했어요")
                logger.info("STT 준비 끝 (%s, %s, %.1f초)", MODEL_NAME, self.device, time.perf_counter() - started)
            except Exception as error:
                logger.exception("STT 를 켜지 못했어요")
                self.error = str(error)


_models = _Models()


def available() -> bool:
    if not ENABLED or _models.error:
        return False
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def warm_up() -> None:
    """서버를 켤 때 뒤에서 모델을 올려 둔다 (첫 말이 늦지 않게)."""
    if available():
        threading.Thread(target=_models.load, daemon=True, name="stt-load").start()


def status() -> dict:
    return {"available": available(), "model": MODEL_NAME, "device": _models.device, "loaded": _models.whisper is not None,
            "error": _models.error}


def speech_probs(audio: np.ndarray) -> np.ndarray:
    """칸(512)마다 말소리일 확률. audio 길이는 512 의 배수."""
    _models.load()
    return np.asarray(_models.vad(audio)).reshape(-1)


def transcribe(audio: np.ndarray) -> str:
    """16kHz float32 소리 → 한국어 글자."""
    _models.load()
    if _models.whisper is None:
        return ""
    with _models.lock:  # 모델 하나를 여러 연결이 같이 쓴다
        segments, _ = _models.whisper.transcribe(audio, language="ko", beam_size=1, vad_filter=False,
                                                 condition_on_previous_text=False, without_timestamps=True)
        return " ".join(s.text.strip() for s in segments).strip()


def pcm16_to_float(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


# ── 말 구간 자르기 (연결마다 하나) ──


class Segmenter:
    """소리를 조금씩 넣으면 말 한 덩이가 끝날 때마다 그 소리를 돌려준다.
    probs(audio) 와 시각 단위는 바꿔 넣을 수 있다 (시험에서는 가짜 확률을 쓴다)."""

    def __init__(self, probs: Callable[[np.ndarray], np.ndarray] = speech_probs):
        self.probs = probs
        self.pending = np.zeros(0, dtype=np.float32)  # 아직 VAD 를 안 돌린 소리 (512 미만)
        self.history = np.zeros(0, dtype=np.float32)  # VAD 맥락과 말 시작 앞부분 (최근 소리)
        self.speech: list[np.ndarray] = []
        self.speaking = False
        self.loud_run = 0
        self.quiet_run = 0

    def feed(self, audio: np.ndarray) -> list[dict]:
        """사건 목록: {"type": "speech_start"} / {"type": "speech_end", "audio": np.ndarray}."""
        events: list[dict] = []
        self.pending = np.concatenate([self.pending, audio.astype(np.float32)])
        whole = len(self.pending) // CHUNK * CHUNK
        if whole == 0:
            return events
        fresh, self.pending = self.pending[:whole], self.pending[whole:]
        context = self.history[-VAD_CONTEXT * CHUNK:]
        context = context[len(context) % CHUNK:]
        probs = self.probs(np.concatenate([context, fresh]))[-(whole // CHUNK):]
        for i, prob in enumerate(probs):
            chunk = fresh[i * CHUNK:(i + 1) * CHUNK]
            self.history = np.concatenate([self.history, chunk])[-(RATE * 2):]
            events.extend(self._step(float(prob), chunk))
        return events

    def _step(self, prob: float, chunk: np.ndarray) -> list[dict]:
        if not self.speaking:
            self.loud_run = self.loud_run + 1 if prob >= START_PROB else 0
            if self.loud_run >= START_CHUNKS:
                self.speaking, self.quiet_run = True, 0
                preroll = int(RATE * PREROLL_MS / 1000) + START_CHUNKS * CHUNK
                self.speech = [self.history[-preroll:].copy()]
                return [{"type": "speech_start"}]
            return []
        self.speech.append(chunk)
        self.quiet_run = self.quiet_run + 1 if prob < END_PROB else 0
        length = sum(len(c) for c in self.speech) / RATE
        if self.quiet_run * CHUNK * 1000 / RATE >= SILENCE_MS or length >= MAX_SPEECH_S:
            audio = np.concatenate(self.speech)
            self.speaking, self.speech, self.loud_run, self.quiet_run = False, [], 0, 0
            return [{"type": "speech_end", "audio": audio}]
        return []

    def reset(self) -> None:
        """도나가 말하는 동안(앱이 pause) 들어온 것은 버린다."""
        self.speaking, self.speech, self.loud_run, self.quiet_run = False, [], 0, 0
