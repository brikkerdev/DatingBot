import csv
import json
import os
import sys


COLUMNS = [
    "run_id",
    "broker",
    "msg_size",
    "target_rate",
    "duration",
    "sent",
    "received",
    "lost",
    "send_errors",
    "consume_errors",
    "actual_rate_in",
    "actual_rate_out",
    "avg_latency_ms",
    "p50_ms",
    "p95_ms",
    "p99_ms",
    "max_ms",
    "peak_backlog",
]


def aggregate(raw_dir: str, out_csv: str) -> int:
    prod = {}
    cons = {}
    for name in sorted(os.listdir(raw_dir)):
        path = os.path.join(raw_dir, name)
        if not name.endswith(".json"):
            continue
        with open(path) as f:
            data = json.load(f)
        run_id = data.get("run_id")
        if name.endswith("_producer.json"):
            prod[run_id] = data
        elif name.endswith("_consumer.json"):
            cons[run_id] = data

    run_ids = sorted(set(prod) | set(cons))
    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for rid in run_ids:
            p = prod.get(rid, {})
            c = cons.get(rid, {})
            # Producer JSON may be missing (orchestrator cutoff); подтягиваем параметры из run_id.
            parts = rid.rsplit("_", 2)
            fallback_size = parts[-2] if len(parts) == 3 else ""
            fallback_rate = parts[-1] if len(parts) == 3 else ""
            sent = int(p.get("sent", 0))
            received = int(c.get("received", 0))
            row = {
                "run_id": rid,
                "broker": p.get("kind") or c.get("kind") or "",
                "msg_size": p.get("msg_size", fallback_size),
                "target_rate": p.get("target_rate", fallback_rate),
                "duration": p.get("duration") or c.get("duration") or "",
                "sent": sent,
                "received": received,
                "lost": max(0, sent - received),
                "send_errors": p.get("send_errors", 0),
                "consume_errors": c.get("consume_errors", 0),
                "actual_rate_in": round(float(p.get("actual_rate", 0.0)), 2),
                "actual_rate_out": round(float(c.get("actual_rate", 0.0)), 2),
                "avg_latency_ms": round(float(c.get("avg_latency_ms", 0.0)), 3),
                "p50_ms": round(float(c.get("p50_ms", 0.0)), 3),
                "p95_ms": round(float(c.get("p95_ms", 0.0)), 3),
                "p99_ms": round(float(c.get("p99_ms", 0.0)), 3),
                "max_ms": round(float(c.get("max_ms", 0.0)), 3),
                "peak_backlog": c.get("peak_backlog", 0),
            }
            w.writerow(row)
    return len(run_ids)


if __name__ == "__main__":
    raw = sys.argv[1] if len(sys.argv) > 1 else "results/raw"
    out = sys.argv[2] if len(sys.argv) > 2 else "results/summary.csv"
    n = aggregate(raw, out)
    print(f"Wrote {n} rows -> {out}")
