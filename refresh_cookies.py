#!/usr/bin/env python3
"""Manually trigger cookie refresh for one or all accounts"""
import os
import sys
import io
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Account configurations
ACCOUNTS = {
    # Commented out non-working accounts
    # 'candy_shopbuy': 'pass@@@123',
    'bhdemo2025': 'passpass',
    # 'elmasedoyle': 'yash1234',

    # New working accounts (using 2 for now)
    # 'ravi108794': 'sharks10',  # Commented out for now
    'raviram8274': 'sharks11'
}

def refresh_single_account(username, password):
    """Refresh cookies for a single account"""
    print("=" * 60)
    print(f"Starting cookie refresh for: {username}")
    print("Browser window will open - complete CAPTCHA if needed")
    print("=" * 60)
    print()

    # Set environment variables
    os.environ['AUTO_COOKIE_REFRESH'] = '1'
    os.environ['SHOW_BROWSER'] = 'true'
    os.environ['INSTAGRAM_USERNAME'] = username
    os.environ['INSTAGRAM_PASSWORD'] = password

    # Import and set cookie file path
    import cookie_auto_refresher
    cookie_auto_refresher.COOKIES_FILE = Path(f'cookies_{username}.txt')

    from cookie_auto_refresher import auto_refresh_cookies

    result = auto_refresh_cookies(f'manual_refresh_{username}')

    print()
    print("=" * 60)
    if result:
        print(f"[SUCCESS] Cookies refreshed for {username}!")
        print(f"Cookies saved to cookies_{username}.txt")
    else:
        print(f"[FAILED] Cookie refresh failed for {username}")
        print("Check the browser window for any errors or challenges")
    print("=" * 60)

    return result

def refresh_all_accounts():
    """Refresh cookies for all accounts"""
    print("Refreshing cookies for all accounts...")
    print(f"Accounts: {', '.join(ACCOUNTS.keys())}")
    print()

    results = {}
    for username, password in ACCOUNTS.items():
        print(f"\n--- Processing {username} ---")
        results[username] = refresh_single_account(username, password)
        print()

    print("SUMMARY:")
    print("=" * 60)
    for username, success in results.items():
        status = "SUCCESS" if success else "FAILED"
        print(f"{username}: {status}")
    print("=" * 60)

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # No arguments - refresh all accounts
        refresh_all_accounts()
    elif len(sys.argv) == 2:
        # One argument - specific account
        username = sys.argv[1]
        if username in ACCOUNTS:
            password = ACCOUNTS[username]
            refresh_single_account(username, password)
        else:
            print(f"Unknown account: {username}")
            print(f"Available accounts: {', '.join(ACCOUNTS.keys())}")
            sys.exit(1)
    elif len(sys.argv) == 3:
        # Two arguments - username and password
        username = sys.argv[1]
        password = sys.argv[2]
        refresh_single_account(username, password)
    else:
        print("Usage:")
        print("  python refresh_cookies.py              # Refresh all accounts")
        print("  python refresh_cookies.py <username>   # Refresh specific account")
        print("  python refresh_cookies.py <username> <password>  # Custom credentials")
        print()
        print(f"Available accounts: {', '.join(ACCOUNTS.keys())}")
        sys.exit(1)

