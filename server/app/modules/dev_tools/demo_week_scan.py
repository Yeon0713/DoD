"""개발자 대시보드 시연 탭: 시연 주간을 알림 시각마다 훑어서, 그때 홈에 어떤 할 일이 오는지 모은다.

시연은 늘 같은 화면이 떠야 해서 실제 오늘이 아니라 정해 둔 2주(DEMO_WEEK_START 부터 DEMO_DAYS 일)를 쓴다.
그 기간의 날마다, 가게 알림 시각(출근 후, 오후, 마감 전)마다 그 시각 5분 뒤의 계획을 새로 만들고(CLOVA 없이),
그 시각에 보내는 알림 묶음을 남긴다. 앱 홈은 서버 시계가 그 시각일 때 바로 이 묶음을 보여 준다.

목업 데이터가 같으니 결과도 늘 같다. 가게 하나에 몇 초가 걸려서 결과를 기억해 둔다.
  - 서버 메모리와 파일(server/db/app_data/demo_scans/<가게>.json, git 에 올라가지 않음) 두 곳에 둔다.
    서버를 다시 켜도 파일을 읽어 바로 쓴다.
  - 기억한 결과에는 '지문'을 붙인다: 가게 DB·공통 DB 파일의 크기와 고친 시각, 그 가게의 등록 정보(네이버 영업시간, 리뷰 플랫폼),
    사장님이 고친 설정, 계산 코드.
    하나라도 바뀌면 지문이 달라져 다시 훑는다.
  - 서버를 켤 때 모든 가게를 뒤에서 미리 훑는다 (prewarm, DEV_TOOLS_ENABLED=true 일 때만).
  - 훑는 동안 몇 개 시각까지 했는지 progress() 로 알 수 있다 (대시보드의 "n / 42").
"""

import dataclasses
import datetime as dt
import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

from app.core.seoul_time import at_time, to_seoul
from app.data_pipeline import read_store_db, registered_stores, store_snapshot_cache
from app.planner.data_shapes import NoticeItem, PlanItem
from db.session import COMMON_DB, DATA_DIR

logger = logging.getLogger(__name__)

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


SAVE_DIR = Path(__file__).resolve().parents[3] / "db" / "app_data" / "demo_scans"
APP_DIR = Path(__file__).resolve().parents[2]
# 계획 결과에 닿는 코드. 이 폴더의 .py 가 바뀌면 기억한 결과를 버린다
CODE_DIRS = ("analysis", "planner", "data_pipeline", "modules/dev_tools")

_scans: dict[str, tuple[str, WeekScan]] = {}  # 가게 → (지문, 결과)
_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}
_progress: dict[str, dict] = {}  # 가게 → {"done", "total"} (훑는 중일 때만)
_code_version: str | None = None


def _lock(store_id: str) -> threading.Lock:
    with _guard:
        return _locks.setdefault(store_id, threading.Lock())


def scan_week(store_id: str) -> WeekScan:
    """그 가게 시연 주간 훑기. 메모리 → 파일 → 새로 훑기 순서로 찾는다. 지문이 다르면 새로 훑는다."""
    with _lock(store_id):
        fingerprint = _fingerprint(store_id)
        kept = _scans.get(store_id)
        if kept and kept[0] == fingerprint:
            return kept[1]
        scan = _load(store_id, fingerprint)
        if scan is None:
            scan = _scan(store_id)
            _save(store_id, fingerprint, scan)
        _scans[store_id] = (fingerprint, scan)
        return scan


def is_ready(store_id: str) -> bool:
    """훑은 결과가 바로 있는지 (메모리나 파일에). 대시보드가 기다림 표시를 할지 정할 때 쓴다."""
    fingerprint = _fingerprint(store_id)
    kept = _scans.get(store_id)
    return bool(kept and kept[0] == fingerprint) or _saved_path(store_id, fingerprint) is not None


def progress() -> dict[str, dict]:
    """훑는 중인 가게와 몇 개 시각까지 했는지. 예) {"s001": {"done": 12, "total": 42}}"""
    return {store_id: dict(p) for store_id, p in _progress.items()}


def forget(store_id: str | None = None) -> None:
    """기억한 훑기 결과를 지운다 (메모리와 파일). 대시보드 '다시 훑기', 테스트."""
    targets = list(_scans) if store_id is None else [store_id]
    for sid in targets:
        _scans.pop(sid, None)
    if SAVE_DIR.is_dir():
        for path in SAVE_DIR.glob("*.json" if store_id is None else f"{store_id}.json"):
            path.unlink(missing_ok=True)


def prewarm() -> None:
    """모든 가게를 뒤에서 차례로 훑어 둔다 (서버를 켤 때 한 번). 대시보드에서 가게를 고르면 바로 열린다."""

    def run() -> None:
        for store_id in read_store_db.list_store_ids():
            try:
                scan_week(store_id)
            except Exception:  # 한 가게가 실패해도 다음 가게는 훑는다
                logger.exception("%s 시연 기간 미리 훑기 실패", store_id)

    threading.Thread(target=run, name="demo-prewarm", daemon=True).start()


# ── 지문과 파일 ──


def _code() -> str:
    """계획에 닿는 코드의 지문. 서버가 켜져 있는 동안은 한 번만 계산한다."""
    global _code_version
    if _code_version is None:
        digest = hashlib.sha256()
        for folder in CODE_DIRS:
            for path in sorted((APP_DIR / folder).rglob("*.py")):
                digest.update(str(path.relative_to(APP_DIR)).encode())
                digest.update(path.read_bytes())
        _code_version = digest.hexdigest()
    return _code_version


def _file_mark(path: Path) -> str:
    if not path.exists():
        return f"{path.name}:-"
    stat = path.stat()
    return f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}"


def _registry_part(store_id: str) -> str:
    """이 가게의 등록 정보 (사장님이 등록한 가게만 있다. 목업 가게는 빈 값)."""
    info = registered_stores.place_info(store_id)
    return json.dumps(
        [dataclasses.asdict(info) if info else None, sorted(registered_stores.review_platforms(store_id).items())],
        sort_keys=True, default=str, ensure_ascii=False,
    )


def _fingerprint(store_id: str) -> str:
    parts = [
        DEMO_WEEK_START.isoformat(),
        DEMO_DAYS,
        AFTER_SLOT.total_seconds(),
        _file_mark(DATA_DIR / f"{store_id}.db"),
        _file_mark(COMMON_DB),
        # 등록 기록 파일 전체가 아니라 이 가게 것만 본다 (다른 가게를 등록하거나 지워도 이 가게 결과는 그대로 쓴다)
        _registry_part(store_id),
        store_snapshot_cache.get_settings_changes(store_id),
        _code(),
    ]
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def _saved_path(store_id: str, fingerprint: str) -> Path | None:
    path = SAVE_DIR / f"{store_id}.json"
    try:
        return path if json.loads(path.read_text(encoding="utf-8")).get("fingerprint") == fingerprint else None
    except (OSError, ValueError):
        return None


def _save(store_id: str, fingerprint: str, scan: WeekScan) -> None:
    body = {
        "fingerprint": fingerprint,
        "store_id": store_id,
        "unavailable": scan.unavailable,
        "slots": [
            {
                "slot": slot.slot,
                "slot_at": slot.slot_at.isoformat(),
                "moment": slot.moment.isoformat(),
                "entries": [
                    {
                        "notify_kind": entry.notify_kind,
                        "plan": entry.plan.model_dump(mode="json") if entry.plan else None,
                        "notice": entry.notice.model_dump(mode="json") if entry.notice else None,
                    }
                    for entry in slot.entries
                ],
            }
            for slot in scan.slots
        ],
    }
    try:
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        temp = SAVE_DIR / f"{store_id}.json.tmp"
        temp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        temp.replace(SAVE_DIR / f"{store_id}.json")
    except OSError:  # 파일을 못 써도 메모리 결과는 쓴다
        logger.exception("%s 시연 훑기 결과를 파일에 남기지 못했다", store_id)


def _load(store_id: str, fingerprint: str) -> WeekScan | None:
    path = _saved_path(store_id, fingerprint)
    if path is None:
        return None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
        slots = [
            SeenSlot(
                slot["slot"],
                dt.datetime.fromisoformat(slot["slot_at"]),
                dt.datetime.fromisoformat(slot["moment"]),
                [
                    SeenEntry(
                        entry["notify_kind"],
                        plan=PlanItem.model_validate(entry["plan"]) if entry["plan"] else None,
                        notice=NoticeItem.model_validate(entry["notice"]) if entry["notice"] else None,
                    )
                    for entry in slot["entries"]
                ],
            )
            for slot in body["slots"]
        ]
        return WeekScan(store_id, slots, body["unavailable"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _scan(store_id: str) -> WeekScan:
    first_moment = at_time(DEMO_WEEK_START, "00:05")
    settings, _, unavailable = store_snapshot_cache.plan_only(store_id, first_moment)
    if settings is None:
        return WeekScan(store_id, unavailable=unavailable.message if unavailable else "계획을 만들지 못했어요")

    scan = WeekScan(store_id)
    slot_times = {name: getattr(settings.slots, name) for name in SLOT_ORDER}
    stops = [
        (name, at_time(day, slot_times[name]))
        for day in (DEMO_WEEK_START + dt.timedelta(days=offset) for offset in range(DEMO_DAYS))
        for name in SLOT_ORDER
    ]
    # DB 는 한 번만 읽고 시각마다 그때까지의 행으로 계획을 만든다 (시각마다 plan_only 를 부르던 것과 결과가 같다)
    _progress[store_id] = {"done": 0, "total": len(stops)}

    def step(done: int) -> None:
        _progress[store_id] = {"done": done, "total": len(stops)}

    try:
        plans = store_snapshot_cache.plan_at_times(store_id, [slot_at + AFTER_SLOT for _, slot_at in stops], on_step=step)
    finally:
        _progress.pop(store_id, None)
    for (name, slot_at), (_, plan, unavailable) in zip(stops, plans):
        moment = slot_at + AFTER_SLOT
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
