#!/usr/bin/env python3
"""
Automatically start Cloudflare tunnel and extract the public URL.
"""
import os
import re
import subprocess
import time
import sys
from pathlib import Path

TUNNEL_LOG = Path("tunnel_output.log")
CLOUDFLARED_EXE = Path("cloudflared.exe")
API_URL = "http://127.0.0.1:8000"


def check_api_running():
    """Check if API server is running on port 8000."""
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', 8000))
        sock.close()
        return result == 0
    except:
        return False


def kill_existing_tunnels():
    """Kill any existing cloudflared processes."""
    try:
        subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"], 
                      capture_output=True, check=False)
        time.sleep(1)
    except:
        pass


def extract_url_from_log(log_file: Path, timeout: int = 30) -> str:
    """Extract tunnel URL from log file."""
    start_time = time.time()
    url_pattern = re.compile(r'https://[a-z-]+\.trycloudflare\.com')
    
    while time.time() - start_time < timeout:
        if log_file.exists():
            try:
                content = log_file.read_text(encoding='utf-8', errors='ignore')
                matches = url_pattern.findall(content)
                if matches:
                    return matches[0]
            except Exception as e:
                pass
        time.sleep(0.5)
    
    return None


def start_tunnel() -> str:
    """Start cloudflare tunnel and return the URL."""
    print("=" * 60)
    print("Starting Cloudflare Tunnel...")
    print("=" * 60)
    print()
    
    # Check if API is running
    if not check_api_running():
        print("ERROR: API server is not running on port 8000!")
        print("   Please start the API server first: python api.py")
        return None
    
    print("API server is running")
    print()
    
    # Check if cloudflared exists
    if not CLOUDFLARED_EXE.exists():
        print(f"ERROR: {CLOUDFLARED_EXE} not found!")
        return None
    
    # Kill existing tunnels
    print("Stopping any existing tunnels...")
    kill_existing_tunnels()
    
    # Remove old log file
    if TUNNEL_LOG.exists():
        TUNNEL_LOG.unlink()
    
    # Start tunnel with output to log file
    print("Starting new tunnel...")
    print("(This may take 10-15 seconds...)")
    print()
    
    try:
        with open(TUNNEL_LOG, 'w', encoding='utf-8') as log_file:
            process = subprocess.Popen(
                [str(CLOUDFLARED_EXE.absolute()), "tunnel", "--url", API_URL],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=Path.cwd()
            )
        
        # Wait a bit for tunnel to initialize
        time.sleep(3)
        
        # Extract URL from log
        url = extract_url_from_log(TUNNEL_LOG, timeout=20)
        
        if url:
            print("=" * 60)
            print("TUNNEL STARTED SUCCESSFULLY!")
            print("=" * 60)
            print()
            print(f"Your Public URL:")
            print(f"   {url}")
            print()
            print("Test Endpoints:")
            print(f"   Health: {url}/health")
            print(f"   Scrape: {url}/scrape?url=INSTAGRAM_REEL_URL")
            print()
            print("WARNING: Keep this script running to maintain the tunnel!")
            print("WARNING: The URL will expire if the tunnel stops.")
            print()
            print("=" * 60)
            return url
        else:
            print("WARNING: Tunnel started but URL not found in log yet.")
            print(f"   Check {TUNNEL_LOG} for details")
            print("   The tunnel is running in the background.")
            return None
            
    except Exception as e:
        print(f"ERROR starting tunnel: {e}")
        return None


if __name__ == "__main__":
    url = start_tunnel()
    if url:
        print("\nPress Ctrl+C to stop the tunnel...")
        try:
            # Keep script running
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\nStopping tunnel...")
            kill_existing_tunnels()
            print("Tunnel stopped.")
    else:
        sys.exit(1)

