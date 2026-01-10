#!/usr/bin/env python3
"""Quick test script to check if accounts can access Instagram API"""

import os
import sys
import requests
from pathlib import Path

def test_account(username):
    """Test if an account can make a basic Instagram API call"""
    print(f"\n{'='*50}")
    print(f"Testing account: {username}")
    print(f"{'='*50}")

    # Load cookies
    cookies_file = Path(f'cookies_{username}.txt')
    if not cookies_file.exists():
        print(f"ERROR: No cookies file found for {username}")
        return False

    # Load cookies from file
    cookies = {}
    try:
        with open(cookies_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    cookies[key] = value
    except Exception as e:
        print(f"ERROR loading cookies: {e}")
        return False

    print(f"Loaded {len(cookies)} cookies")

    # Test basic Instagram request
    try:
        session = requests.Session()
        session.cookies.update(cookies)

        # Add headers
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })

        # Test with a simple Instagram page
        test_url = 'https://www.instagram.com/'
        response = session.get(test_url, timeout=10)

        if response.status_code == 200:
            print(f"HTTP {response.status_code} - Connection successful")
            # Check if we're logged in by looking for username in response
            if username.lower() in response.text.lower():
                print(f"Account appears to be logged in as {username}")
                return True
            else:
                print(f"WARNING: Account may not be properly logged in")
                return False
        else:
            print(f"ERROR: HTTP {response.status_code} - Connection failed")
            return False

    except Exception as e:
        print(f"ERROR testing account: {e}")
        return False

def main():
    """Test all accounts"""
    # Import current accounts from config
    from multi_account_config import MULTI_ACCOUNT_CONFIG
    accounts = [acc['username'] for acc in MULTI_ACCOUNT_CONFIG['accounts']]

    print("Testing Instagram account connectivity...")
    print("This checks if cookies are valid and accounts can access Instagram")

    results = {}
    for username in accounts:
        results[username] = test_account(username)

    print(f"\n{'='*50}")
    print("SUMMARY:")
    print(f"{'='*50}")
    for username, success in results.items():
        status = "WORKING" if success else "NEEDS REFRESH"
        print(f"{username}: {status}")

    working_count = sum(results.values())
    print(f"\n{working_count}/{len(accounts)} accounts are working")

if __name__ == "__main__":
    main()
