#!/usr/bin/env python3
"""
Automatically get tunnel URL, restart tunnel if URL is expired.
"""
import os
import re
import subprocess
import time
import sys
import requests
from pathlib import Path

TUNNEL_LOG = Path("tunnel_output.log")
CLOUDFLARED_EXE = Path("cloudflared.exe")


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


def test_url(url):
    """Test if tunnel URL is working."""
    try:
        response = requests.get(f"{url}/health", timeout=5)
        return response.status_code == 200
    except:
        return False


def get_url_from_log():
    """Extract URL from log file."""
    if not TUNNEL_LOG.exists():
        return None
    
    try:
        content = TUNNEL_LOG.read_text(encoding='utf-8', errors='ignore')
        url_pattern = re.compile(r'https://[a-z-]+\.trycloudflare\.com')
        matches = url_pattern.findall(content)
        if matches:
            return matches[-1]  # Get most recent
    except:
        pass
    
    return None


def kill_tunnel():
    """Kill existing tunnel processes."""
    try:
        subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"], 
                      capture_output=True, check=False)
        time.sleep(1)
    except:
        pass


def start_tunnel():
    """Start tunnel in background."""
    if not CLOUDFLARED_EXE.exists():
        print(f"ERROR: {CLOUDFLARED_EXE} not found!")
        return False
    
    kill_tunnel()
    if TUNNEL_LOG.exists():
        TUNNEL_LOG.unlink()
    
    try:
        with open(TUNNEL_LOG, 'w', encoding='utf-8') as log_file:
            subprocess.Popen(
                [str(CLOUDFLARED_EXE.absolute()), "tunnel", "--url", "http://127.0.0.1:8000"],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=Path.cwd()
            )
        return True
    except Exception as e:
        print(f"ERROR starting tunnel: {e}")
        return False


def main():
    print("=" * 60)
    print("Getting Tunnel URL...")
    print("=" * 60)
    print()
    
    # Check API
    if not check_api_running():
        print("ERROR: API server is not running on port 8000!")
        print("Please start the API server first: python api.py")
        return 1
    
    print("API server is running")
    print()
    
    # Get URL from log
    url = get_url_from_log()
    
    if url:
        print(f"Found URL: {url}")
        print("Testing connection...")
        
        if test_url(url):
            print()
            print("=" * 60)
            print("YOUR TUNNEL URL:")
            print("=" * 60)
            print()
            print(url)
            print()
            print("Test Endpoints:")
            print(f"  Health: {url}/health")
            print(f"  Scrape: {url}/scrape?url=INSTAGRAM_REEL_URL")
            print()
            print("=" * 60)
            print()
            
            # Try to copy to clipboard (Windows)
            try:
                import pyperclip
                pyperclip.copy(url)
                print("URL copied to clipboard!")
            except:
                try:
                    subprocess.run(["clip"], input=url.encode(), check=True)
                    print("URL copied to clipboard!")
                except:
                    pass
            
            return 0
        else:
            print("URL expired or not working. Restarting tunnel...")
            print()
    
    # Need to start/restart tunnel
    if not url:
        print("URL not found. Starting tunnel...")
    else:
        print("Restarting tunnel...")
    
    print()
    
    if not start_tunnel():
        return 1
    
    print("Waiting for tunnel to start (20 seconds)...")
    time.sleep(20)
    
    # Try to get new URL
    url = get_url_from_log()
    
    if url:
        print(f"Found URL: {url}")
        print("Testing connection...")
        
        # Wait a bit more if needed
        for i in range(5):
            if test_url(url):
                break
            time.sleep(2)
            url = get_url_from_log()
        
        if url and test_url(url):
            print()
            print("=" * 60)
            print("TUNNEL URL:")
            print("=" * 60)
            print()
            print(url)
            print()
            print("Test Endpoints:")
            print(f"  Health: {url}/health")
            print(f"  Scrape: {url}/scrape?url=INSTAGRAM_REEL_URL")
            print()
            print("=" * 60)
            print()
            
            # Try to copy to clipboard
            try:
                import pyperclip
                pyperclip.copy(url)
                print("URL copied to clipboard!")
            except:
                try:
                    subprocess.run(["clip"], input=url.encode(), check=True)
                    print("URL copied to clipboard!")
                except:
                    pass
            
            return 0
        else:
            print("Tunnel started but URL not ready yet.")
            print("Run this script again in 10 seconds.")
            return 1
    else:
        print("Tunnel log not created yet.")
        print("Run this script again in 10 seconds.")
        return 1


if __name__ == "__main__":
    sys.exit(main())


