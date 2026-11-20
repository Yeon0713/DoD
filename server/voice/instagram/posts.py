"""인스타 게시물: 초안 만들기, 게시 작업 걸기, 실제로 올리기, 연결 상태.

게시물은 repo 의 instagram_post 로 둔다.
  {id, store_id, kind: feed | story, slides: [{src, top_label, title}], caption, quote,
   status: draft → queued → publishing → published | failed, post_at, created_at, published_at, media_id, permalink, error}
연결 상태는 가게 설정(repo.settings)의 instagram 칸에 둔다: {connected, handle, profile_picture_url, ig_user_id, connected_at}
실제 OAuth 전이라 연결은 .env 의 토큰을 확인하는 것이다 (graph.is_enabled).

/v1/turn 은 5초 안에 답해야 해서 게시는 작업 큐(instagram_publish)로 돌린다. 지금 올릴 것은 kick 으로 큐를 바로 한 번 돌린다.
"""

import datetime as dt
import logging
import re
import threading

from voice import activity, clock, hours, notices, repo
from voice.clock import iso, parse
from voice.context import VoiceStore
from voice.instagram import graph, media
from voice.instagram.graph import InstagramError
from voice.jobs import queue

logger = logging.getLogger(__name__)

FEED_SLIDES = 3 # 많이 나간 메뉴 몇 개를 올리나 (그 뒤에 가게 소개 한 장)
LIVE = ("queued", "publishing", "published")


def kick() -> None:
    """지금 올릴 게시 작업을 30초 tick 을 기다리지 않고 바로 돌린다 (뒤에서). 테스트에서는 끈다."""
    threading.Thread(target=queue.run_due, kwargs={"lane": "slow"}, daemon=True, name="instagram-publish").start()


# ── 연결 ──


def connection(store_id: str) -> dict:
    return {"connected": False, **(repo.settings(store_id).get("instagram") or {})}


def save_connection(store_id: str, data: dict) -> dict:
    repo.save_settings(store_id, {**repo.settings(store_id), "instagram": data})
    return data


def connect(store_id: str) -> dict:
    """.env 의 토큰으로 계정을 확인하고 연결 상태를 저장한다. 토큰이 없거나 틀리면 InstagramError."""
    if not graph.is_enabled():
        raise InstagramError("INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_USER_ID 가 비어 있어요")
    account = graph.account()
    return save_connection(store_id, {"connected": True, "handle": account.get("username"), "ig_user_id": account.get("id"),
                                      "profile_picture_url": account.get("profile_picture_url"), "connected_at": iso(clock.now())})


def disconnect(store_id: str, reason: str) -> None:
    save_connection(store_id, {**connection(store_id), "connected": False, "disconnected_reason": reason})


# ── 초안 ──


def top_menus(view: VoiceStore, n: int = FEED_SLIDES) -> dict:
    """많이 나간 메뉴 (사진이 있는 것만): {period, items: [{id, rank, name, count_label, photo_url}]}.
    포스 매출의 이번 달 순위(top_menus_month)가 있으면 그것을, 없으면 어제 순위를 쓴다.
    이번 달 순위의 단위는 매출 탭(api/tabs.py)과 같이 '그릇'이다."""
    sales = (view.data.get("sales") or [{}])[0]
    month = sales.get("top_menus_month")
    if month:
        period, unit, ranked = "이번 달", "그릇", month
    else:
        period, unit, ranked = "어제", "개", sales.get("top_menus_yesterday") or []
    by_id = {m["id"]: m for m in view.menus}
    items = []
    for item in ranked:
        menu = by_id.get(item["id"])
        if menu and menu.get("photo_url"):
            items.append({"id": menu["id"], "rank": len(items) + 1, "name": menu["name"],
                          "count_label": f"{item['count']:,}{unit}", "photo_url": menu["photo_url"]})
    return {"period": period, "items": items[:n]}


def quote(view: VoiceStore) -> str | None:
    """글에 넣을 손님 한마디: 가장 최근 별 다섯 개 좋은 리뷰의 첫 문장 (짧은 것)."""
    reviews = sorted((r for r in view.reviews() if r.get("sentiment") == "positive" and r.get("rating", 0) >= 5),
                     key=lambda r: r["written_at"], reverse=True)
    for review in reviews:
        first = re.split(r"(?<=[.!?])\s+", review["text"].strip())[0].rstrip(".!~ ")
        if 4 <= len(first) <= 20:
            return first
    return None


def hashtag(name: str) -> str:
    """가게 이름 해시태그. 인스타 해시태그는 띄어쓰기와 문장 부호에서 끊기므로 글자·숫자·_ 만 남긴다 ('새뱅이 국수' → '#새뱅이국수')."""
    return "#" + re.sub(r"[^\w]", "", name)


def _chosen(view: VoiceStore, plan: dict | None) -> dict:
    """올릴 메뉴 3개: 마케팅 소재 사원이 고른 메뉴를 먼저, 모자라면 많이 나간 순서로 채운다 (voice/marketing.py)."""
    top = top_menus(view, len(view.menus) or FEED_SLIDES)
    if not plan or not plan.get("menu_ids"):
        return {**top, "items": top["items"][:FEED_SLIDES]}
    ranked = {m["id"]: m for m in top["items"]}
    by_id = {m["id"]: m for m in view.menus if m.get("photo_url")}
    items = [ranked.get(i) or {"id": i, "rank": None, "name": by_id[i]["name"], "count_label": None, "photo_url": by_id[i]["photo_url"]}
             for i in plan["menu_ids"] if i in by_id]
    items += [m for m in top["items"] if m["id"] not in plan["menu_ids"]]
    return {**top, "items": items[:FEED_SLIDES], "angle": plan.get("angle")}


def store_lines(view: VoiceStore) -> list[str]:
    """글 끝 가게 정보 (코드가 붙인다. LLM 이 쓰지 않는다): 내일 쉬는 날, 가게 이름·주소, 영업시간, 가게 해시태그."""
    store = view.store
    tomorrow = view.now.date() + dt.timedelta(days=1)
    lines = [f"내일({tomorrow.month}월 {tomorrow.day}일)은 쉬어요."] if hours.on(store, tomorrow) is None else []
    lines.append(" · ".join(x for x in (store["name"], store.get("address")) if x))
    open_days = [d for d in hours.week(store) if d]
    if open_days and len({(d["open"], d["close"]) for d in open_days}) == 1:
        lines.append(f"영업시간 {hours.summary(hours.week(store))}")
    return lines + [hashtag(store["name"])]


def build_feed(view: VoiceStore) -> dict | None:
    """메뉴 3장 + 가게 소개 1장 캐러셀. 메뉴 사진이 3개보다 적으면 None.
    마케팅 계획(소재·글, voice/marketing.py)이 있으면 그 메뉴와 글을, 없으면 많이 나간 메뉴와 템플릿 글을 쓴다."""
    from voice import marketing

    plan = marketing.today(view)
    top = _chosen(view, plan)
    if len(top["items"]) < FEED_SLIDES:
        return None
    store = view.store
    slides = [{"src": m["photo_url"], "top_label": f"{top['period']} {m['rank']}등" if m["rank"] else "오늘 추천", "title": m["name"]}
              for m in top["items"]]
    if store.get("logo_url"):  # 가게 소개 장: 가게 사진이 없어서 지금은 로고를 쓴다
        slides.append({"src": store["logo_url"], "top_label": store.get("address") or store["name"], "title": store["name"], "store": True})
    said = quote(view)
    if plan and plan.get("body"):
        lines = [plan["body"], " ".join(plan.get("hashtags") or [])]
    else:
        lines = [f"{top['period']} 가장 많이 나간 메뉴예요."] + [f"{m['rank']}등 {m['name']}" for m in top["items"]]
        if said:
            lines += ["", f"손님 한마디 “{said}”"]
    lines += ["", *store_lines(view)]
    return {"kind": "feed", "slides": slides, "caption": "\n".join(line for line in lines if line is not None), "quote": said,
            "menus": top}


def build_story(view: VoiceStore) -> dict | None:
    """1등 메뉴 한 장 스토리. 캡션은 없다 (스토리는 캡션을 받지 않는다)."""
    top = top_menus(view, 1)
    if not top["items"]:
        return None
    first = top["items"][0]
    return {"kind": "story", "slides": [{"src": first["photo_url"], "top_label": f"{top['period']} 1등", "title": first["name"]}],
            "caption": None, "quote": None, "menus": top}


def preview_card(built: dict, slide: int, store: dict, handle: str | None) -> dict:
    """앱의 insta_post 카드 (D-15). 가게 소개 장은 사진 없이 가게 이름만 보인다 (목업과 같은 모양)."""
    slide = max(1, min(slide, len(built["slides"])))
    item = built["slides"][slide - 1]
    first_line = (built["caption"] or "").split("\n")[0]
    return {"type": "insta_post", "id": "insta_post", "handle": handle or "", "logo_url": store.get("logo_url"), "slide": slide,
            "slides": len(built["slides"]), "photo_url": None if item.get("store") else item["src"],
            "top_label": item["top_label"], "title": item["title"], "caption": f"{first_line}… 더 보기" if first_line else ""}


# ── 게시 ──


def create(store_id: str, built: dict) -> dict:
    post_id = f"ig_{store_id}_{repo.next_number(f'instagram_post:{store_id}'):04d}"  # repo 키와 사진 폴더는 가게를 가리지 않으므로 가게 id 를 넣는다
    data = {"id": post_id, "store_id": store_id, "kind": built["kind"], "slides": built["slides"], "caption": built["caption"],
            "quote": built.get("quote"), "status": "draft", "post_at": None, "created_at": iso(clock.now()),
            "published_at": None, "media_id": None, "permalink": None, "error": None}
    return repo.put("instagram_post", post_id, store_id, data)


def get(post_id: str) -> dict | None:
    return repo.get("instagram_post", post_id)


def save(post: dict) -> dict:
    return repo.put("instagram_post", post["id"], post["store_id"], post)


def recent(store_id: str, n: int = 10) -> list[dict]:
    return sorted(repo.all_of("instagram_post", store_id), key=lambda p: p["created_at"], reverse=True)[:n]


def posted_on(store_id: str, kind: str, day: dt.date) -> list[dict]:
    """그날 올렸거나 올리는 중인 게시물."""
    return [p for p in repo.all_of("instagram_post", store_id)
            if p["kind"] == kind and p["status"] in LIVE and parse(p["created_at"]).date() == day]


def queue_publish(store_id: str, post: dict, at: dt.datetime | None = None) -> dict:
    """게시 작업을 건다. at 이 없으면 지금 (kick 으로 바로 돈다)."""
    due = at or clock.now()
    post = save({**post, "status": "queued", "post_at": iso(due)})
    queue.add(store_id, "instagram_publish", due, {"post_id": post["id"]})
    if due <= clock.now():
        kick()
    return post


def _upload(post: dict) -> str:
    """사진을 공개 주소에 두고 컨테이너를 만든다. 게시할 컨테이너 id.
    이미 만든 그림(/media/..., 이벤트 포스터)은 그대로 올린다."""
    sources = [s["src"] for s in post["slides"]]
    if all(src.startswith("/media/") for src in sources):
        paths = [media.made_path(src) for src in sources]
    else:
        paths = media.prepare(post["id"], sources, post["kind"])
    urls = [media.public_url(path) for path in paths]
    if post["kind"] == "story":
        return graph.story_container(urls[0])
    if len(urls) == 1:
        return graph.image_container(urls[0], post["caption"])
    children = [graph.image_container(url, carousel_item=True) for url in urls]
    for child in children:
        graph.wait_ready(child)
    return graph.carousel_container(children, post["caption"])


def publish(store_id: str, post_id: str) -> dict | None:
    """큐에 건 게시물을 실제로 올린다. 실패하면 failed 와 이유를 남기고, 토큰 문제(190)면 연결을 끊음으로 바꾼다."""
    post = get(post_id)
    if post is None or post["status"] != "queued":
        return post
    post = save({**post, "status": "publishing"})
    what = "인기 메뉴를" if post["kind"] == "feed" else "스토리를"
    try:
        if not graph.is_enabled() or not connection(store_id)["connected"]:
            raise InstagramError("인스타가 연결되어 있지 않아요")
        container = _upload(post)
        graph.wait_ready(container)
        media_id = graph.publish(container)
    except Exception as error:  # 사진 파일·업로드(boto3) 오류도 failed 로 남긴다. 아니면 publishing 에 멈춘다
        if isinstance(error, InstagramError) and error.token_invalid:
            disconnect(store_id, str(error))
        if not isinstance(error, InstagramError):
            logger.exception("인스타 게시 실패 %s", post_id)
        reason = str(error) if isinstance(error, InstagramError) else f"{type(error).__name__}: {error}"
        post = save({**post, "status": "failed", "error": reason})
        if post.get("event_id"):  # 이벤트 스토리는 story_event 가 알린다
            from voice.instagram import story_event

            story_event.on_post_done(store_id, post)
        else:
            notices.push(store_id, "instagram", f"인스타에 {what} 올리지 못했어요")
        return post
    try:
        link = graph.permalink(media_id)
    except InstagramError:  # 올라갔다. 주소만 못 받았다
        link = None
    post = save({**post, "status": "published", "media_id": media_id, "permalink": link, "published_at": iso(clock.now()), "error": None})
    if post.get("event_id"):  # 이벤트 스토리: 알바생 할 일을 넣고 story_event 가 알린다
        from voice.instagram import story_event

        story_event.on_post_done(store_id, post)
        return post
    if post.get("auto"):  # 묻지 않고 올린 게시물 (인스타 게시 대리, 인사과 4-b)
        from voice import hr

        hr.record(store_id, "instagram_post", post["id"], "done")
    text = f"인스타에 {what} 올렸어요"
    activity.log(store_id, "donna", text, f"instagram_{post['kind']}")
    notices.push(store_id, "instagram", text)
    return post


def delete(store_id: str, post_id: str) -> dict:
    """올린 게시물을 지운다 (사후 취소, 인사과 5단계). 지우면 status deleted. 못 지우면 InstagramError 를 그대로 낸다."""
    post = get(post_id)
    if post.get("media_id"):
        graph.delete_media(post["media_id"])
    return save({**post, "status": "deleted", "deleted_at": iso(clock.now())})
