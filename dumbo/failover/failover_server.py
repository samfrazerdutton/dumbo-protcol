import logging, time, os, sys
from fastapi import FastAPI, Request

sys.path.insert(0, '/home/samfrazerdutton/.local/lib/python3.12/site-packages')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [FAILOVER] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("dumbo/logs/failover.log"),
    ],
)
log = logging.getLogger("failover")

# Generate keypair at startup — sk never leaves this process
from dumbo.shared.fhe_engine import FailoverKeyHolder
log.info("[FHE] Generating BFV keypair...")
KEY_HOLDER = FailoverKeyHolder()
log.info("[FHE] Ready. Waiting for MAYDAY.")

app   = FastAPI()
STATE = {}

STRESS_THRESHOLD = 0.85
TEMP_THRESHOLD   = 90

def routing_decision(tel: dict) -> str:
    stress_crit = tel["stress"] > STRESS_THRESHOLD
    temp_crit   = tel["temp_c"] > TEMP_THRESHOLD
    if stress_crit and temp_crit:
        return "NULL_ROUTE_ALL_INBOUND"
    elif stress_crit or temp_crit:
        return "THROTTLE_NEW_FLOWS"
    else:
        return "MAINTAIN_CURRENT"

@app.get("/healthz")
def health():
    return {"status": "ok", "ts": time.time()}

@app.post("/lifeboat")
async def lifeboat(request: Request):
    body    = await request.json()
    node_id = body.get("node_id", "unknown")
    log.warning(f"LIFEBOAT received for {node_id}")

    # Decrypt the ciphertext — hub forwarded it opaque
    ct_b64 = body.get("fhe_ct_b64")
    if not ct_b64:
        return {"error": "no ciphertext"}, 400

    tel    = KEY_HOLDER.decrypt(ct_b64)
    action = routing_decision(tel)

    log.info("=" * 55)
    log.info("CONTEXTUAL REBIRTH")
    log.info(f"  flows={tel['flows']}  vram={tel['vram_mb']}MB  "
             f"temp={tel['temp_c']}C  stress={tel['stress']:.3f}")
    log.info(f"  >>> ROUTING DECISION: {action}")
    log.info("=" * 55)

    STATE.update({
        "node_id":          node_id,
        "telemetry":        tel,
        "routing_decision": action,
        "rebirth_ts":       time.time(),
        "fhe_mode":         "real_bfv",
    })
    return {"status": "reborn", "action": action}

@app.get("/state")
def state():
    return STATE
