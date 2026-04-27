class CacheAside:
    """Read: cache → DB → cache. Write: DB only, invalidate cache (Write-Around)."""

    name = "cache_aside"

    def __init__(self, db, cache) -> None:
        self.db = db
        self.cache = cache

    def get(self, key: str):
        v = self.cache.get(key)
        if v is not None:
            return v
        v = self.db.get(key)
        if v is not None:
            self.cache.set(key, v)
        return v

    def set(self, key: str, value: str) -> None:
        self.db.upsert(key, value)
        self.cache.delete(key)

    def shutdown(self) -> None:
        pass
