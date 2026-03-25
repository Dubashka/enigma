#!/bin/bash
# deploy.sh — Deploy Enigma to VM (run from project root)
set -euo pipefail

SSH_KEY="${SSH_KEY:-$HOME/ssh-key-1773052328598}"
SSH_USER="${SSH_USER:-ilyamukha}"
VM_HOST="158.160.27.49"
VM_APP="/home/enigma/app"
VM_VENV="/home/enigma/venv"
SSH_OPTS="-o ConnectTimeout=30 -o ServerAliveInterval=10 -i ${SSH_KEY}"

echo "[1/4] Syncing code..."
rsync -avz --delete \
    --exclude='.venv' \
    --exclude='.venv2' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.git' \
    --exclude='*.xlsx' \
    --exclude='*.XLSX' \
    --exclude='.planning' \
    --exclude='deploy' \
    --exclude='.claude' \
    -e "ssh ${SSH_OPTS}" \
    . /tmp/enigma-stage/

rsync -avz --delete \
    --exclude='.venv' \
    --exclude='.venv2' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.git' \
    --exclude='*.xlsx' \
    --exclude='*.XLSX' \
    --exclude='.planning' \
    --exclude='deploy' \
    --exclude='.claude' \
    -e "ssh ${SSH_OPTS}" \
    . "${SSH_USER}@${VM_HOST}:/tmp/enigma-deploy/"

ssh ${SSH_OPTS} "${SSH_USER}@${VM_HOST}" \
    "sudo rsync -a --delete /tmp/enigma-deploy/ ${VM_APP}/ && sudo chown -R enigma:enigma ${VM_APP}"

echo "[2/4] Installing dependencies..."
ssh ${SSH_OPTS} "${SSH_USER}@${VM_HOST}" \
    "sudo su - enigma -c '${VM_VENV}/bin/pip install -q --no-deps streamlit==1.55.0 pandas openpyxl==3.1.5 xlsxwriter==3.2.9 et-xmlfile && ${VM_VENV}/bin/pip install -q streamlit==1.55.0'"

echo "[3/4] Restarting service..."
ssh ${SSH_OPTS} "${SSH_USER}@${VM_HOST}" \
    "sudo systemctl restart enigma"

echo "[4/4] Checking status..."
ssh ${SSH_OPTS} "${SSH_USER}@${VM_HOST}" \
    "sudo systemctl status enigma --no-pager"

echo ""
echo "Deploy complete. Visit http://${VM_HOST}"
