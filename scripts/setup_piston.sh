#!/usr/bin/env bash
# setup_piston.sh — One-time Piston setup on Ubuntu 22.04
# Run as: sudo bash scripts/setup_piston.sh
#
# This script is idempotent (safe to re-run).
# Language versions installed here must match LANGUAGE_VERSIONS in piston.py.
set -euo pipefail

# --- 1. Install Docker ---
if ! command -v docker &>/dev/null; then
    echo "Installing Docker..."
    apt-get update -y
    apt-get install -y ca-certificates curl gnupg lsb-release
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io
    systemctl enable --now docker
    echo "Docker installed."
else
    echo "Docker already installed, skipping."
fi

# --- 2. Start Piston container with a persistent volume ---
# The piston-data volume persists installed runtimes and pip packages across
# container restarts. --restart always means Piston survives server reboots
# without needing a systemd unit.
# Bound to 127.0.0.1 — Flask calls Piston internally; not exposed to internet.
echo "Starting Piston container..."
docker rm -f piston 2>/dev/null || true
docker run -d \
    --name piston \
    --restart always \
    -p 127.0.0.1:2000:2000 \
    -v piston-data:/piston/packages \
    ghcr.io/engineer-man/piston

echo "Waiting for Piston API to become available..."
until curl -sf http://localhost:2000/api/v2/runtimes >/dev/null; do
    sleep 2
done
echo "Piston is up."

# --- 3. Install language runtimes via ppman ---
# Versions must exactly match LANGUAGE_VERSIONS in piston.py.
echo "Installing language runtimes..."
docker exec piston ppman install python 3.12.0
docker exec piston ppman install c 10.2.0
docker exec piston ppman install cpp 10.2.0
docker exec piston ppman install rust 1.73.0
docker exec piston ppman install java 15.0.2
echo "Language runtimes installed."

# --- 4. Install Python scientific packages into the Piston Python runtime ---
# Packages are pip-installed inside the container so they are available when
# user code runs in Piston's sandboxed Python environment.
echo "Installing Python scientific packages (this may take several minutes)..."
PYTHON_BIN=$(docker exec piston find /piston/packages/python/3.12.0 -name 'python3' | head -1)

docker exec piston "$PYTHON_BIN" -m pip install --upgrade pip
docker exec piston "$PYTHON_BIN" -m pip install numpy matplotlib scikit-learn

# torch CPU-only (~2 GB); install separately with the CPU-only index
echo "Installing PyTorch CPU (large download, please wait)..."
docker exec piston "$PYTHON_BIN" -m pip install \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    torch torchvision

echo ""
echo "Setup complete. Piston is running on port 2000 (localhost only)."
echo "Verify installed runtimes:"
echo "  curl http://localhost:2000/api/v2/runtimes | python3 -m json.tool"
