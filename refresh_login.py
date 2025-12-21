"""
Refresh Instagram Login - Get fresh cookies with new password
"""
import os
import time

def main():
    print("🔐 INSTAGRAM LOGIN REFRESH")
    print("="*60)
    print("This will open a browser to login and get fresh cookies")
    print("="*60)
    
    # Set credentials
    username = "bhdemo2025"
    password = "passpass"
    
    print(f"\n👤 Account: {username}")
    print(f"🔑 Password: {'*' * len(password)}")
    
    # Set environment variables
    os.environ['AUTO_COOKIE_REFRESH'] = '1'
    os.environ['INSTAGRAM_USERNAME'] = username
    os.environ['INSTAGRAM_PASSWORD'] = password
    os.environ['SHOW_BROWSER'] = 'true'  # Show browser for manual CAPTCHA
    
    print("\n🌐 Opening browser for login...")
    print("⚠️  If CAPTCHA appears, please complete it manually")
    print("="*60)
    
    # Import and run cookie refresh
    from cookie_auto_refresher import auto_refresh_cookies
    
    success = auto_refresh_cookies(reason="Password changed - need fresh cookies")
    
    if success:
        print("\n✅ LOGIN SUCCESSFUL!")
        print("📁 Fresh cookies saved to cookies.txt")
        print("\nYou can now run the rate limit test again.")
    else:
        print("\n❌ LOGIN FAILED!")
        print("Please check:")
        print("  - Username and password are correct")
        print("  - Complete any CAPTCHA in the browser")
        print("  - Account is not blocked")
    
    return success

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()