import json
import os
import time

import payload
from broker import make_broker
from rate_limiter import Pacer
from wait_for import wait_for


def run() -> None:
    kind = os.getenv("BROKER_KIND", "rabbit")
    url = os.getenv("BROKER_URL", "")
    queue = os.getenv("QUEUE_NAME", "bench")
    run_id = os.getenv("RUN_ID", "smoke")
    msg_size = int(os.getenv("MSG_SIZE", "1024"))
    rate = int(os.getenv("RATE", "1000"))
    duration = int(os.getenv("DURATION_SEC", "30"))
    warmup = float(os.getenv("WARMUP_SEC", "2"))

    print(f"[producer] run_id={run_id} kind={kind} size={msg_size} rate={rate} duration={duration}")

    broker = make_broker(kind, url, queue)
    wait_for(broker)
    broker.declare()

    # Пауза, чтобы consumer успел объявить очередь до первого publish.
    if warmup > 0:
        time.sleep(warmup)

    sent = 0
    errors = 0
    pacer = Pacer(rate)
    start = time.perf_counter()
    deadline = start + duration

    i = 0
    while time.perf_counter() < deadline:
        pacer.wait(i)
        try:
            broker.publish(payload.build(i, msg_size))
            sent += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"[producer] publish error: {e}")
        i += 1

    elapsed = time.perf_counter() - start
    actual_rate = sent / elapsed if elapsed > 0 else 0.0
    broker.close()

    out = {
        "run_id": run_id,
        "kind": kind,
        "msg_size": msg_size,
        "target_rate": rate,
        "duration": duration,
        "sent": sent,
        "send_errors": errors,
        "actual_rate": actual_rate,
        "wall_time": elapsed,
    }
    os.makedirs("results/raw", exist_ok=True)
    path = f"results/raw/{run_id}_producer.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"[producer] done: {out}")
