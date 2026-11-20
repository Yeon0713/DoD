"""Instagram Graph API 호출 (graph.facebook.com, Content Publishing). Unified Login 토큰으로 확인했다.

게시는 두 단계다: 컨테이너를 만들고(POST /{ig-user-id}/media), 준비되면(status_code FINISHED) 게시한다(POST /{ig-user-id}/media_publish).
- 사진은 JPEG 만 받고, 인스타 서버가 공개 주소(image_url)에서 직접 내려받는다 (media.py 가 주소를 만든다).
- 캐러셀: 장마다 is_carousel_item 컨테이너 → media_type=CAROUSEL, children=id,id,... (최대 20장). 첫 장 비율로 나머지를 자른다.
- 스토리: media_type=STORIES. 캡션을 받지 않는다.
- API 로 올린 게시물은 24시간에 한도가 있다 (GET /{ig-user-id}/content_publishing_limit). 캐러셀은 1개로 센다.
- 오류 code 190 은 토큰이 만료되었거나 무효라는 뜻이다 (다시 연결해야 한다).

post / get / delete / sleep 은 테스트에서 가짜로 바꾼다 (voice/context.py 의 post 와 같은 방식).
"""

import logging
import time

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

HOST = "https://graph.facebook.com"
TIMEOUT = 20
READY_TRIES = 10  # 사진 컨테이너는 보통 바로 FINISHED 다. 아니면 READY_INTERVAL 초마다 다시 본다
READY_INTERVAL = 3
CONNECT_TRIES = 3  # 연결 자체가 안 될 때만 다시 시도한다. 요청이 가지 않았으니 두 번 올라갈 일이 없다
CONNECT_INTERVAL = 1

post = httpx.post
get = httpx.get
delete = httpx.delete
sleep = time.sleep


class InstagramError(Exception):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code

    @property
    def token_invalid(self) -> bool:
        return self.code == 190


def is_enabled() -> bool:
    """토큰과 IG 사용자 id 가 둘 다 있어야 켜진다."""
    return bool(settings.instagram_access_token and settings.instagram_user_id)


def _call(method: str, path: str, params: dict) -> dict:
    url = f"{HOST}/{settings.instagram_graph_version}/{path}"
    params = {**params, "access_token": settings.instagram_access_token}
    for attempt in range(1, CONNECT_TRIES + 1):
        try:
            if method == "POST":
                response = post(url, data=params, timeout=TIMEOUT)
            elif method == "DELETE":
                response = delete(url, params=params, timeout=TIMEOUT)
            else:
                response = get(url, params=params, timeout=TIMEOUT)
            break
        except (httpx.ConnectError, httpx.ConnectTimeout) as error:
            if attempt == CONNECT_TRIES:
                raise InstagramError(f"인스타 서버에 닿지 못했어요 ({type(error).__name__})") from error
            logger.info("Instagram %s %s 연결 실패 (%s), 다시 시도 %d/%d", method, path, type(error).__name__, attempt, CONNECT_TRIES - 1)
            sleep(CONNECT_INTERVAL)
        except httpx.HTTPError as error:  # 읽기 시간 초과 등: 요청이 갔을 수 있으니 다시 보내지 않는다
            raise InstagramError(f"인스타 서버에 닿지 못했어요 ({type(error).__name__})") from error
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code != 200 or "error" in body:
        error = body.get("error") or {}
        logger.warning("Instagram %s %s → %s %s", method, path, response.status_code, response.text[:300])
        raise InstagramError(error.get("message") or f"HTTP {response.status_code}", error.get("code"))
    return body


def _user() -> str:
    return settings.instagram_user_id


def account() -> dict:
    """연결한 계정: {id, username, profile_picture_url}."""
    return _call("GET", _user(), {"fields": "id,username,profile_picture_url"})


def image_container(image_url: str, caption: str | None = None, carousel_item: bool = False) -> str:
    params: dict = {"image_url": image_url}
    if carousel_item:
        params["is_carousel_item"] = "true"
    elif caption:
        params["caption"] = caption
    return _call("POST", f"{_user()}/media", params)["id"]


def carousel_container(children: list[str], caption: str) -> str:
    return _call("POST", f"{_user()}/media", {"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption})["id"]


def story_container(image_url: str) -> str:
    return _call("POST", f"{_user()}/media", {"media_type": "STORIES", "image_url": image_url})["id"]


def wait_ready(container_id: str) -> None:
    """컨테이너가 FINISHED 가 될 때까지 기다린다. ERROR, EXPIRED 이거나 끝내 안 되면 InstagramError."""
    for attempt in range(READY_TRIES):
        status = _call("GET", container_id, {"fields": "status_code"}).get("status_code")
        if status in ("FINISHED", "PUBLISHED"):
            return
        if status in ("ERROR", "EXPIRED"):
            raise InstagramError(f"인스타가 사진을 받지 못했어요 ({status})")
        if attempt < READY_TRIES - 1:
            sleep(READY_INTERVAL)
    raise InstagramError("인스타가 사진을 아직 준비하지 못했어요 (IN_PROGRESS)")


def publish(container_id: str) -> str:
    """게시하고 media id 를 돌려준다."""
    return _call("POST", f"{_user()}/media_publish", {"creation_id": container_id})["id"]


def delete_media(media_id: str) -> None:
    """올린 게시물을 지운다 (사후 취소, 인사과 5단계). Graph API 가 실제로 지우기를 받는지는 실제 계정으로 확인해야 한다
    (donna-voice/docs/agent-structure.md 7장, hr-impl-notes.md). 안 되면 InstagramError 가 나고 부르는 쪽이 알린다."""
    _call("DELETE", media_id, {})


def permalink(media_id: str) -> str | None:
    return _call("GET", media_id, {"fields": "permalink"}).get("permalink")


def publishing_limit() -> dict:
    """{quota_usage, config: {quota_total, quota_duration}} (최근 24시간)."""
    data = _call("GET", f"{_user()}/content_publishing_limit", {"fields": "quota_usage,config"}).get("data") or [{}]
    return data[0]
