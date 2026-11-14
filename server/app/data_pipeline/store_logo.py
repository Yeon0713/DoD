"""가게 로고 (포스터 모서리에 넣는다). 바탕을 지우고 여백을 자른 PNG 로 둔다 (app/core/logo_image.py).

어디서 오나 (앞선 것을 쓴다)
1. 사장님이 앱에서 올린 로고: db/app_data/logos/<가게>.png
2. 네이버 소식 사진 중 로고처럼 생긴 사진(PlaceInfo.logo): 처음 쓸 때 받아 바탕을 지워 db/app_data/logos/<가게>.naver-<주소 지문>.png 로 둔다
   네이버 로고 주소가 바뀌면 새로 받는다.
db/app_data 는 git 에 올라가지 않는다. 사장님이 올린 로고를 지우면 네이버에서 찾은 로고로 돌아간다.
"""

import base64
import binascii
import hashlib
import re
from pathlib import Path

LOGO_DIR = Path(__file__).resolve().parents[2] / "db" / "app_data" / "logos"
MAX_BYTES = 5 * 1024 * 1024  # 5MB (받은 뒤 바탕을 지우고 줄여서 저장한다)
TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
OLD_EXTS = ("png", "jpg", "webp")  # 예전에 원본 그대로 저장한 로고
DATA_URL = re.compile(r"^data:(image/[a-z]+);base64,(.+)$", re.S)


class LogoError(ValueError):
    pass


def _owner_path(store_id: str) -> Path | None:
    for ext in OLD_EXTS:
        path = LOGO_DIR / f"{store_id}.{ext}"
        if path.exists():
            return path
    return None


def _naver_path(store_id: str, url: str) -> Path:
    return LOGO_DIR / f"{store_id}.naver-{hashlib.sha1(url.encode()).hexdigest()[:10]}.png"


def _naver_files(store_id: str) -> list[Path]:
    return sorted(LOGO_DIR.glob(f"{store_id}.naver-*.png")) if LOGO_DIR.exists() else []


def path_of(store_id: str) -> Path | None:
    """지금 쓸 로고 파일 (올린 로고 → 네이버에서 받아 둔 로고)"""
    return _owner_path(store_id) or next(iter(_naver_files(store_id)), None)


def source_of(store_id: str) -> str | None:
    if _owner_path(store_id):
        return "OWNER"
    return "NAVER" if _naver_files(store_id) else None


def _cut(raw: bytes) -> bytes:
    from app.core import logo_image

    try:
        return logo_image.cut_out(raw)
    except logo_image.LogoImageError:
        raise LogoError("사진을 읽지 못했어요") from None


def save(store_id: str, data_url: str) -> Path:
    """data:image/png;base64,... 로 받은 로고의 바탕을 지워 저장한다 (앞서 올린 로고는 지운다)."""
    match = DATA_URL.match(data_url.strip())
    if not match or match.group(1) not in TYPES:
        raise LogoError("PNG, JPG, WEBP 사진만 올릴 수 있어요")
    try:
        raw = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError):
        raise LogoError("사진을 읽지 못했어요") from None
    if len(raw) > MAX_BYTES:
        raise LogoError("5MB 보다 작은 사진으로 올려 주세요")
    png = _cut(raw)
    remove(store_id)
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    path = LOGO_DIR / f"{store_id}.png"
    path.write_bytes(png)
    return path


def keep_naver(store_id: str, url: str | None) -> Path | None:
    """네이버에서 찾은 로고를 받아 바탕을 지워 둔다 (이미 받아 두었으면 그대로). 받지 못하면 None"""
    if not url:
        return None
    path = _naver_path(store_id, url)
    if path.exists():
        return path
    from app.core.naver_place import _image

    raw = _image(url)
    if not raw:
        return None
    try:
        png = _cut(raw)
    except LogoError:
        return None
    for old in _naver_files(store_id):
        old.unlink()
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    return path


def remove(store_id: str) -> bool:
    """사장님이 올린 로고를 지운다 (네이버에서 찾은 로고는 남는다)"""
    path = _owner_path(store_id)
    if path is None:
        return False
    path.unlink()
    return True


def url_of(store_id: str, naver_url: str | None = None) -> str | None:
    """앱이 그릴 로고 주소 (파일이 바뀌면 주소도 바뀌어 새로 받는다). 네이버 로고 주소를 주면 처음 한 번 받아 둔다. 없으면 None"""
    if not _owner_path(store_id):
        keep_naver(store_id, naver_url)
    path = path_of(store_id)
    return f"/api/stores/{store_id}/logo?v={path.stat().st_mtime_ns}" if path else None
