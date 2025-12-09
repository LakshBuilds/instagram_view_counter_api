#!/usr/bin/env python3
"""
Quick script to get the current tunnel URL from log file.
"""
import re
from pathlib import Path

TUNNEL_LOG = Path("tunnel_output.log")

def get_url():
    """Extract URL from log file."""
    if not TUNNEL_LOG.exists():
        print("No tunnel log found. Start the tunnel first with: python start_tunnel.py")
        return None
    
    try:
        content = TUNNEL_LOG.read_text(encoding='utf-8', errors='ignore')
        url_pattern = re.compile(r'https://[a-z-]+\.trycloudflare\.com')
        matches = url_pattern.findall(content)
        if matches:
            return matches[-1]  # Get the most recent one
    except Exception as e:
        print(f"Error reading log: {e}")
    
    return None

if __name__ == "__main__":
    url = get_url()
    if url:
        print(url)
    else:
        print("No URL found in log file.")
        exit(1)

