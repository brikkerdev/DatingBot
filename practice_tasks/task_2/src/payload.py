import struct
import time

HEADER = struct.Struct(">QQ")
HEADER_SIZE = HEADER.size  # 16


def build(seq: int, size: int) -> bytes:
    size = max(size, HEADER_SIZE)
    ts = time.time_ns()
    head = HEADER.pack(seq, ts)
    if size == HEADER_SIZE:
        return head
    return head + b"\x00" * (size - HEADER_SIZE)


def parse(body: bytes) -> tuple[int, int]:
    if len(body) < HEADER_SIZE:
        raise ValueError(f"payload too short: {len(body)}")
    seq, ts = HEADER.unpack_from(body, 0)
    return seq, ts
