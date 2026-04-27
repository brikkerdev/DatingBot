import time


class Pacer:
    def __init__(self, rate: float) -> None:
        self.rate = rate
        self.start = time.perf_counter()

    def wait(self, i: int) -> None:
        if self.rate <= 0:
            return
        deadline = self.start + i / self.rate
        delta = deadline - time.perf_counter()
        if delta > 0:
            time.sleep(delta)
