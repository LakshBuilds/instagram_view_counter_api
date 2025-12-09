#!/usr/bin/env python3
"""Manually trigger cookie refresh"""
import os
import sys
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Set environment variables
os.environ['AUTO_COOKIE_REFRESH'] = '1'
os.environ['INSTAGRAM_USERNAME'] = 'chandy_shopbuy'
os.environ['INSTAGRAM_PASSWORD'] = 'pass@@@123'
os.environ['SHOW_BROWSER'] = 'true'

from cookie_auto_refresher import auto_refresh_cookies

print("=" * 60)
print("Starting manual cookie refresh...")
print("Browser window will open - you can complete CAPTCHA if needed")
print("=" * 60)
print()

result = auto_refresh_cookies('manual_refresh')

print()
print("=" * 60)
if result:
    print("[SUCCESS] Cookies refreshed successfully!")
    print("Cookies saved to cookies.txt")
else:
    print("[FAILED] Cookie refresh failed")
    print("Check the browser window for any errors or challenges")
print("=" * 60)

sys.exit(0 if result else 1)

