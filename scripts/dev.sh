#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PYTHON=python3
if [[ -x .venv/bin/python ]]; then
  PYTHON="$ROOT/.venv/bin/python"
fi

children=()
cleanup() {
  trap - EXIT INT TERM
  for pid in "${children[@]}"; do kill "$pid" 2>/dev/null || true; done
  for pid in "${children[@]}"; do wait "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT INT TERM

start_box() {
  local student="$1" port="$2"
  env DATA_DIR="$ROOT/.data/$student" PORT="$port" ALLOW_SEED=1 \
    STUCK_MINUTES="${STUCK_MINUTES:-2}" \
    GEMMA_BACKEND="${GEMMA_BACKEND:-fake}" \
    COURSE_URL="http://127.0.0.1:8000/course/csc116/course.json" \
    GEMINI_API_KEY="${GEMINI_API_KEY:-}" \
    OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}" \
    OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:e4b}" \
    "$PYTHON" box/start.py &
  children+=("$!")
}

start_box alex 8101
start_box sam 8102
LOCAL_BOXES="alex=http://127.0.0.1:8101,sam=http://127.0.0.1:8102" \
BOX_BACKEND=local "$PYTHON" -m uvicorn wolfhub.main:app --app-dir orchestrator --host 127.0.0.1 --port 8000 &
children+=("$!")

wait_for_health() {
  local name="$1" url="$2"
  for _ in {1..40}; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    for pid in "${children[@]}"; do
      if ! kill -0 "$pid" 2>/dev/null; then
        echo "$name exited before becoming healthy" >&2
        return 1
      fi
    done
    sleep 0.5
  done
  echo "$name did not become healthy: $url" >&2
  return 1
}

wait_for_health alex http://127.0.0.1:8101/health
wait_for_health sam http://127.0.0.1:8102/health
wait_for_health orchestrator http://127.0.0.1:8000/api/health
curl -fsS -X POST http://127.0.0.1:8000/api/students \
  -H 'Content-Type: application/json' -d '{"id":"alex","name":"Alex Rivera"}' >/dev/null
curl -fsS -X POST http://127.0.0.1:8000/api/students \
  -H 'Content-Type: application/json' -d '{"id":"sam","name":"Sam Chen"}' >/dev/null
echo "WolfBox dev stack is ready at http://127.0.0.1:8000"
wait
