"""시험 날짜: 시험 주간 데이터(db/test_scenarios/<가게>.json)가 있는 가게의 그 주 알림 시각과, 그때 홈에 오는 할 일.

앱 ☰ 메뉴와 설정의 "시험 날짜"가 쓴다 (데모 테스트 모드). 알림 시각을 고르면 서버 시계를 그 시각 5분 뒤로 옮긴다.
- 목록: 그 주 날마다 알림 시각(출근 후, 오후, 마감 전)마다 그 시각에 오는 할 일. 반복 불만 신호를 앞 시각에서 이어 받아
  계산한다(서버가 그 주 내내 켜져 있었을 때와 같다). 몇 초 걸려서 시험 데이터·설정이 그대로면 기억해 둔 값을 쓴다.
- 옮기기: 서버 시계를 옮기고, 그 주 첫 알림 시각부터 고른 시각까지 이어 계산해 결과를 보관한다(jump_to).
"""

import datetime as dt
import threading

from app.core.config import settings as app_settings
from app.core.error_response import ApiError
from app.core.seoul_time import at_time, clock_shift, now_seoul, set_clock_shift, to_seoul
from app.data_pipeline import read_store_db, store_snapshot_cache, test_scenario

AFTER_SLOT = dt.timedelta(minutes=5)
SLOT_ORDER = ("OPENING", "AFTERNOON", "CLOSING")
SLOT_NAMES = {"OPENING": "출근 후", "AFTERNOON": "오후", "CLOSING": "마감 전"}
WEEKDAYS = "월화수목금토일"
TASK_NAMES = {
    "REVISIT_REPLY": "리뷰 답글",
    "MENU_ORDER": "메뉴판 바꾸기",
    "POSTER": "포스터",
    "REVIEW_FIX": "같은 불만 점검",
    "REORDER_NUDGE": "단골 재주문 인사",
    "WEEKLY_PREVIEW": "이번 주 미리보기",
    "SALES_ANOMALY": "매출 이상",
}
KIND_NAMES = {"APPROVAL_REQUEST": "승인", "EXECUTE_REMINDER": "실행", "PREVIEW": "알림", "NOTICE": "알림"}

# Killer Feature 네 가지와 시연 단계. 단계: (할 일 종류, 알림 종류, 답글 종류(None 이면 모두), 단계 이름, 여러 번 보여 줄지)
FEATURES = [
    {
        "key": "revisit",
        "mark": "①",
        "name": "고객 재방문 유도",
        "flow": "방문 고객 분석 → 리뷰 답변 → 매장 재인지 → 주말 재방문 유도",
        "steps": [
            ("REORDER_NUDGE", "APPROVAL_REQUEST", None, "한 달 단골에게 재주문 인사", False),
            ("REVISIT_REPLY", "APPROVAL_REQUEST", ("BASIC", "WEEKLY", "MONTHLY"), "좋은 리뷰에 답글 묶음", False),
        ],
    },
    {
        "key": "menu",
        "mark": "②",
        "name": "AI 메뉴판 최적화",
        "flow": "매출·수요·계절·행사 분석 → 추천 메뉴 선정 → 메뉴판 노출 순서 재배치",
        "steps": [("MENU_ORDER", "APPROVAL_REQUEST", None, "메뉴판 새로 맞추기", True)],
    },
    {
        "key": "poster",
        "mark": "③",
        "name": "AI 홍보 콘텐츠 제작",
        "flow": "홍보 메뉴 선정 → 계절·날씨·행사 반영 → 인스타그램 포스터 자동 제작",
        "steps": [
            ("POSTER", "APPROVAL_REQUEST", None, "행사 포스터 만들기", False),
            ("POSTER", "EXECUTE_REMINDER", None, "포스터 올리기", False),
        ],
    },
    {
        "key": "fix",
        "mark": "④",
        "name": "부정 리뷰 기반 개선 선순환",
        "flow": "부정 리뷰 감지 → 위험 신호·원인 분석 → 개선 방안 제안 → 매장 운영 개선",
        "steps": [
            ("REVISIT_REPLY", "APPROVAL_REQUEST", ("QUICK",), "불만 리뷰에 사과 답글", False),
            ("REVIEW_FIX", "APPROVAL_REQUEST", None, "같은 불만 점검 목록", False),
        ],
    },
]
MAX_REPEAT = 3  # 여러 번 보여 주는 단계(메뉴판)는 이만큼까지


def _mark_of(task_type: str, revisit_class: str | None) -> str:
    """할 일 종류 → Killer Feature 번호 (주간 미리보기 같은 알림은 빈 값)"""
    if task_type == "REVISIT_REPLY":
        return "④" if revisit_class == "QUICK" else "①"
    return {"REORDER_NUDGE": "①", "MENU_ORDER": "②", "POSTER": "③", "REVIEW_FIX": "④"}.get(task_type, "")

_cache: dict[str, tuple[str, dict]] = {}
_lock = threading.Lock()


def _week(store_id: str) -> tuple[dt.date, dt.date]:
    week = test_scenario.week(store_id)
    if week is None:
        raise ApiError(404, "NO_TEST_WEEK", "이 가게에는 시험 주간 데이터가 없어요")
    return week


def _stops(store_id: str) -> list[tuple[dt.date, str, dt.datetime]]:
    """(날짜, 알림 이름, 시계를 둘 시각) 시간순"""
    start, end = _week(store_id)
    settings, _, unavailable = store_snapshot_cache.plan_only(store_id, at_time(start, "00:05"))
    if settings is None:
        raise ApiError(400, "PLAN_UNAVAILABLE", unavailable.message if unavailable else "계획을 만들지 못했어요")
    stops = []
    day = start
    while day <= end:
        for name in SLOT_ORDER:
            stops.append((day, name, at_time(day, getattr(settings.slots, name)) + AFTER_SLOT))
        day += dt.timedelta(days=1)
    return stops


def _fingerprint(store_id: str) -> str:
    return f"{test_scenario.mark(store_id)}|{store_snapshot_cache.get_settings_changes(store_id)}"


def week_stops(store_id: str) -> dict:
    """그 가게 시험 주간의 알림 시각과 그때 오는 할 일."""
    fingerprint = _fingerprint(store_id)
    with _lock:
        cached = _cache.get(store_id)
        if cached and cached[0] == fingerprint:
            return {**cached[1], "now": now_seoul().isoformat(timespec="minutes")}
        stops = _stops(store_id)
        plans = store_snapshot_cache.plan_at_times(store_id, [at for _, _, at in stops], chain=True)
        rows, seen = [], []  # seen: (단계를 찾을 정보, 그 시각 줄)
        for (day, name, at), (_, plan, _) in zip(stops, plans):
            slot_at = at - AFTER_SLOT
            tasks = []
            row = {
                "at": at.isoformat(timespec="minutes"),
                "day": f"{day.month}/{day.day}({WEEKDAYS[day.weekday()]})",
                "slot": name,
                "slot_name": SLOT_NAMES[name],
                "time": slot_at.strftime("%H:%M"),
                "tasks": tasks,
            }
            if plan is not None:
                items = {item.plan_id: item for item in plan.plan_items}
                notices = {notice.notice_id: notice for notice in plan.notice_items}
                for batch in plan.batches:
                    if to_seoul(batch.slot_at) != slot_at:
                        continue
                    for entry in batch.entries:
                        item, notice = items.get(entry.plan_id or ""), notices.get(entry.notice_id or "")
                        kind = item.task_type if item else notice.kind if notice else None
                        if kind:
                            mark = _mark_of(kind, item.revisit_class if item else None)
                            tasks.append(f"{mark} {TASK_NAMES.get(kind, kind)} {KIND_NAMES.get(entry.notify_kind, '')}".strip())
                        if item:
                            seen.append(((item.task_type, entry.notify_kind, item.revisit_class, item.plan_id, item.reason_line), row))
            rows.append(row)
        start, end = _week(store_id)
        result = {
            "store_id": store_id,
            "store_name": read_store_db.read_store(store_id)["name"],
            "start": start.isoformat(),
            "end": end.isoformat(),
            "stops": rows,
            "features": _features(seen),
        }
        _cache[store_id] = (fingerprint, result)
    return {**result, "now": now_seoul().isoformat(timespec="minutes")}


def _features(seen: list[tuple[tuple, dict]]) -> list[dict]:
    """Killer Feature 마다 시연 단계: 그 주에서 그 단계가 처음 오는 알림 시각과 도나가 든 까닭."""
    result = []
    for feature in FEATURES:
        steps = []
        for task_type, notify_kind, classes, label, repeat in feature["steps"]:
            used: set[str] = set()
            for (t, n, revisit_class, plan_id, reason), row in seen:
                if t != task_type or n != notify_kind or (classes and revisit_class not in classes) or plan_id in used:
                    continue
                used.add(plan_id)
                steps.append({"label": label, "reason": reason, **{k: row[k] for k in ("at", "day", "time", "slot_name")}})
                if not repeat or len(used) >= MAX_REPEAT:
                    break
        result.append({k: feature[k] for k in ("key", "mark", "name", "flow")} | {"steps": sorted(steps, key=lambda st: st["at"])})
    return result


def go_to(store_id: str, at: dt.datetime) -> dict:
    """서버 시계를 at 으로 옮기고, 그 주 앞 알림 시각부터 이어 계산해 at 의 결과를 보관한다."""
    if not app_settings.dev_clock_enabled:
        raise ApiError(400, "DEV_CLOCK_OFF", "서버 시계를 옮기려면 python run_dev.py 로 켜 주세요")
    at = to_seoul(at)
    earlier = [stop_at for _, _, stop_at in _stops(store_id) if stop_at < at]
    real_now = now_seoul() - clock_shift()
    set_clock_shift(at - real_now)
    store_snapshot_cache.forget(store_id)
    snapshot = store_snapshot_cache.jump_to(store_id, at, earlier)
    return {"now": now_seoul().isoformat(timespec="minutes"), "clock_shift_minutes": int(clock_shift().total_seconds() // 60),
            "computed_at": snapshot.computed_at.isoformat(timespec="minutes")}
