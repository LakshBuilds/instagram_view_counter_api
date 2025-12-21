"""
Instagram Rate Limit Tester
Tests single account to determine safe request limits before scaling

WHAT THIS TESTS:
1. How many requests before rate limiting
2. CAPTCHA detection
3. Account block detection
4. Response time patterns
5. Error patterns and recovery time
"""
import time
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from scraper import scrape_instagram_reel, get_session_cookies

class RateLimitTester:
    """Test Instagram rate limits with a single account"""
    
    # Known Instagram rate limit indicators
    RATE_LIMIT_INDICATORS = [
        "rate limit",
        "too many requests",
        "please wait",
        "try again later",
        "temporarily blocked",
        "action blocked",
        "challenge_required",
        "checkpoint_required",
        "login_required",
        "feedback_required",
        "spam",
        "suspicious",
    ]
    
    CAPTCHA_INDICATORS = [
        "captcha",
        "verify",
        "challenge",
        "checkpoint",
        "confirm",
        "security code",
        "suspicious activity",
    ]
    
    BLOCK_INDICATORS = [
        "blocked",
        "disabled",
        "suspended",
        "banned",
        "restricted",
        "action blocked",
    ]
    
    def __init__(self, username: str, password: str):
        """Initialize tester with account credentials"""
        self.username = username
        self.password = password
        self.session = None
        self.csrf_token = ""
        
        # Test results
        self.results = {
            "account": username,
            "test_start": None,
            "test_end": None,
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "rate_limited_at": None,
            "captcha_detected_at": None,
            "block_detected_at": None,
            "response_times": [],
            "errors": [],
            "request_log": [],
        }
        
        # Test configuration
        self.delay_between_requests = 1.0  # Start with 1 second delay
        self.max_requests = 100  # Maximum requests to test
        self.stop_on_rate_limit = True
        self.use_smart_delay = False  # Will be set externally
        self.smart_delay = None  # Will be set externally
        
    def setup_session(self) -> bool:
        """Setup session for the account"""
        print(f"🔧 Setting up session for {self.username}...")
        
        try:
            # Set environment variables
            os.environ['INSTAGRAM_USERNAME'] = self.username
            os.environ['INSTAGRAM_PASSWORD'] = self.password
            os.environ['AUTO_COOKIE_REFRESH'] = '0'  # Disable auto-refresh during testing
            
            # Get session
            self.session, self.csrf_token = get_session_cookies()
            
            if self.session:
                print(f"✅ Session ready for {self.username}")
                return True
            else:
                print(f"❌ Failed to setup session for {self.username}")
                return False
                
        except Exception as e:
            print(f"❌ Session setup error: {e}")
            return False
    
    def detect_rate_limit(self, result: Dict) -> bool:
        """Check if response indicates rate limiting"""
        error = str(result.get('error', '')).lower()
        status_code = result.get('status_code', 0)
        
        # Check status codes
        if status_code == 429:  # Too Many Requests
            return True
        
        # Check error messages
        for indicator in self.RATE_LIMIT_INDICATORS:
            if indicator in error:
                return True
        
        return False
    
    def detect_captcha(self, result: Dict) -> bool:
        """Check if response indicates CAPTCHA requirement"""
        error = str(result.get('error', '')).lower()
        
        for indicator in self.CAPTCHA_INDICATORS:
            if indicator in error:
                return True
        
        return False
    
    def detect_block(self, result: Dict) -> bool:
        """Check if response indicates account block"""
        error = str(result.get('error', '')).lower()
        status_code = result.get('status_code', 0)
        
        # Check status codes
        if status_code in (401, 403):
            return True
        
        # Check error messages
        for indicator in self.BLOCK_INDICATORS:
            if indicator in error:
                return True
        
        return False
    
    def analyze_response(self, result: Dict, request_num: int, response_time: float) -> Dict:
        """Analyze a single response for issues"""
        analysis = {
            "request_num": request_num,
            "timestamp": datetime.now().isoformat(),
            "response_time_ms": round(response_time * 1000, 2),
            "success": result.get('success', False),
            "error": result.get('error'),
            "status_code": result.get('status_code'),
            "rate_limited": False,
            "captcha_detected": False,
            "block_detected": False,
        }
        
        if not result.get('success'):
            analysis["rate_limited"] = self.detect_rate_limit(result)
            analysis["captcha_detected"] = self.detect_captcha(result)
            analysis["block_detected"] = self.detect_block(result)
        
        return analysis
    
    def run_test(self, urls: List[str], delay: float = 1.0, max_requests: int = 50) -> Dict:
        """
        Run rate limit test
        
        Args:
            urls: List of Instagram URLs to test with
            delay: Seconds between requests
            max_requests: Maximum number of requests to send
            
        Returns:
            Test results dictionary
        """
        self.delay_between_requests = delay
        self.max_requests = max_requests
        
        print(f"\n{'='*60}")
        print(f"🧪 RATE LIMIT TEST - {self.username}")
        print(f"{'='*60}")
        print(f"📋 Configuration:")
        print(f"   Delay between requests: {delay}s")
        print(f"   Max requests: {max_requests}")
        print(f"   URLs available: {len(urls)}")
        print(f"{'='*60}\n")
        
        # Setup session
        if not self.setup_session():
            self.results["errors"].append("Failed to setup session")
            return self.results
        
        self.results["test_start"] = datetime.now().isoformat()
        
        # Run test requests
        consecutive_failures = 0
        url_index = 0
        
        for i in range(1, max_requests + 1):
            # Get URL (cycle through available URLs)
            url = urls[url_index % len(urls)]
            url_index += 1
            
            print(f"📤 Request {i}/{max_requests}: {url[:50]}...")
            
            # Make request and measure time
            start_time = time.time()
            result = scrape_instagram_reel(url, session=self.session, save_json=False)
            end_time = time.time()
            response_time = end_time - start_time
            
            # Analyze response
            analysis = self.analyze_response(result, i, response_time)
            self.results["request_log"].append(analysis)
            self.results["response_times"].append(response_time)
            self.results["total_requests"] = i
            
            # Update counters
            if result.get('success'):
                self.results["successful_requests"] += 1
                consecutive_failures = 0
                
                # Extract some data for verification
                extracted = result.get('extracted', {})
                engagement = extracted.get('engagement', {})
                print(f"   ✅ Success! Views: {engagement.get('play_count', 'N/A')}, "
                      f"Likes: {engagement.get('like_count', 'N/A')}, "
                      f"Time: {response_time:.2f}s")
            else:
                self.results["failed_requests"] += 1
                consecutive_failures += 1
                
                error = result.get('error', 'Unknown error')
                print(f"   ❌ Failed: {error[:100]}")
                self.results["errors"].append({
                    "request": i,
                    "error": error,
                    "timestamp": datetime.now().isoformat()
                })
                
                # Check for critical issues
                if analysis["rate_limited"]:
                    print(f"\n🚨 RATE LIMIT DETECTED at request {i}!")
                    self.results["rate_limited_at"] = i
                    if self.stop_on_rate_limit:
                        print("   Stopping test due to rate limit...")
                        break
                
                if analysis["captcha_detected"]:
                    print(f"\n🔐 CAPTCHA DETECTED at request {i}!")
                    self.results["captcha_detected_at"] = i
                    print("   Stopping test - manual intervention required...")
                    break
                
                if analysis["block_detected"]:
                    print(f"\n🚫 ACCOUNT BLOCK DETECTED at request {i}!")
                    self.results["block_detected_at"] = i
                    print("   Stopping test - account may be restricted...")
                    break
            
            # Check for too many consecutive failures
            if consecutive_failures >= 5:
                print(f"\n⚠️ 5 consecutive failures - stopping test")
                break
            
            # Progress update every 10 requests
            if i % 10 == 0:
                success_rate = (self.results["successful_requests"] / i) * 100
                avg_time = sum(self.results["response_times"]) / len(self.results["response_times"])
                print(f"\n📊 Progress: {i}/{max_requests} requests")
                print(f"   Success rate: {success_rate:.1f}%")
                print(f"   Avg response time: {avg_time:.2f}s")
                print()
            
            # Wait before next request
            if i < max_requests:
                if self.use_smart_delay and self.smart_delay:
                    # Use smart random delay
                    self.smart_delay.wait(verbose=True)
                else:
                    print(f"   ⏳ Waiting {delay}s...")
                    time.sleep(delay)
        
        self.results["test_end"] = datetime.now().isoformat()
        
        # Generate summary
        self.print_summary()
        self.save_results()
        
        return self.results
    
    def print_summary(self):
        """Print test summary"""
        print(f"\n{'='*60}")
        print(f"📊 TEST SUMMARY - {self.username}")
        print(f"{'='*60}")
        
        total = self.results["total_requests"]
        success = self.results["successful_requests"]
        failed = self.results["failed_requests"]
        
        print(f"📈 Total Requests: {total}")
        print(f"✅ Successful: {success} ({(success/total*100):.1f}%)")
        print(f"❌ Failed: {failed} ({(failed/total*100):.1f}%)")
        
        if self.results["response_times"]:
            avg_time = sum(self.results["response_times"]) / len(self.results["response_times"])
            min_time = min(self.results["response_times"])
            max_time = max(self.results["response_times"])
            print(f"\n⏱️ Response Times:")
            print(f"   Average: {avg_time:.2f}s")
            print(f"   Min: {min_time:.2f}s")
            print(f"   Max: {max_time:.2f}s")
        
        print(f"\n🚨 Issues Detected:")
        if self.results["rate_limited_at"]:
            print(f"   ⚠️ Rate limited at request: {self.results['rate_limited_at']}")
        else:
            print(f"   ✅ No rate limiting detected")
        
        if self.results["captcha_detected_at"]:
            print(f"   🔐 CAPTCHA at request: {self.results['captcha_detected_at']}")
        else:
            print(f"   ✅ No CAPTCHA detected")
        
        if self.results["block_detected_at"]:
            print(f"   🚫 Block at request: {self.results['block_detected_at']}")
        else:
            print(f"   ✅ No block detected")
        
        # Recommendations
        print(f"\n💡 RECOMMENDATIONS:")
        if self.results["rate_limited_at"]:
            safe_limit = max(1, self.results["rate_limited_at"] - 5)
            print(f"   - Safe requests per session: ~{safe_limit}")
            print(f"   - Increase delay between requests")
            print(f"   - Consider longer wait periods between batches")
        elif total >= 20 and success >= total * 0.9:
            print(f"   - Account appears healthy!")
            print(f"   - Safe to use with current delay ({self.delay_between_requests}s)")
            print(f"   - Can likely handle {total}+ requests per session")
        else:
            print(f"   - High failure rate detected")
            print(f"   - Check cookies/session validity")
            print(f"   - May need to refresh login")
        
        print(f"{'='*60}\n")
    
    def save_results(self):
        """Save test results to file"""
        filename = f"rate_test_{self.username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, indent=2, ensure_ascii=False)
            print(f"📁 Results saved to: {filename}")
        except Exception as e:
            print(f"❌ Failed to save results: {e}")


def load_urls(filename: str = 'real_urls.txt') -> List[str]:
    """Load URLs from file"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip()]
        return urls
    except FileNotFoundError:
        print(f"❌ File {filename} not found")
        return []


def main():
    """Main function to run rate limit test"""
    print("🧪 INSTAGRAM RATE LIMIT TESTER")
    print("="*60)
    print("This tool tests how many requests an account can handle")
    print("before hitting rate limits, CAPTCHA, or blocks.")
    print("="*60)
    
    # Default test account (from your config)
    default_username = "bhdemo2025"
    default_password = "2210991837"
    
    print(f"\nDefault test account: {default_username}")
    use_default = input("Use default account? (y/n): ").strip().lower()
    
    if use_default != 'y':
        username = input("Enter Instagram username: ").strip()
        password = input("Enter Instagram password: ").strip()
    else:
        username = default_username
        password = default_password
    
    # Test configuration
    print("\n📋 TEST CONFIGURATION:")
    print("1. Quick test (20 requests, 2s delay)")
    print("2. Standard test (50 requests, 3s delay)")
    print("3. Aggressive test (100 requests, 1s delay)")
    print("4. Custom test")
    
    choice = input("\nSelect test type (1-4): ").strip()
    
    if choice == '1':
        max_requests = 20
        delay = 2.0
    elif choice == '2':
        max_requests = 50
        delay = 3.0
    elif choice == '3':
        max_requests = 100
        delay = 1.0
    elif choice == '4':
        max_requests = int(input("Max requests: ").strip() or "30")
        delay = float(input("Delay between requests (seconds): ").strip() or "2")
    else:
        max_requests = 30
        delay = 2.0
    
    # Load URLs
    urls = load_urls()
    if not urls:
        print("❌ No URLs available for testing")
        return
    
    print(f"\n📋 Loaded {len(urls)} URLs for testing")
    
    # Confirm before starting
    print(f"\n⚠️ ABOUT TO START TEST:")
    print(f"   Account: {username}")
    print(f"   Max requests: {max_requests}")
    print(f"   Delay: {delay}s")
    print(f"   Estimated time: {(max_requests * delay) / 60:.1f} minutes")
    
    confirm = input("\nStart test? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Test cancelled.")
        return
    
    # Run test
    tester = RateLimitTester(username, password)
    results = tester.run_test(urls, delay=delay, max_requests=max_requests)
    
    print("\n✅ Test completed!")
    print("Check the JSON file for detailed results.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Test stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
else:
    # When imported as module, don't run main()
    pass