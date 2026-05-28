"""
Discrete Gaussian noise for Mode B polynomial encoding.

Without noise, the polynomial encoding is deterministic and invertible
by anyone who knows the mixing matrix M. Adding discrete Gaussian error
e ~ DG(0, sigma) makes the output computationally indistinguishable from
a real RLWE sample under the RLWE hardness assumption.

sigma=3.2 is the OpenFHE default standard deviation.
T must match the modulus used by the encoder (65537 for current GPU HAL).
"""

import numpy as np

SIGMA = 3.2


def sample_discrete_gaussian(n: int, sigma: float = SIGMA) -> np.ndarray:
    bound = int(6 * sigma) + 1
    samples = []
    rng = np.random.default_rng()
    while len(samples) < n:
        batch = np.round(rng.normal(0, sigma, n * 2)).astype(np.int64)
        batch = batch[np.abs(batch) <= bound]
        samples.extend(batch.tolist())
    return np.array(samples[:n], dtype=np.int64)


def add_rlwe_noise(ct_coeffs: list, T: int, sigma: float = SIGMA) -> list:
    """
    Add discrete Gaussian noise to polynomial coefficients mod T.
    T must match the modulus of the encoder that produced ct_coeffs.
    Output: (ct[i] + e[i]) mod T where e ~ DG(0, sigma).
    """
    n = len(ct_coeffs)
    e = sample_discrete_gaussian(n, sigma)
    return [(int(ct_coeffs[i]) + int(e[i])) % T for i in range(n)]


def verify_noise_distribution(n: int = 10000) -> dict:
    samples = sample_discrete_gaussian(n)
    return {
        "mean":         float(np.mean(samples)),
        "std":          float(np.std(samples)),
        "target_std":   SIGMA,
        "max_abs":      int(np.max(np.abs(samples))),
        "within_3sigma": float(np.mean(np.abs(samples) <= 3 * SIGMA)),
    }
