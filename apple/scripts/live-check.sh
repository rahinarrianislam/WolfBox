#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
PYTHON="$ROOT/apple/.venv/bin/python"
export WOLFBOX_LIVE_PORT="${WOLFBOX_LIVE_PORT:-18300}"
BOX_A_PORT=$((WOLFBOX_LIVE_PORT + 1))
BOX_B_PORT=$((WOLFBOX_LIVE_PORT + 2))
if [[ ! -x "$PYTHON" ]]; then echo 'Create apple/.venv with Python 3.11+ and install box/requirements.txt and orchestrator/requirements.txt first.' >&2; exit 1; fi
"$PYTHON" - <<'PY'
import os, socket
base = int(os.environ["WOLFBOX_LIVE_PORT"])
for port in range(base, base + 3):
    with socket.socket() as sock:
        try: sock.bind(('127.0.0.1', port))
        except OSError: raise SystemExit(f'Port {port} is already in use; no processes were changed.')
PY
LIVE_DIR="$(mktemp -d "$ROOT/.data-apple-live.XXXXXX")"
children=()
cleanup() {
  trap - EXIT INT TERM
  for pid in "${children[@]}"; do kill "$pid" 2>/dev/null || true; done
  for pid in "${children[@]}"; do wait "$pid" 2>/dev/null || true; done
  # Only this script's disposable, freshly-created directory is removed.
  rm -rf "$LIVE_DIR"
}
trap cleanup EXIT INT TERM
cp -R orchestrator/course_site "$LIVE_DIR/course_site"
mkdir -p "$LIVE_DIR/static"
for pair in "alex:$BOX_A_PORT" "sam:$BOX_B_PORT"; do
  student="${pair%:*}"; port="${pair#*:}"
  env DATA_DIR="$LIVE_DIR/$student" PORT="$port" ALLOW_SEED=1 STUCK_MINUTES=2 GEMMA_BACKEND=fake \
    COURSE_URL="http://127.0.0.1:$WOLFBOX_LIVE_PORT/course/csc116/course.json" \
    "$PYTHON" box/start.py >"$LIVE_DIR/$student.log" 2>&1 &
  children+=("$!")
done
env PYTHONPATH="$ROOT/orchestrator" WOLFBOX_LIVE_ROOT="$LIVE_DIR" REGISTRY_PATH="$LIVE_DIR/students.json" \
  LOCAL_BOXES="alex=http://127.0.0.1:$BOX_A_PORT,sam=http://127.0.0.1:$BOX_B_PORT" BOX_BACKEND=local \
  "$PYTHON" apple/scripts/live_server.py >"$LIVE_DIR/orchestrator.log" 2>&1 &
children+=("$!")
"$PYTHON" - <<'PY'
import os, time, urllib.request
base = int(os.environ["WOLFBOX_LIVE_PORT"])
for port, path in [(base+1,'health'),(base+2,'health'),(base,'api/health')]:
    for attempt in range(40):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/{path}', timeout=.5)
            break
        except OSError: time.sleep(.25)
    else: raise SystemExit(f'Server on {port} did not become healthy')
PY
WOLFBOX_LIVE_URL="http://127.0.0.1:$WOLFBOX_LIVE_PORT" swift test --package-path apple --filter LiveTests
