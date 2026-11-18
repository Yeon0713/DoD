"""짧은 마이크 발화를 WAV로 감싸 네이버 CSR로 받아 적는다."""
import io
import wave
from collections import deque

import httpx

from app.core.config import settings

RATE = 16000
FRAME = 640  # mono PCM16, 20ms
MAX_PCM = RATE * 2 * 60


def available() -> bool:
    return bool(settings.voice_stt and settings.clova_voice_client_id and settings.clova_voice_client_secret)


async def transcribe(client: httpx.AsyncClient, pcm: bytes) -> str:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setparams((1, 2, RATE, 0, "NONE", ""))
        wav.writeframes(pcm)
    response = await client.post(
        "https://naveropenapi.apigw.ntruss.com/recog/v1/stt",
        params={"lang": "Kor"}, content=buf.getvalue(),
        headers={"Content-Type": "application/octet-stream",
                 "X-NCP-APIGW-API-KEY-ID": settings.clova_voice_client_id,
                 "X-NCP-APIGW-API-KEY": settings.clova_voice_client_secret},
    )
    response.raise_for_status()
    return (response.json()["text"] or "").strip()


class Utterances:
    def __init__(self):
        import webrtcvad

        self.vad = webrtcvad.Vad(2)
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
            if self.quiet >= 35 or len(self.frames) >= 750:  # 700ms 침묵 또는 15초
                yield "final", b"".join(self.frames)
                self.frames.clear()
