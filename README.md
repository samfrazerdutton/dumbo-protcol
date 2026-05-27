Dumbo Protocol
Dumbo Protocol is a high-performance, GPU-accelerated edge failover system designed for critical infrastructure. It enables secure, homomorphic state handoffs between edge nodes during stress events, ensuring that sensitive routing state is never exposed in plaintext to intermediate hub infrastructure.
-------------------------------------------------------------
Architecture Overview
Dumbo Protocol operates in an asymmetrical trust model:
----------------------------------------------------------------
1 Edge Node (GPU-Accelerated): Uses custom CUDA kernels to perform a Negacyclic NTT (Number Theoretic Transform) to pack live telemetry into a polynomial.
2 Hub (Un-trusted): Relays the encrypted coefficients without the ability to observe or alter the underlying state.
3  Failover Node (Matrix-Decoded): Un-mixes the polynomial coefficients using a pre-computed finite field matrix inverse ($\mathbb{M}^{-1} \pmod T$) to recover state and trigger routing actions.
--------------------------------------------------------------
Engine Specifications
-Polynomial Degree ($N$): 1024
-Plaintext Modulus ($T$): 65537
-Math Backend: Custom Barrett Reduction / Montgomery PTX Assembly
-Throughput: ~550+ Ops/sec (Encode)
-Latency: Sub-5ms E2E Handoff
-----------------------------------------------------------
Key Engineering Highlights
- PTX Assembly: Replaced high-level 128-bit integer emulation with inline PTX assembly for native 64-bit modular reduction, drastically reducing NTT butterfly latency.
- Gauss-Jordan Decoding: Implemented modular matrix inversion over $\mathbb{Z}_{65537}$ to un-mix the packed channels, allowing the Failover node to act on recovered telemetry without requiring a secret key or traditional decryption overhead.
- Stream Management: Custom CUDA StreamPool instance implementation to maximize GPU occupancy and VRAM throughput during parallel state packing.
----------------------------------------------------------
Getting Started
Prerequisites

-NVIDIA GPU (CUDA-capable)
-Python 3.12+
-CUDA Toolkit (12.x recommended)
------------------------------------------------------
Setup
----------------------------------------------------
# Clone and build extensions
git clone https://github.com/samfrazerdutton/dumbo-protcol
cd dumbo-protcol
./dumbo_setup.sh
-----------------------------------------------------
Run the Showcase
To verify the engine is fully operational and to see a breakdown of the hardware performance:

export PYTHONPATH=.
python3 dumbo_showcase.py
----------------------------------------------------------
Performance Benchmarks
----------------------------------------------------------
Running the integrated stress test (5,000 randomized state handoffs) yields the following performance profiles on an NVIDIA RTX 2060:
-----------------------------------------------------------
Metric	      GPU Encode (CUDA)	    CPU Decode (Matrix Math
------------------------------------------------------------
Avg Latency           1.8 ms               0.016 ms

99th Percentile       3.5 ms                0.028 ms

Peak Throughput       555 Ops/sec           62,091 Ops/sec


License

MIT License. Created by Sam Frazer Dutton (Billinghurst).





