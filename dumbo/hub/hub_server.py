import logging, time, requests
from fastapi import FastAPI, Request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [HUB] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("dumbo/logs/hub.log"),
    ],
)
log = logging.getLogger("hub")

app = FastAPI(title="Dumbo Hub", version="2.0.0")
FAILOVER = "http://127.0.0.1:8001"
_lifeboats: dict = {}


@app.get("/healthz")
def health():
    return {"status": "ok", "ts": time.time(), "lifeboats": len(_lifeboats)}


@app.post("/mayday")
async def mayday(request: Request):
    t0 = time.time()
    body     = await request.json()
    node_id  = body.get("node_id", "unknown")
    stress   = body.get("stress", 0)
    snapshot = body.get("snapshot", {})
    fhe_ct   = snapshot.get("fhe_ct", [])
    fhe_mock = snapshot.get("fhe_mock", True)
    log.warning(f"MAYDAY from {node_id}  stress={stress:.3f}  mock={fhe_mock}")
    if fhe_ct:
        log.info(f"FHE ciphertext received  coeffs={len(fhe_ct)}  ct[0]={fhe_ct[0]}")
    try:
        r = requests.post(f"{FAILOVER}/rebirth", json=snapshot, timeout=5)
        ms = (time.time() - t0) * 1000
        log.info(f"Bootstrap complete {ms:.1f}ms")
        log.info(f"Lifeboat dropped -> failover {r.status_code}")
        _lifeboats[node_id] = {"ts": time.time(), "stress": stress}
    except Exception as e:
        ms = (time.time() - t0) * 1000
        log.warning(f"Failover unreachable: {e}")
    return {"status": "lifeboat_delivered", "bootstrap_ms": ms}


@app.get("/lifeboats")
def list_lifeboats():
    return _lifeboats
