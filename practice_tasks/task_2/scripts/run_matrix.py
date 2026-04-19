"""Оркестратор прогонов: matrix = brokers × sizes × rates.

Для каждой ячейки поднимает compose-стек, ждёт завершения consumer,
гасит стек с -v. В конце агрегирует результаты в results/summary.csv.
"""

import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

COMPOSE_RABBIT = os.path.join(ROOT, "docker-compose.rabbit.yml")
COMPOSE_REDIS = os.path.join(ROOT, "docker-compose.redis.yml")

BROKERS_DEFAULT = ["rabbit", "redis"]
SIZES_DEFAULT = [128, 1024, 10240, 102400]
RATES_DEFAULT = [1000, 5000, 10000]
DURATION_DEFAULT = 30
GRACE_DEFAULT = 5
WARMUP_DEFAULT = 2


def compose_file(broker: str) -> str:
    if broker == "rabbit":
        return COMPOSE_RABBIT
    if broker == "redis":
        return COMPOSE_REDIS
    raise ValueError(f"unknown broker {broker}")


def project_name(broker: str) -> str:
    # Уникальный project-name для чистой изоляции томов/сетей.
    return f"bench_{broker}"


def run_cell(broker: str, size: int, rate: int, duration: int, grace: int, warmup: int) -> int:
    run_id = f"{broker}_{size}_{rate}"
    env = os.environ.copy()
    env.update({
        "RUN_ID": run_id,
        "MSG_SIZE": str(size),
        "RATE": str(rate),
        "DURATION_SEC": str(duration),
        "GRACE_SEC": str(grace),
        "WARMUP_SEC": str(warmup),
        "BROKER_KIND": broker,
    })
    compose = compose_file(broker)
    project = project_name(broker)
    base = ["docker", "compose", "-p", project, "-f", compose]

    print(f"\n===== run {run_id} =====")
    # Поднимаем detached.
    r = subprocess.run(base + ["up", "-d", "--build"], env=env, cwd=ROOT)
    if r.returncode != 0:
        print(f"[run_matrix] compose up failed for {run_id}")
        subprocess.run(base + ["down", "-v"], env=env, cwd=ROOT)
        return r.returncode

    # Находим id контейнера consumer и ждём его exit.
    try:
        cid = subprocess.check_output(
            base + ["ps", "-q", "consumer"], env=env, cwd=ROOT
        ).decode().strip().splitlines()[0]
    except Exception as e:
        print(f"[run_matrix] cannot find consumer container: {e}")
        subprocess.run(base + ["down", "-v"], env=env, cwd=ROOT)
        return 1

    # Hard ceiling на случай подвисшего consumer: duration + grace + buffer.
    ceiling = duration + grace + 120
    start = time.time()
    wait_proc = subprocess.Popen(["docker", "wait", cid])
    while wait_proc.poll() is None:
        if time.time() - start > ceiling:
            print(f"[run_matrix] ceiling exceeded for {run_id}, killing")
            wait_proc.kill()
            break
        time.sleep(1)

    # Логи для отладки (tail).
    subprocess.run(base + ["logs", "--tail", "50", "consumer"], env=env, cwd=ROOT)
    subprocess.run(base + ["logs", "--tail", "20", "producer"], env=env, cwd=ROOT)

    # Гасим и чистим state.
    subprocess.run(base + ["down", "-v"], env=env, cwd=ROOT)
    return 0


def aggregate() -> None:
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import metrics
    raw = os.path.join(ROOT, "results", "raw")
    out = os.path.join(ROOT, "results", "summary.csv")
    n = metrics.aggregate(raw, out)
    print(f"\nAggregated {n} runs -> {out}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="Reduced matrix for smoke test")
    ap.add_argument("--only", action="append", default=[],
                    help="Broker to run (repeatable): rabbit | redis")
    ap.add_argument("--duration", type=int, default=DURATION_DEFAULT)
    args = ap.parse_args()

    if args.quick:
        brokers = args.only or ["rabbit", "redis"]
        sizes = [128, 10240]
        rates = [1000, 5000]
        duration = 15
    else:
        brokers = args.only or BROKERS_DEFAULT
        sizes = SIZES_DEFAULT
        rates = RATES_DEFAULT
        duration = args.duration

    print(f"Matrix: brokers={brokers} sizes={sizes} rates={rates} duration={duration}s")

    total = len(brokers) * len(sizes) * len(rates)
    n = 0
    for broker in brokers:
        for size in sizes:
            for rate in rates:
                n += 1
                print(f"\n[{n}/{total}]")
                run_cell(broker, size, rate, duration, GRACE_DEFAULT, WARMUP_DEFAULT)

    aggregate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
