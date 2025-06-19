#!/bin/bash

# Cleanup and deploy script
set -e

SERVER_IP="64.23.129.92"
SERVER_USER="root"
REMOTE_DIR="/root/GetToastData"

echo "🧹 Cleaning up old services and processes..."

# Step 1: Clean up everything on the server
ssh "$SERVER_USER@$SERVER_IP" << 'CLEANUP'
set -e

echo "Stopping all related services..."
systemctl stop toast-api toast-app 2>/dev/null || true
systemctl disable toast-app 2>/dev/null || true

echo "Killing any remaining Python processes..."
pkill -f "python.*server" 2>/dev/null || true
pkill -f "python.*5000" 2>/dev/null || true
pkill -f "python.*5001" 2>/dev/null || true

sleep 3

echo "Checking if ports are free..."
if lsof -i :5000 >/dev/null 2>&1; then
    echo "Killing processes on port 5000..."
    lsof -ti:5000 | xargs kill -9 2>/dev/null || true
fi

if lsof -i :5001 >/dev/null 2>&1; then
    echo "Killing processes on port 5001..."
    lsof -ti:5001 | xargs kill -9 2>/dev/null || true
fi

sleep 2

echo "Removing old service files..."
rm -f /etc/systemd/system/toast-app.service
systemctl daemon-reload

echo "Cleanup completed!"
CLEANUP

# Step 2: Deploy new code
echo "📁 Syncing files to server..."
rsync -avz --delete \
    --exclude 'venv/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.git/' \
    --exclude 'logs/' \
    --exclude '*.log' \
    ./ "$SERVER_USER@$SERVER_IP:$REMOTE_DIR/"

# Step 3: Set up new service
echo "🔧 Setting up new service..."

ssh "$SERVER_USER@$SERVER_IP" << 'SETUP'
set -e

cd /root/GetToastData

echo "Setting up Python environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "Creating logs directory..."
mkdir -p logs

echo "Creating systemd service..."
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
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "Starting service..."
systemctl daemon-reload
systemctl enable toast-api
systemctl start toast-api

echo "Waiting for service to start..."
sleep 5

echo "Service Status:"
systemctl status toast-api --no-pager -l

echo ""
echo "Checking which port the server is using..."
sleep 2
if lsof -i :5000 >/dev/null 2>&1; then
    echo "✅ Server running on port 5000"
    SERVER_PORT=5000
elif lsof -i :5001 >/dev/null 2>&1; then
    echo "✅ Server running on port 5001"
    SERVER_PORT=5001
else
    echo "❌ Server not found on either port"
    SERVER_PORT=5000
fi

echo ""
echo "Testing server health..."
curl -s "http://localhost:$SERVER_PORT/health" | python3 -m json.tool || echo "❌ Health check failed"

SETUP

echo ""
echo "🎉 Deployment completed!"
echo ""
echo "🧪 Test your API:"
echo "   python test_api.py"
echo ""
echo "📋 Check logs:"
echo "   ssh root@64.23.129.92 'journalctl -u toast-api -f'"