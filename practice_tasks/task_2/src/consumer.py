import json
import os
import threading
import time

import payload
from broker import make_broker
from wait_for import wait_for


def _percentile(sorted_vals, p: float):
    if not sorted_vals:
        return 0
    idx = int(round((len(sorted_vals) - 1) * p))
    return sorted_vals[idx]


def run() -> None:
    kind = os.getenv("BROKER_KIND", "rabbit")
    url = os.getenv("BROKER_URL", "")
    queue = os.getenv("QUEUE_NAME", "bench")
    run_id = os.getenv("RUN_ID", "smoke")
    duration = int(os.getenv("DURATION_SEC", "30"))
    grace = int(os.getenv("GRACE_SEC", "5"))

    print(f"[consumer] run_id={run_id} kind={kind} duration={duration} grace={grace}")

    broker = make_broker(kind, url, queue)
    wait_for(broker)
    broker.declare()
    broker.start_consuming()

    # Поток-семплер глубины очереди (отдельное подключение).
    depth_samples: list[int] = []
    stop_flag = threading.Event()

    def sampler():
        mon = make_broker(kind, url, queue)
        try:
            mon.connect()
        except Exception as e:
            print(f"[sampler] connect failed: {e}")
            return
        while not stop_flag.is_set():
            try:
                depth_samples.append(mon.queue_depth())
            except Exception:
                pass
            time.sleep(1.0)
        try:
            mon.close()
        except Exception:
            pass

    t = threading.Thread(target=sampler, daemon=True)
    t.start()

    latencies_ns: list[int] = []
    errors = 0
    received = 0
    start = time.perf_counter()
    # Жёсткий верхний предел: длительность + щедрый буфер на дренаж очереди.
    hard_deadline = start + duration + grace + 60
    idle_budget_s = float(grace)
    last_msg_t = time.perf_counter()

    while True:
        now = time.perf_counter()
        if now > hard_deadline:
            print("[consumer] hard deadline reached")
            break
        if received > 0 and (now - last_msg_t) > idle_budget_s:
            print(f"[consumer] idle >{idle_budget_s}s after receiving, stopping")
            break
        try:
            tag, body = broker.consume(1.0)
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"[consumer] consume error: {e}")
            continue
        if body is None:
            continue
        try:
            _seq, send_ts_ns = payload.parse(body)
            lat = time.time_ns() - send_ts_ns
            latencies_ns.append(lat)
            received += 1
            last_msg_t = time.perf_counter()
            broker.ack(tag)
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"[consumer] parse/ack error: {e}")

    stop_flag.set()
    t.join(timeout=2.0)
    broker.close()

    elapsed = time.perf_counter() - start
    actual_rate = received / elapsed if elapsed > 0 else 0.0

    latencies_ns.sort()
    avg_ns = sum(latencies_ns) // len(latencies_ns) if latencies_ns else 0
    p50 = _percentile(latencies_ns, 0.50)
    p95 = _percentile(latencies_ns, 0.95)
    p99 = _percentile(latencies_ns, 0.99)
    mx = latencies_ns[-1] if latencies_ns else 0
    peak_backlog = max(depth_samples) if depth_samples else 0

    out = {
        "run_id": run_id,
        "kind": kind,
        "duration": duration,
        "received": received,
        "consume_errors": errors,
        "actual_rate": actual_rate,
        "wall_time": elapsed,
        "avg_latency_ms": avg_ns / 1e6,
        "p50_ms": p50 / 1e6,
        "p95_ms": p95 / 1e6,
        "p99_ms": p99 / 1e6,
        "max_ms": mx / 1e6,
        "peak_backlog": peak_backlog,
        "depth_samples": depth_samples,
    }
    os.makedirs("results/raw", exist_ok=True)
    path = f"results/raw/{run_id}_consumer.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(
        f"[consumer] done: received={received} avg={out['avg_latency_ms']:.2f}ms "
        f"p95={out['p95_ms']:.2f}ms peak_backlog={peak_backlog}"
    )
