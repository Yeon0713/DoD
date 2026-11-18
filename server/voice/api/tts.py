"""앱에서 지금 재생할 한 문장을 합성한다."""
import logging

import httpx
from fastapi import APIRouter, Query, Response

from voice import tts

router = APIRouter()
NO_STORE = {"Cache-Control": "no-store"}


@router.get("/tts")
def get_tts(text: str = Query(min_length=1, max_length=2000)):
    if not tts.available():
        return Response(status_code=204, headers=NO_STORE)
    phrase = tts.spoken(text.strip())
    if not phrase or len(phrase) > 2000:
        return Response(status_code=422, headers=NO_STORE)
    try:
        audio = tts.synthesize(phrase)
    except httpx.HTTPError as exc:
        logging.getLogger(__name__).warning("CLOVA Voice 요청 실패: %s", exc)
        return Response(status_code=503, headers=NO_STORE)
    return Response(audio, media_type="audio/wav", headers=NO_STORE)


@router.get("/tts/status")
def get_tts_status():
    return {"available": tts.available(), "model": tts.MODEL, **tts.OPTIONS}
