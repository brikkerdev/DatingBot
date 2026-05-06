"""
Run all SQL isolation anomaly tests.
"""

import asyncio
import sys
import os
from pathlib import Path

log_file = Path("/app/results/run.log")
log_file.parent.mkdir(parents=True, exist_ok=True)

def log(msg: str):
    with open(log_file, "a") as f:
        f.write(msg + "\n")

log(f"Python: {sys.version}")
log(f"CWD: {os.getcwd()}")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from isolated_tx import run_all_anomalies

if __name__ == "__main__":
    asyncio.run(run_all_anomalies())