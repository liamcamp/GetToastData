#!/bin/bash

# Simple, reliable deployment script for Toast API Server
# Usage: ./deploy_simple.sh

set -e  # Exit on any error

# Configuration
SERVER_IP="64.23.129.92"
SERVER_USER="root"
REMOTE_DIR="/root/GetToastData"
SERVICE_NAME="toast-api"

echo "🚀 Starting deployment to $SERVER_IP..."

# Step 1: Deploy code
echo "📁 Syncing files to server..."
rsync -avz --delete \
    --exclude 'venv/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.git/' \
    --exclude 'logs/' \
    --exclude '*.log' \
    ./ "$SERVER_USER@$SERVER_IP:$REMOTE_DIR/"

echo "✅ Files synced successfully"

# Step 2: Set up and restart service
echo "🔧 Setting up service on server..."

ssh "$SERVER_USER@$SERVER_IP" << 'ENDSSH'
set -e

cd /root/GetToastData

echo "📦 Setting up Python environment..."

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Activate and install dependencies
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "🔧 Creating systemd service..."

# Create systemd service file
cat > /etc/systemd/system/toast-api.service << 'EOF'
[Unit]
Description=Toast API Server (Simplified)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/GetToastData
Environment=PATH=/root/GetToastData/venv/bin
EnvironmentFile=-/root/GetToastData/.env
ExecStart=/root/GetToastData/venv/bin/python simple_server.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "🔄 Reloading systemd and starting service..."

# Reload systemd and restart service
systemctl daemon-reload
systemctl enable toast-api
systemctl stop toast-api 2>/dev/null || true
sleep 2
systemctl start toast-api

echo "⏳ Waiting for service to start..."
sleep 3

# Check service status
echo "📊 Service Status:"
systemctl status toast-api --no-pager -l

echo ""
echo "📋 Recent Service Logs:"
journalctl -u toast-api -n 20 --no-pager

echo ""
echo "🌐 Testing server health..."
curl -s http://localhost:5000/health | python3 -m json.tool || echo "❌ Health check failed"

ENDSSH

echo ""
echo "🎉 Deployment completed!"
echo ""
echo "📋 Useful commands for your server:"
echo "   View logs:           journalctl -u toast-api -f"
echo "   Restart service:     systemctl restart toast-api"
echo "   Service status:      systemctl status toast-api"
echo "   Debug info:          curl http://localhost:5000/debug"
echo "   Health check:        curl http://localhost:5000/health"
echo ""
echo "🌐 Test your API:"
echo "   curl -X POST http://$SERVER_IP:5000/tips \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"startDate\":\"2025-06-13\",\"endDate\":\"2025-06-15\",\"webhook\":\"https://your-webhook-url\",\"locationIndex\":1}'"
echo ""