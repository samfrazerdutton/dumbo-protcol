import logging, time, requests
from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [HUB] %(levelname)s %(message)s")
log = logging.getLogger("hub")

app = FastAPI()
FAILOVER = "http://127.0.0.1:8001"

@app.post("/mayday")
async def mayday(request: Request):
    t0 = time.time()
    body = await request.json()
    node_id = body.get("node_id", "unknown")
    stress  = body.get("stress", 0)
    snapshot = body.get("snapshot", {})
    fhe_ct  = snapshot.get("fhe_ct", [])
    log.warning(f"MAYDAY from {node_id}  stress={stress:.3f}")
    if fhe_ct:
        log.info(f"FHE ciphertext received  coeffs={len(fhe_ct)}  ct[0]={fhe_ct[0]}")
    resp = requests.post(f"{FAILOVER}/rebirth", json=snapshot, timeout=5)
    ms = (time.time()-t0)*1000
    log.info(f"Bootstrap complete {ms:.1f}ms")
    log.info(f"Lifeboat dropped -> failover {resp.status_code}")
    return {"status": "lifeboat_delivered", "failover_ms": ms}
