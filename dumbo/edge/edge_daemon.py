import logging, time, json, os, random, sys, requests
from pathlib import Path

sys.path.insert(0, '/home/samfrazerdutton/.local/lib/python3.12/site-packages')
sys.path.insert(0, str(Path(__file__).parent / "../.."))

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

from dumbo.shared.fhe_engine import EdgeEncryptor
encryptor = EdgeEncryptor()

def sample_telemetry(tick):
    return {
        "flows":   random.randint(5000, 80000),
        "vram_mb": random.randint(50, 500),
        "temp_c":  random.randint(60, 95),
        "stress":  round(random.uniform(0.3, 0.99), 3),
    }

log.info(f"Edge daemon started  node={NODE_ID}  hub={HUB}")

tick = 0
while True:
    tel = sample_telemetry(tick)
    log.info(f"[{tick:03d}] flows={tel['flows']:,}  vram={tel['vram_mb']}MB  "
             f"temp={tel['temp_c']}C  stress={tel['stress']}")

    if tel["stress"] > 0.85:
        log.warning(f"MAYDAY triggered  stress={tel['stress']}")

        ct_b64 = encryptor.encrypt(
            tel["flows"], tel["vram_mb"], tel["temp_c"], tel["stress"]
        )
        log.info(f"BFV ciphertext ready  size={len(ct_b64):,} chars")

        payload = {
            "node_id":    NODE_ID,
            "fhe_ct_b64": ct_b64,
            "fhe_mode":   "real_bfv",
            # Hub sees only these — no raw telemetry
            "node_stress": tel["stress"],  # just for hub routing triage
        }

        # Save snapshot
        snap_path = STATE_DIR / f"{NODE_ID}_mayday_{int(time.time())}.json"
        with open(snap_path, "w") as f:
            json.dump({"node_id": NODE_ID, "ts": time.time(),
                       "fhe_mode": "real_bfv"}, f)
        log.info(f"Snapshot saved -> {snap_path}")

        for attempt in range(1, 4):
            try:
                r = requests.post(f"{HUB}/mayday", json=payload, timeout=10)
                log.info(f"Mayday delivered -> hub {r.status_code}")
                break
            except Exception as e:
                log.warning(f"Hub unreachable (attempt {attempt}/3): {e}")
                time.sleep(1)
        else:
            log.critical("Hub unreachable after 3 attempts.")

        log.critical("Edge node controlled shutdown.")
        break

    tick += 1
    time.sleep(POLL_SEC)
