#!/bin/bash
# setup-vm.sh — First-time VM setup for Enigma
# Run: bash deploy/setup-vm.sh (from local machine, SSHs into VM)
# OR: copy to VM and run directly
set -euo pipefail

VM_USER="enigma"
VM_HOST="158.160.27.49"

echo "=== Enigma VM Setup ==="

echo "[1/7] Installing system packages..."
ssh root@${VM_HOST} "apt-get update && apt-get install -y nginx python3.11-venv python3.11-dev"

echo "[2/7] Creating dedicated user..."
ssh root@${VM_HOST} "id -u ${VM_USER} &>/dev/null || useradd --system --create-home --shell /bin/bash ${VM_USER}"

echo "[3/7] Creating app directory..."
ssh root@${VM_HOST} "mkdir -p /home/${VM_USER}/app && chown -R ${VM_USER}:${VM_USER} /home/${VM_USER}"

echo "[4/7] Creating Python venv..."
ssh root@${VM_HOST} "su - ${VM_USER} -c 'python3.11 -m venv /home/${VM_USER}/venv'"

echo "[5/7] Installing systemd service..."
scp deploy/enigma.service root@${VM_HOST}:/etc/systemd/system/enigma.service
ssh root@${VM_HOST} "systemctl daemon-reload && systemctl enable enigma"

echo "[6/7] Installing nginx config..."
scp deploy/enigma.nginx root@${VM_HOST}:/etc/nginx/sites-available/enigma
ssh root@${VM_HOST} "ln -sf /etc/nginx/sites-available/enigma /etc/nginx/sites-enabled/ && rm -f /etc/nginx/sites-enabled/default && nginx -t && systemctl reload nginx"

echo "[7/7] Configuring sudoers for deploy..."
ssh root@${VM_HOST} "echo '${VM_USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart enigma, /bin/systemctl status enigma' > /etc/sudoers.d/${VM_USER} && chmod 440 /etc/sudoers.d/${VM_USER}"

echo ""
echo "=== Setup complete ==="
echo "Next: run ./deploy/deploy.sh to deploy the app"
