#!/usr/bin/env bash
# Launch the lp2graph demo UI.
#   ./run.sh                 -> http://127.0.0.1:8000
#   ./run.sh --port 9000     -> custom port
#   HOST=0.0.0.0 ./run.sh    -> expose on the LAN (for the self-hosted demo)
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
exec "$PY" server.py "$@"
