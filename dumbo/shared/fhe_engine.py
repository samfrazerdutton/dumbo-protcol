"""
Dumbo FHE Engine — Real BFV mode using OpenFHE.

The secret key is generated once at failover startup and never transmitted.
The edge encrypts telemetry with the public key.
The hub forwards the ciphertext without being able to read it.
The failover decrypts with the secret key.

Key distribution model (demo):
  - Failover generates keypair on startup, writes pk to a shared state dir
  - Edge loads pk from that dir before sending MAYDAY
  - In production this would be a proper PKI exchange
"""

import os, sys, json, base64, tempfile, logging

sys.path.insert(0, '/home/samfrazerdutton/.local/lib/python3.12/site-packages')
import openfhe

log = logging.getLogger("fhe_engine")

T          = 65537
BATCH_SIZE = 1024
KEY_DIR = os.path.join(os.path.dirname(__file__), "../state/keys")


def _make_cc():
    params = openfhe.CCParamsBFVRNS()
    params.SetPlaintextModulus(T)
    params.SetMultiplicativeDepth(1)
    params.SetBatchSize(BATCH_SIZE)
    cc = openfhe.GenCryptoContext(params)
    cc.Enable(openfhe.PKESchemeFeature.PKE)
    return cc


def encode_telemetry(flows, vram_mb, temp_c, stress):
    """Pack telemetry into BFV plaintext slots. All values must be < 32768."""
    return [
        int(flows)   % 32768,
        int(vram_mb) % 32768,
        int(temp_c)  % 32768,
        int(stress * 32768),   # stress in [0,1) -> [0, 32767]
    ] + [0] * (BATCH_SIZE - 4)


def decode_telemetry(vals):
    """Recover telemetry from decrypted BFV slots."""
    return {
        "flows":   vals[0],
        "vram_mb": vals[1],
        "temp_c":  vals[2],
        "stress":  vals[3] / 32768.0,
    }


class FailoverKeyHolder:
    """
    Runs on the failover node.
    Generates keypair, persists public key for the edge to load.
    Holds secret key in memory only — never written to disk in prod.
    """
    def __init__(self):
        os.makedirs(KEY_DIR, exist_ok=True)
        self.cc   = _make_cc()
        self.keys = self.cc.KeyGen()
        # Write public key and cc params so edge can encrypt
        openfhe.SerializeToFile(KEY_DIR + "/cc.json", self.cc, openfhe.JSON)
        openfhe.SerializeToFile(KEY_DIR + "/pk.json", self.keys.publicKey, openfhe.JSON)
        log.info(f"[FHE] Keypair generated. Public key written to {KEY_DIR}")
        log.info("[FHE] Secret key held in memory only.")

    def decrypt(self, ct_b64: str) -> dict:
        """Decrypt a base64-encoded serialized ciphertext. Returns telemetry dict."""
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
    """
    Runs on the edge node.
    Loads the public key written by FailoverKeyHolder.
    Encrypts telemetry — never sees or holds the secret key.
    """
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
        log.info("[FHE] Edge loaded public key. Telemetry will be BFV-encrypted.")

    def encrypt(self, flows, vram_mb, temp_c, stress) -> str:
        """Encrypt telemetry. Returns base64 string safe for JSON transmission."""
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
