#!/usr/bin/env python3
"""
Voice Assistant with Dashboard Launcher
Cross-platform script to run both the voice assistant and dashboard
"""

import subprocess
import sys
import os
import time
import signal

def run_command(command, name, cwd=None):
    """Run a command in a subprocess"""
    print(f"🚀 Starting {name}...")
    try:
        if sys.platform == "win32":
            # Windows needs shell=True for npm commands
            process = subprocess.Popen(command, shell=True, cwd=cwd)
        else:
            # Unix-like systems
            process = subprocess.Popen(command, shell=True, cwd=cwd)
        return process
    except Exception as e:
        print(f"❌ Failed to start {name}: {e}")
        return None

def check_npm():
    """Check if npm is installed"""
    try:
        subprocess.run(["npm", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return False

def check_dashboard_deps():
    """Check if dashboard dependencies are installed"""
    return os.path.exists("dashboard/node_modules")

def install_dashboard_deps():
    """Install dashboard dependencies"""
    print("📦 Installing dashboard dependencies...")
    try:
        subprocess.run(["npm", "install"], cwd="dashboard", check=True)
        print("✅ Dependencies installed successfully")
    except Exception as e:
        print(f"❌ Failed to install dependencies: {e}")
        sys.exit(1)

def main():
    print("🎙️  Voice Assistant with Dashboard Launcher")
    print("=" * 50)
    print()
    
    # Check npm
    if not check_npm():
        print("❌ npm is not installed. Please install Node.js and npm first.")
        print("   Visit: https://nodejs.org/")
        sys.exit(1)
    
    # Check/install dashboard dependencies
    if not check_dashboard_deps():
        install_dashboard_deps()
    
    # Start voice assistant
    assistant_process = run_command(
        [sys.executable, "main.py"],
        "Voice Assistant"
    )
    
    if not assistant_process:
        sys.exit(1)
    
    # Wait for assistant to start
    print("⏳ Waiting for voice assistant to initialize...")
    time.sleep(5)
    
    # Start dashboard
    dashboard_process = run_command(
        "npm run dev",
        "Dashboard",
        cwd="dashboard"
    )
    
    if not dashboard_process:
        assistant_process.terminate()
        sys.exit(1)
    
    print()
    print("✅ Voice Assistant is running!")
    print("✅ Dashboard is running at http://localhost:3000")
    print()
    print("Press Ctrl+C to stop both services...")
    
    # Handle shutdown
    def signal_handler(sig, frame):
        print("\n\n🛑 Shutting down...")
        try:
            # Try graceful shutdown first
            assistant_process.terminate()
            dashboard_process.terminate()
            
            # Give them time to shut down gracefully
            assistant_process.wait(timeout=5)
            dashboard_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print("⚠️  Force killing processes...")
            assistant_process.kill()
            dashboard_process.kill()
        except Exception as e:
            print(f"Error during shutdown: {e}")
        finally:
            sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Wait for processes
    try:
        assistant_process.wait()
        dashboard_process.wait()
    except KeyboardInterrupt:
        signal_handler(None, None)

if __name__ == "__main__":
    main()