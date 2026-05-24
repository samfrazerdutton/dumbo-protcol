import logging, time, json
from fastapi import FastAPI, Request
from typing import Any

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [FAILOVER] %(levelname)s %(message)s")
log = logging.getLogger("failover")

app = FastAPI()
STATE: dict = {}

@app.post("/rebirth")
async def rebirth(request: Request):
    global STATE
    STATE = await request.json()
    node = STATE.get("node_id", "unknown")
    flows = STATE.get("active_flows", 0)
    null_routes = STATE.get("null_routes", [])
    ddos = STATE.get("ddos_signatures", [])
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
    log.info("=" * 55)
    STATE["rebirth_ts"] = time.time()
    return {"status": "reborn", "flows": flows}

@app.get("/state")
async def state():
    return STATE
