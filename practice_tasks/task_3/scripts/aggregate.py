import csv
import json
import os
import sys


COLUMNS = [
    "run_id",
    "strategy",
    "profile",
    "read_ratio",
    "target_rps",
    "duration",
    "elapsed",
    "total_reqs",
    "reads",
    "writes",
    "throughput_rps",
    "avg_latency_ms",
    "p50_ms",
    "p95_ms",
    "p99_ms",
    "max_ms",
    "cache_hits",
    "cache_misses",
    "hit_rate",
    "db_reads",
    "db_writes",
    "wb_flushed_during",
    "wb_drained_at_end",
    "errors",
]


PRETTY_COLS = [
    ("strategy", "strategy", 14),
    ("profile", "profile", 12),
    ("throughput_rps", "rps", 9),
    ("avg_latency_ms", "avg ms", 8),
    ("p95_ms", "p95 ms", 8),
    ("p99_ms", "p99 ms", 8),
    ("hit_rate", "hit", 6),
    ("db_reads", "db_reads", 9),
    ("db_writes", "db_writes", 10),
    ("wb_flushed_during", "wb_flush", 9),
    ("wb_drained_at_end", "wb_drain", 9),
]


def aggregate(raw_dir: str, out_csv: str) -> int:
    rows = []
    for name in sorted(os.listdir(raw_dir)):
        if not name.endswith(".json") or name.endswith("_dirty.json"):
            continue
        with open(os.path.join(raw_dir, name)) as f:
            data = json.load(f)
        rows.append({k: data.get(k, "") for k in COLUMNS})
    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for row in rows:
            w.writerow(row)
    return len(rows)


def _profile_order(p):
    return {"read_heavy": 0, "balanced": 1, "write_heavy": 2}.get(p, 99)


def print_summary(out_csv: str) -> None:
    with open(out_csv) as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: (r["strategy"], _profile_order(r["profile"])))

    header = " | ".join(name.ljust(w) for _, name, w in PRETTY_COLS)
    sep = "-+-".join("-" * w for _, _, w in PRETTY_COLS)
    print()
    print("===== RESULTS =====")
    print(header)
    print(sep)
    last_strategy = None
    for r in rows:
        if last_strategy is not None and r["strategy"] != last_strategy:
            print(sep)
        cells = []
        for key, _, w in PRETTY_COLS:
            v = r.get(key, "")
            if key in ("throughput_rps", "avg_latency_ms", "p95_ms", "p99_ms"):
                try:
                    v = f"{float(v):.2f}"
                except (TypeError, ValueError):
                    pass
            elif key == "hit_rate":
                try:
                    v = f"{float(v):.2f}"
                except (TypeError, ValueError):
                    pass
            cells.append(str(v).ljust(w))
        print(" | ".join(cells))
        last_strategy = r["strategy"]
    print()


if __name__ == "__main__":
    raw = sys.argv[1] if len(sys.argv) > 1 else "results/raw"
    out = sys.argv[2] if len(sys.argv) > 2 else "results/summary.csv"
    n = aggregate(raw, out)
    print(f"Wrote {n} rows -> {out}")
    print_summary(out)
