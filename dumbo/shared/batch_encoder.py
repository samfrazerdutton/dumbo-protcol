import sys, os, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../dumbo_ext')))

HARDWARE = False
try:
    import dumbo_cuda
    HARDWARE = True
except ImportError:
    pass

import numpy as np

class BatchEncoder:
    """
    Dumbo Protocol batch encoder.
    Hot path: OpenFHE NVIDIA GPU HAL (CRTEncodeKernel via pybind).
    Cold path: pure-Python numpy fallback (DUMBO_MOCK_FHE=1).
    """
    def __init__(self, N=1024, T=65537):
        self.N, self.T = N, T
        if HARDWARE:
            print(f"[ENCODER] GPU HAL online  N={N}  T={T}")
            self._engine = dumbo_cuda.DumboBatchEncoder(N, T)
        else:
            print(f"[ENCODER] Mock mode (no CUDA)  N={N}  T={T}")
            self._engine = None
            omega = pow(3, (T-1)//(2*N), T)
            roots = [pow(omega, 2*self._bitrev(i)+1, T) for i in range(N)]
            inv_N = pow(N, T-2, T)
            self._enc = np.array([
                [inv_N * pow(pow(roots[j], T-2, T), i, T) % T for j in range(N)]
                for i in range(N)], dtype=np.int64)

    def _bitrev(self, x):
        bits = int(np.log2(self.N))
        r = 0
        for _ in range(bits):
            r = (r << 1) | (x & 1); x >>= 1
        return r

    def encode(self, state_vectors: list) -> list:
        flat = [int(v) for v in state_vectors]
        if HARDWARE:
            return self._engine.encode_batch(flat)
        arr = np.array(flat, dtype=np.int64).reshape(-1, self.N)
        out = (arr @ self._enc.T) % self.T
        return out.flatten().tolist()
