"""NAVER API HUB 호출 (네이버 지역·블로그·뉴스 검색, 검색어 트렌드, 쇼핑 인사이트). Client ID / Secret 을 헤더에 붙인다."""

import httpx

from app.core.config import settings


def _headers() -> dict[str, str]:
    return {
        "X-NCP-APIGW-API-KEY-ID": settings.naver_api_hub_client_id,
        "X-NCP-APIGW-API-KEY": settings.naver_api_hub_client_secret,
    }


def get(path: str, params: dict | None = None) -> httpx.Response:
    """검색 API. path 예) /search/v1/local"""
    return httpx.get(
        settings.naver_api_hub_base_url + path, params=params, headers=_headers(), timeout=10
    )


def post(path: str, json: dict) -> httpx.Response:
    """검색어 트렌드, 쇼핑 인사이트 API."""
    return httpx.post(
        settings.naver_api_hub_base_url + path, json=json, headers=_headers(), timeout=10
    )
