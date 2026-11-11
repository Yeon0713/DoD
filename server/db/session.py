"""DB 연결. 다른 코드는 여기 engine / SessionLocal / store_engine 을 가져다 쓴다.

개발 DB 는 SQLite 파일이다 (git 에 같이 올라간다). 서버가 처음 DB 에 접속할 때 파일을 연다.
    db/data/common.db   공통 테이블 (events, games, weather_daily)
    db/data/s001.db     매장 전용 테이블. 's001' 이라는 이름으로 붙여 s001.orders 처럼 쓴다.
"""

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import sessionmaker

from db.models import STORE_SCHEMA

DATA_DIR = Path(__file__).parent / "data"
COMMON_DB = DATA_DIR / "common.db"


def store_db_files() -> list[Path]:
    """db/data 안의 매장 파일 (s001.db, s002.db ...)."""
    return sorted(DATA_DIR.glob("s[0-9][0-9][0-9].db"))


engine = create_engine(f"sqlite:///{COMMON_DB}")
SessionLocal = sessionmaker(engine)


@event.listens_for(engine, "connect")
def _on_connect(dbapi_conn, _record):
    """새 연결마다 외래 키 검사를 켜고 매장 파일을 붙인다."""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")
    for path in store_db_files():
        cur.execute("ATTACH DATABASE ? AS ?", (str(path), path.stem))
    cur.close()


def store_engine(store_id: str) -> Engine:
    """한 매장 전용 연결. 매장 테이블(models.Order 등)이 그 매장 테이블(예: s001.orders)을 가리킨다.

    공통 테이블(events, games, weather_daily)은 그대로 공통 DB 를 가리킨다.
        with store_engine("s001").connect() as conn:
            conn.execute(select(Order))  # → s001.orders
    """
    return engine.execution_options(schema_translate_map={STORE_SCHEMA: store_id})
