# Dumbo Protocol × OpenFHE NVIDIA GPU HAL

## What This Is

The first demonstrated system to perform **FHE-sealed network state handoff** 
at the edge-failover layer.

When an edge node detects critical stress, it:
1. GPU-encodes all live telemetry into a 1024-slot CRT polynomial using 
   OpenFHE NVIDIA CUDA HAL (EvalMultRNS, ~2.3ms per encode)
2. Transmits the ciphertext snapshot to the hub (<15ms bootstrap)
3. The failover node inherits encrypted operational context — flows, VRAM 
   pressure, thermal load, stress — without the hub ever seeing plaintext

## Architecture
edge-alpha (GPU HAL)
│  MAYDAY + fhe_ct
▼
hub :8000  ──── lifeboat ────▶  failover :8001
│
└── inherits: flows, null_routes,
ddos_blocks, fhe_ct
## FHE Slot Layout (N=1024, T=65537)

| Slots     | Channel         | Example value |
|-----------|-----------------|---------------|
| 0–255     | active_flows    | 28188         |
| 256–511   | vram_free_mb    | 45345         |
| 512–767   | gpu_temp_c      | 57994         |
| 768–1023  | stress ×65536   | 36336         |

## Performance (measured)

| Event                  | Latency  |
|------------------------|----------|
| GPU CRT encode (1024N) | ~11ms    |
| Hub bootstrap          | 4–15ms   |
| Full MAYDAY→rebirth    | <30ms    |

## Stack

- OpenFHE NVIDIA GPU HAL (`CUDAMathHAL::EvalMultRNS`)
- CUDA kernels: `cuda_math.cu`, `cuda_ntt.cu`, `cuda_keyswitch.cu`
- Python bridge: pybind11 → `dumbo_cuda.so`
- FastAPI edge/hub/failover microservices

## Run

```bash
# Terminal 1
bash dumbo/run_demo.sh failover

# Terminal 2  
bash dumbo/run_demo.sh hub

# Terminal 3
export DUMBO_MOCK_FHE=0
bash dumbo/run_demo.sh edge

# Inspect state
bash dumbo/run_demo.sh state
```
