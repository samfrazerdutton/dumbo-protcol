import logging, time, json, os, random, sys, signal, requests
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EDGE] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent / "../logs/edge.log"),
    ],
)
log = logging.getLogger("edge")

HUB      = os.getenv("DUMBO_HUB",  "http://127.0.0.1:8000")
NODE_ID  = os.getenv("DUMBO_NODE", "edge-alpha")
POLL_SEC = float(os.getenv("DUMBO_POLL_SEC", "2"))
STATE_DIR = Path(__file__).parent / "../state"
STATE_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(Path(__file__).parent / "../../dumbo_ext"))
MOCK = os.getenv("DUMBO_MOCK_FHE", "0") == "1"

encoder = None
if not MOCK:
    try:
        from dumbo_cuda import DumboBatchEncoder
        encoder = DumboBatchEncoder(1024, 65537)
        log.info("GPU HAL encoder online  N=1024 T=65537")
    except ImportError as e:
        log.warning(f"GPU HAL unavailable ({e}) — falling back to mock FHE")
else:
    log.info("Mock FHE mode (DUMBO_MOCK_FHE=1)")


def sample_state():
    return {
        "node_id":        NODE_ID,
        "active_flows":   random.randint(10_000, 80_000),
        "vram_free_mb":   random.randint(30, 500),
        "gpu_temp_c":     random.randint(70, 95),
        "stress":         round(random.uniform(0.1, 0.95), 3),
        "null_routes":    ["8.96.159.0/24", "96.96.158.0/24", "158.158.161.0/24"],
        "ddos_signatures": [
            "SRC_204.0","SRC_54.156","SRC_222.171","SRC_58.2","SRC_76.72",
            "SRC_18.244","SRC_178.152","SRC_122.83","SRC_157.18",
            "SRC_177.165","SRC_41.73"
        ],
    }


def fhe_encode(state):
    T = 65537
    flows  = state["active_flows"] % T
    vram   = state["vram_free_mb"] % T
    temp   = state["gpu_temp_c"]   % T
    stress = int(state["stress"] * 65536) % T
    flat   = ([flows]  * 256 +
              [vram]   * 256 +
              [temp]   * 256 +
              [stress] * 256)
    if encoder is None:
        # mock: return plaintext slots
        state["fhe_ct"]     = flat[:16]
        state["fhe_ct_len"] = 1024
        state["fhe_slots"]  = {
            "flows_slot0":    flows,
            "vram_slot256":   vram,
            "temp_slot512":   temp,
            "stress_slot768": stress,
        }
        state["fhe_mock"] = True
        return state

    ct = encoder.encode_batch(flat)
    state["fhe_ct"]     = [int(x) for x in ct[:16]]
    state["fhe_ct_len"] = len(ct)
    state["fhe_slots"]  = {
        "flows_slot0":    int(ct[0])   if len(ct) > 0   else None,
        "vram_slot256":   int(ct[256]) if len(ct) > 256 else None,
        "temp_slot512":   int(ct[512]) if len(ct) > 512 else None,
        "stress_slot768": int(ct[768]) if len(ct) > 768 else None,
    }
    state["fhe_mock"] = False
    return state


def send_mayday(state, retries=3):
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(
                f"{HUB}/mayday",
                json={"node_id": NODE_ID, "stress": state["stress"], "snapshot": state},
                timeout=5,
            )
            log.info(f"Mayday delivered -> hub {r.status_code}")
            return True
        except Exception as e:
            log.warning(f"Hub unreachable (attempt {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(1)
    log.error("All mayday delivery attempts failed — state saved locally only")
    return False


shutdown = False
def _sig(signum, frame):
    global shutdown
    shutdown = True
signal.signal(signal.SIGTERM, _sig)
signal.signal(signal.SIGINT,  _sig)

tick = 0
log.info(f"Edge daemon started  node={NODE_ID}  hub={HUB}  mock={MOCK}")

while not shutdown:
    s = sample_state()
    log.info(f"[{tick:03d}] flows={s['active_flows']:,}  vram={s['vram_free_mb']}MB  "
             f"temp={s['gpu_temp_c']}C  stress={s['stress']}")

    if s["stress"] > 0.85:
        log.warning(f"MAYDAY triggered  stress={s['stress']}")
        s = fhe_encode(s)
        if "fhe_slots" in s:
            log.info(f"FHE encoded  mock={s.get('fhe_mock')}  "
                     f"flows={s['fhe_slots']['flows_slot0']}  "
                     f"vram={s['fhe_slots']['vram_slot256']}  "
                     f"temp={s['fhe_slots']['temp_slot512']}  "
                     f"stress={s['fhe_slots']['stress_slot768']}")
        snap = STATE_DIR / f"{NODE_ID}_mayday_{int(time.time())}.json"
        snap.write_text(json.dumps(s, indent=2, default=str))
        log.info(f"Snapshot saved -> {snap}")
        send_mayday(s)
        log.critical("Edge node controlled shutdown.")
        break

    time.sleep(POLL_SEC)
    tick += 1
