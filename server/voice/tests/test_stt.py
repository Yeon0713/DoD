"""받아 적기 (voice/stt.py, api/stt.py, 2026-11-18). 실제 Whisper·VAD 대신 가짜를 넣어 '말 구간 자르기'와 WebSocket 을 시험한다."""

import numpy as np
import pytest

from voice import stt
from voice.tests.conftest import Donna

CHUNK = stt.CHUNK


def loud(n_chunks: int) -> np.ndarray:
    return np.full(n_chunks * CHUNK, 0.5, dtype=np.float32)


def quiet(n_chunks: int) -> np.ndarray:
    return np.zeros(n_chunks * CHUNK, dtype=np.float32)


def fake_probs(audio: np.ndarray) -> np.ndarray:
    """칸마다: 소리가 크면 말(0.9), 조용하면 0.05."""
    return np.array([0.9 if np.abs(c).mean() > 0.1 else 0.05 for c in audio.reshape(-1, CHUNK)])


def silence_chunks() -> int:
    return int(np.ceil(stt.SILENCE_MS / 1000 * stt.RATE / CHUNK))


def test_speech_is_cut_after_silence():
    seg = stt.Segmenter(fake_probs)
    assert seg.feed(quiet(20)) == []  # 조용하면 아무 일도 없다
    started = seg.feed(loud(30))
    assert [e["type"] for e in started] == ["speech_start"]
    ended = seg.feed(quiet(silence_chunks() + 2))
    [end] = [e for e in ended if e["type"] == "speech_end"]
    seconds = len(end["audio"]) / stt.RATE
    assert 30 * CHUNK / stt.RATE < seconds < (30 + silence_chunks() + 2) * CHUNK / stt.RATE + stt.PREROLL_MS / 1000 + 0.2
    assert seg.feed(quiet(10)) == []  # 끝난 뒤 조용하면 다시 아무 일도 없다


def test_short_click_is_not_speech():
    seg = stt.Segmenter(fake_probs)
    assert seg.feed(np.concatenate([loud(stt.START_CHUNKS - 1), quiet(40)])) == []


def test_small_pieces_like_a_microphone():
    """앱은 0.1초(1600)씩 보낸다. 512 로 안 나눠떨어져도 남은 것을 다음 조각과 이어 본다."""
    seg = stt.Segmenter(fake_probs)
    audio = np.concatenate([quiet(10), loud(40), quiet(silence_chunks() + 5)])
    events = []
    for i in range(0, len(audio), 1600):
        events += seg.feed(audio[i:i + 1600])
    assert [e["type"] for e in events] == ["speech_start", "speech_end"]


def test_long_speech_is_cut_at_max():
    seg = stt.Segmenter(fake_probs)
    events = seg.feed(loud(int(stt.MAX_SPEECH_S * stt.RATE / CHUNK) + 20))
    assert [e["type"] for e in events][:2] == ["speech_start", "speech_end"]


@pytest.fixture
def fake_models(monkeypatch):
    monkeypatch.setattr(stt, "ENABLED", True)
    monkeypatch.setattr(stt._models, "load", lambda: None)
    monkeypatch.setattr(stt, "speech_probs", fake_probs)
    monkeypatch.setattr(stt.Segmenter.__init__, "__defaults__", (fake_probs,))
    heard = []

    def transcribe(audio):
        heard.append(len(audio))
        return "도나야 오늘 일정 브리핑해 줘"

    monkeypatch.setattr(stt, "transcribe", transcribe)
    return heard


def pcm(audio: np.ndarray) -> bytes:
    return (audio * 32767).astype(np.int16).tobytes()


def test_websocket_stream_sends_final_text(fake_models):
    donna = Donna()
    with donna.client.websocket_connect("/v1/stt/stream") as ws:
        assert ws.receive_json()["type"] == "ready"
        audio = np.concatenate([quiet(10), loud(40), quiet(silence_chunks() + 5)])
        for i in range(0, len(audio), 1600):
            ws.send_bytes(pcm(audio[i:i + 1600]))
        assert ws.receive_json() == {"type": "speech_start"}
        final = ws.receive_json()
        assert final["type"] == "final" and final["text"] == "도나야 오늘 일정 브리핑해 줘"


def test_websocket_pause_ignores_donna_speaking(fake_models):
    donna = Donna()
    with donna.client.websocket_connect("/v1/stt/stream") as ws:
        ws.receive_json()
        ws.send_text('{"type": "pause"}')
        ws.send_bytes(pcm(np.concatenate([loud(40), quiet(silence_chunks() + 5)])))  # 도나 목소리가 마이크로 들어옴
        ws.send_text('{"type": "resume"}')
        ws.send_bytes(pcm(np.concatenate([loud(40), quiet(silence_chunks() + 5)])))
        assert ws.receive_json() == {"type": "speech_start"}
        assert ws.receive_json()["type"] == "final"
    assert len(fake_models) == 1  # 멈춘 동안의 소리는 받아 적지 않았다


def test_status_and_off_switch():
    donna = Donna()
    assert donna.client.get("/v1/stt/status").json()["available"] is False  # conftest: 시험에서는 꺼 둔다
    with donna.client.websocket_connect("/v1/stt/stream") as ws:
        assert ws.receive_json()["type"] == "error"
