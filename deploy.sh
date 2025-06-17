#!/bin/bash

# Configuration
DROPLET_IP="64.23.129.92"
DROPLET_USER="root"
DROPLET_PASS="9FqFxUJqszhT8oyoYAYA"
APP_DIR="/opt/toast-app"

# Create SSH key if it doesn't exist
if [ ! -f ~/.ssh/id_rsa ]; then
    ssh-keygen -t rsa -N "" -f ~/.ssh/id_rsa
fi

# Copy SSH key to server if not already done
# sshpass -p "$DROPLET_PASS" ssh-copy-id "$DROPLET_USER@$DROPLET_IP"  # Removed this line - key should already be there

# Add a small pause
echo "Pausing for 5 seconds before mkdir..."
sleep 5

# Create app directory on server if it doesn't exist
ssh "$DROPLET_USER@$DROPLET_IP" "mkdir -p $APP_DIR"

# Add another pause
echo "Pausing for 2 seconds before rsync..."
sleep 2

# Sync files to server using rsync
# --delete removes files on server that don't exist locally
# --exclude prevents syncing unnecessary files
rsync -avz --delete \
    --exclude 'venv/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.git/' \
    --exclude '.env' \
    ./ "$DROPLET_USER@$DROPLET_IP:$APP_DIR/"

# Add another pause
echo "Pausing for 2 seconds before running remote commands..."
sleep 2

# Install dependencies and restart service
ssh "$DROPLET_USER@$DROPLET_IP" "cd $APP_DIR && \
    source venv/bin/activate && \
    pip install -r requirements.txt && \
    systemctl restart toast-app && \
    systemctl status toast-app && \
    echo '=== Service Logs ===' && \
    journalctl -u toast-app -n 50 --no-pager" 