import json
import os
import random
import threading
import time

from cache import Cache
from db import Db
from rate_limiter import Pacer
from wait_for import wait_for
import strategies


def _percentile(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def _sample_dirty(cache: Cache, samples, stop_evt: threading.Event, interval: float, start_ts: float):
    while not stop_evt.is_set():
        try:
            n = cache.dirty_size()
        except Exception:
            n = -1
        samples.append({"t": round(time.perf_counter() - start_ts, 3), "dirty": n})
        stop_evt.wait(interval)


def run() -> None:
    pg_dsn = os.environ["PG_DSN"]
    redis_url = os.environ["REDIS_URL"]
    strategy_name = os.getenv("STRATEGY", "cache_aside")
    run_id = os.getenv("RUN_ID", "smoke")
    profile = os.getenv("PROFILE", "read_heavy")
    read_ratio = float(os.getenv("READ_RATIO", "0.8"))
    target_rps = float(os.getenv("TARGET_RPS", "2000"))
    duration = int(os.getenv("DURATION_SEC", "60"))
    key_space = int(os.getenv("KEY_SPACE", "10000"))
    value_size = int(os.getenv("VALUE_SIZE", "256"))
    cache_ttl = int(os.getenv("CACHE_TTL_SEC", "300"))
    flush_interval = float(os.getenv("FLUSH_INTERVAL_SEC", "1.0"))
    flush_batch = int(os.getenv("FLUSH_BATCH_SIZE", "500"))
    dirty_sample = float(os.getenv("DIRTY_SAMPLE_INTERVAL_SEC", "0.2"))

    print(f"[runner] run_id={run_id} strategy={strategy_name} profile={profile} "
          f"read_ratio={read_ratio} target_rps={target_rps} duration={duration}s "
          f"key_space={key_space} value_size={value_size}")

    db = Db(pg_dsn)
    cache = Cache(redis_url, ttl=cache_ttl)

    wait_for("postgres", db.ping)
    wait_for("redis", cache.ping)

    db.init_schema()
    db.truncate()
    cache.flushall()

    print("[runner] seeding DB...")
    db.seed(key_space, value_size)
    # Reset op counters after seed so they don't pollute test metrics.
    db.reads = 0
    db.writes = 0

    strat = strategies.make(
        strategy_name, db, cache,
        flush_interval=flush_interval, flush_batch=flush_batch,
    )
    if hasattr(strat, "start"):
        strat.start()

    rng = random.Random(42)
    write_value = "y" * value_size

    latencies_ms = []
    reads_done = 0
    writes_done = 0
    errors = 0

    pacer = Pacer(target_rps)
    start = time.perf_counter()
    deadline = start + duration

    dirty_samples = []
    stop_sampler = threading.Event()
    sampler_thread = None
    if strategy_name == "write_back":
        sampler_thread = threading.Thread(
            target=_sample_dirty,
            args=(cache, dirty_samples, stop_sampler, dirty_sample, start),
            daemon=True,
        )
        sampler_thread.start()

    i = 0
    while True:
        now = time.perf_counter()
        if now >= deadline:
            break
        pacer.wait(i)
        key = f"k{rng.randrange(key_space)}"
        is_read = rng.random() < read_ratio
        op_start = time.perf_counter()
        try:
            if is_read:
                strat.get(key)
                reads_done += 1
            else:
                strat.set(key, write_value)
                writes_done += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"[runner] op error: {e}")
        op_lat_ms = (time.perf_counter() - op_start) * 1000.0
        latencies_ms.append(op_lat_ms)
        i += 1

    elapsed = time.perf_counter() - start
    if sampler_thread is not None:
        stop_sampler.set()
        sampler_thread.join(timeout=2)

    # For write-back: track flushed during workload separately from drain.
    flushed_during = getattr(strat, "flushed_total", 0)
    drain_count = 0
    if hasattr(strat, "drain"):
        # Stop background loop and drain remaining dirty entries.
        if hasattr(strat, "_stop"):
            strat._stop.set()
        drain_count = strat.drain()
    if hasattr(strat, "shutdown"):
        strat.shutdown()

    total = reads_done + writes_done
    throughput = total / elapsed if elapsed > 0 else 0.0
    latencies_sorted = sorted(latencies_ms)
    avg_lat = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0
    p50 = _percentile(latencies_sorted, 0.50)
    p95 = _percentile(latencies_sorted, 0.95)
    p99 = _percentile(latencies_sorted, 0.99)
    max_lat = latencies_sorted[-1] if latencies_sorted else 0.0

    hits = cache.hits
    misses = cache.misses
    hit_rate = hits / (hits + misses) if (hits + misses) > 0 else 0.0

    out = {
        "run_id": run_id,
        "strategy": strategy_name,
        "profile": profile,
        "read_ratio": read_ratio,
        "target_rps": target_rps,
        "duration": duration,
        "elapsed": round(elapsed, 3),
        "total_reqs": total,
        "reads": reads_done,
        "writes": writes_done,
        "errors": errors,
        "throughput_rps": round(throughput, 2),
        "avg_latency_ms": round(avg_lat, 3),
        "p50_ms": round(p50, 3),
        "p95_ms": round(p95, 3),
        "p99_ms": round(p99, 3),
        "max_ms": round(max_lat, 3),
        "cache_hits": hits,
        "cache_misses": misses,
        "hit_rate": round(hit_rate, 4),
        "db_reads": db.reads,
        "db_writes": db.writes,
        "wb_flushed_during": flushed_during,
        "wb_drained_at_end": drain_count,
    }

    os.makedirs("results/raw", exist_ok=True)
    with open(f"results/raw/{run_id}.json", "w") as f:
        json.dump(out, f, indent=2)
    if dirty_samples:
        with open(f"results/raw/{run_id}_dirty.json", "w") as f:
            json.dump({"run_id": run_id, "samples": dirty_samples}, f)

    print(f"[runner] done: {out}")

    cache.close()
    db.close()


if __name__ == "__main__":
    run()
