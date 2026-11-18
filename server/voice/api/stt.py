import json

import httpx
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from app.core.config import settings
from voice import stt

router = APIRouter(prefix="/stt")


@router.get("/status")
def status():
    return {"enabled": settings.voice_stt, "available": stt.available(), "model": stt.engine(),
            "boostings": stt.boostings() if stt.engine() == "clova-speech" else []}


@router.post("")
async def recognize(request: Request):
    if not stt.available():
        raise HTTPException(503, "CSR 사용 설정과 인증 정보를 확인해 주세요.")
    pcm = bytearray()
    async for chunk in request.stream():
        if len(pcm) + len(chunk) > stt.MAX_PCM:
            raise HTTPException(413, "최대 60초까지 인식할 수 있어요.")
        pcm.extend(chunk)
    if len(pcm) <= stt.RATE * 2 * 0.4 or len(pcm) % 2:
        raise HTTPException(422, "16kHz 모노 PCM16 음성이 필요해요 (400ms 초과).")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            return {"text": await stt.transcribe(client, pcm)}
    except (httpx.HTTPError, ValueError, KeyError) as error:
        raise HTTPException(502, "CSR에서 음성을 인식하지 못했어요.") from error


@router.websocket("/stream")
async def stream(ws: WebSocket):
    await ws.accept()
    if not stt.available():
        await ws.close(code=1008)
        return
    segments = stt.Utterances()
    generation = 0
    paused = False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await ws.send_json({"type": "ready"})
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    return
                if msg.get("text"):
                    cmd = json.loads(msg["text"])
                    if cmd["type"] in ("pause", "resume"):
                        paused = cmd["type"] == "pause"
                        generation = cmd.get("generation", 0)
                        segments = stt.Utterances()
                    continue
                pcm = msg.get("bytes")
                if not pcm or paused:
                    continue
                if len(pcm) > stt.RATE * 2 or len(pcm) % 2:
                    await ws.close(code=1009)
                    return
                for event, audio in segments.feed(pcm):
                    result = {"type": event, "generation": generation}
                    if audio is not None:
                        result["text"] = await stt.transcribe(client, audio)
                    await ws.send_json(result)
    except WebSocketDisconnect:
        pass
    except (httpx.HTTPError, ValueError, KeyError):
        await ws.close(code=1011)
