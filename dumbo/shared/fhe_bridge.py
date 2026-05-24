import os, time
from typing import Optional

MOCK_MODE = os.environ.get("DUMBO_MOCK_FHE", "1") == "1"
if not MOCK_MODE:
    try:
        import openfhe as fhe
        MOCK_MODE = False
    except ImportError:
        MOCK_MODE = True

class FHEContext:
    def __init__(self):
        self.mock = MOCK_MODE
        if not self.mock:
            params = fhe.CCParamsCKKSRNS()
            params.SetMultiplicativeDepth(6)
            params.SetScalingModSize(50)
            params.SetBatchSize(1024)
            self.cc   = fhe.GenCryptoContext(params)
            self.cc.Enable(fhe.PKESchemeFeature.PKE)
            self.cc.Enable(fhe.PKESchemeFeature.LEVELEDSHE)
            self.cc.Enable(fhe.PKESchemeFeature.ADVANCEDSHE)
            self.keys = self.cc.KeyGen()
            self.cc.EvalMultKeyGen(self.keys.secretKey)
            self.cc.EvalBootstrapSetup(self.cc)
            self.cc.EvalBootstrapKeyGen(self.keys.secretKey, 1)

    def encrypt(self, values: list) -> dict:
        if self.mock:
            return {"mock": True, "data": list(values), "ts": time.time()}
        pt = self.cc.MakeCKKSPackedPlaintext(values)
        ct = self.cc.Encrypt(self.keys.publicKey, pt)
        return {"mock": False, "serial": ct.Serialize()}

    def decrypt(self, ct_dict: dict) -> list:
        if self.mock or ct_dict.get("mock"):
            return ct_dict["data"]
        ct = self.cc.DeserializeCiphertext(ct_dict["serial"])
        pt = self.cc.Decrypt(self.keys.secretKey, ct)
        pt.SetLength(1024)
        return pt.GetCKKSPackedValue()

    def bootstrap(self, ct_dict: dict) -> dict:
        if self.mock or ct_dict.get("mock"):
            from dumbo.shared.noise_model import bootstrap_clean
            ct_dict["data"] = bootstrap_clean(ct_dict["data"])
            ct_dict["bootstrapped"] = True
            return ct_dict
        ct_in  = self.cc.DeserializeCiphertext(ct_dict["serial"])
        ct_out = self.cc.EvalBootstrap(ct_in)
        return {"mock": False, "serial": ct_out.Serialize(), "bootstrapped": True}

_ctx: Optional[FHEContext] = None
def get_context() -> FHEContext:
    global _ctx
    if _ctx is None:
        _ctx = FHEContext()
    return _ctx
