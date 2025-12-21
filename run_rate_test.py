"""
Automated Rate Limit Test - No user input required
Tests bhdemo2025 account with Quick test settings
"""
import time
import json
import os
from datetime import datetime
from rate_limit_tester import RateLimitTester, load_urls

def main():
    print("🧪 AUTOMATED RATE LIMIT TEST WITH SMART DELAYS")
    print("="*60)
    print("Account: bhdemo2025")
    print("Test type: Quick (20 requests, random 1.5-4s delays)")
    print("="*60)
    
    # Test configuration
    username = "bhdemo2025"
    password = "passpass"
    max_requests = 20
    
    # Enable auto cookie refresh for fresh login
    import os
    os.environ['AUTO_COOKIE_REFRESH'] = '1'
    os.environ['INSTAGRAM_USERNAME'] = username
    os.environ['INSTAGRAM_PASSWORD'] = password
    os.environ['SHOW_BROWSER'] = 'true'  # Show browser for manual CAPTCHA if needed
    
    # Import smart delay
    from smart_delay import SmartDelay
    smart_delay = SmartDelay(min_delay=1.5, max_delay=4.0)
    
    # Load URLs
    urls = load_urls()
    if not urls:
        print("❌ No URLs available for testing")
        return
    
    print(f"\n📋 Loaded {len(urls)} URLs for testing")
    print(f"⏱️ Estimated time: 1-2 minutes (random delays)")
    print(f"\n🚀 Starting test in 3 seconds...")
    time.sleep(3)
    
    # Run test with smart delays
    tester = RateLimitTester(username, password)
    tester.use_smart_delay = True
    tester.smart_delay = smart_delay
    results = tester.run_test(urls, delay=2.0, max_requests=max_requests)  # delay is fallback
    
    print("\n✅ Test completed!")
    
    # Return key findings
    return results

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Test stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()