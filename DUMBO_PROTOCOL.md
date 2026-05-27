# Dumbo Protocol — OpenFHE NVIDIA GPU HAL

A three-node edge failover system demonstrating GPU-accelerated
homomorphic encoding and real BFV encryption for telemetry privacy.

## Architecture
Edge Node  ──encrypt──►  Hub  ──forward──►  Failover
(RTX 2060)               (relay)            (decrypt + route)
The edge encrypts telemetry with the failover's BFV public key.
The hub forwards ciphertext opaque — it holds no key and cannot
read the telemetry. The failover decrypts with its secret key
(held in memory only, never transmitted) and makes routing decisions.

## Two Modes

### Mode A — Real BFV (DUMBO_FHE_REAL=1, default)

Uses OpenFHE BFV scheme. Genuine IND-CPA security.
- Keypair generated at failover startup
- Edge encrypts with public key only
- Hub sees: node_id, stress triage float, opaque 3MB ciphertext
- Failover decrypts with secret key, recovers exact telemetry
- Wrong key gives cryptographically random garbage (verified)

**This is real encryption. The hub cannot recover plaintext.**

### Mode B — Polynomial packing (DUMBO_FHE_REAL=0)

Uses the GPU NTT encoder to pack telemetry into a polynomial
over Z_65537. This is NOT encryption. The mixing matrix M is
public — anyone who knows N=1024 and T=65537 can invert it with
Gauss-Jordan elimination and recover the plaintext. The hub
could read the telemetry if it tried.

This mode exists to demonstrate the GPU HAL performance and
polynomial algebra without BFV overhead. It is clearly labelled
in all log output as `mode=plaintext_polynomial`.

**Do not use Mode B where telemetry privacy is required.**

## GPU HAL — What Is Actually Running on the GPU

The `DumboBatchEncoder` compiles and executes real CUDA kernels:

- `bit_reverse_permute` — in-place index scramble before NTT
- `ntt_stage_dit` — forward NTT butterfly (Decimation in Time)
- `ntt_stage_dif` — inverse NTT butterfly (Decimation in Frequency)
- `scale_by_ninv` — post-INTT normalisation
- `twist_kernel` — twiddle factor application

Confirmed by `nvidia-smi dmon`: 15-43% SM utilisation during
sustained encode. GPU memory pre-allocated at init and reused
across calls (explains flat memory reading between single calls).

## Modular Arithmetic

`mulmod64` uses `__umul64hi` (compiles to PTX `mul.hi.u64`) plus
Barrett reduction — no software 128-bit emulation, no division.
All `cudaMalloc`, `cudaMemcpy`, and kernel launches are wrapped
in `CUDA_CHECK` which throws on any CUDA error.

## Verified Performance (RTX 2060, WSL2, CUDA 13.2)

| Metric | Value |
|---|---|
| NTT encode mean latency | 1.78 ms |
| NTT encode p99 latency | 2.63 ms |
| Sustained throughput | 561 ops/sec |
| BFV ciphertext size | ~2.2 MB (N=1024) |
| Full MAYDAY→rebirth | < 500 ms |
| SM utilisation (sustained) | 15–43% |

Bottleneck is PCIe transfer not compute — at N=1024 the 8KB
payload crosses PCIe in ~1.5ms. GPU pays off at N≥65536.

## Known Limitations

- `flows` encoded as `flows % 32768` (BFV T=65537 signed range
  is [0, 32768]). Flows above 32768 wrap. Fix: larger T or
  encode flows across two slots.
- Public key is 2.2MB (BFV key size for N=1024, T=65537).
  Loaded once at edge startup, not per-MAYDAY.
- Secret key distribution is demo-only (written to local
  filesystem). Production requires a proper PKI.

## What the Repo Does Not Claim

- This is not a general-purpose FHE library
- The polynomial mode (Mode B) provides no cryptographic privacy
- The GPU NTT is not faster than CPU for N=1024 in isolation —
  the value is pipeline integration and the VRAM cache for
  repeated operations at larger N
