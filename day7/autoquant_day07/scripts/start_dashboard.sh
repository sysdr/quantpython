#!/bin/bash
# Start the web dashboard server

cd "$(dirname "$0")/.."

echo "============================================================"
echo "🚀 Starting AutoQuant-Alpha Web Dashboard"
echo "============================================================"
echo ""

# Check if Flask is installed
python -c "import flask" 2>/dev/null || {
    echo "Installing Flask..."
    pip install flask -q
}

# Kill any existing dashboard processes
pkill -f "web_dashboard.py" 2>/dev/null
sleep 1

# Start the server
echo "Starting server..."
python scripts/web_dashboard.py

