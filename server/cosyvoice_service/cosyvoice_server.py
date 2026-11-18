"""도나 목소리 서비스 (CosyVoice 2). 음성 서버(server/voice/tts.py)가 글을 보내면 wav 를 돌려준다.

왜 따로 도나: CosyVoice 2 는 PyTorch·Python 3.10 과 정해진 라이브러리 버전이 필요해서 서버 가상환경(server/.venv)과 섞으면
다른 기능이 깨질 수 있다. 그래서 conda 환경 donna-cosyvoice 에서 이 작은 서비스로만 돈다 (setup_cosyvoice.sh).

켜기 (server/cosyvoice_service 에서):
    conda run -n donna-cosyvoice --no-capture-output python cosyvoice_server.py
주소: http://127.0.0.1:8110  (COSYVOICE_PORT 로 바꿀 수 있다. 이 컴퓨터 안에서만 받는다)

목소리: CosyVoice 2 는 정해진 목소리가 없고, 짧은 본보기 녹음을 듣고 그 목소리로 읽는다 (zero-shot).
본보기는 prompt/donna_prompt.wav 와 그 글 prompt/donna_prompt.txt 다 (make_prompt.py 가 Qwen3-TTS 의 Sohee 목소리로 만든다.
그래서 모델을 바꿔도 도나 목소리 결이 이어진다). 켤 때 한 번 읽어 'donna' 목소리로 기억해 둔다.

  GET  /health   {"ready", "sample_rate", "speaker", "device", "error"}
  POST /tts      {"text": "오늘 일정이에요.", "speed": 1.0} → audio/wav (16비트, 모노)
한 번에 한 문장씩 만든다 (모델이 하나라서). 음성 서버는 이미 문장마다 차례를 지어 보낸다.
"""

import io
import logging
import os
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np
import uvicorn
from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse, Response

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor" / "CosyVoice"
sys.path[:0] = [str(VENDOR), str(VENDOR / "third_party" / "Matcha-TTS")]

MODEL_DIR = Path(os.environ.get("COSYVOICE_MODEL_DIR", HERE / "pretrained_models" / "CosyVoice2-0.5B"))
PROMPT_WAV = Path(os.environ.get("COSYVOICE_PROMPT_WAV", HERE / "prompt" / "donna_prompt.wav"))
PROMPT_TEXT = Path(os.environ.get("COSYVOICE_PROMPT_TEXT", HERE / "prompt" / "donna_prompt.txt"))
PORT = int(os.environ.get("COSYVOICE_PORT", "8110"))
SPEAKER = "donna"

logger = logging.getLogger("cosyvoice_server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class Voice:
    def __init__(self):
        self.model = None
        self.error: str | None = None
        self.lock = threading.Lock()

    def load(self) -> None:
        try:
            from cosyvoice.cli.cosyvoice import AutoModel

            started = time.perf_counter()
            self.model = AutoModel(model_dir=str(MODEL_DIR))
            prompt_text = PROMPT_TEXT.read_text(encoding="utf-8").strip()
            if not self.model.add_zero_shot_spk(prompt_text, str(PROMPT_WAV), SPEAKER):
                raise RuntimeError("본보기 목소리를 기억하지 못했어요")
            logger.info("CosyVoice 2 준비 끝 (%.1f초)", time.perf_counter() - started)
        except Exception as error:  # 음성 서버는 이때 기기 목소리로 읽는다
            logger.exception("CosyVoice 2 를 올리지 못했어요")
            self.error = str(error)

    def wav(self, text: str, speed: float) -> bytes:
        with self.lock:
            parts = [np.asarray(out["tts_speech"]).reshape(-1)
                     for out in self.model.inference_zero_shot(text, "", "", zero_shot_spk_id=SPEAKER, stream=False, speed=speed)]
        audio = np.concatenate(parts) if parts else np.zeros(1, dtype=np.float32)
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(self.model.sample_rate)
            out.writeframes(pcm.tobytes())
        return buffer.getvalue()


voice = Voice()
app = FastAPI(title="donna-cosyvoice")


@app.on_event("startup")
def startup() -> None:
    threading.Thread(target=voice.load, daemon=True, name="cosyvoice-load").start()


@app.get("/health")
def health():
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    return {"ready": voice.model is not None and voice.error is None, "sample_rate": getattr(voice.model, "sample_rate", None),
            "speaker": SPEAKER, "device": device, "error": voice.error}


@app.post("/tts")
def tts(body: dict = Body(...)):
    text = str(body.get("text") or "").strip()
    if not text:
        return JSONResponse(status_code=400, content={"error": "text 가 비었어요"})
    if voice.model is None or voice.error:
        return JSONResponse(status_code=503, content={"error": voice.error or "아직 모델을 올리고 있어요"})
    started = time.perf_counter()
    data = voice.wav(text, float(body.get("speed") or 1.0))
    logger.info("%.1f초 걸림: %s", time.perf_counter() - started, text[:30])
    return Response(content=data, media_type="audio/wav")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT)
