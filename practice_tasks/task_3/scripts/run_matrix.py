"""Run 3 strategies x 3 profiles. For each cell: compose up runner, wait exit, save metrics."""

import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
COMPOSE = os.path.join(ROOT, "docker-compose.yml")

STRATEGIES_DEFAULT = ["cache_aside", "write_through", "write_back"]
PROFILES_DEFAULT = [
    ("read_heavy", 0.8),
    ("balanced", 0.5),
    ("write_heavy", 0.2),
]
DURATION_DEFAULT = 60
TARGET_RPS_DEFAULT = 2000
KEY_SPACE_DEFAULT = 10000
VALUE_SIZE_DEFAULT = 256


def project_name(strategy: str) -> str:
    return f"cache_bench_{strategy}"


def run_cell(strategy: str, profile: str, read_ratio: float,
             duration: int, target_rps: int, key_space: int, value_size: int) -> int:
    run_id = f"{strategy}_{profile}"
    env = os.environ.copy()
    env.update({
        "STRATEGY": strategy,
        "PROFILE": profile,
        "READ_RATIO": str(read_ratio),
        "RUN_ID": run_id,
        "DURATION_SEC": str(duration),
        "TARGET_RPS": str(target_rps),
        "KEY_SPACE": str(key_space),
        "VALUE_SIZE": str(value_size),
    })
    project = project_name(strategy)
    base = ["docker", "compose", "-p", project, "-f", COMPOSE]

    print(f"\n===== {run_id} =====")
    r = subprocess.run(base + ["up", "-d", "--build"], env=env, cwd=ROOT)
    if r.returncode != 0:
        subprocess.run(base + ["down", "-v"], env=env, cwd=ROOT)
        return r.returncode

    try:
        cid = subprocess.check_output(
            base + ["ps", "-q", "runner"], env=env, cwd=ROOT
        ).decode().strip().splitlines()[0]
    except Exception as e:
        print(f"[run_matrix] cannot find runner container: {e}")
        subprocess.run(base + ["down", "-v"], env=env, cwd=ROOT)
        return 1

    ceiling = duration + 180
    start = time.time()
    wait_proc = subprocess.Popen(["docker", "wait", cid])
    while wait_proc.poll() is None:
        if time.time() - start > ceiling:
            print(f"[run_matrix] ceiling exceeded for {run_id}, killing")
            wait_proc.kill()
            break
        time.sleep(1)

    subprocess.run(base + ["logs", "--tail", "60", "runner"], env=env, cwd=ROOT)
    subprocess.run(base + ["down", "-v"], env=env, cwd=ROOT)
    return 0


def aggregate() -> None:
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import aggregate as agg
    raw = os.path.join(ROOT, "results", "raw")
    out = os.path.join(ROOT, "results", "summary.csv")
    n = agg.aggregate(raw, out)
    print(f"\nAggregated {n} runs -> {out}")
    agg.print_summary(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--only-strategy", action="append", default=[])
    ap.add_argument("--only-profile", action="append", default=[])
    ap.add_argument("--duration", type=int, default=DURATION_DEFAULT)
    ap.add_argument("--rps", type=int, default=TARGET_RPS_DEFAULT)
    ap.add_argument("--key-space", type=int, default=KEY_SPACE_DEFAULT)
    ap.add_argument("--value-size", type=int, default=VALUE_SIZE_DEFAULT)
    args = ap.parse_args()

    strategies = args.only_strategy or STRATEGIES_DEFAULT
    profiles = [(n, r) for n, r in PROFILES_DEFAULT
                if not args.only_profile or n in args.only_profile]

    if args.quick:
        duration = 15
    else:
        duration = args.duration

    print(f"Matrix: strategies={strategies} profiles={[p[0] for p in profiles]} "
          f"duration={duration}s rps={args.rps} key_space={args.key_space}")

    total = len(strategies) * len(profiles)
    n = 0
    for s in strategies:
        for pname, ratio in profiles:
            n += 1
            print(f"\n[{n}/{total}]")
            run_cell(s, pname, ratio, duration, args.rps, args.key_space, args.value_size)

    aggregate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
