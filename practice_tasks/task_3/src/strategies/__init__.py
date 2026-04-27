from .cache_aside import CacheAside
from .write_through import WriteThrough
from .write_back import WriteBack


def make(name: str, db, cache, **kw):
    if name == "cache_aside":
        return CacheAside(db, cache)
    if name == "write_through":
        return WriteThrough(db, cache)
    if name == "write_back":
        return WriteBack(db, cache, **kw)
    raise ValueError(f"unknown strategy {name!r}")
