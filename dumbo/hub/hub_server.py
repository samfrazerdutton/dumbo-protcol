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

app      = FastAPI(title="Dumbo Hub", version="3.0.0")
FAILOVER = "http://127.0.0.1:8001"
_lifeboats: dict = {}


@app.get("/healthz")
def health():
    return {"status": "ok", "ts": time.time(), "lifeboats": len(_lifeboats)}


@app.post("/mayday")
async def mayday(request: Request):
    t0   = time.time()
    body = await request.json()

    node_id = body.get("node_id", "unknown")
    stress  = body.get("node_stress", 0.0)   # triage only — hub never sees telemetry
    mode    = body.get("fhe_mode", "unknown")

    log.warning(f"MAYDAY from {node_id}  stress={stress:.3f}  mode={mode}")

    has_ct = "fhe_ct_b64" in body
    log.info(f"Ciphertext present: {has_ct}  "
             f"payload_size={len(str(body)):,} chars")

    # Forward the complete body opaque to failover — hub cannot decrypt it
    try:
        r  = requests.post(f"{FAILOVER}/lifeboat", json=body, timeout=30)
        ms = (time.time() - t0) * 1000
        log.info(f"Lifeboat dropped -> failover {r.status_code}  {ms:.1f}ms")
        _lifeboats[node_id] = {"ts": time.time(), "stress": stress, "mode": mode}
        return {"status": "lifeboat_delivered", "bootstrap_ms": ms}
    except Exception as e:
        log.warning(f"Failover unreachable: {e}")
        return {"status": "failover_unreachable", "error": str(e)}


@app.get("/lifeboats")
def list_lifeboats():
    return _lifeboats
