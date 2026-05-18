#!/usr/bin/env bash
# P1.AIVideo — one-click stack launcher used by the desktop shortcut.
# Brings up the dev compose stack, the SadTalker GPU wrapper, and the
# F5TTS-Ro wrapper, then opens the frontend in the default browser.

set -u
PROJECT_DIR="/home/cesiro/Documents/P1.AIVideo"
cd "$PROJECT_DIR" || { echo "Cannot cd to $PROJECT_DIR"; read -r -p "Press Enter to close..."; exit 1; }

# Load FRONTEND_PORT / BACKEND_PORT from .env without exporting everything.
FRONTEND_PORT="$(grep -E '^FRONTEND_PORT=' .env | head -1 | cut -d= -f2 | tr -d ' \r')"
BACKEND_PORT="$(grep -E '^BACKEND_PORT=' .env | head -1 | cut -d= -f2 | tr -d ' \r')"
FRONTEND_PORT="${FRONTEND_PORT:-3010}"
BACKEND_PORT="${BACKEND_PORT:-8001}"

echo "============================================================"
echo " P1.AIVideo — pornesc stack-ul Docker"
echo " Proiect: $PROJECT_DIR"
echo "============================================================"

COMPOSE="docker compose --env-file .env -f docker/compose.dev.yml"

echo
echo "[1/3] Stack dev (CPU: postgres, redis, minio, backend, frontend, orchestrator, agents)"
$COMPOSE up -d || { echo "compose up a esuat"; read -r -p "Press Enter..."; exit 1; }

echo
echo "[2/3] Wrapper GPU SadTalker (profile sadtalker)"
$COMPOSE --profile sadtalker up -d model-sadtalker || echo "  -> sadtalker up a esuat (continui)"

echo
echo "[3/3] Wrapper TTS Romana F5TTS-Ro (profile tts-ro)"
$COMPOSE --profile tts-ro up -d model-tts-ro || echo "  -> tts-ro up a esuat (continui)"

echo
echo "============================================================"
echo " Status containere:"
echo "============================================================"
docker ps --filter "name=aivideo-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo
echo "URLs:"
echo "  Frontend:  http://localhost:${FRONTEND_PORT}"
echo "  Backend:   http://localhost:${BACKEND_PORT}/docs"
echo "  MinIO UI:  http://localhost:9001 (user/pass din .env)"
echo "  SadTalker: http://localhost:8062/health"
echo "  TTS-Ro:    http://localhost:8061/health"

# Open the frontend in the default browser if a display is available.
if command -v xdg-open >/dev/null 2>&1; then
  ( sleep 2 && xdg-open "http://localhost:${FRONTEND_PORT}" >/dev/null 2>&1 ) &
fi

echo
read -r -p "Apasa Enter pentru a inchide aceasta fereastra (containerele raman pornite)..."
