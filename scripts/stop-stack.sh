#!/usr/bin/env bash
# P1.AIVideo — one-click stack shutdown used by the desktop shortcut.
# Opreste containerele aduse de start-stack.sh fara sa stearga volumele
# (postgres_data / minio_data / inputs_data / artifacts_data raman intacte).

set -u
PROJECT_DIR="/home/cesiro/Documents/P1.AIVideo"
cd "$PROJECT_DIR" || { echo "Cannot cd to $PROJECT_DIR"; read -r -p "Press Enter to close..."; exit 1; }

COMPOSE="docker compose --env-file .env -f docker/compose.dev.yml"

echo "============================================================"
echo " P1.AIVideo — opresc stack-ul Docker"
echo " Proiect: $PROJECT_DIR"
echo " (volumele NU sunt sterse: postgres/minio/inputs/artifacts raman)"
echo "============================================================"

echo
echo "[1/3] Opresc wrapper-ul GPU SadTalker (profile sadtalker)"
$COMPOSE --profile sadtalker stop model-sadtalker || true

echo
echo "[2/3] Opresc wrapper-ul TTS Romana F5TTS-Ro (profile tts-ro)"
$COMPOSE --profile tts-ro stop model-tts-ro || true

echo
echo "[3/3] Opresc stack-ul dev (backend, frontend, agents, orchestrator, infra)"
$COMPOSE down || { echo "make down a esuat"; read -r -p "Press Enter..."; exit 1; }

echo
echo "============================================================"
echo " Containere aivideo-* ramase pornite (ar trebui sa fie zero):"
echo "============================================================"
docker ps --filter "name=aivideo-" --format "table {{.Names}}\t{{.Status}}"

echo
read -r -p "Apasa Enter pentru a inchide aceasta fereastra..."
