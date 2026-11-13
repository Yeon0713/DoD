"""등록한 가게 날씨를 3시간마다 새로 받는다.

서버가 켜져 있는 동안 백그라운드 스레드가 10분마다 등록한 가게를 훑어, 마지막으로 받은 지 3시간이 지난 가게만 다시 받는다
(app/main.py 가 서버를 켤 때 시작한다. KMA_API_KEY 가 비어 있으면 켜지 않는다).
마지막으로 받은 시각은 가게 파일(store_weather_fetch)에 있어서 서버를 다시 켜도 간격이 이어지고,
키를 넣기 전에 등록한 가게도 다음 확인 때 채워진다.

서버를 여러 개(worker 여러 개) 켜면 서버마다 따로 받는다. 지금 개발 서버는 하나라 괜찮다.
"""

import datetime as dt
import logging
import threading

from app.core.seoul_time import SEOUL
from app.data_pipeline import read_store_db
from app.data_pipeline.store_snapshot_cache import save_settings_changes
from app.weather import store_weather
from app.weather.client import KmaError

logger = logging.getLogger(__name__)

REFRESH_EVERY = dt.timedelta(hours=3)
CHECK_EVERY_SECONDS = 600


def refresh_store(store_id: str) -> bool:
    """한 가게 날씨를 받아 저장하고, 새 날씨로 달력을 다시 계산하게 한다. 실패하면 기록만 남기고 False."""
    try:
        store_weather.update_store_weather(store_id)
    except KmaError as error:
        logger.warning("가게 %s 날씨를 받지 못했어요: %s", store_id, error)
        return False
    save_settings_changes(store_id, {})
    return True


def stores_due(now: dt.datetime) -> list[str]:
    """날씨를 받을 때가 된 가게: 받은 적이 없거나 마지막으로 받은 지 REFRESH_EVERY 가 지났다."""
    due = []
    for store_id in read_store_db.list_store_ids():
        if not store_weather.can_fetch(store_id):
            continue
        fetch = read_store_db.read_store_weather_fetch(store_id)
        if fetch is None or now - fetch["fetched_at"] >= REFRESH_EVERY:
            due.append(store_id)
    return due


def refresh_due(now: dt.datetime | None = None) -> list[str]:
    """때가 된 가게를 모두 새로 받는다. 받은 가게 id 를 돌려준다."""
    # 기상청 자료는 실제 시각 기준이라 개발용 시계 앞당김(now_seoul)은 쓰지 않는다
    now = now or dt.datetime.now(SEOUL)
    return [store_id for store_id in stores_due(now) if refresh_store(store_id)]


class AutoRefresh:
    def __init__(self, check_every: float = CHECK_EVERY_SECONDS):
        self._check_every = check_every
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="weather-auto-refresh", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                refresh_due()
            except Exception:  # 한 번 실패해도 다음 확인은 계속한다
                logger.exception("날씨 자동 새로 고침 중 오류")
            self._stop.wait(self._check_every)
