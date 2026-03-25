#!/bin/bash
# setup-vm.sh — First-time VM setup for Enigma
# Run: bash deploy/setup-vm.sh (from local machine, SSHs into VM)
set -euo pipefail

SSH_KEY="${SSH_KEY:-$HOME/ssh-key-1773052328598}"
SSH_USER="${SSH_USER:-ilyamukha}"
VM_HOST="158.160.27.49"
VM_USER="enigma"
SSH_OPTS="-o ConnectTimeout=30 -o ServerAliveInterval=10 -i ${SSH_KEY}"

echo "=== Enigma VM Setup ==="

echo "[1/7] Installing system packages..."
ssh ${SSH_OPTS} ${SSH_USER}@${VM_HOST} "sudo apt-get update -qq && sudo apt-get install -y -qq nginx python3-venv python3-dev"

echo "[2/7] Creating dedicated user..."
ssh ${SSH_OPTS} ${SSH_USER}@${VM_HOST} "sudo id -u ${VM_USER} 2>/dev/null && echo 'User exists' || sudo useradd --system --create-home --shell /bin/bash ${VM_USER}"

echo "[3/7] Creating app directory..."
ssh ${SSH_OPTS} ${SSH_USER}@${VM_HOST} "sudo mkdir -p /home/${VM_USER}/app && sudo chown -R ${VM_USER}:${VM_USER} /home/${VM_USER}"

echo "[4/7] Creating Python venv..."
ssh ${SSH_OPTS} ${SSH_USER}@${VM_HOST} "sudo su - ${VM_USER} -c 'python3 -m venv /home/${VM_USER}/venv'"

echo "[5/7] Installing systemd service..."
scp -i ${SSH_KEY} deploy/enigma.service ${SSH_USER}@${VM_HOST}:/tmp/enigma.service
ssh ${SSH_OPTS} ${SSH_USER}@${VM_HOST} "sudo cp /tmp/enigma.service /etc/systemd/system/enigma.service && sudo systemctl daemon-reload && sudo systemctl enable enigma"

echo "[6/7] Installing nginx config..."
scp -i ${SSH_KEY} deploy/enigma.nginx ${SSH_USER}@${VM_HOST}:/tmp/enigma.nginx
ssh ${SSH_OPTS} ${SSH_USER}@${VM_HOST} "sudo cp /tmp/enigma.nginx /etc/nginx/sites-available/enigma && sudo ln -sf /etc/nginx/sites-available/enigma /etc/nginx/sites-enabled/ && sudo rm -f /etc/nginx/sites-enabled/default && sudo nginx -t && sudo systemctl reload nginx"

echo "[7/7] Configuring sudoers for deploy..."
ssh ${SSH_OPTS} ${SSH_USER}@${VM_HOST} "echo '${VM_USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart enigma, /bin/systemctl status enigma' | sudo tee /etc/sudoers.d/${VM_USER} > /dev/null && sudo chmod 440 /etc/sudoers.d/${VM_USER}"

echo ""
echo "=== Setup complete ==="
echo "Next: run ./deploy/deploy.sh to deploy the app"
