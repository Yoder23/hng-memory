from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
import math
import statistics
import time


class ComponentProfiler:
    def __init__(self): self.samples: dict[str, list[float]] = defaultdict(list)

    @contextmanager
    def measure(self, component: str):
        started = time.perf_counter()
        try: yield
        finally: self.samples[component].append((time.perf_counter() - started) * 1000.0)

    def record(self, component: str, milliseconds: float) -> None:
        self.samples[component].append(float(milliseconds))

    @staticmethod
    def _percentile(values: list[float], fraction: float) -> float:
        values = sorted(values)
        if not values: return 0.0
        position = (len(values) - 1) * fraction; low = math.floor(position); high = math.ceil(position)
        return values[low] if low == high else values[low] * (high-position) + values[high] * (position-low)

    def summary(self) -> dict[str, dict[str, float | int]]:
        return {name: {"count": len(values), "median_ms": statistics.median(values),
                       "p95_ms": self._percentile(values, .95), "p99_ms": self._percentile(values, .99),
                       "stdev_ms": statistics.pstdev(values) if len(values) > 1 else 0.0}
                for name, values in sorted(self.samples.items()) if values}
