#!/bin/bash

# Voice Assistant with Dashboard Launcher
# This script runs both the voice assistant and the dashboard

echo "🚀 Starting Voice Assistant with Dashboard..."
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down..."
    kill $MAIN_PID $DASHBOARD_PID 2>/dev/null
    exit
}

# Set trap for cleanup
trap cleanup EXIT INT TERM

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo "❌ npm is not installed. Please install Node.js and npm first."
    exit 1
fi

# Check if dashboard dependencies are installed
if [ ! -d "dashboard/node_modules" ]; then
    echo "📦 Installing dashboard dependencies..."
    cd dashboard
    npm install
    cd ..
fi

# Start the voice assistant in background
echo "🎙️  Starting voice assistant..."
python main.py &
MAIN_PID=$!

# Wait a bit for the voice assistant to start
sleep 5

# Start the dashboard
echo "📊 Starting dashboard..."
cd dashboard
npm run dev &
DASHBOARD_PID=$!
cd ..

echo ""
echo "✅ Voice Assistant is running!"
echo "✅ Dashboard is running at http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop both services..."

# Wait for processes
wait