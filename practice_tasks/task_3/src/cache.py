import redis


class Cache:
    """Redis wrapper with hit/miss counters."""

    def __init__(self, url: str, ttl: int) -> None:
        self.r = redis.Redis.from_url(url, decode_responses=True)
        self.ttl = ttl
        self.hits = 0
        self.misses = 0

    def get(self, key: str):
        v = self.r.get(key)
        if v is None:
            self.misses += 1
        else:
            self.hits += 1
        return v

    def set(self, key: str, value: str, ttl: int = None) -> None:
        self.r.set(key, value, ex=ttl if ttl is not None else self.ttl)

    def delete(self, key: str) -> None:
        self.r.delete(key)

    def sadd_dirty(self, key: str) -> None:
        self.r.sadd("dirty_set", key)

    def dirty_size(self) -> int:
        return int(self.r.scard("dirty_set"))

    def pop_dirty_batch(self, n: int):
        # SPOP returns up to n random members and removes them atomically.
        members = self.r.spop("dirty_set", n)
        if not members:
            return []
        if isinstance(members, (str, bytes)):
            members = [members]
        return list(members)

    def mget(self, keys):
        return self.r.mget(keys)

    def flushall(self) -> None:
        self.r.flushdb()

    def ping(self) -> None:
        self.r.ping()

    def close(self) -> None:
        self.r.close()
