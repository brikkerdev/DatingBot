import threading

import psycopg


SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


class Db:
    """Thin psycopg wrapper with manual op counters.

    psycopg connection is not thread-safe for concurrent use; in particular
    `executemany` enters pipeline mode and conflicts with any other op on
    the same connection. Write-Back's flusher runs in a background thread
    while the main thread still issues `get`/`upsert`, so every method
    here serialises access through `self._lock`.
    """

    def __init__(self, dsn: str) -> None:
        self.conn = psycopg.connect(dsn, autocommit=True)
        self._lock = threading.Lock()
        self.reads = 0
        self.writes = 0

    def init_schema(self) -> None:
        with self._lock, self.conn.cursor() as cur:
            cur.execute(SCHEMA)

    def truncate(self) -> None:
        with self._lock, self.conn.cursor() as cur:
            cur.execute("TRUNCATE items")

    def seed(self, key_space: int, value_size: int) -> None:
        value = "x" * value_size
        with self._lock, self.conn.cursor() as cur:
            with cur.copy("COPY items (key, value) FROM STDIN") as copy:
                for i in range(key_space):
                    copy.write_row((f"k{i}", value))

    def get(self, key: str):
        with self._lock:
            self.reads += 1
            with self.conn.cursor() as cur:
                cur.execute("SELECT value FROM items WHERE key = %s", (key,))
                row = cur.fetchone()
            return row[0] if row else None

    def upsert(self, key: str, value: str) -> None:
        with self._lock:
            self.writes += 1
            with self.conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO items (key, value, updated_at) VALUES (%s, %s, NOW()) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()",
                    (key, value),
                )

    def upsert_many(self, items) -> int:
        items = list(items)
        if not items:
            return 0
        with self._lock:
            self.writes += len(items)
            with self.conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO items (key, value, updated_at) VALUES (%s, %s, NOW()) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()",
                    items,
                )
            return len(items)

    def ping(self) -> None:
        with self._lock, self.conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()

    def close(self) -> None:
        with self._lock:
            self.conn.close()
