"""개발자 대시보드(dev/ 폴더)에 보여 줄 데이터를 모은다. 로컬 시험용이라 .env 의 DEV_TOOLS_ENABLED=true 일 때만 열린다.

탭마다 함수 하나:
  overview()      개요: 가게·계정 수, 오늘·이번 달 CLOVA 비용, 서버 상태, 업종 분포
  stores()        매장: 목업 가게와 등록 가게, 영업시간, 주문·리뷰·메뉴·알바 수, 마지막 계산
  analysis()      분석: 태성 분석 결과 원본 (35일 달력, 하루 매출, 단골, 리뷰 분류, 반복 불만)
  timeline()      알림 타임라인: 계획 엔진이 정한 알림 시각별 할 일
  ai_usage()      AI 비용: CLOVA 호출·토큰·비용 (기능별, 가게별, 날짜별)
  ai_quality()    AI 품질: 통과·버림·실패, 버린 이유, 최근 호출
  system()        시스템: 설정 스위치, 키가 있는지(값은 안 보임), 가게별 계산 시간, 테스트 계정

손님 리뷰 글의 전화번호와 @닉네임은 가려서 보낸다. API 키 값은 보내지 않는다.
"""

import datetime as dt
import sqlite3
from collections import Counter, defaultdict

from app.analysis.review.hcx_classifier import mask_personal_info
from app.core import clova_usage_log
from app.core.config import settings
from app.core.error_response import ApiError
from app.core.seoul_time import clock_shift, now_seoul, set_clock_shift, to_seoul
from app.data_pipeline import read_store_db, registered_stores, store_snapshot_cache
from app.planner.notification_time_helpers import KOREAN_WEEKDAYS
from app.planner.rule_review_reply import SATURDAY_SEND_TIME
from app.planner.rule_complaint_fix import COMPLAINT_NAMES
from app.sentence_polish.polish_with_clova import polished

TASK_NAMES = {
    "REVISIT_REPLY": "리뷰 답글",
    "MENU_ORDER": "메뉴판 순서",
    "POSTER": "홍보 포스터",
    "REVIEW_FIX": "반복 불만 점검",
    "REORDER_NUDGE": "재주문 인사",
}
NOTIFY_NAMES = {"APPROVAL_REQUEST": "승인 요청", "EXECUTE_REMINDER": "실행 알림", "PREVIEW": "미리 보기", "NOTICE": "알림"}
SLOT_NAMES = {"OPENING": "출근 후", "AFTERNOON": "오후", "CLOSING": "마감 전", "EXTRA": "더 넣은 알림"}
CLASS_NAMES = {"QUICK": "불만", "WEEKLY": "매주 단골", "MONTHLY": "매달 단골", "BASIC": "일반"}


def _iso(t: dt.datetime | None) -> str | None:
    return to_seoul(t).isoformat(timespec="minutes") if t else None


def _registry_counts() -> dict[str, int]:
    """등록 가게 수와 가게를 연결한 네이버 계정 수 (registry.db). 파일이 없으면 0."""
    path = registered_stores.REGISTRY_PATH
    if not path.exists():
        return {"registered_stores": 0, "owners": 0}
    with sqlite3.connect(path) as conn:
        stores = conn.execute("SELECT COUNT(*) FROM stores").fetchone()[0]
        owners = conn.execute("SELECT COUNT(*) FROM owners").fetchone()[0]
    return {"registered_stores": stores, "owners": owners}


def _store_kind(store_id: str) -> str:
    return "registered" if registered_stores.place_info(store_id) is not None else "mock"


def _hours_text(store: dict) -> str:
    return f"{store['open_time'].strftime('%H:%M')} ~ {store['close_time'].strftime('%H:%M')}"


def _price_set() -> bool:
    return bool(settings.clova_price_input_per_1k or settings.clova_price_output_per_1k)


# ── 개요 ──


def overview() -> dict:
    now = now_seoul()
    store_ids = read_store_db.list_store_ids()
    stores = [read_store_db.read_store(sid) for sid in store_ids]
    today = clova_usage_log.usage_summary(1)["total"]
    month_days = now.day
    month = clova_usage_log.usage_summary(month_days)["total"]
    days_in_month = ((now.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)).day
    projected = round(month["cost_won"] / month_days * days_in_month, 2) if month_days else 0
    return {
        "now": now.isoformat(timespec="minutes"),
        "clock_shift_minutes": int(clock_shift().total_seconds() // 60),
        "stores_total": len(store_ids),
        "stores_mock": sum(1 for sid in store_ids if _store_kind(sid) == "mock"),
        **_registry_counts(),
        "categories": [{"name": name, "count": count} for name, count in Counter(s["category"] for s in stores).most_common()],
        "clova_today": today,
        "clova_month": {**month, "projected_cost_won": projected},
        "price_set": _price_set(),
        "computed_stores": sum(1 for sid in store_ids if store_snapshot_cache.cached_snapshot(sid) is not None),
    }


# ── 매장 ──


def stores() -> list[dict]:
    now = now_seoul()
    rows = []
    for store_id in read_store_db.list_store_ids():
        store = read_store_db.read_store(store_id)
        snapshot = store_snapshot_cache.cached_snapshot(store_id)
        rows.append(
            {
                "store_id": store_id,
                "name": store["name"],
                "category": store["category"],
                "address": store["address"],
                "hours": _hours_text(store),
                "closed_weekdays": store["closed_weekdays"] or [],
                "overnight": store["close_time"] < store["open_time"],
                "kind": _store_kind(store_id),
                **read_store_db.count_rows(store_id, now),
                "computed_at": _iso(snapshot.computed_at) if snapshot else None,
                "compute_seconds": store_snapshot_cache.compute_seconds(store_id),
                "plan_ok": snapshot.plan is not None if snapshot else None,
            }
        )
    return rows


# ── 분석 ──


def analysis(store_id: str) -> dict:
    snapshot = store_snapshot_cache.get_snapshot(store_id)
    today = snapshot.computed_at.date()

    daily: dict[dt.date, dict] = defaultdict(lambda: {"sales": 0, "labor": 0, "profit": 0})
    for row in snapshot.sales_daily:
        if row.date >= today - dt.timedelta(days=28):
            daily[row.date]["sales"] += row.sales_amount
            daily[row.date]["labor"] += row.labor_cost or 0
            daily[row.date]["profit"] += row.profit

    labels = [r.label for r in snapshot.reviews if r.label]
    complaint_counts = Counter(t for label in labels for t in label.complaint_types)
    recent_reviews = sorted(snapshot.reviews, key=lambda r: r.written_at, reverse=True)[:20]
    return {
        "store": {"store_id": store_id, "name": snapshot.store["name"]},
        "computed_at": _iso(snapshot.computed_at),
        "calendar": [
            {
                "date": cell.date.isoformat(),
                "weekday": KOREAN_WEEKDAYS[cell.date.weekday()][0],
                "daypart": cell.daypart,
                "signal": cell.signal,
                "ratio": cell.ratio,
                "baseline": cell.baseline_sales,
                "expected": cell.expected_sales,
                "reasons": [r.tag for r in cell.reasons],
                "reason_text": polished("calendar_reason", cell.reason_text, snapshot.store),
            }
            for cell in snapshot.calendar_cells
        ],
        "daily_sales": [{"date": day.isoformat(), **values} for day, values in sorted(daily.items())],
        "regulars": [
            {
                "customer_key": c.customer_key,
                "cycle": c.cycle,
                "next_expected_at": _iso(c.next_expected_at),
                "intervals_days": c.intervals_days,
            }
            for c in snapshot.customer_cycles
            if c.cycle != "NONE"
        ],
        "review_summary": {
            "total": len(snapshot.reviews),
            "quick": sum(1 for label in labels if label.is_quick),
            "sentiment": dict(Counter(label.sentiment for label in labels)),
            "complaints": [{"name": COMPLAINT_NAMES.get(k, k), "count": v} for k, v in complaint_counts.most_common()],
            "labeler": dict(Counter(label.labeler for label in labels)),
        },
        "recent_reviews": [
            {
                "review_id": r.review_id,
                "written_at": _iso(r.written_at),
                "platform": r.platform,
                "rating": r.rating,
                "text": mask_personal_info(r.text),
                "sentiment": r.label.sentiment if r.label else None,
                "complaints": [COMPLAINT_NAMES.get(t, t) for t in r.label.complaint_types] if r.label else [],
                "quick": bool(r.label and r.label.is_quick),
            }
            for r in recent_reviews
        ],
        "risk_signals": [
            {
                "risk_id": s.risk_id,
                "complaint": COMPLAINT_NAMES.get(s.complaint_type, s.complaint_type),
                "reviews": len(s.review_ids),
                "detected_at": _iso(s.detected_at),
            }
            for s in snapshot.risk_signals
        ],
    }


# ── 알림 타임라인 ──


def timeline(store_id: str, days_before: int, days_after: int) -> dict:
    snapshot = store_snapshot_cache.get_snapshot(store_id)
    now = now_seoul()
    if snapshot.plan is None:
        return {"store": {"store_id": store_id, "name": snapshot.store["name"]}, "now": now.isoformat(timespec="minutes"),
                "unavailable": snapshot.plan_unavailable.message if snapshot.plan_unavailable else "계획이 없어요", "days": []}
    first, last = now.date() - dt.timedelta(days=days_before), now.date() + dt.timedelta(days=days_after)
    items = {item.plan_id: item for item in snapshot.plan.plan_items}
    notices = {notice.notice_id: notice for notice in snapshot.plan.notice_items}
    days: dict[str, list] = defaultdict(list)
    for batch in snapshot.plan.batches:
        slot_at = to_seoul(batch.slot_at)
        if not first <= slot_at.date() <= last:
            continue
        entries = []
        for entry in batch.entries:
            if entry.plan_id and entry.plan_id in items:
                item = items[entry.plan_id]
                entries.append(
                    {
                        "id": item.plan_id,
                        "task": TASK_NAMES.get(item.task_type, item.task_type),
                        "class": CLASS_NAMES.get(item.revisit_class or "", None),
                        "notify": NOTIFY_NAMES.get(entry.notify_kind, entry.notify_kind),
                        "priority": entry.priority,
                        "text": polished("plan_card", item.reason_line, snapshot.store),
                        "draft": snapshot.draft_texts.get(item.plan_id),
                        "execute_at": _iso(item.execute_at),
                        "deadline_at": _iso(item.deadline_at),
                    }
                )
            elif entry.notice_id and entry.notice_id in notices:
                notice = notices[entry.notice_id]
                entries.append(
                    {
                        "id": notice.notice_id,
                        "task": "미리보기" if notice.kind == "WEEKLY_PREVIEW" else "매출 이상",
                        "class": None,
                        "notify": NOTIFY_NAMES.get(entry.notify_kind, entry.notify_kind),
                        "priority": entry.priority,
                        "text": polished("notice", notice.text, snapshot.store),
                        "draft": None,
                        "execute_at": None,
                        "deadline_at": None,
                    }
                )
        days[slot_at.date().isoformat()].append(
            {
                "slot_at": slot_at.isoformat(timespec="minutes"),
                "slot": SLOT_NAMES.get(batch.slot, batch.slot),
                "passed": slot_at <= now,
                "entries": entries,
            }
        )
    settings_now = snapshot.settings
    return {
        "store": {"store_id": store_id, "name": snapshot.store["name"]},
        "now": now.isoformat(timespec="minutes"),
        "slots": settings_now.slots.model_dump() if settings_now else None,
        "rules": [
            "불만 리뷰: 리뷰 뒤 첫 알림 시각에 승인 요청, 승인과 함께 답글",
            f"그 밖의 리뷰: 지난 토요일 {SATURDAY_SEND_TIME} ~ 이번 토요일 {SATURDAY_SEND_TIME}에 달린 리뷰를 토요일 출근 후 승인, {SATURDAY_SEND_TIME} 게시",
            "매달 단골 재주문 인사: 답글 4주 뒤 토요일",
            "메뉴판 순서: 바뀌는 날 전날 오후 승인, 당일 출근 후 실행",
            "행사·경기 포스터: 3일 전 오후 승인, 2일 전 출근 후 실행",
            "반복 불만 점검: 발견 뒤 첫 오후",
        ],
        "days": [{"date": day, "weekday": KOREAN_WEEKDAYS[dt.date.fromisoformat(day).weekday()], "batches": batches}
                 for day, batches in sorted(days.items())],
    }


# ── AI 비용, 품질 ──


def ai_usage(days: int) -> dict:
    return {
        **clova_usage_log.usage_summary(days),
        "days": days,
        "model": settings.clova_studio_model,
        "price_set": _price_set(),
        "price_input_per_1k": settings.clova_price_input_per_1k,
        "price_output_per_1k": settings.clova_price_output_per_1k,
        "stores": {sid: read_store_db.read_store(sid)["name"] for sid in read_store_db.list_store_ids()},
    }


def ai_quality(limit: int) -> dict:
    return clova_usage_log.quality_summary(limit)


# ── 시스템 ──


def system(boot_id: str) -> dict:
    from app.modules.auth.test_accounts import TEST_ACCOUNTS

    store_ids = read_store_db.list_store_ids()
    return {
        "boot_id": boot_id,
        "now": now_seoul().isoformat(timespec="minutes"),
        "clock_shift_minutes": int(clock_shift().total_seconds() // 60),
        "switches": {
            "DEV_TOOLS_ENABLED": settings.dev_tools_enabled,
            "DEV_CLOCK_ENABLED": settings.dev_clock_enabled,
            "SENTENCE_POLISH_ENABLED": settings.sentence_polish_enabled,
            "DEMO_STORE_DATA": settings.demo_store_data,
        },
        "values": {
            "DEMO_STORE_ID": settings.demo_store_id,
            "SNAPSHOT_REFRESH_MINUTES": settings.snapshot_refresh_minutes,
            "CLOVA_STUDIO_MODEL": settings.clova_studio_model,
        },
        "keys": {  # 값은 보내지 않고 들어 있는지만
            "CLOVA_STUDIO_API_KEY": bool(settings.clova_studio_api_key),
            "NAVER_LOGIN_CLIENT_ID": bool(settings.naver_login_client_id),
            "NAVER_API_HUB_CLIENT_ID": bool(settings.naver_api_hub_client_id),
            "NAVER_MAPS_CLIENT_ID": bool(settings.naver_maps_client_id),
            "NCLOUD_ACCESS_KEY": bool(settings.ncloud_access_key),
        },
        "storage": {
            "가게 DB": "server/db/data/ (SQLite, s001~s003 목업 + 등록 가게 s1xx)",
            "등록·로그인 기록": "server/db/app_data/registry.db",
            "CLOVA 사용 기록": "server/db/app_data/clova_usage.db",
            "계산 결과, 고친 설정": "서버 메모리 (서버를 다시 켜면 사라짐)",
        },
        "compute": [
            {
                "store_id": sid,
                "computed_at": _iso(snap.computed_at) if (snap := store_snapshot_cache.cached_snapshot(sid)) else None,
                "seconds": store_snapshot_cache.compute_seconds(sid),
            }
            for sid in store_ids
        ],
        "test_accounts": [
            {"login_id": a["login_id"], "password": a["password"], "scenario": a.get("scenario", ""),
             "linked_store": registered_stores.store_for_owner(f"naver:{a['profile']['id']}")}
            for a in TEST_ACCOUNTS
        ],
    }


# ── 조작 ──


def recompute(store_id: str) -> dict:
    store_snapshot_cache.forget(store_id)
    snapshot = store_snapshot_cache.get_snapshot(store_id)
    return {"store_id": store_id, "computed_at": _iso(snapshot.computed_at), "seconds": store_snapshot_cache.compute_seconds(store_id)}


def set_polish(enabled: bool) -> dict:
    settings.sentence_polish_enabled = enabled
    return {"SENTENCE_POLISH_ENABLED": enabled}


# ── 시연 (Figma UC01~UC16) ──


def _require_dev_clock() -> None:
    if not settings.dev_clock_enabled:
        raise ApiError(400, "DEV_CLOCK_OFF", "시연 단계를 열려면 서버 시계를 옮겨야 해요. server/.env 에 DEV_CLOCK_ENABLED=true 를 넣고 서버를 다시 켜 주세요.")


def demo_go(store_id: str, at: dt.datetime) -> dict:
    """서버 시계를 at 으로 맞추고 그 가게를 처음부터 다시 계산해 둔다 (앱이 열리자마자 그 시각의 카드를 받게).

    반복 불만은 앞 결과를 이어 쓰므로, 보관한 결과를 지우고 계산해야 시계를 앞뒤로 옮겨도 늘 같은 화면이 나온다.
    """
    _require_dev_clock()
    real_now = now_seoul() - clock_shift()
    set_clock_shift(to_seoul(at) - real_now)
    store_snapshot_cache.forget(store_id)
    snapshot = store_snapshot_cache.get_snapshot(store_id)
    return {"now": now_seoul().isoformat(timespec="minutes"), "clock_shift_minutes": int(clock_shift().total_seconds() // 60),
            "computed_at": _iso(snapshot.computed_at)}


def demo_clock_reset(store_id: str | None) -> dict:
    """서버 시계를 실제 시각으로 돌린다."""
    _require_dev_clock()
    set_clock_shift(dt.timedelta(0))
    if store_id:
        store_snapshot_cache.forget(store_id)
    return {"now": now_seoul().isoformat(timespec="minutes"), "clock_shift_minutes": 0}
