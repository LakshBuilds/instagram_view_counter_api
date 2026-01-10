"""
Login Single Account - Get fresh cookies for one account
"""
import os
import sys
import time
from pathlib import Path

def login_account(username, password):
    """Login a single account and get cookies"""
    print(f"\n{'='*60}")
    print(f"LOGGING IN: {username}")
    print(f"{'='*60}")
    
    # Set environment variables
    os.environ['AUTO_COOKIE_REFRESH'] = '1'
    os.environ['INSTAGRAM_USERNAME'] = username
    os.environ['INSTAGRAM_PASSWORD'] = password
    os.environ['SHOW_BROWSER'] = 'true'
    
    # Update cookies file path
    import cookie_auto_refresher
    cookie_auto_refresher.COOKIES_FILE = Path(f'cookies_{username}.txt')
    
    print(f"   Opening browser for {username}...")
    print(f"   WARNING: Complete any CAPTCHA manually if needed")
    
    from cookie_auto_refresher import auto_refresh_cookies
    success = auto_refresh_cookies(reason=f"Login for {username}")
    
    if success:
        print(f"\nSUCCESS: {username} - LOGIN SUCCESSFUL!")
        print(f"Cookies saved to: cookies_{username}.txt")
    else:
        print(f"\nFAILED: {username} - LOGIN FAILED!")
    
    return success

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python login_single_account.py <username> <password>")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    
    try:
        login_account(username, password)
    except Exception as e:
        print(f"Error: {e}")