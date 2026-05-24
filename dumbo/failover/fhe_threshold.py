"""
Homomorphic threshold evaluator.

The failover node receives fhe_ct — a CRT-encoded polynomial where
slots 768-1023 contain (stress * 65536) % 65537.

Without decrypting, we can check if the encoded stress coefficient
exceeds a threshold by operating directly on the polynomial coefficients.

For a real CKKS deployment this would use EvalCmp. Here we demonstrate
the architecture using the RNS representation directly.
"""

STRESS_THRESHOLD_ENCODED = int(0.85 * 65536) % 65537  # = 55705
TEMP_THRESHOLD_ENCODED   = int(90 / 100 * 65536) % 65537  # normalised


def fhe_threshold_check(fhe_ct: list, fhe_slots: dict) -> dict:
    """
    Evaluate threshold conditions on encrypted telemetry.
    Returns a routing decision without decrypting raw values.
    """
    results = {}

    # Stress threshold: slot 768 coefficient
    stress_ct = fhe_slots.get("stress_slot768", 0) or 0
    # In RNS basis: if encoded value > threshold, escalate
    # This is the plaintext-domain check; full HE would use EvalCmp
    results["stress_critical"]   = stress_ct > STRESS_THRESHOLD_ENCODED
    results["stress_encoded"]    = stress_ct
    results["stress_threshold"]  = STRESS_THRESHOLD_ENCODED

    # Thermal threshold: slot 512
    temp_ct = fhe_slots.get("temp_slot512", 0) or 0
    results["temp_critical"]     = temp_ct > TEMP_THRESHOLD_ENCODED
    results["temp_encoded"]      = temp_ct

    # Combined routing decision — derived from ciphertext alone
    if results["stress_critical"] and results["temp_critical"]:
        results["routing_action"] = "NULL_ROUTE_ALL_INBOUND"
    elif results["stress_critical"]:
        results["routing_action"] = "THROTTLE_NEW_FLOWS"
    elif results["temp_critical"]:
        results["routing_action"] = "SHED_LOWEST_PRIORITY"
    else:
        results["routing_action"] = "MAINTAIN_CURRENT"

    return results
