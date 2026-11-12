"""개발자 대시보드 API. 화면은 저장소 맨 위 dev/ 폴더 (서버가 http://localhost:8000/dev-dashboard/ 로 보여 준다).

.env 의 DEV_TOOLS_ENABLED=true 일 때만 열린다. 꺼져 있으면 모든 주소가 404 다 (배포에서는 켜지 않는다).

GET  /api/dev_tools/overview                개요
GET  /api/dev_tools/stores                  매장 목록
GET  /api/dev_tools/analysis?store_id=      분석 결과 원본
GET  /api/dev_tools/timeline?store_id=      알림 타임라인 (어제 ~ 7일 뒤)
GET  /api/dev_tools/ai_usage?days=30        CLOVA 호출·토큰·비용
GET  /api/dev_tools/ai_quality?limit=50     CLOVA 통과·버림, 최근 호출
GET  /api/dev_tools/system                  설정 스위치, 키 유무, 계산 시간, 테스트 계정
POST /api/dev_tools/recompute?store_id=     그 가게 다시 계산
POST /api/dev_tools/polish                  문장 다듬기 켜기/끄기 {"enabled": true}
POST /api/dev_tools/clova_log/clear         CLOVA 사용 기록 지우기
GET  /api/dev_tools/demo_steps?store_id=    시연: Figma UC01~UC16 단계 (그 가게 시연 기간에서 찾은 시각과 앱 화면)
POST /api/dev_tools/demo_go                 시연: 서버 시계를 그 단계 시각으로 맞추고 가게를 다시 계산 {"store_id", "at"}
POST /api/dev_tools/demo_clock_reset        시연: 서버 시계를 실제 시각으로
POST /api/dev_tools/demo_rescan?store_id=   시연: 기억한 시연 기간 훑기 결과를 지우고 다시 훑기
시연의 시계 옮기기는 DEV_CLOCK_ENABLED=true 도 필요하다.
시계 앞당기기와 초기화는 팀원이 만든 /dev/clock, /dev/reset 을 쓴다 (DEV_CLOCK_ENABLED=true 필요).
"""

from fastapi import APIRouter, Depends, Query

from app.core import clova_usage_log
from app.core.config import settings
from app.core.error_response import ApiError
from app.data_pipeline.store_selection import resolve_store_id
from app.modules.dev_tools import data_provider, demo_scenario, demo_week_scan
from app.modules.dev_tools.response_format import DemoGo, PolishSwitch


def require_dev_tools() -> None:
    if not settings.dev_tools_enabled:
        raise ApiError(404, "NOT_FOUND", "개발자 대시보드가 꺼져 있어요. server/.env 에 DEV_TOOLS_ENABLED=true 를 넣고 서버를 다시 켜 주세요.")


router = APIRouter(dependencies=[Depends(require_dev_tools)])

STORE = Query(None, description="가게. 비우면 DEMO_STORE_ID")


@router.get("/overview", summary="개요")
def overview():
    return data_provider.overview()


@router.get("/stores", summary="매장 목록")
def stores():
    return data_provider.stores()


@router.get("/analysis", summary="분석 결과 원본")
def analysis(store_id: str | None = STORE):
    return data_provider.analysis(resolve_store_id(store_id))


@router.get("/timeline", summary="알림 타임라인")
def timeline(store_id: str | None = STORE, days_before: int = Query(1, ge=0, le=14), days_after: int = Query(7, ge=0, le=35)):
    return data_provider.timeline(resolve_store_id(store_id), days_before, days_after)


@router.get("/ai_usage", summary="CLOVA 호출·토큰·비용")
def ai_usage(days: int = Query(30, ge=1, le=365)):
    return data_provider.ai_usage(days)


@router.get("/ai_quality", summary="CLOVA 통과·버림과 최근 호출")
def ai_quality(limit: int = Query(50, ge=1, le=500)):
    return data_provider.ai_quality(limit)


@router.get("/system", summary="시스템 상태")
def system():
    from app.main import BOOT_ID

    return data_provider.system(BOOT_ID)


@router.post("/recompute", summary="그 가게 다시 계산")
def recompute(store_id: str | None = STORE):
    return data_provider.recompute(resolve_store_id(store_id))


@router.post("/polish", summary="문장 다듬기 켜기/끄기")
def polish(body: PolishSwitch):
    return data_provider.set_polish(body.enabled)


@router.post("/clova_log/clear", summary="CLOVA 사용 기록 지우기")
def clear_clova_log():
    clova_usage_log.clear()
    return {"cleared": True}


@router.get("/demo_steps", summary="시연: Figma UC01~UC16 단계")
def demo_steps(store_id: str | None = STORE):
    return demo_scenario.build_steps(resolve_store_id(store_id))


@router.post("/demo_go", summary="시연: 서버 시계를 그 단계 시각으로")
def demo_go(body: DemoGo):
    return data_provider.demo_go(resolve_store_id(body.store_id), body.at)


@router.post("/demo_clock_reset", summary="시연: 서버 시계를 실제 시각으로")
def demo_clock_reset(store_id: str | None = STORE):
    return data_provider.demo_clock_reset(resolve_store_id(store_id) if store_id else None)


@router.post("/demo_rescan", summary="시연: 시연 기간 다시 훑기")
def demo_rescan(store_id: str | None = STORE):
    sid = resolve_store_id(store_id)
    demo_week_scan.forget(sid)
    return demo_scenario.build_steps(sid)
