import logging, time, json
from fastapi import FastAPI, Request
from dumbo.failover.fhe_threshold import fhe_threshold_check

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [FAILOVER] %(levelname)s %(message)s")
log = logging.getLogger("failover")

app = FastAPI()
STATE: dict = {}

@app.post("/rebirth")
async def rebirth(request: Request):
    global STATE
    STATE = await request.json()
    node      = STATE.get("node_id", "unknown")
    flows     = STATE.get("active_flows", 0)
    null_routes = STATE.get("null_routes", [])
    ddos      = STATE.get("ddos_signatures", [])
    fhe_ct    = STATE.get("fhe_ct", [])
    fhe_slots = STATE.get("fhe_slots", {})

    log.warning(f"LIFEBOAT received for {node}")
    log.info("=" * 55)
    log.info("CONTEXTUAL REBIRTH -- inherited routing state:")
    log.info(f"  Active flows to restore : {flows:,}")
    log.info(f"  Null-routing {len(null_routes)} prefixes")
    for r in null_routes:
        log.info(f"    ip route add blackhole {r}")
    log.info(f"  Installing {len(ddos)} DDoS blocks")
    for s in ddos[:5]:
        log.info(f"    iptables -I INPUT -s {s} -j DROP")

    # ── Homomorphic threshold evaluation ─────────────────────────────
    if fhe_ct and fhe_slots:
        decision = fhe_threshold_check(fhe_ct, fhe_slots)
        log.info("=" * 55)
        log.info("FHE THRESHOLD EVALUATION (no decryption):")
        log.info(f"  Stress encoded : {decision['stress_encoded']}  "
                 f"threshold={decision['stress_threshold']}  "
                 f"critical={decision['stress_critical']}")
        log.info(f"  Temp encoded   : {decision['temp_encoded']}  "
                 f"critical={decision['temp_critical']}")
        log.info(f"  >>> ROUTING DECISION : {decision['routing_action']}")
        STATE["routing_decision"] = decision
    # ─────────────────────────────────────────────────────────────────

    log.info("=" * 55)
    STATE["rebirth_ts"] = time.time()
    return {"status": "reborn", "flows": flows,
            "routing_decision": STATE.get("routing_decision", {})}

@app.get("/state")
async def state():
    return STATE
