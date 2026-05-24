from typing import List

DEFAULT_MODULI: List[int] = [
    1073741827, 1073741831, 1073741833, 1073741909,
    1073741939, 1073741953, 1073741969, 1073741971,
]

def pack(values: List[float], scale: int = 1_000_000) -> dict:
    int_vals = [int(round(v * scale)) for v in values]
    residues = {}
    for q in DEFAULT_MODULI:
        residues[str(q)] = [v % q for v in int_vals]
    return {"residues": residues, "scale": scale, "n": len(values)}

def unpack(payload: dict) -> List[float]:
    residues = payload["residues"]
    scale    = payload["scale"]
    n        = payload["n"]
    moduli   = [int(k) for k in residues.keys()]
    M = 1
    for q in moduli:
        M *= q
    results = []
    for i in range(n):
        x = 0
        for q in moduli:
            r  = residues[str(q)][i]
            Mi = M // q
            yi = pow(Mi, q - 2, q)
            x += r * Mi * yi
        results.append((x % M) / scale)
    return results
