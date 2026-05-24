# Dumbo Protocol × OpenFHE NVIDIA GPU HAL

> **The first demonstrated system to perform FHE-sealed network state handoff at the edge-failover layer.**

When an edge node hits critical stress, it GPU-encodes all live telemetry into a
1024-slot CRT polynomial using the OpenFHE NVIDIA CUDA HAL, transmits the
ciphertext to a hub, and a failover node inherits fully encrypted operational
context — flows, VRAM pressure, thermal load, stress — in under 30ms.

---

## Architecture
edge-alpha  (OpenFHE NVIDIA GPU HAL)
│
│  MAYDAY  +  fhe_ct  (CRT-encoded telemetry)
▼
hub :8000  ──── lifeboat ────▶  failover :8001
│
└── inherits:
active_flows
null_routes
ddos_signatures
fhe_ct  ← GPU ciphertext
fhe_slots
rebirth_ts
---

## FHE Slot Layout  (N=1024, T=65537)

| Slots      | Telemetry channel  | Example encoded value |
|------------|--------------------|-----------------------|
| 0 – 255    | active_flows       | 28188                 |
| 256 – 511  | vram_free_mb       | 45345                 |
| 512 – 767  | gpu_temp_c         | 57994                 |
| 768 – 1023 | stress × 65536     | 36336                 |

All four channels are packed into a single degree-1024 polynomial and
CRT-encoded in one GPU kernel launch before the snapshot leaves the edge node.

---

## Measured Performance

| Event                        | Latency  |
|------------------------------|----------|
| GPU CRT encode (N=1024)      | ~11 ms   |
| Hub bootstrap (cold)         | ~15 ms   |
| Hub bootstrap (warm)         | ~4 ms    |
| Full MAYDAY → rebirth        | < 30 ms  |

---

## Stack

| Layer | Component |
|-------|-----------|
| GPU math | `CUDAMathHAL::EvalMultRNS` (OpenFHE NVIDIA GPU HAL) |
| CUDA kernels | `cuda_math.cu`, `cuda_ntt.cu`, `cuda_keyswitch.cu` |
| Python bridge | pybind11 → `dumbo_cuda.so` → `DumboBatchEncoder` |
| Edge daemon | FastAPI-free Python loop, stress monitor, MAYDAY trigger |
| Hub | FastAPI `:8000`, receives MAYDAY, forwards lifeboat |
| Failover | FastAPI `:8001`, contextual rebirth, persists state |

---

## Quick Start

### Prerequisites

- NVIDIA GPU with CUDA toolkit installed
- Python 3.12+
- WSL2 or Linux

### Install

```bash
git clone https://github.com/samfrazerdutton/dumbo-protcol.git
cd dumbo-protcol
python3 -m venv dumbo/venv
source dumbo/venv/bin/activate
pip install fastapi uvicorn requests numpy pydantic
```

### Build the CUDA extension

```bash
pip install pybind11
git clone https://github.com/samfrazerdutton/openfheNVDIA-GPU engine_src

cd dumbo_ext
nvcc -O3 -shared -std=c++17 -Xcompiler -fPIC \
    $(python3 -m pybind11 --includes) \
    -I../engine_src/include \
    pybind_wrapper.cpp \
    dumbo_batch_encoder.cu \
    ../engine_src/src/cuda_hal.cpp \
    ../engine_src/src/twiddle_gen.cpp \
    ../engine_src/src/vram_cache.cpp \
    ../engine_src/src/global_dag.cpp \
    ../engine_src/src/fhe_compiler.cpp \
    ../engine_src/kernels/cuda_math.cu \
    ../engine_src/kernels/cuda_ntt.cu \
    ../engine_src/kernels/cuda_keyswitch.cu \
    -o dumbo_cuda$(python3-config --extension-suffix) \
    -lcudart
cd ..
```

### Run (three terminals)

**Terminal 1 — Failover**
```bash
export PYTHONPATH=.
bash dumbo/run_demo.sh failover
```

**Terminal 2 — Hub**
```bash
export PYTHONPATH=.
bash dumbo/run_demo.sh hub
```

**Terminal 3 — Edge (real GPU HAL)**
```bash
export PYTHONPATH=.
export DUMBO_MOCK_FHE=0
bash dumbo/run_demo.sh edge
```

**Inspect inherited state after MAYDAY fires**
```bash
bash dumbo/run_demo.sh state
```

### No GPU? Run in mock mode

```bash
export DUMBO_MOCK_FHE=1
bash dumbo/run_demo.sh edge
```

---

## Example Output
[EDGE] INFO  GPU HAL encoder online
[EDGE] INFO  [004] flows=51,428  vram=281MB  temp=95C  stress=0.930
[EDGE] WARNING  MAYDAY triggered  stress=0.930
[EDGE] INFO  FHE slots encoded  flows=28188  vram=45345  temp=57994  stress=36336
[EDGE] INFO  Mayday delivered -> hub 200
[HUB]  WARNING  MAYDAY from edge-alpha  stress=0.930
[HUB]  INFO     FHE ciphertext received  coeffs=16  ct[0]=28188
[HUB]  INFO     Bootstrap complete 14.6ms
[HUB]  INFO     Lifeboat dropped -> failover 200
[FAILOVER] WARNING  LIFEBOAT received for edge-alpha
[FAILOVER] INFO     Active flows to restore : 51,428
[FAILOVER] INFO     Null-routing 3 prefixes
[FAILOVER] INFO     Installing 11 DDoS blocks
---

## Why This Matters

Existing failover systems hand off plaintext routing state. Dumbo Protocol
seals that state homomorphically at the moment of crisis — the hub and any
intermediate observers see only ciphertext. The failover node receives
encrypted context it can act on without decryption, opening the door to
privacy-preserving network state replication across untrusted infrastructure.

---

## Related

- [openfheNVDIA-GPU](https://github.com/samfrazerdutton/openfheNVDIA-GPU) — the CUDA HAL powering the encoder
- [OpenFHE](https://openfhe.org) — the underlying FHE library

---

## Author

**Sam Frazer-Dutton**
