"""
NTT mixing matrix for DumboBatchEncoder(N=1024, T=65537).
Inverts the polynomial coefficients back to plaintext channels.
"""

T = 65537
POSITIONS = [0, 256, 512, 768]

# M[pos_index][channel]
M_RAW = [
    [49153, 49153, 49153, 49153],
    [65533, 4,     64513, 1024],
    [64,    64,    65473, 65473],
    [64513, 1024,  65533, 4]
]

def _modinv(a, m):
    return pow(int(a), m - 2, m)

def _eye(n):
    return [[int(i == j) for j in range(n)] for i in range(n)]

def _matinv_mod(M, m):
    n = len(M)
    A = [row[:] for row in M]
    I = _eye(n)
    
    for col in range(n):
        pivot = next((r for r in range(col, n) if A[r][col] % m != 0), None)
        if pivot is None:
            raise ValueError(f"Matrix is singular at col {col}")
            
        A[col], A[pivot] = A[pivot], A[col]
        I[col], I[pivot] = I[pivot], I[col]
        
        inv = _modinv(A[col][col], m)
        for j in range(n):
            A[col][j] = (A[col][j] * inv) % m
            I[col][j] = (I[col][j] * inv) % m
            
        for row in range(n):
            if row != col:
                factor = A[row][col]
                for j in range(n):
                    A[row][j] = (A[row][j] - factor * A[col][j]) % m
                    I[row][j] = (I[row][j] - factor * I[col][j]) % m
    return I

M_INV = _matinv_mod(M_RAW, T)

def decode_plains(ct_vals):
    """
    Decodes the 4 transmitted polynomial coefficients back into plaintext integers.
    ct_vals: [ct[0], ct[256], ct[512], ct[768]]
    Returns: [flows, vram, temp, stress]
    """
    return [
        sum(M_INV[ch][k] * ct_vals[k] for k in range(4)) % T
        for ch in range(4)
    ]
