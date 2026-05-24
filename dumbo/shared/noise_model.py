import numpy as np
import statistics

def inject_stress_noise(values: list, stress_level: float) -> list:
    sigma = stress_level * 0.05 * (max(abs(v) for v in values) + 1e-9)
    rng   = np.random.default_rng(42)
    return [v + float(rng.normal(0, sigma)) for v in values]

def bootstrap_clean(noisy: list, window: int = 3) -> list:
    cleaned = []
    for i in range(len(noisy)):
        lo = max(0, i - window)
        hi = min(len(noisy), i + window + 1)
        cleaned.append(statistics.median(noisy[lo:hi]))
    return cleaned
