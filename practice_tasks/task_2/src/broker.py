from abc import ABC, abstractmethod
from typing import Optional, Tuple


class Broker(ABC):
    """Единый контракт для RabbitMQ и Redis (LIST-очередь).

    Consume возвращает (tag, body). Tag нужен для ack у RabbitMQ;
    для Redis LIST всегда None (BLPOP удаляет атомарно).
    """

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def declare(self) -> None:
        """Идемпотентно создать очередь."""

    @abstractmethod
    def publish(self, body: bytes) -> None: ...

    @abstractmethod
    def start_consuming(self) -> None:
        """Настроить consumer-состояние (если нужно)."""

    @abstractmethod
    def consume(self, timeout_s: float) -> Tuple[Optional[object], Optional[bytes]]:
        """Получить одно сообщение или (None, None) по таймауту."""

    @abstractmethod
    def ack(self, tag: Optional[object]) -> None: ...

    @abstractmethod
    def queue_depth(self) -> int: ...

    @abstractmethod
    def close(self) -> None: ...


def make_broker(kind: str, url: str, queue: str) -> Broker:
    kind = (kind or "").lower()
    if kind == "rabbit":
        from rabbit_client import RabbitClient
        return RabbitClient(url, queue)
    if kind == "redis":
        from redis_client import RedisClient
        return RedisClient(url, queue)
    raise ValueError(f"Unknown BROKER_KIND: {kind!r}")
