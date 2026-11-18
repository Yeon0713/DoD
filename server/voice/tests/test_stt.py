import io
import wave

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from voice import stt
from voice.api.stt import router


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    monkeypatch.setattr(settings, "voice_stt", True)
    monkeypatch.setattr(settings, "clova_voice_client_id", "test-id")
    monkeypatch.setattr(settings, "clova_voice_client_secret", "test-secret")
    return TestClient(app)


def test_disabled_csr_cannot_send_audio(client, monkeypatch):
    monkeypatch.setattr(settings, "voice_stt", False)
    assert client.get("/v1/stt/status").json()["available"] is False
    assert client.post("/v1/stt", content=bytes(16000)).status_code == 503
    with client.websocket_connect("/v1/stt/stream") as ws, pytest.raises(WebSocketDisconnect):
        ws.receive_json()


def test_rest_sends_korean_wav(client, monkeypatch):
    pcm = bytes(16000)

    async def post(self, url, *, headers, params, content):
        assert url == "https://naveropenapi.apigw.ntruss.com/recog/v1/stt"
        assert params == {"lang": "Kor"}
        assert headers["X-NCP-APIGW-API-KEY-ID"] == "test-id"
        assert headers["X-NCP-APIGW-API-KEY"] == "test-secret"
        with wave.open(io.BytesIO(content)) as wav:
            assert (wav.getframerate(), wav.getsampwidth(), wav.getnchannels()) == (16000, 2, 1)
            assert wav.readframes(wav.getnframes()) == pcm
        return httpx.Response(200, json={"text": "도나야"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    assert client.post("/v1/stt", content=pcm).json() == {"text": "도나야"}
    assert client.post("/v1/stt", content=b"short").status_code == 422


def test_only_finished_unpaused_utterance_is_sent(client, monkeypatch):
    import webrtcvad

    sent = []
    async def transcribe(_, audio):
        sent.append(audio)
        return "도나야 오늘 일정 알려줘"

    monkeypatch.setattr(webrtcvad.Vad, "is_speech", lambda self, frame, rate: any(frame))
    monkeypatch.setattr(stt, "transcribe", transcribe)
    speech = bytes([1, 0]) * (stt.FRAME * 5)
    silence = bytes(stt.FRAME * 35)
    with client.websocket_connect("/v1/stt/stream") as ws:
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(speech)
        assert ws.receive_json()["type"] == "speech_start"
        ws.send_json({"type": "pause", "generation": 1})
        ws.send_bytes(speech + silence)
        ws.send_json({"type": "resume", "generation": 1})
        ws.send_bytes(speech + silence)
        assert ws.receive_json()["type"] == "speech_start"
        assert ws.receive_json() == {"type": "final", "text": "도나야 오늘 일정 알려줘", "generation": 1}
    assert sent == [speech + silence]
