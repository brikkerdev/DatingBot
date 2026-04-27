import threading
import time


class WriteBack:
    """Read: cache → DB → cache. Write: cache + dirty_set; background flusher writes to DB."""

    name = "write_back"

    def __init__(self, db, cache, flush_interval: float = 1.0, flush_batch: int = 500) -> None:
        self.db = db
        self.cache = cache
        self.flush_interval = flush_interval
        self.flush_batch = flush_batch
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self.flushed_total = 0

    def start(self) -> None:
        self._thread.start()

    def get(self, key: str):
        v = self.cache.get(key)
        if v is not None:
            return v
        v = self.db.get(key)
        if v is not None:
            self.cache.set(key, v)
        return v

    def set(self, key: str, value: str) -> None:
        # Cache write + mark dirty. DB stays untouched until flusher runs.
        self.cache.set(key, value)
        self.cache.sadd_dirty(key)

    def _flush_once(self) -> int:
        keys = self.cache.pop_dirty_batch(self.flush_batch)
        if not keys:
            return 0
        values = self.cache.mget(keys)
        items = [(k, v) for k, v in zip(keys, values) if v is not None]
        n = self.db.upsert_many(items)
        self.flushed_total += n
        return n

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._flush_once()
            except Exception as e:
                print(f"[write_back] flush error: {e}")
            self._stop.wait(self.flush_interval)

    def drain(self) -> int:
        total = 0
        while True:
            n = self._flush_once()
            total += n
            if n < self.flush_batch:
                break
        return total

    def shutdown(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)
        # Final drain so DB is consistent at end of run.
        try:
            self.drain()
        except Exception as e:
            print(f"[write_back] drain error: {e}")
