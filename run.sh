#!/usr/bin/env bash
# Starts the API and the interface together.
#
#   ./run.sh          both, in the foreground (Ctrl-C stops both)
#   ./run.sh api      just the API on :8077
#   ./run.sh ui       just the interface on :5173
#
# The database must already be running — see STATUS.md section 5.1.
set -euo pipefail
cd "$(dirname "$0")"

api() {
  echo "API   → http://localhost:8077  (docs at /docs)"
  cd backend/src && PYTHONPATH=. ../../.venv/bin/uvicorn biet_api.main:app --port 8077 --reload
}
ui() {
  echo "UI    → http://localhost:5173"
  cd frontend && npm run dev
}

case "${1:-both}" in
  api) api ;;
  ui)  ui ;;
  both)
    api & API_PID=$!
    ui  & UI_PID=$!
    trap 'kill $API_PID $UI_PID 2>/dev/null' EXIT INT TERM
    wait
    ;;
  *) echo "usage: ./run.sh [api|ui|both]" >&2; exit 2 ;;
esac
