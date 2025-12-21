"""
Login All Accounts - Get fresh cookies for all 3 accounts
Uses human-like cursor movements and typing
"""
import os
import time
from multi_account_config import MULTI_ACCOUNT_CONFIG

def login_account(username, password):
    """Login a single account and get cookies"""
    print(f"\n{'='*60}")
    print(f"🔐 LOGGING IN: {username}")
    print(f"{'='*60}")
    
    # Set environment variables
    os.environ['AUTO_COOKIE_REFRESH'] = '1'
    os.environ['INSTAGRAM_USERNAME'] = username
    os.environ['INSTAGRAM_PASSWORD'] = password
    os.environ['INSTAGRAM_COOKIES_FILE'] = f'cookies_{username}.txt'
    os.environ['SHOW_BROWSER'] = 'true'  # Show browser for manual CAPTCHA
    
    # Import and run cookie refresh
    from cookie_auto_refresher import auto_refresh_cookies, COOKIES_FILE
    from pathlib import Path
    
    # Update cookies file path
    import cookie_auto_refresher
    cookie_auto_refresher.COOKIES_FILE = Path(f'cookies_{username}.txt')
    
    print(f"   Opening browser for {username}...")
    print(f"   ⚠️ Complete any CAPTCHA manually if needed")
    
    success = auto_refresh_cookies(reason=f"Initial login for {username}")
    
    if success:
        print(f"   ✅ {username} - LOGIN SUCCESSFUL!")
        print(f"   📁 Cookies saved to: cookies_{username}.txt")
    else:
        print(f"   ❌ {username} - LOGIN FAILED!")
    
    return success

def main():
    print("🔐 LOGIN ALL ACCOUNTS")
    print("="*60)
    print("This will login all 3 accounts and save cookies")
    print("Complete any CAPTCHA manually in the browser")
    print("="*60)
    
    accounts = MULTI_ACCOUNT_CONFIG["accounts"]
    print(f"\n📋 Accounts to login: {len(accounts)}")
    for acc in accounts:
        print(f"   - {acc['username']}")
    
    results = {}
    
    for account in accounts:
        username = account['username']
        password = account['password']
        
        success = login_account(username, password)
        results[username] = success
        
        # Wait between logins to avoid suspicion
        if account != accounts[-1]:
            print(f"\n⏳ Waiting 10 seconds before next login...")
            time.sleep(10)
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 LOGIN SUMMARY")
    print("="*60)
    
    successful = sum(1 for v in results.values() if v)
    failed = len(results) - successful
    
    for username, success in results.items():
        status = "✅ Success" if success else "❌ Failed"
        print(f"   {username}: {status}")
    
    print(f"\n   Total: {successful}/{len(results)} accounts logged in")
    
    if successful == len(results):
        print("\n🎉 ALL ACCOUNTS READY!")
        print("You can now run: python auto_run_parallel.py")
    else:
        print(f"\n⚠️ {failed} account(s) failed to login")
        print("Please check credentials and try again")
    
    return results

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()