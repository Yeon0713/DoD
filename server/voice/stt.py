"""짧은 마이크 발화를 WAV로 감싸 네이버로 받아 적는다.

CLOVA_SPEECH_SECRET_KEY 가 있으면 CLOVA Speech 단문 인식 + 키워드 부스팅(VOICE_STT_BOOSTINGS, 기본 "도나야"),
없으면 CSR(CLOVA Speech Recognition). 보내는 방식(60초 이내 wav, lang=Kor)은 같다.
CSR 은 호출어 "도나야"를 "누나야"·"도나헤어"·"돈호야"로 적어 앱이 부르지 않은 말로 버렸다 (2026-11-19, 내 목소리 8개 중 1개).
CLOVA Speech + "도나야" 부스팅은 8개 모두, 네이버 목소리 18문장 모두 "도나야"로 적었고 진짜 "누나야"는 그대로 뒀다.
https://api.ncloud-docs.com/docs/ai-application-service-clovaspeech-shortsentence
"""
import io
import wave
from collections import deque

import httpx

from app.core.config import settings

RATE = 16000
FRAME = 640  # mono PCM16, 20ms
QUIET_FRAMES = 35  # 700ms 조용하면 말이 끝난 것으로 본다
MAX_FRAMES = 150  # 3초 (2026-11-22, 6초에서 줄임). 조용한 틈이 없어도 3초에 끊어 받아 적는다
MAX_PCM = RATE * 2 * 60
CSR_URL = "https://naveropenapi.apigw.ntruss.com/recog/v1/stt"
SPEECH_URL = "https://clovaspeech-gw.ncloud.com/recog/v1/stt"


def engine() -> str:
    """받아 적는 상품: clova-speech (부스팅) 또는 naver-csr."""
    return "clova-speech" if settings.clova_speech_secret_key else "naver-csr"


def boostings() -> list[str]:
    """부스팅 단어. CLOVA Speech 는 3글자보다 짧은 단어를 무시한다."""
    return [w.strip() for w in settings.voice_stt_boostings.split(",") if len(w.strip()) >= 3]


def available() -> bool:
    keys = settings.clova_speech_secret_key or (settings.clova_voice_client_id and settings.clova_voice_client_secret)
    return bool(settings.voice_stt and keys)


async def transcribe(client: httpx.AsyncClient, pcm: bytes) -> str:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setparams((1, 2, RATE, 0, "NONE", ""))
        wav.writeframes(pcm)
    if engine() == "clova-speech":
        url, params = SPEECH_URL, {"lang": "Kor"}
        if boostings():
            params["boostings"] = "\t".join(boostings())  # 단어 사이는 탭
        headers = {"X-CLOVASPEECH-API-KEY": settings.clova_speech_secret_key}
    else:
        url, params = CSR_URL, {"lang": "Kor"}
        headers = {"X-NCP-APIGW-API-KEY-ID": settings.clova_voice_client_id,
                   "X-NCP-APIGW-API-KEY": settings.clova_voice_client_secret}
    response = await client.post(
        url, params=params, content=buf.getvalue(),
        headers={"Content-Type": "application/octet-stream", **headers},
    )
    response.raise_for_status()
    return (response.json()["text"] or "").strip()


class Utterances:
    def __init__(self):
        import webrtcvad

        self.vad = webrtcvad.Vad(3)  # 가장 엄격하게: 멀리서 들리는 말소리·웃음을 말로 덜 본다 (2026-11-22, 가게 소리에 끝맺음이 늦던 것)
        self.pending = b""
        self.lead = deque(maxlen=15)  # 첫 음절 앞 300ms
        self.frames = []
        self.quiet = 0

    def feed(self, pcm: bytes):
        data = self.pending + pcm
        whole = len(data) - len(data) % FRAME
        self.pending = data[whole:]
        for offset in range(0, whole, FRAME):
            frame = data[offset:offset + FRAME]
            speech = self.vad.is_speech(frame, RATE)
            if not self.frames:
                self.lead.append(frame)
                if not speech:
                    continue
                self.frames.extend(self.lead)
                self.lead.clear()
                yield "speech_start", None
            else:
                self.frames.append(frame)
            self.quiet = 0 if speech else self.quiet + 1
            if self.quiet >= QUIET_FRAMES or len(self.frames) >= MAX_FRAMES:  # 700ms 침묵 또는 3초
                yield "final", b"".join(self.frames)
                self.frames.clear()
