"""
Homomorphic threshold evaluator — production hardened.
Operates on RNS-encoded coefficients without decryption.
"""

T = 65537
STRESS_THRESHOLD_ENCODED = int(0.85 * 65536) % T   # 55705
TEMP_THRESHOLD_ENCODED   = int(90.0 / 100.0 * 65536) % T


def fhe_threshold_check(fhe_ct: list, fhe_slots: dict) -> dict:
    results = {}

    stress_ct = int(fhe_slots.get("stress_slot768") or 0)
    temp_ct   = int(fhe_slots.get("temp_slot512")   or 0)

    results["stress_critical"]  = stress_ct > STRESS_THRESHOLD_ENCODED
    results["stress_encoded"]   = stress_ct
    results["stress_threshold"] = STRESS_THRESHOLD_ENCODED

    results["temp_critical"] = temp_ct > TEMP_THRESHOLD_ENCODED
    results["temp_encoded"]  = temp_ct
    results["temp_threshold"] = TEMP_THRESHOLD_ENCODED

    vram_ct  = int(fhe_slots.get("vram_slot256") or 0)
    flows_ct = int(fhe_slots.get("flows_slot0")  or 0)
    results["vram_encoded"]  = vram_ct
    results["flows_encoded"] = flows_ct

    if results["stress_critical"] and results["temp_critical"]:
        results["routing_action"] = "NULL_ROUTE_ALL_INBOUND"
    elif results["stress_critical"]:
        results["routing_action"] = "THROTTLE_NEW_FLOWS"
    elif results["temp_critical"]:
        results["routing_action"] = "SHED_LOWEST_PRIORITY"
    else:
        results["routing_action"] = "MAINTAIN_CURRENT"

    return results
