import logging, time, json, os, random, requests
from pathlib import Path

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [EDGE] %(levelname)s %(message)s")
log = logging.getLogger("edge")

HUB      = os.getenv("DUMBO_HUB",  "http://127.0.0.1:8000")
NODE_ID  = os.getenv("DUMBO_NODE", "edge-alpha")
STATE_DIR = Path(__file__).parent / "../state"
STATE_DIR.mkdir(exist_ok=True)

MOCK = os.getenv("DUMBO_MOCK_FHE", "0") == "1"
if not MOCK:
    import sys
    sys.path.insert(0, str(Path(__file__).parent / "../../dumbo_ext"))
    from dumbo_cuda import DumboBatchEncoder
    encoder = DumboBatchEncoder(1024, 65537)
    log.info("GPU HAL encoder online")
else:
    encoder = None
    log.info("Mock FHE mode active")

def sample_state():
    return {
        "node_id":      NODE_ID,
        "active_flows": random.randint(10_000, 80_000),
        "vram_free_mb": random.randint(30, 500),
        "gpu_temp_c":   random.randint(70, 95),
        "stress":       round(random.uniform(0.1, 0.95), 3),
        "null_routes":  ["8.96.159.0/24","96.96.158.0/24","158.158.161.0/24"],
        "ddos_signatures": [
            "SRC_204.0","SRC_54.156","SRC_222.171","SRC_58.2","SRC_76.72",
            "SRC_18.244","SRC_178.152","SRC_122.83","SRC_157.18",
            "SRC_177.165","SRC_41.73"
        ]
    }

def fhe_encode(state):
    if encoder is None:
        return state
    # Pack all telemetry into 1024 slots:
    # slots 0-255   : active_flows repeated (network load signal)
    # slots 256-511 : vram_free_mb repeated (memory pressure signal)
    # slots 512-767 : gpu_temp_c repeated   (thermal signal)
    # slots 768-1023: stress * 65536        (normalised stress signal)
    T = 65537
    flows  = state["active_flows"] % T
    vram   = state["vram_free_mb"] % T
    temp   = state["gpu_temp_c"]   % T
    stress = int(state["stress"] * 65536) % T
    flat   = ([flows]  * 256 +
              [vram]   * 256 +
              [temp]   * 256 +
              [stress] * 256)
    ct = encoder.encode_batch(flat)
    state["fhe_ct"]        = ct[:16]   # first 16 coefficients in snapshot
    state["fhe_ct_len"]    = len(ct)
    state["fhe_slots"]     = {
        "flows_slot0":  ct[0],
        "vram_slot256": ct[256] if len(ct) > 256 else None,
        "temp_slot512": ct[512] if len(ct) > 512 else None,
        "stress_slot768": ct[768] if len(ct) > 768 else None,
    }
    return state

tick = 0
log.info(f"Edge daemon started  node={NODE_ID}  hub={HUB}")

while True:
    s = sample_state()
    log.info(f"[{tick:03d}] flows={s['active_flows']:,}  vram={s['vram_free_mb']}MB  "
             f"temp={s['gpu_temp_c']}C  stress={s['stress']}")

    if s["stress"] > 0.85:
        log.warning(f"MAYDAY triggered  stress={s['stress']}")
        s = fhe_encode(s)
        if "fhe_slots" in s:
            log.info(f"FHE slots encoded  "
                     f"flows={s['fhe_slots']['flows_slot0']}  "
                     f"vram={s['fhe_slots']['vram_slot256']}  "
                     f"temp={s['fhe_slots']['temp_slot512']}  "
                     f"stress={s['fhe_slots']['stress_slot768']}")
        snap_path = STATE_DIR / f"{NODE_ID}_mayday_{int(time.time())}.json"
        snap_path.write_text(json.dumps(s, indent=2, default=str))
        log.info(f"Snapshot saved -> {snap_path}")
        try:
            r = requests.post(f"{HUB}/mayday",
                json={"node_id": NODE_ID, "stress": s["stress"], "snapshot": s},
                timeout=5)
            log.info(f"Mayday delivered -> hub {r.status_code}")
        except Exception as e:
            log.error(f"Hub unreachable: {e}")
        log.critical("Edge node controlled shutdown.")
        break

    time.sleep(2)
    tick += 1
