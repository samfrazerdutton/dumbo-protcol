import os, sys, time
from typing import Optional

_ext_dir = os.path.join(os.path.dirname(__file__), '../../dumbo_ext')
sys.path.insert(0, os.path.abspath(_ext_dir))

MOCK_MODE = os.environ.get("DUMBO_MOCK_FHE", "0") == "1"

if not MOCK_MODE:
    try:
        from dumbo_cuda import DumboBatchEncoder as _Enc
        _GPU_ENCODER = _Enc(1024, 65537)
        MOCK_MODE = False
        print("[FHE BRIDGE] GPU HAL online  N=1024 T=65537", flush=True)
    except ImportError as _e:
        print(f"[FHE BRIDGE] WARNING: GPU HAL unavailable ({_e}), falling back to mock",
              flush=True)
        MOCK_MODE = True
        _GPU_ENCODER = None
else:
    _GPU_ENCODER = None
    print("[FHE BRIDGE] Mock mode (DUMBO_MOCK_FHE=1)", flush=True)


class FHEContext:
    def __init__(self):
        self.mock = MOCK_MODE

    def encrypt(self, values: list) -> dict:
        if self.mock or _GPU_ENCODER is None:
            return {"mock": True, "data": list(values), "ts": time.time()}
        T = 65537
        N = 1024
        flat = []
        for v in values[:N]:
            iv = int(v * 65536) % T
            flat.append(iv)
        while len(flat) < N:
            flat.append(0)
        ct = _GPU_ENCODER.encode_batch(flat)
        return {
            "mock": False,
            "ct": list(ct),
            "ts": time.time(),
        }

    def decrypt(self, ct_dict: dict) -> list:
        if ct_dict.get("mock", True):
            return ct_dict.get("data", [0.0] * 1024)
        ct = ct_dict.get("ct", [])
        T = 65537
        return [c / T for c in ct]

    def bootstrap(self, ct_dict: dict) -> dict:
        if ct_dict.get("mock", True):
            from dumbo.shared.noise_model import bootstrap_clean
            ct_dict = dict(ct_dict)
            ct_dict["data"] = bootstrap_clean(ct_dict.get("data", []))
            ct_dict["bootstrapped"] = True
            return ct_dict
        ct_dict = dict(ct_dict)
        ct_dict["bootstrapped"] = True
        return ct_dict


_ctx: Optional[FHEContext] = None


def get_context() -> FHEContext:
    global _ctx
    if _ctx is None:
        _ctx = FHEContext()
    return _ctx
