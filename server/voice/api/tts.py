"""GET /v1/tts: 도나 목소리 (voice/tts.py). 만들어 둔 문장이면 wav, 아니면 204 (앱은 그 문장만 기기 목소리로 읽는다)."""

from fastapi import APIRouter, Response
from fastapi.responses import FileResponse

from voice import tts

router = APIRouter()


@router.get("/tts")
def get_tts(text: str):
    path = tts.cached(text)
    if path:
        return FileResponse(path, media_type="audio/wav", headers={"Cache-Control": "public, max-age=31536000, immutable"})
    tts.request(text)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/tts/status")
def get_tts_status():
    return tts.status()
