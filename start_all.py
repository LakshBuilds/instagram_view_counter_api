#!/usr/bin/env python3
"""
🚀 ONE COMMAND TO START EVERYTHING
- API Server (python api.py)
- Cloudflare Tunnel
- Smart Watchdog (monitoring + auto-restart)

Usage: python start_all.py
"""

import subprocess
import time
import os
import sys
import signal
import re
from pathlib import Path
from datetime import datetime

# Configuration
API_PORT = 8000
TUNNEL_LOG = Path("tunnel_output.log")
CLOUDFLARED_EXE = Path("cloudflared.exe")

# Process handles
api_process = None
tunnel_process = None
watchdog_process = None


def log(message, level="INFO"):
    """Print timestamped log message"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    emoji = {
        "INFO": "ℹ️",
        "SUCCESS": "✅", 
        "WARNING": "⚠️",
        "ERROR": "❌",
        "START": "🚀"
    }.get(level, "")
    print(f"[{timestamp}] {emoji} {message}")


def kill_port(port):
    """Kill any process using the specified port"""
    try:
        result = subprocess.run(
            f'netstat -ano | findstr :{port} | findstr LISTENING',
            shell=True, capture_output=True, text=True
        )
        killed_pids = set()
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    if pid != '0' and pid not in killed_pids:
                        try:
                            subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
                            killed_pids.add(pid)
                        except:
                            pass
        time.sleep(1)
    except:
        pass


def kill_existing_tunnels():
    """Kill any existing cloudflared processes"""
    try:
        subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"], 
                      capture_output=True, check=False)
        time.sleep(1)
    except:
        pass


def check_api_running():
    """Check if API is responding"""
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('127.0.0.1', API_PORT))
        sock.close()
        return result == 0
    except:
        return False


def start_api():
    """Start the API server"""
    global api_process
    
    log("Starting API server...", "START")
    kill_port(API_PORT)
    time.sleep(2)
    
    api_process = subprocess.Popen(
        ["python", "api.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=os.getcwd(),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
    )
    
    # Wait for API to be ready
    for i in range(15):
        if check_api_running():
            log(f"API server started on port {API_PORT}", "SUCCESS")
            return True
        time.sleep(1)
        print(f"   Waiting for API... ({i+1}/15)")
    
    log("API failed to start!", "ERROR")
    return False


def start_tunnel():
    """Start Cloudflare tunnel"""
    global tunnel_process
    
    log("Starting Cloudflare tunnel...", "START")
    kill_existing_tunnels()
    
    # Remove old log
    if TUNNEL_LOG.exists():
        TUNNEL_LOG.unlink()
    
    # Start tunnel with http2 protocol
    with open(TUNNEL_LOG, 'w', encoding='utf-8') as log_file:
        tunnel_process = subprocess.Popen(
            [str(CLOUDFLARED_EXE.absolute()), "tunnel", "--url", f"http://localhost:{API_PORT}", "--protocol", "http2"],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=Path.cwd()
        )
    
    # Wait for URL
    url_pattern = re.compile(r'https://[a-z0-9-]+\.trycloudflare\.com')
    start_time = time.time()
    
    while time.time() - start_time < 25:
        if TUNNEL_LOG.exists():
            try:
                content = TUNNEL_LOG.read_text(encoding='utf-8', errors='ignore')
                matches = url_pattern.findall(content)
                if matches:
                    url = matches[0]
                    log(f"Tunnel started!", "SUCCESS")
                    print(f"\n   🌐 PUBLIC URL: {url}\n")
                    return url
            except:
                pass
        time.sleep(1)
        print(f"   Waiting for tunnel URL... ({int(time.time() - start_time)}s)")
    
    log("Tunnel started but URL not found yet", "WARNING")
    return None


def start_watchdog():
    """Start the watchdog in background"""
    global watchdog_process
    
    log("Starting watchdog monitor...", "START")
    
    # Run watchdog in a separate window so user can see logs
    watchdog_process = subprocess.Popen(
        ["python", "api_watchdog.py"],
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )
    
    log("Watchdog started in separate window", "SUCCESS")
    return True


def cleanup():
    """Stop all processes"""
    log("Shutting down all services...", "WARNING")
    
    if watchdog_process:
        try:
            watchdog_process.terminate()
        except:
            pass
    
    if tunnel_process:
        try:
            tunnel_process.terminate()
        except:
            pass
        kill_existing_tunnels()
    
    if api_process:
        try:
            api_process.terminate()
        except:
            pass
        kill_port(API_PORT)
    
    log("All services stopped", "SUCCESS")


def signal_handler(sig, frame):
    """Handle Ctrl+C"""
    print("\n")
    cleanup()
    sys.exit(0)


def main():
    """Main function - start everything"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║         🚀 INSTAGRAM SCRAPER - ALL-IN-ONE STARTER            ║
║                                                              ║
║  Starting:                                                   ║
║    1. API Server (python api.py)                             ║
║    2. Cloudflare Tunnel (public URL)                         ║
║    3. Smart Watchdog (auto-restart + monitoring)             ║
║                                                              ║
║  Press Ctrl+C to stop all services                           ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    # Step 1: Start API
    if not start_api():
        log("Failed to start API. Exiting.", "ERROR")
        return
    
    time.sleep(2)
    
    # Step 2: Start Tunnel
    tunnel_url = start_tunnel()
    
    time.sleep(2)
    
    # Step 3: Start Watchdog
    start_watchdog()
    
    # Print summary
    print("\n" + "=" * 60)
    print("✅ ALL SERVICES STARTED!")
    print("=" * 60)
    print(f"\n📡 Local API:  http://localhost:{API_PORT}")
    if tunnel_url:
        print(f"🌐 Public URL: {tunnel_url}")
        print(f"\n📋 Test endpoints:")
        print(f"   Health: {tunnel_url}/health")
        print(f"   Scrape: {tunnel_url}/scrape?url=REEL_URL")
    print("\n🐕 Watchdog is monitoring in separate window")
    print("\n⚠️  Keep this window open to maintain services")
    print("   Press Ctrl+C to stop everything")
    print("=" * 60)
    
    # Keep running
    try:
        while True:
            time.sleep(5)
            # Check if processes are still running
            if api_process and api_process.poll() is not None:
                log("API process died! Watchdog should restart it.", "WARNING")
            if tunnel_process and tunnel_process.poll() is not None:
                log("Tunnel died! Restarting...", "WARNING")
                start_tunnel()
    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    main()
