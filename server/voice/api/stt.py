"""받아 적기 API (voice/stt.py, 2026-11-18).

  WebSocket /v1/stt/stream   앱이 마이크 소리(16kHz, 16비트, 모노 PCM)를 조각으로 계속 보낸다.
                             글로 {"type": "pause"} / {"type": "resume"} 을 보내면 도나가 말하는 동안 듣지 않는다.
                             서버가 보내는 것: {"type": "ready"} / {"type": "speech_start"} / {"type": "final", "text"} / {"type": "error"}
  POST /v1/stt               소리 한 덩이(같은 PCM)를 받아 적는다 (시험·확인용). {"text"}
  GET  /v1/stt/status        {"available", "model", "device", "loaded", "error"}. 앱은 available 이 아니면 브라우저 음성 인식을 쓴다
"""

import json

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from voice import stt

router = APIRouter(prefix="/stt")


@router.get("/status")
def get_status():
    return stt.status()


@router.post("")
async def post_stt(request: Request):
    if not stt.available():
        return JSONResponse(status_code=503, content={"error": {"code": "stt_off", "message": "받아 적기가 꺼져 있어요."}})
    audio = stt.pcm16_to_float(await request.body())
    return {"text": await run_in_threadpool(stt.transcribe, audio)}


@router.websocket("/stream")
async def stream(socket: WebSocket):
    await socket.accept()
    if not stt.available():
        await socket.send_json({"type": "error", "message": "받아 적기가 꺼져 있어요."})
        await socket.close()
        return
    await run_in_threadpool(stt._models.load)
    await socket.send_json({"type": "ready", **stt.status()})
    segmenter = stt.Segmenter()
    paused = False
    try:
        while True:
            message = await socket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("text"):
                command = json.loads(message["text"]).get("type")
                if command in ("pause", "resume"):
                    paused = command == "pause"
                    segmenter.reset()
                continue
            data = message.get("bytes")
            if not data or paused:
                continue
            events = await run_in_threadpool(segmenter.feed, stt.pcm16_to_float(data))
            for event in events:
                if event["type"] == "speech_start":
                    await socket.send_json({"type": "speech_start"})
                else:
                    text = await run_in_threadpool(stt.transcribe, event["audio"])
                    await socket.send_json({"type": "final", "text": text, "seconds": round(len(event["audio"]) / stt.RATE, 2)})
    except WebSocketDisconnect:
        pass
