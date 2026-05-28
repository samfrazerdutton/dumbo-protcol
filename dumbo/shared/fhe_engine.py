"""
Dumbo FHE Engine — Real BFV mode using OpenFHE.

T=1376257 is an NTT prime supporting N up to 65536.
Max safe plaintext value: 688128 (covers all realistic telemetry).
flows up to 688K, vram up to 688K, temp always < 200, stress*688128.

Key distribution model (demo):
  Failover generates keypair on startup, writes pk to shared state dir.
  Edge loads pk before sending MAYDAY.
"""

import os, sys, json, base64, tempfile, logging

sys.path.insert(0, '/home/samfrazerdutton/.local/lib/python3.12/site-packages')
import openfhe

log = logging.getLogger("fhe_engine")

T          = 1376257
HALF_T     = (T - 1) // 2   # 688128 — max safe plaintext value
BATCH_SIZE = 1024
KEY_DIR    = os.path.join(os.path.dirname(__file__), "../state/keys")


def _make_cc():
    params = openfhe.CCParamsBFVRNS()
    params.SetPlaintextModulus(T)
    params.SetMultiplicativeDepth(1)
    params.SetBatchSize(BATCH_SIZE)
    cc = openfhe.GenCryptoContext(params)
    cc.Enable(openfhe.PKESchemeFeature.PKE)
    return cc


def encode_telemetry(flows, vram_mb, temp_c, stress):
    """Pack telemetry into BFV plaintext slots.
    T=1376257, HALF_T=688128 — all realistic telemetry fits without wrapping.
    flows up to 688K, vram up to 688K, temp always safe, stress*HALF_T.
    """
    assert int(flows)   <= HALF_T, f"flows {flows} exceeds HALF_T {HALF_T}"
    assert int(vram_mb) <= HALF_T, f"vram {vram_mb} exceeds HALF_T {HALF_T}"
    assert int(temp_c)  <= HALF_T, f"temp {temp_c} exceeds HALF_T {HALF_T}"
    return [
        int(flows),
        int(vram_mb),
        int(temp_c),
        int(stress * HALF_T),
    ] + [0] * (BATCH_SIZE - 4)


def decode_telemetry(vals):
    """Recover telemetry from decrypted BFV slots."""
    return {
        "flows":   vals[0],
        "vram_mb": vals[1],
        "temp_c":  vals[2],
        "stress":  vals[3] / HALF_T,
    }


class FailoverKeyHolder:
    def __init__(self):
        os.makedirs(KEY_DIR, exist_ok=True)
        self.cc   = _make_cc()
        self.keys = self.cc.KeyGen()
        openfhe.SerializeToFile(KEY_DIR + "/cc.json", self.cc, openfhe.JSON)
        openfhe.SerializeToFile(KEY_DIR + "/pk.json", self.keys.publicKey, openfhe.JSON)
        log.info(f"[FHE] Keypair generated (T={T}). Public key -> {KEY_DIR}")
        log.info("[FHE] Secret key held in memory only.")

    def decrypt(self, ct_b64: str) -> dict:
        ct_bytes = base64.b64decode(ct_b64)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(ct_bytes)
            ct_path = f.name
        try:
            ct, ok = openfhe.DeserializeCiphertext(ct_path, openfhe.JSON)
            if not ok:
                raise ValueError("Ciphertext deserialization failed")
            result = self.cc.Decrypt(self.keys.secretKey, ct)
            result.SetLength(4)
            vals = result.GetPackedValue()
            return decode_telemetry(vals)
        finally:
            os.unlink(ct_path)


class EdgeEncryptor:
    def __init__(self):
        if not os.path.exists(KEY_DIR + "/pk.json"):
            raise RuntimeError(
                f"Public key not found at {KEY_DIR}/pk.json. "
                "Start the failover server first."
            )
        self.cc, ok1 = openfhe.DeserializeCryptoContext(KEY_DIR + "/cc.json", openfhe.JSON)
        if not ok1:
            raise RuntimeError("Failed to load CryptoContext")
        self.pk, ok2 = openfhe.DeserializePublicKey(KEY_DIR + "/pk.json", openfhe.JSON)
        if not ok2:
            raise RuntimeError("Failed to load public key")
        log.info(f"[FHE] Edge loaded public key (T={T}). Encrypting telemetry.")

    def encrypt(self, flows, vram_mb, temp_c, stress) -> str:
        slots  = encode_telemetry(flows, vram_mb, temp_c, stress)
        pt     = self.cc.MakePackedPlaintext(slots)
        ct     = self.cc.Encrypt(self.pk, pt)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            ct_path = f.name
        try:
            openfhe.SerializeToFile(ct_path, ct, openfhe.JSON)
            with open(ct_path, "rb") as f:
                ct_b64 = base64.b64encode(f.read()).decode()
            return ct_b64
        finally:
            os.unlink(ct_path)
