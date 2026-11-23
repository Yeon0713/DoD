"""PostgreSQL connections and the initial voice schema for deployed environments."""

from contextlib import contextmanager
from functools import lru_cache

from voice import config


class Connection:
    """Adapt the voice repository's static qmark SQL to the psycopg driver."""

    def __init__(self, connection, *, named: bool):
        from psycopg.rows import dict_row

        self.connection = connection
        self.row_factory = dict_row if named else None

    def execute(self, sql: str, params=()):
        cursor = self.connection.cursor(row_factory=self.row_factory)
        return cursor.execute(sql.replace("?", "%s"), params)

    def executemany(self, sql: str, params):
        with self.connection.cursor() as cursor:
            cursor.executemany(sql.replace("?", "%s"), params)


@lru_cache(maxsize=1)
def pool(url: str):
    from psycopg_pool import ConnectionPool

    result = ConnectionPool(
        url, kwargs={"options": "-c search_path=donna_voice", "connect_timeout": 5},
        min_size=1, max_size=4, timeout=8, open=False,
    )
    result.open(wait=True, timeout=8)
    return result


@contextmanager
def connect(*, named: bool = False):
    with pool(config.DATABASE_URL).connection() as connection:
        yield Connection(connection, named=named)


def initialize() -> None:
    from voice.repo import STAFF_TABLES

    if not config.DATABASE_URL:
        raise SystemExit("Set VOICE_DATABASE_URL before initializing PostgreSQL.")
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS docs (
                rowid bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
                kind text NOT NULL, id text NOT NULL, store_id text, data jsonb NOT NULL,
                PRIMARY KEY (kind, id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS docs_store_kind ON docs (store_id, kind, rowid)")
        conn.execute("CREATE TABLE IF NOT EXISTS counters (name text PRIMARY KEY, value bigint NOT NULL)")
        for table, columns in STAFF_TABLES.items():
            conn.execute(f"CREATE TABLE IF NOT EXISTS {table} (rowid bigint GENERATED ALWAYS AS IDENTITY UNIQUE, {columns})")


if __name__ == "__main__":
    initialize()
