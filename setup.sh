#!/bin/bash

# Configuration
DROPLET_IP="64.23.129.92"
DROPLET_USER="root"
DROPLET_PASS="9FqFxUJqszhT8oyoYAYA"
APP_DIR="/opt/toast-app"

# First, deploy the code
echo "Deploying code..."
rsync -avz --delete \
    --exclude 'venv/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.git/' \
    ./ "$DROPLET_USER@$DROPLET_IP:$APP_DIR/"

# Then set up the environment and service
sshpass -p "$DROPLET_PASS" ssh "$DROPLET_USER@$DROPLET_IP" << "ENDSSH"
# Install only required packages
apt install -y python3 python3-pip python3-venv

# Set up app directory
cd /opt/toast-app

# Fix permissions
chown -R root:root /opt/toast-app
chmod -R 755 /opt/toast-app
chmod 644 /opt/toast-app/.env

# Remove old venv if it exists
rm -rf /opt/toast-app/venv

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create systemd service file with environment variables
cat > /etc/systemd/system/toast-app.service << 'EOF'
[Unit]
Description=Toast Orders API Service
After=network.target

[Service]
User=root
WorkingDirectory=/opt/toast-app
Environment="PATH=/opt/toast-app/venv/bin"
EnvironmentFile=/opt/toast-app/.env
ExecStart=/opt/toast-app/venv/bin/python server.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and start service
systemctl daemon-reload
systemctl enable toast-app
systemctl restart toast-app

# Show service status and logs
echo "=== Service Status ==="
systemctl status toast-app
echo "=== Service Logs ==="
journalctl -u toast-app -n 50 --no-pager
ENDSSH