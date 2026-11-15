"""AI 포스터 (인스타 스토리 1080 × 1920).

GET  /api/poster_ai/engine                       그림을 만들 수 있는지 (Codex ChatGPT 로그인)
GET  /api/poster_ai/suggest?plan_id=             그날 상황 + CLOVA 멘트 3개 + 포스터 모양 고르기
POST /api/poster_ai/jobs                         그림 만들기 시작 {"plan_id", "photos": [{"label", "url"}], "use_logo", "headline", "line", "extra", "style", "menu"}
GET  /api/poster_ai/jobs/{job_id}                다 됐는지 (RUNNING, DONE, FAILED + fail_reason)
GET  /api/poster_ai/jobs/{job_id}/image          다 만든 그림 PNG

흐름: 사장님이 사진(메뉴·매장 사진, 로고)을 고르고 → 멘트·모양·더 넣을 말을 고르면 →
서버가 상황과 고른 것을 모아 프롬프트를 만들어 그림 모델(지금은 Codex 의 gpt-image-2, ChatGPT 구독제)에 사진과 함께 준다.
설명: docs/poster-ai.md
"""

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from app.core.error_response import ApiError
from app.data_pipeline import store_logo
from app.data_pipeline.store_selection import store_id_param
from app.data_pipeline.store_snapshot_cache import get_snapshot
from Harness import app_bridge
from app.poster_ai import image_engine, jobs, ment, situation
from app.poster_ai.prompt import STYLES, PosterChoice

router = APIRouter()


def _situation(store_id: str, plan_id: str) -> situation.Situation:
    try:
        return situation.from_plan(get_snapshot(store_id), plan_id)
    except ValueError as error:
        raise ApiError(422, "INVALID_INPUT", str(error))


@router.get("/engine", summary="그림을 만들 수 있는지")
def engine():
    return image_engine.engine_status()


@router.get("/suggest", summary="상황과 멘트 추천")
def suggest(plan_id: str, store_id: str = Depends(store_id_param)):
    s = _situation(store_id, plan_id)
    # 에이전트 하네스를 켰고 campaign_agent 가 이미 멘트를 냈으면 그것을 쓴다 (메뉴판과 주제가 맞는다). 아니면 기존 단일 호출
    agent_ments = app_bridge.poster_ments(store_id, plan_id) if app_bridge.enabled() else None
    if agent_ments:
        ments, source = [ment.Ment(**m) for m in agent_ments], "AGENT"
    else:
        ments, source = ment.suggest(s)
    return {
        "situation": {"date": s.date.isoformat(), "kind": s.kind, "title": s.title, "lines": s.lines(), "weather_tags": s.weather_tags},
        "ments": [m.to_dict() for m in ments],
        "ment_source": source,
        "styles": [{"key": k, "label": label} for k, (label, _) in STYLES.items()],
        "has_logo": store_logo.path_of(store_id) is not None,
        "engine": image_engine.engine_status(),
    }


class Photo(BaseModel):
    label: str = Field(max_length=40)
    url: str  # 네이버 사진(pstatic.net) 주소 또는 휴대폰에서 고른 사진 data:image/...;base64


class NewPoster(BaseModel):
    plan_id: str
    photos: list[Photo] = Field(min_length=1, max_length=jobs.MAX_PHOTOS)
    use_logo: bool = True
    headline: str = Field(min_length=1, max_length=40)
    line: str = Field(default="", max_length=80)
    extra: str = Field(default="", max_length=80)
    style: str = "PHOTO"
    menu: str = Field(default="", max_length=40)


def _view(job: dict) -> dict:
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "fail_reason": job.get("error"),  # FAILED 일 때 이유. 앱은 응답에 "error" 칸이 있으면 실패로 보므로 이름을 달리 둔다
        "seconds": jobs.elapsed_seconds(job),
        "image": f"/api/poster_ai/jobs/{job['job_id']}/image" if job["status"] == "DONE" else None,
        "headline": job["headline"],
        "line": job["line"],
        "extra": job["extra"],
        "style": job["style"],
        "engine": job["engine"],
    }


@router.post("/jobs", summary="포스터 그림 만들기 시작")
def start(body: NewPoster, store_id: str = Depends(store_id_param)):
    if body.style not in STYLES:
        raise ApiError(422, "INVALID_INPUT", "포스터 모양이 이상해요")
    status = image_engine.engine_status()
    if not status["ready"]:
        raise ApiError(503, "POSTER_ENGINE_NOT_READY", status["note"])
    s = _situation(store_id, body.plan_id)
    choice = PosterChoice(headline=body.headline.strip(), line=body.line.strip(), extra=body.extra, style=body.style, menu=body.menu, has_logo=body.use_logo)
    try:
        job = jobs.start(s, choice, [(p.label, p.url) for p in body.photos], body.plan_id)
    except jobs.PhotoError as error:
        raise ApiError(422, "BAD_PHOTO", str(error))
    return _view(job)


@router.get("/jobs/{job_id}", summary="포스터 그림이 다 됐는지")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise ApiError(404, "NO_POSTER_JOB", "만들던 포스터를 찾지 못했어요")
    return _view(job)


@router.get("/jobs/{job_id}/image", summary="다 만든 포스터 그림")
def job_image(job_id: str):
    path = jobs.image_path(job_id)
    if path is None:
        raise ApiError(404, "NO_POSTER_IMAGE", "포스터 그림이 아직 없어요")
    return Response(path.read_bytes(), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
