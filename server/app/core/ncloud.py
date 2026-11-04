"""네이버 클라우드 API 호출. 요청마다 Access Key / Secret Key 로 서명을 만들어 헤더에 붙인다."""

import base64
import hashlib
import hmac
import time

import httpx

from app.core.config import settings

BASE_URL = "https://ncloud.apigw.ntruss.com"


def _signed_headers(method: str, uri: str) -> dict[str, str]:
    timestamp = str(int(time.time() * 1000))
    message = f"{method} {uri}\n{timestamp}\n{settings.ncloud_access_key}"
    signature = base64.b64encode(
        hmac.new(settings.ncloud_secret_key.encode(), message.encode(), hashlib.sha256).digest()
    ).decode()
    return {
        "x-ncp-apigw-timestamp": timestamp,
        "x-ncp-iam-access-key": settings.ncloud_access_key,
        "x-ncp-apigw-signature-v2": signature,
    }


def request(method: str, uri: str, base_url: str = BASE_URL, json: dict | None = None) -> httpx.Response:
    """uri 는 쿼리까지 포함한 경로. 서명에는 주소(base_url)를 빼고 uri 만 들어간다."""
    return httpx.request(
        method, base_url + uri, headers=_signed_headers(method, uri), json=json, timeout=10
    )


def get(uri: str) -> httpx.Response:
    """예) get("/vserver/v2/getRegionList?responseFormatType=json")"""
    return request("GET", uri)
