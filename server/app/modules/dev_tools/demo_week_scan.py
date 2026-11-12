"""개발자 대시보드 시연 탭: 시연 주간을 알림 시각마다 훑어서, 그때 홈에 어떤 할 일이 오는지 모은다.

시연은 늘 같은 화면이 떠야 해서 실제 오늘이 아니라 정해 둔 2주(DEMO_WEEK_START 부터 DEMO_DAYS 일)를 쓴다.
그 기간의 날마다, 가게 알림 시각(출근 후, 오후, 마감 전)마다 그 시각 5분 뒤의 계획을 새로 만들고(CLOVA 없이),
그 시각에 보내는 알림 묶음을 남긴다. 앱 홈은 서버 시계가 그 시각일 때 바로 이 묶음을 보여 준다.

목업 데이터가 같으니 결과도 늘 같다. 가게 하나에 수십 초가 걸려서 서버가 켜져 있는 동안 기억해 둔다.
"""

import datetime as dt
import threading
from dataclasses import dataclass, field

from app.core.seoul_time import at_time, to_seoul
from app.data_pipeline import store_snapshot_cache
from app.planner.data_shapes import NoticeItem, PlanItem

# 목업 리뷰가 2026-11-10(화)까지 있어서, 그 주 월요일부터 2주를 시연 기간으로 둔다.
# 첫 주에 불만 답글(화요일 오후)과 좋은 리뷰 묶음, 포스터가, 둘째 주에 메뉴판 바꾸기가 나온다.
DEMO_WEEK_START = dt.date(2026, 11, 9)  # 월요일
DEMO_DAYS = 14
# 알림 시각 바로 뒤에 시계를 둔다 (그 시각 묶음이 막 도착한 때)
AFTER_SLOT = dt.timedelta(minutes=5)
SLOT_ORDER = ("OPENING", "AFTERNOON", "CLOSING")


@dataclass
class SeenEntry:
    """그 시각 홈에 온 할 일 하나."""

    notify_kind: str
    plan: PlanItem | None = None
    notice: NoticeItem | None = None


@dataclass
class SeenSlot:
    """알림 시각 하나와 그때 온 할 일들 (우선순위 순서)."""

    slot: str  # OPENING, AFTERNOON, CLOSING
    slot_at: dt.datetime
    moment: dt.datetime  # 시연 때 서버 시계를 둘 시각 (slot_at + 5분)
    entries: list[SeenEntry]


@dataclass
class WeekScan:
    store_id: str
    slots: list[SeenSlot] = field(default_factory=list)
    unavailable: str | None = None  # 계획을 못 만들었으면 그 까닭


_scans: dict[str, WeekScan] = {}
_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}


def scan_week(store_id: str) -> WeekScan:
    """그 가게 시연 주간 훑기. 한 번 훑은 결과는 서버가 켜져 있는 동안 기억한다."""
    with _guard:
        lock = _locks.setdefault(store_id, threading.Lock())
    with lock:
        if store_id not in _scans:
            _scans[store_id] = _scan(store_id)
        return _scans[store_id]


def forget(store_id: str | None = None) -> None:
    """기억한 훑기 결과를 지운다 (가게 설정을 바꿨을 때, 대시보드 '다시 훑기')."""
    if store_id is None:
        _scans.clear()
    else:
        _scans.pop(store_id, None)


def _scan(store_id: str) -> WeekScan:
    first_moment = at_time(DEMO_WEEK_START, "00:05")
    settings, _, unavailable = store_snapshot_cache.plan_only(store_id, first_moment)
    if settings is None:
        return WeekScan(store_id, unavailable=unavailable.message if unavailable else "계획을 만들지 못했어요")

    scan = WeekScan(store_id)
    slot_times = {name: getattr(settings.slots, name) for name in SLOT_ORDER}
    for offset in range(DEMO_DAYS):
        day = DEMO_WEEK_START + dt.timedelta(days=offset)
        for name in SLOT_ORDER:
            slot_at = at_time(day, slot_times[name])
            moment = slot_at + AFTER_SLOT
            _, plan, unavailable = store_snapshot_cache.plan_only(store_id, moment)
            if plan is None:
                scan.unavailable = unavailable.message if unavailable else "계획을 만들지 못했어요"
                return scan
            items = {item.plan_id: item for item in plan.plan_items}
            notices = {notice.notice_id: notice for notice in plan.notice_items}
            for batch in plan.batches:
                if to_seoul(batch.slot_at) != slot_at:
                    continue
                entries = [
                    SeenEntry(
                        entry.notify_kind,
                        plan=items.get(entry.plan_id) if entry.plan_id else None,
                        notice=notices.get(entry.notice_id) if entry.notice_id else None,
                    )
                    for entry in batch.entries
                ]
                scan.slots.append(SeenSlot(name, slot_at, moment, [e for e in entries if e.plan or e.notice]))
    return scan
