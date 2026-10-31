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

OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:e4b}"
if ! curl -fsS "$OLLAMA_URL/api/tags" | OLLAMA_MODEL="$OLLAMA_MODEL" python3 -c \
  'import json, os, sys; names = {m.get("name") for m in json.load(sys.stdin).get("models", [])}; sys.exit(0 if os.environ["OLLAMA_MODEL"] in names else 1)'; then
  echo "Ollama model ${OLLAMA_MODEL} is unavailable. Run: ollama pull ${OLLAMA_MODEL}" >&2
  exit 1
fi

export BOX_BACKEND=local
export GEMMA_BACKEND=ollama
exec scripts/dev.sh
