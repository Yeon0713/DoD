"""SENS 문자 보내기. 네이버 클라우드 Access Key / Secret Key 서명을 쓴다."""

import httpx

from app.core import ncloud
from app.core.config import settings

BASE_URL = "https://sens.apigw.ntruss.com"

SMS_MAX_BYTES = 80  # 단문. 한글 약 40자
LMS_MAX_BYTES = 2000  # 장문. 한글 약 1000자


def _byte_length(text: str) -> int:
    """문자 길이 계산 기준: 영문·숫자·공백은 1바이트, 한글 등 나머지는 2바이트."""
    return sum(1 if ord(ch) < 128 else 2 for ch in text)


def send_sms(to: str, content: str) -> httpx.Response:
    """to 는 숫자만. 예) "01012345678". 보내는 번호(SENS_SMS_FROM)는 콘솔에 등록된 번호여야 한다.

    80바이트를 넘으면 자동으로 LMS(장문)로 보낸다. LMS 는 요금이 더 비싸다.
    """
    length = _byte_length(content)
    if length > LMS_MAX_BYTES:
        raise ValueError(f"문자가 너무 깁니다: {length}바이트 (최대 {LMS_MAX_BYTES})")

    return ncloud.request(
        "POST",
        f"/sms/v2/services/{settings.sens_sms_service_id}/messages",
        base_url=BASE_URL,
        json={
            "type": "SMS" if length <= SMS_MAX_BYTES else "LMS",
            "from": settings.sens_sms_from,
            "content": content,
            "messages": [{"to": to}],
        },
    )
