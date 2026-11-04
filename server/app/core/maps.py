"""Maps 호출 (주소 → 좌표, 좌표 → 주소, 길찾기 등). Client ID / Secret 을 헤더에 붙인다."""

import httpx

from app.core.config import settings


def get(path: str, params: dict | None = None) -> httpx.Response:
    """path 예) /map-geocode/v2/geocode"""
    return httpx.get(
        settings.naver_maps_base_url + path,
        params=params,
        headers={
            "x-ncp-apigw-api-key-id": settings.naver_maps_client_id,
            "x-ncp-apigw-api-key": settings.naver_maps_client_secret,
        },
        timeout=10,
    )
