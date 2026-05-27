import sys
import time
import os

sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('dumbo_ext'))

try:
    from dumbo_cuda import DumboBatchEncoder
    from dumbo.shared.fhe_matrix import decode_plains, T
except ImportError as e:
    print(f"Error loading CUDA extensions: {e}")
    sys.exit(1)

def print_header():
    print("\n" + "="*65)
    print(" 🐘 DUMBO PROTOCOL : GPU-ACCELERATED EDGE FHE ENGINE")
    print("="*65)

def run_showcase():
    print_header()
    
    print("\n[*] Initializing OpenFHE NVIDIA GPU HAL...")
    t0 = time.perf_counter()
    enc = DumboBatchEncoder(1024, T)
    t1 = time.perf_counter()
    print(f"    [+] CUDA Encoder Online (Init time: {(t1-t0)*1000:.2f} ms)")
    
    print("\n[*] Engine Specifications:")
    print("    - Polynomial Degree (N)  : 1024")
    print("    - Plaintext Modulus (T)  : 65537 (Negacyclic NTT)")
    print("    - Hardware Target        : NVIDIA CUDA")
    print("    - State Channels         : 4 Uniform Bands (256 slots/channel)")
    print("    - Math Backend           : Custom Barrett Reduction / Montgomery PTX")

    print("\n[*] Simulating MAYDAY Event (Edge-Failover Handoff)")
    flows_p = 13574
    vram_p = 290
    temp_p = 90
    stress_raw = 0.909
    stress_p = int(stress_raw * 65536) % T

    print("    [>] Raw Telemetry Captured:")
    print(f"        Flows: {flows_p} | VRAM: {vram_p}MB | Temp: {temp_p}C | Stress: {stress_raw}")

    flat = [flows_p]*256 + [vram_p]*256 + [temp_p]*256 + [stress_p]*256
    
    t_enc_start = time.perf_counter()
    ct = enc.encode_batch(flat)
    t_enc_end = time.perf_counter()
    
    ct_vals = [int(ct[0]), int(ct[256]), int(ct[512]), int(ct[768])]
    
    print(f"\n    [>] GPU NTT Polynomial Encode Latency: {(t_enc_end-t_enc_start)*1000:.3f} ms")
    print(f"    [>] Scrambled Coefficients Transmitted: {ct_vals}")

    print("\n[*] Failover Node: Z_65537 Matrix Inversion Decode")
    
    t_dec_start = time.perf_counter()
    decoded = decode_plains(ct_vals)
    t_dec_end = time.perf_counter()
    
    print(f"    [>] Gauss-Jordan Decode Latency: {(t_dec_end-t_dec_start)*1000:.3f} ms")
    print(f"    [>] Recovered Plaintext: Flows={decoded[0]}, VRAM={decoded[1]}, Temp={decoded[2]}")
    
    print("\n[*] Routing Decision Evaluation")
    stress_critical = decoded[3] > int(0.85 * 65536) % T
    temp_critical = decoded[2] > 90
    
    if stress_critical and temp_critical:
        action = "NULL_ROUTE_ALL_INBOUND"
    elif stress_critical or temp_critical:
        action = "THROTTLE_NEW_FLOWS"
    else:
        action = "MAINTAIN_CURRENT"
        
    print(f"    [+] Decision Executed: {action}")
    print("="*65 + "\n")

if __name__ == "__main__":
    run_showcase()
