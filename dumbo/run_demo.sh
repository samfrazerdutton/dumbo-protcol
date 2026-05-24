#!/bin/bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT"
export DUMBO_MOCK_FHE="${DUMBO_MOCK_FHE:-0}"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║      DUMBO PROTOCOL  ×  OpenFHE NVIDIA GPU HAL              ║"
echo "║      Three-terminal demo: failover → hub → edge             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  TERMINAL 1:  bash dumbo/run_demo.sh failover"
echo "  TERMINAL 2:  bash dumbo/run_demo.sh hub"
echo "  TERMINAL 3:  bash dumbo/run_demo.sh edge"
echo ""

COMPONENT="${1:-help}"

case "$COMPONENT" in
  failover)
    echo "[*] Starting failover server on :8001"
    dumbo/venv/bin/uvicorn dumbo.failover.failover_server:app \
        --host 127.0.0.1 --port 8001 --log-level warning
    ;;
  hub)
    echo "[*] Starting hub server on :8000"
    dumbo/venv/bin/uvicorn dumbo.hub.hub_server:app \
        --host 127.0.0.1 --port 8000 --log-level warning
    ;;
  edge)
    echo "[*] Starting edge daemon"
    dumbo/venv/bin/python3 dumbo/edge/edge_daemon.py
    ;;
  state)
    echo "[*] Failover state snapshot:"
    curl -s http://127.0.0.1:8001/state | python3 -m json.tool
    ;;
  *)
    echo "Usage: bash dumbo/run_demo.sh [failover|hub|edge|state]"
    ;;
esac
