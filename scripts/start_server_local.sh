#!/bin/bash

# Local development server startup script
# Usage: ./start_server_local.sh

echo "🚀 Starting local Toast API server..."

# Check if we're in the right directory
if [ ! -f "simple_server.py" ]; then
    echo "❌ simple_server.py not found. Make sure you're in the correct directory."
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install/upgrade dependencies
echo "📦 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create logs directory
mkdir -p logs

# Check environment variables
echo "🔍 Checking environment..."
if [ -z "$TOAST_CLIENT_ID" ] && [ ! -f ".env" ]; then
    echo "⚠️  Warning: No .env file found and TOAST_CLIENT_ID not set"
    echo "   Make sure your .env file exists with proper credentials"
fi

echo "🌐 Starting server on http://localhost:5000..."
echo ""
echo "Available endpoints:"
echo "  POST /tips         - Process tips data"
echo "  GET  /health       - Health check"
echo "  GET  /debug        - Debug info"
echo "  GET  /status/<id>  - Task status"
echo "  GET  /logs/<id>    - Task logs"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start the server
python simple_server.py