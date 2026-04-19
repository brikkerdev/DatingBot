from typing import Optional, Tuple

import pika

from broker import Broker


class RabbitClient(Broker):
    def __init__(self, url: str, queue: str) -> None:
        self.url = url
        self.queue = queue
        self.conn: Optional[pika.BlockingConnection] = None
        self.ch = None
        self._consume_gen = None

    def connect(self) -> None:
        params = pika.URLParameters(self.url)
        params.heartbeat = 60
        params.blocked_connection_timeout = 30
        self.conn = pika.BlockingConnection(params)
        self.ch = self.conn.channel()

    def declare(self) -> None:
        self.ch.queue_declare(queue=self.queue, durable=True)

    def publish(self, body: bytes) -> None:
        self.ch.basic_publish(
            exchange="",
            routing_key=self.queue,
            body=body,
            properties=pika.BasicProperties(delivery_mode=2),
        )

    def start_consuming(self) -> None:
        self.ch.basic_qos(prefetch_count=256)
        self._consume_gen = self.ch.consume(
            queue=self.queue,
            inactivity_timeout=1.0,
            auto_ack=False,
        )

    def consume(self, timeout_s: float) -> Tuple[Optional[object], Optional[bytes]]:
        try:
            item = next(self._consume_gen)
        except StopIteration:
            return None, None
        if item is None:
            return None, None
        method, _props, body = item
        if method is None:
            return None, None
        return method.delivery_tag, body

    def ack(self, tag) -> None:
        if tag is not None:
            self.ch.basic_ack(delivery_tag=tag)

    def queue_depth(self) -> int:
        res = self.ch.queue_declare(queue=self.queue, durable=True, passive=True)
        return int(res.method.message_count)

    def close(self) -> None:
        try:
            if self._consume_gen is not None and self.ch is not None:
                self.ch.cancel()
        except Exception:
            pass
        try:
            if self.conn is not None and self.conn.is_open:
                self.conn.close()
        except Exception:
            pass
