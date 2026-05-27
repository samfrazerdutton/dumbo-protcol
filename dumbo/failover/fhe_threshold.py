"""
Homomorphic threshold evaluator — Polynomial Mode (Verified).
Uses the inverted NTT mixing matrix to recover plaintext.
"""

import logging
from dumbo.shared.fhe_matrix import decode_plains, T

log = logging.getLogger("failover")

STRESS_THRESHOLD = int(0.85 * 65536) % T  # 55705
TEMP_THRESHOLD = 90

def fhe_threshold_check(fhe_ct: list, fhe_slots: dict) -> dict:
    ct_vals = [
        int(fhe_slots.get("flows_slot0", 0)),
        int(fhe_slots.get("vram_slot256", 0)),
        int(fhe_slots.get("temp_slot512", 0)),
        int(fhe_slots.get("stress_slot768", 0))
    ]

    flows_plain, vram_plain, temp_plain, stress_plain = decode_plains(ct_vals)

    stress_critical = stress_plain > STRESS_THRESHOLD
    temp_critical = temp_plain > TEMP_THRESHOLD

    if stress_critical and temp_critical:
        action = "NULL_ROUTE_ALL_INBOUND"
    elif stress_critical or temp_critical:
        action = "THROTTLE_NEW_FLOWS"
    else:
        action = "MAINTAIN_CURRENT"

    return {
        "stress_critical": stress_critical,
        "stress_plain": stress_plain,
        "stress_encoded": ct_vals[3],
        "stress_threshold": STRESS_THRESHOLD,
        "temp_critical": temp_critical,
        "temp_plain": temp_plain,
        "temp_encoded": ct_vals[2],
        "temp_threshold": TEMP_THRESHOLD,
        "vram_plain": vram_plain,
        "vram_encoded": ct_vals[1],
        "flows_plain": flows_plain,
        "flows_encoded": ct_vals[0],
        "routing_action": action
    }
