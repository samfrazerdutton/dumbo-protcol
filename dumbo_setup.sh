#!/bin/bash
set -e
REPO_ROOT="$(pwd)"
DUMBO="$REPO_ROOT/dumbo"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          DUMBO PROTOCOL — PoC Bootstrap Script               ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

mkdir -p "$DUMBO"/{edge,hub,failover,shared,state,logs}
echo "[+] Directory tree created"

cd "$REPO_ROOT"
python3 -m venv dumbo/venv
source dumbo/venv/bin/activate
pip install --quiet fastapi uvicorn requests numpy pydantic cryptography
echo "[+] Python venv ready"

# ── shared/crt_codec.py ──────────────────────────────────────────────────────
cat > dumbo/shared/crt_codec.py << 'PYEOF'
import numpy as np
from typing import List

DEFAULT_MODULI: List[int] = [
    1073741827, 1073741831, 1073741833, 1073741909,
    1073741939, 1073741953, 1073741969, 1073741971,
]

def pack(values: List[float], scale: int = 1_000_000) -> dict:
    int_vals = [int(round(v * scale)) for v in values]
    residues = {}
    for q in DEFAULT_MODULI:
        residues[str(q)] = [v % q for v in int_vals]
    return {"residues": residues, "scale": scale, "n": len(values)}

def unpack(payload: dict) -> List[float]:
    residues = payload["residues"]
    scale    = payload["scale"]
    n        = payload["n"]
    moduli   = [int(k) for k in residues.keys()]
    M = 1
    for q in moduli:
        M *= q
    results = []
    for i in range(n):
        x = 0
        for q in moduli:
            r  = residues[str(q)][i]
            Mi = M // q
            yi = pow(Mi, q - 2, q)
            x += r * Mi * yi
        results.append((x % M) / scale)
    return results
PYEOF

# ── shared/noise_model.py ────────────────────────────────────────────────────
cat > dumbo/shared/noise_model.py << 'PYEOF'
import numpy as np
import statistics

def inject_stress_noise(values: list, stress_level: float) -> list:
    sigma = stress_level * 0.05 * (max(abs(v) for v in values) + 1e-9)
    rng   = np.random.default_rng(42)
    return [v + float(rng.normal(0, sigma)) for v in values]

def bootstrap_clean(noisy: list, window: int = 3) -> list:
    cleaned = []
    for i, v in enumerate(noisy):
        lo = max(0, i - window)
        hi = min(len(noisy), i + window + 1)
        cleaned.append(statistics.median(noisy[lo:hi]))
    return cleaned
PYEOF

# ── shared/fhe_bridge.py ─────────────────────────────────────────────────────
cat > dumbo/shared/fhe_bridge.py << 'PYEOF'
import os, time
from typing import Optional

MOCK_MODE = os.environ.get("DUMBO_MOCK_FHE", "1") == "1"
if not MOCK_MODE:
    try:
        import openfhe as fhe
        MOCK_MODE = False
    except ImportError:
        MOCK_MODE = True

class FHEContext:
    def __init__(self):
        self.mock = MOCK_MODE
        if not self.mock:
            params = fhe.CCParamsCKKSRNS()
            params.SetMultiplicativeDepth(6)
            params.SetScalingModSize(50)
            params.SetBatchSize(1024)
            self.cc   = fhe.GenCryptoContext(params)
            self.cc.Enable(fhe.PKESchemeFeature.PKE)
            self.cc.Enable(fhe.PKESchemeFeature.LEVELEDSHE)
            self.cc.Enable(fhe.PKESchemeFeature.ADVANCEDSHE)
            self.keys = self.cc.KeyGen()
            self.cc.EvalMultKeyGen(self.keys.secretKey)
            self.cc.EvalBootstrapSetup(self.cc)
            self.cc.EvalBootstrapKeyGen(self.keys.secretKey, 1)

    def encrypt(self, values: list) -> dict:
        if self.mock:
            return {"mock": True, "data": list(values), "ts": time.time()}
        pt = self.cc.MakeCKKSPackedPlaintext(values)
        ct = self.cc.Encrypt(self.keys.publicKey, pt)
        return {"mock": False, "serial": ct.Serialize()}

    def decrypt(self, ct_dict: dict) -> list:
        if self.mock or ct_dict.get("mock"):
            return ct_dict["data"]
        ct = self.cc.DeserializeCiphertext(ct_dict["serial"])
        pt = self.cc.Decrypt(self.keys.secretKey, ct)
        pt.SetLength(1024)
        return pt.GetCKKSPackedValue()

    def bootstrap(self, ct_dict: dict) -> dict:
        if self.mock or ct_dict.get("mock"):
            from dumbo.shared.noise_model import bootstrap_clean
            ct_dict["data"] = bootstrap_clean(ct_dict["data"])
            ct_dict["bootstrapped"] = True
            return ct_dict
        ct_in  = self.cc.DeserializeCiphertext(ct_dict["serial"])
        ct_out = self.cc.EvalBootstrap(ct_in)
        return {"mock": False, "serial": ct_out.Serialize(), "bootstrapped": True}

_ctx: Optional[FHEContext] = None
def get_context() -> FHEContext:
    global _ctx
    if _ctx is None:
        _ctx = FHEContext()
    return _ctx
PYEOF

# ── edge/edge_daemon.py ──────────────────────────────────────────────────────
cat > dumbo/edge/edge_daemon.py << 'PYEOF'
#!/usr/bin/env python3
import os, sys, json, time, random, logging, signal, requests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from dumbo.shared.crt_codec   import pack
from dumbo.shared.noise_model import inject_stress_noise
from dumbo.shared.fhe_bridge  import get_context

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EDGE] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "../logs/edge.log")),
    ],
)
log = logging.getLogger("edge")

HUB_URL   = os.environ.get("DUMBO_HUB_URL",  "http://127.0.0.1:8000")
NODE_ID   = os.environ.get("DUMBO_NODE_ID",   "edge-alpha")
STATE_DIR = os.path.join(os.path.dirname(__file__), "../state")

def get_routing_state() -> dict:
    return {
        "node_id":        NODE_ID,
        "timestamp":      time.time(),
        "active_flows":   random.randint(10_000, 80_000),
        "null_routes":    [f"192.168.{random.randint(1,254)}.0/24"
                           for _ in range(random.randint(3, 12))],
        "ddos_signatures":[f"SRC_{random.randint(1,255)}.{random.randint(0,255)}"
                           for _ in range(random.randint(5, 20))],
        "latency_ms":     round(random.uniform(0.5, 4.5), 3),
        "vram_free_mb":   random.randint(0, 512),
        "gpu_temp_c":     random.randint(70, 95),
    }

def stress_level(state: dict) -> float:
    vram_stress = max(0.0, 1.0 - state["vram_free_mb"] / 512.0)
    temp_stress = max(0.0, (state["gpu_temp_c"] - 70) / 25.0)
    lat_stress  = max(0.0, (state["latency_ms"] - 1.0) / 3.5)
    return min(1.0, vram_stress * 0.5 + temp_stress * 0.3 + lat_stress * 0.2)

def encode_state_vector(state: dict) -> list:
    vec = [0.0] * 1024
    vec[0] = state["active_flows"] / 100_000.0
    vec[1] = state["latency_ms"]   / 10.0
    vec[2] = state["vram_free_mb"] / 4096.0
    vec[3] = state["gpu_temp_c"]   / 100.0
    vec[4] = float(len(state["null_routes"]))    / 64.0
    vec[5] = float(len(state["ddos_signatures"])) / 256.0
    for i, cidr in enumerate(state["null_routes"][:64]):
        base = 8 + i * 4
        parts = cidr.split("/")[0].split(".")
        for j, octet in enumerate(parts):
            vec[base + j] = int(octet) / 255.0
    for i, sig in enumerate(state["ddos_signatures"][:256]):
        vec[264 + i] = (hash(sig) % 100_000) / 100_000.0
    return vec

def mayday(state: dict, stress: float):
    log.warning(f"MAYDAY triggered  stress={stress:.3f}")
    raw_vec   = encode_state_vector(state)
    noisy_vec = inject_stress_noise(raw_vec, stress)
    ctx = get_context()
    ct  = ctx.encrypt(noisy_vec)
    payload = {
        "node_id":        NODE_ID,
        "stress":         stress,
        "state_meta":     {k: v for k, v in state.items()
                           if k not in ("null_routes", "ddos_signatures")},
        "null_routes":    state["null_routes"],
        "ddos_signatures":state["ddos_signatures"],
        "ciphertext":     ct,
    }
    snap = os.path.join(STATE_DIR, f"{NODE_ID}_mayday_{int(time.time())}.json")
    with open(snap, "w") as f:
        json.dump(payload, f, indent=2)
    log.info(f"Snapshot saved -> {snap}")
    try:
        r = requests.post(f"{HUB_URL}/mayday", json=payload, timeout=5)
        r.raise_for_status()
        log.info(f"Mayday delivered -> hub {r.status_code}")
    except Exception as e:
        log.error(f"Hub unreachable ({e}) — payload in {snap}")
    log.critical("Edge node entering controlled shutdown.")
    sys.exit(0)

def run():
    log.info(f"Edge daemon started  node={NODE_ID}  hub={HUB_URL}")
    poll = float(os.environ.get("DUMBO_POLL_SEC",    "2"))
    maxc = int(os.environ.get("DUMBO_MAX_CYCLES", "9999"))
    for cycle in range(maxc):
        state = get_routing_state()
        sl    = stress_level(state)
        log.info(f"[{cycle:03d}] flows={state['active_flows']:,}  "
                 f"vram={state['vram_free_mb']}MB  "
                 f"temp={state['gpu_temp_c']}C  stress={sl:.3f}")
        if sl >= 0.85:
            mayday(state, sl)
            return
        time.sleep(poll)
    log.info("Max cycles reached — exiting cleanly.")

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    run()
PYEOF

# ── hub/hub_server.py ────────────────────────────────────────────────────────
cat > dumbo/hub/hub_server.py << 'PYEOF'
#!/usr/bin/env python3
import os, sys, json, time, logging, requests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from fastapi           import FastAPI, HTTPException
from pydantic          import BaseModel
from typing            import Any, Dict, List
from dumbo.shared.fhe_bridge import get_context

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [HUB] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "../logs/hub.log")),
    ],
)
log = logging.getLogger("hub")

FAILOVER_URL = os.environ.get("DUMBO_FAILOVER_URL", "http://127.0.0.1:8001")
STATE_DIR    = os.path.join(os.path.dirname(__file__), "../state")
app          = FastAPI(title="Dumbo Hub", version="1.0.0")
lifeboats: Dict[str, dict] = {}

class MaydayPayload(BaseModel):
    node_id:        str
    stress:         float
    state_meta:     Dict[str, Any]
    null_routes:    List[str]
    ddos_signatures:List[str]
    ciphertext:     Dict[str, Any]

@app.get("/healthz")
def health():
    return {"status": "ok", "ts": time.time()}

@app.post("/mayday")
def receive_mayday(payload: MaydayPayload):
    log.warning(f"MAYDAY from {payload.node_id}  stress={payload.stress:.3f}")
    ctx = get_context()
    t0  = time.perf_counter()
    clean_ct   = ctx.bootstrap(dict(payload.ciphertext))
    elapsed_ms = (time.perf_counter() - t0) * 1000
    log.info(f"Bootstrap complete {elapsed_ms:.1f}ms")
    lifeboat = {
        "node_id":        payload.node_id,
        "born_at":        time.time(),
        "stress_at_death":payload.stress,
        "state_meta":     payload.state_meta,
        "null_routes":    payload.null_routes,
        "ddos_signatures":payload.ddos_signatures,
        "ciphertext":     clean_ct,
        "bootstrap_ms":   elapsed_ms,
    }
    lifeboats[payload.node_id] = lifeboat
    with open(os.path.join(STATE_DIR, f"{payload.node_id}_lifeboat.json"), "w") as f:
        json.dump(lifeboat, f, indent=2)
    try:
        r = requests.post(f"{FAILOVER_URL}/rebirth", json=lifeboat, timeout=5)
        r.raise_for_status()
        log.info(f"Lifeboat dropped -> failover {r.status_code}")
    except Exception as e:
        log.warning(f"Failover unreachable ({e})")
    return {"status": "bootstrapped", "node_id": payload.node_id,
            "bootstrap_ms": elapsed_ms}

@app.get("/lifeboats")
def list_lifeboats():
    return {nid: {k: v for k, v in lb.items() if k != "ciphertext"}
            for nid, lb in lifeboats.items()}

@app.get("/lifeboat/{node_id}")
def get_lifeboat(node_id: str):
    if node_id not in lifeboats:
        raise HTTPException(404, f"No lifeboat for {node_id}")
    lb = dict(lifeboats[node_id])
    lb.pop("ciphertext", None)
    return lb
PYEOF

# ── failover/failover_server.py ──────────────────────────────────────────────
cat > dumbo/failover/failover_server.py << 'PYEOF'
#!/usr/bin/env python3
import os, sys, json, time, logging
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from fastapi           import FastAPI
from pydantic          import BaseModel
from typing            import Any, Dict, List, Optional
from dumbo.shared.fhe_bridge import get_context

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [FAILOVER] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "../logs/failover.log")),
    ],
)
log      = logging.getLogger("failover")
STATE_DIR = os.path.join(os.path.dirname(__file__), "../state")
app       = FastAPI(title="Dumbo Failover", version="1.0.0")
reborn_state: Optional[dict] = None

class LifeboatPayload(BaseModel):
    node_id:         str
    born_at:         float
    stress_at_death: float
    state_meta:      Dict[str, Any]
    null_routes:     List[str]
    ddos_signatures: List[str]
    ciphertext:      Dict[str, Any]
    bootstrap_ms:    float

def decode_state_vector(vec: list, meta: dict) -> dict:
    null_routes = []
    n_null = max(0, int(round(vec[4] * 64)))
    for i in range(min(n_null, 64)):
        base   = 8 + i * 4
        octets = [int(round(vec[base + j] * 255)) for j in range(4)]
        null_routes.append(f"{octets[0]}.{octets[1]}.{octets[2]}.0/24")
    return {
        "inherited_from":  meta.get("node_id", "unknown"),
        "active_flows":    int(vec[0] * 100_000),
        "latency_ms":      round(vec[1] * 10.0, 3),
        "vram_free_mb":    round(vec[2] * 4096.0),
        "gpu_temp_c":      round(vec[3] * 100.0),
        "null_routes":     null_routes,
        "ddos_signatures": meta.get("ddos_signatures", []),
        "rebirth_ts":      time.time(),
    }

def apply_routing_context(state: dict):
    log.info(f"  Active flows to restore : {state['active_flows']:,}")
    log.info(f"  Null-routing {len(state['null_routes'])} prefixes")
    for r in state["null_routes"][:5]:
        log.info(f"    ip route add blackhole {r}")
    log.info(f"  Installing {len(state['ddos_signatures'])} DDoS blocks")
    for sig in state["ddos_signatures"][:5]:
        log.info(f"    iptables -I INPUT -s {sig} -j DROP")

@app.get("/healthz")
def health():
    return {"status": "standby" if reborn_state is None else "active",
            "ts": time.time()}

@app.post("/rebirth")
def receive_lifeboat(payload: LifeboatPayload):
    global reborn_state
    log.warning(f"LIFEBOAT received for {payload.node_id}")
    ctx = get_context()
    vec   = ctx.decrypt(dict(payload.ciphertext))
    state = decode_state_vector(vec, {
        "node_id":        payload.node_id,
        "ddos_signatures":payload.ddos_signatures,
    })
    log.info("=" * 55)
    log.info("CONTEXTUAL REBIRTH — inherited routing state:")
    apply_routing_context(state)
    log.info("=" * 55)
    reborn_state = state
    with open(os.path.join(STATE_DIR, f"{payload.node_id}_rebirth.json"), "w") as f:
        json.dump(state, f, indent=2)
    return {"status": "reborn", "node_id": payload.node_id,
            "inherited_flows": state["active_flows"],
            "null_routes_applied": len(state["null_routes"]),
            "ddos_sigs_applied": len(state["ddos_signatures"])}

@app.get("/state")
def get_state():
    return {"status": "cold_standby"} if reborn_state is None else reborn_state
PYEOF

# ── __init__ stubs ────────────────────────────────────────────────────────────
touch dumbo/shared/__init__.py dumbo/edge/__init__.py \
      dumbo/hub/__init__.py dumbo/failover/__init__.py dumbo/__init__.py

# ── run_demo.sh ───────────────────────────────────────────────────────────────
cat > dumbo/run_demo.sh << 'RUNEOF'
#!/bin/bash
set -e
cd "$(dirname "$0")/.."          # repo root
source dumbo/venv/bin/activate
export PYTHONPATH="$(pwd)"
export DUMBO_MOCK_FHE=1
export DUMBO_HUB_URL=http://127.0.0.1:8000
export DUMBO_FAILOVER_URL=http://127.0.0.1:8001
export DUMBO_POLL_SEC=2
export DUMBO_MAX_CYCLES=9999
mkdir -p dumbo/logs dumbo/state

echo ""
echo "Dumbo Protocol — starting all components"
echo ""

if command -v tmux &>/dev/null; then
    SESSION="dumbo"
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    tmux new-session -d -s "$SESSION" -x 220 -y 50

    tmux rename-window -t "$SESSION:0" hub
    tmux send-keys -t "$SESSION:0" \
      "source dumbo/venv/bin/activate && PYTHONPATH=$(pwd) \
       uvicorn dumbo.hub.hub_server:app --host 0.0.0.0 --port 8000" Enter

    tmux new-window -t "$SESSION" -n failover
    tmux send-keys -t "$SESSION:failover" \
      "source dumbo/venv/bin/activate && PYTHONPATH=$(pwd) \
       uvicorn dumbo.failover.failover_server:app --host 0.0.0.0 --port 8001" Enter

    sleep 2

    tmux new-window -t "$SESSION" -n edge
    tmux send-keys -t "$SESSION:edge" \
      "source dumbo/venv/bin/activate && PYTHONPATH=$(pwd) \
       DUMBO_MOCK_FHE=1 python3 dumbo/edge/edge_daemon.py" Enter

    echo "tmux session 'dumbo' running."
    echo "  Attach : tmux attach -t dumbo"
    echo "  Windows: hub | failover | edge"
    echo ""
    echo "API:"
    echo "  curl http://localhost:8000/lifeboats"
    echo "  curl http://localhost:8001/state"
else
    uvicorn dumbo.hub.hub_server:app \
        --host 0.0.0.0 --port 8000 >> dumbo/logs/hub.log 2>&1 &
    echo "Hub PID: $!"

    uvicorn dumbo.failover.failover_server:app \
        --host 0.0.0.0 --port 8001 >> dumbo/logs/failover.log 2>&1 &
    echo "Failover PID: $!"

    sleep 2
    echo "Starting edge daemon (will mayday when stress >= 0.85)..."
    python3 dumbo/edge/edge_daemon.py 2>&1 | tee dumbo/logs/edge.log
fi
RUNEOF
chmod +x dumbo/run_demo.sh

echo ""
echo "[✓] Dumbo Protocol files written to: $DUMBO"
echo ""
echo "Next:"
echo "  bash dumbo/run_demo.sh"
echo ""
echo "API once running:"
echo "  curl http://localhost:8000/lifeboats | python3 -m json.tool"
echo "  curl http://localhost:8001/state     | python3 -m json.tool"
