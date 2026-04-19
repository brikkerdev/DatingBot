import time


def wait_for(broker, retries: int = 20, delay: float = 1.5) -> None:
    for attempt in range(1, retries + 1):
        try:
            broker.connect()
            print(f"Broker is ready (attempt {attempt}).")
            return
        except Exception as e:
            print(f"Waiting for broker... attempt {attempt}/{retries}: {e}")
            time.sleep(delay)
    raise RuntimeError("Could not connect to broker")
