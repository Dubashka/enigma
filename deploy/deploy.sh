#!/bin/bash
# deploy.sh — Deploy Enigma to VM (run from project root)
set -euo pipefail

VM_USER="enigma"
VM_HOST="158.160.27.49"
VM_APP="/home/enigma/app"
VM_VENV="/home/enigma/venv"

echo "[1/4] Syncing code..."
rsync -avz --delete \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.git' \
    --exclude='*.xlsx' \
    --exclude='*.XLSX' \
    --exclude='.planning' \
    --exclude='deploy' \
    . "${VM_USER}@${VM_HOST}:${VM_APP}/"

echo "[2/4] Installing dependencies..."
ssh "${VM_USER}@${VM_HOST}" \
    "${VM_VENV}/bin/pip install -q -r ${VM_APP}/requirements.txt"

echo "[3/4] Restarting service..."
ssh "${VM_USER}@${VM_HOST}" \
    "sudo systemctl restart enigma"

echo "[4/4] Checking status..."
ssh "${VM_USER}@${VM_HOST}" \
    "sudo systemctl status enigma --no-pager"

echo ""
echo "Deploy complete. Visit http://${VM_HOST}"
