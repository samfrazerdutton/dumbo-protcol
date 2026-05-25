"""
Homomorphic threshold evaluator — decode-then-compare, verified.

ct[band_start] = v * C_k mod T  (uniform band encoding property)
v = ct[band_start] * C_k^-1 mod T  (recovered at failover)

C_k constants are computed fresh at import time from the same encoder
used by edge_daemon.py, guaranteeing consistency.

Channel layout (N=1024, T=65537, 256 slots per channel):
  ch 0 → polynomial positions [0..255]   flows  (v = flows % T)
  ch 1 → polynomial positions [256..511] vram   (v = vram_mb % T)
  ch 2 → polynomial positions [512..767] temp   (v = temp_c % T)
  ch 3 → polynomial positions [768..1023] stress (v = int(stress*65536) % T)
"""

import os, sys, logging

log = logging.getLogger("failover")
T = 65537


def _modinv(a: int, m: int) -> int:
    return pow(a, m - 2, m)


def _compute_ck_inverses() -> dict:
    """
    Encode v=1 uniformly in each channel band and read ct[band_start].
    Returns {channel_idx: (C_k, C_k_inv)} using the SAME encoder as edge.
    Falls back to no-op (identity) if GPU unavailable.
    """
    try:
        _ext = os.path.join(os.path.dirname(__file__), '../../dumbo_ext')
        sys.path.insert(0, os.path.abspath(_ext))
        from dumbo_cuda import DumboBatchEncoder
        enc = DumboBatchEncoder(1024, T)
        result = {}
        for ch in range(4):
            flat = [0] * 1024
            band_start = ch * 256
            for i in range(256):
                flat[band_start + i] = 1
            ct = enc.encode_batch(flat)
            ck = int(ct[band_start])
            ck_inv = _modinv(ck, T)
            # Self-test: encode v=100, decode, verify
            flat_test = [0] * 1024
            for i in range(256):
                flat_test[band_start + i] = 100
            ct_test = enc.encode_batch(flat_test)
            decoded_test = (int(ct_test[band_start]) * ck_inv) % T
            assert decoded_test == 100, (
                f"Channel {ch} self-test failed: "
                f"encoded 100, decoded {decoded_test}  C_k={ck}"
            )
            result[ch] = (ck, ck_inv)
            log.info(
                f"[fhe_threshold] ch{ch} C_k={ck} C_k_inv={ck_inv} "
                f"self-test=PASS"
            )
        return result
    except AssertionError:
        raise
    except Exception as e:
        log.warning(f"[fhe_threshold] GPU unavailable, identity fallback: {e}")
        return {ch: (1, 1) for ch in range(4)}


# Computed once at import — public parameters, not secret keys
_CK = _compute_ck_inverses()

# Plaintext thresholds (compare in plaintext domain after decode)
STRESS_THRESHOLD = int(0.85 * 65536) % T   # 55705 — stress*65536 >= this
TEMP_THRESHOLD   = 90                        # gpu_temp_c >= this


def decode_slot(channel_idx: int, ct_value: int) -> int:
    """Recover plaintext v from ct[band_start] = v * C_k mod T."""
    _, ck_inv = _CK[channel_idx]
    return (int(ct_value) * ck_inv) % T


def fhe_threshold_check(fhe_ct: list, fhe_slots: dict) -> dict:
    flows_enc  = int(fhe_slots.get("flows_slot0")    or 0)
    vram_enc   = int(fhe_slots.get("vram_slot256")   or 0)
    temp_enc   = int(fhe_slots.get("temp_slot512")   or 0)
    stress_enc = int(fhe_slots.get("stress_slot768") or 0)

    flows_plain  = decode_slot(0, flows_enc)
    vram_plain   = decode_slot(1, vram_enc)
    temp_plain   = decode_slot(2, temp_enc)
    stress_plain = decode_slot(3, stress_enc)

    stress_critical = stress_plain >= STRESS_THRESHOLD
    temp_critical   = temp_plain   >= TEMP_THRESHOLD

    if stress_critical and temp_critical:
        routing_action = "NULL_ROUTE_ALL_INBOUND"
    elif stress_critical:
        routing_action = "THROTTLE_NEW_FLOWS"
    elif temp_critical:
        routing_action = "SHED_LOWEST_PRIORITY"
    else:
        routing_action = "MAINTAIN_CURRENT"

    return {
        "stress_critical":  stress_critical,
        "stress_plain":     stress_plain,
        "stress_encoded":   stress_enc,
        "stress_threshold": STRESS_THRESHOLD,
        "temp_critical":    temp_critical,
        "temp_plain":       temp_plain,
        "temp_encoded":     temp_enc,
        "temp_threshold":   TEMP_THRESHOLD,
        "vram_plain":       vram_plain,
        "vram_encoded":     vram_enc,
        "flows_plain":      flows_plain,
        "flows_encoded":    flows_enc,
        "routing_action":   routing_action,
    }
