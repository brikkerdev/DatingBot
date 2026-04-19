from typing import Optional, Tuple

import redis

from broker import Broker


class RedisClient(Broker):
    def __init__(self, url: str, queue: str) -> None:
        self.url = url
        self.queue = queue
        self.r: Optional[redis.Redis] = None

    def connect(self) -> None:
        self.r = redis.Redis.from_url(self.url)
        self.r.ping()

    def declare(self) -> None:
        # LIST не требует декларации.
        pass

    def publish(self, body: bytes) -> None:
        self.r.rpush(self.queue, body)

    def start_consuming(self) -> None:
        pass

    def consume(self, timeout_s: float) -> Tuple[Optional[object], Optional[bytes]]:
        # BLPOP таймаут в секундах, >=1.
        res = self.r.blpop([self.queue], timeout=max(1, int(timeout_s)))
        if res is None:
            return None, None
        _, body = res
        return None, body

    def ack(self, tag) -> None:
        # BLPOP удаляет элемент атомарно, ack не нужен.
        pass

    def queue_depth(self) -> int:
        return int(self.r.llen(self.queue))

    def close(self) -> None:
        try:
            if self.r is not None:
                self.r.close()
        except Exception:
            pass
