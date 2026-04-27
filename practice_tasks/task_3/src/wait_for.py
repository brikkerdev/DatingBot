import time


def wait_for(name: str, probe, retries: int = 30, delay: float = 1.0) -> None:
    for attempt in range(1, retries + 1):
        try:
            probe()
            print(f"[wait_for] {name} ready (attempt {attempt})")
            return
        except Exception as e:
            print(f"[wait_for] {name} not ready ({attempt}/{retries}): {e}")
            time.sleep(delay)
    raise RuntimeError(f"{name} not reachable")
