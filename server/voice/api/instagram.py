"""인스타 연결과 게시 (POST /v1/instagram/connect, GET /v1/instagram, POST·GET /v1/instagram/posts).

실제 OAuth 전이라 연결은 .env 의 토큰을 확인하는 것이다. 앱의 허용 화면(instagram.tsx)이 connect 를 {} 로 부른다.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from voice import clock, config, repo
from voice.api.errors import store_not_found
from voice.api.schemas import InstagramConnectIn, InstagramPostIn
from voice.context import load
from voice.instagram import graph, posts
from voice.instagram.graph import InstagramError
from voice.jobs import briefing

router = APIRouter(prefix="/instagram")


def demo_store_id() -> str | None:
    if not config.DEMO_FIXTURE:
        return None
    from voice.api.dev import fixture

    return fixture(config.DEMO_FIXTURE)["store"]["id"]


@router.post("/connect")
def post_connect(body: InstagramConnectIn | None = None):
    store_id = (body.store_id if body else None) or demo_store_id()
    if not store_id or repo.store(store_id) is None:
        return store_not_found()
    try:
        connected = posts.connect(store_id)
    except InstagramError as error:
        return {"connected": False, "error": str(error), "say": "인스타에 연결하지 못했어요. 잠시 뒤에 다시 해 주세요."}
    briefing.refresh_instagram(store_id)  # 오늘 브리핑에 '인스타에 올릴까요' 단계를 넣는다
    return {"connected": True, "handle": connected["handle"], "say": "인스타를 연결했어요. 많이 나간 메뉴는 브리핑 때 여쭤보고 올릴게요."}


@router.get("")
def get_instagram(store_id: str):
    if repo.store(store_id) is None:
        return store_not_found()
    connection = posts.connection(store_id)
    limit = None
    if connection["connected"] and graph.is_enabled():
        try:
            limit = graph.publishing_limit()
        except InstagramError:
            limit = None
    return {"connection": connection, "limit": limit, "posts": posts.recent(store_id)}


@router.post("/posts")
def post_posts(body: InstagramPostIn):
    view = load(body.store_id)
    if view is None:
        return store_not_found()
    if not posts.connection(body.store_id)["connected"]:
        return JSONResponse(status_code=409, content={"error": "instagram_not_connected", "message": "인스타가 연결되어 있지 않아요"})
    built = posts.build_feed(view) if body.kind == "feed" else posts.build_story(view)
    if built is None:
        return JSONResponse(status_code=422, content={"error": "no_menu_photos", "message": "올릴 메뉴 사진이 모자라요"})
    at = clock.parse(body.post_at) if body.post_at else None
    return posts.queue_publish(body.store_id, posts.create(body.store_id, built), at)


@router.get("/posts/{post_id}")
def get_post(post_id: str):
    post = posts.get(post_id)
    if post is None:
        return JSONResponse(status_code=404, content={"error": "post_not_found"})
    return post
