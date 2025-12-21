"""
Instagram Scraper Monitoring Console
Real-time monitoring of API requests, rate limits, and auto cookie refresh
"""
import time
import json
import requests
from datetime import datetime, timedelta
from collections import defaultdict
import os
import threading
from cookie_auto_refresher import auto_refresh_cookies

class ScraperMonitor:
    def __init__(self):
        self.request_counts = defaultdict(int)
        self.hourly_counts = defaultdict(int)
        self.daily_counts = defaultdict(int)
        self.last_refresh_time = {}
        self.rate_limits = {
            'requests_per_hour': 50,  # Conservative limit
            'requests_per_day': 500,  # Daily limit
            'auto_refresh_threshold': 40  # Refresh cookies at 40 requests/hour
        }
        self.accounts = [
            {'username': 'bhdemo2025', 'password': 'passpass'},
            {'username': 'candy_shopbuy', 'password': 'pass@@@123'},
            {'username': 'elmasedoyle', 'password': 'yash1234'},
            {'username': 'ravi108794', 'password': 'sharks10'},
            {'username': 'raviram8274', 'password': 'sharks11'}
        ]
        self.current_account = 'bhdemo2025'
        self.api_urls = {
            'single': 'http://127.0.0.1:8000',
            'multi': 'http://127.0.0.1:8001'
        }
        self.start_time = datetime.now()
        
    def get_api_stats(self):
        """Get current API statistics"""
        try:
            # Try single account API
            single_response = requests.get(f"{self.api_urls['single']}/health", timeout=5)
            single_status = "✅ Online" if single_response.status_code == 200 else "❌ Error"
        except:
            single_status = "❌ Offline"
            
        try:
            # Try multi-account API
            multi_response = requests.get(f"{self.api_urls['multi']}/health", timeout=5)
            multi_status = "✅ Online" if multi_response.status_code == 200 else "❌ Error"
        except:
            multi_status = "❌ Offline"
            
        try:
            # Get multi-account stats
            stats_response = requests.get(f"{self.api_urls['multi']}/stats", timeout=5)
            multi_stats = stats_response.json() if stats_response.status_code == 200 else {}
        except:
            multi_stats = {}
            
        return {
            'single_api': single_status,
            'multi_api': multi_status,
            'multi_stats': multi_stats
        }
    
    def check_rate_limits(self, account):
        """Check if account is approaching rate limits"""
        current_hour = datetime.now().hour
        current_date = datetime.now().date()
        
        hourly_key = f"{account}_{current_date}_{current_hour}"
        daily_key = f"{account}_{current_date}"
        
        hourly_count = self.hourly_counts[hourly_key]
        daily_count = self.daily_counts[daily_key]
        
        return {
            'hourly_count': hourly_count,
            'daily_count': daily_count,
            'hourly_limit': self.rate_limits['requests_per_hour'],
            'daily_limit': self.rate_limits['requests_per_day'],
            'needs_refresh': hourly_count >= self.rate_limits['auto_refresh_threshold'],
            'hourly_remaining': max(0, self.rate_limits['requests_per_hour'] - hourly_count),
            'daily_remaining': max(0, self.rate_limits['requests_per_day'] - daily_count)
        }
    
    def auto_refresh_if_needed(self, account):
        """Automatically refresh cookies if rate limit threshold reached"""
        limits = self.check_rate_limits(account)
        
        if limits['needs_refresh']:
            print(f"\n🔄 AUTO-REFRESH TRIGGERED for {account}")
            print(f"   Reason: {limits['hourly_count']}/{limits['hourly_limit']} requests this hour")
            
            # Find account credentials
            account_creds = None
            for acc in self.accounts:
                if acc['username'] == account:
                    account_creds = acc
                    break
            
            if account_creds:
                # Set environment variables
                os.environ['AUTO_COOKIE_REFRESH'] = '1'
                os.environ['INSTAGRAM_USERNAME'] = account_creds['username']
                os.environ['INSTAGRAM_PASSWORD'] = account_creds['password']
                os.environ['SHOW_BROWSER'] = 'false'  # Headless for auto-refresh
                
                print(f"   🔐 Refreshing cookies for {account}...")
                success = auto_refresh_cookies(f"Auto-refresh at {limits['hourly_count']} requests")
                
                if success:
                    print(f"   ✅ Cookie refresh successful for {account}")
                    self.last_refresh_time[account] = datetime.now()
                    # Reset hourly count after refresh
                    current_hour = datetime.now().hour
                    current_date = datetime.now().date()
                    hourly_key = f"{account}_{current_date}_{current_hour}"
                    self.hourly_counts[hourly_key] = 0
                else:
                    print(f"   ❌ Cookie refresh failed for {account}")
                    
                return success
        
        return False
    
    def log_request(self, account, success=True):
        """Log a request for rate limiting tracking"""
        current_hour = datetime.now().hour
        current_date = datetime.now().date()
        
        hourly_key = f"{account}_{current_date}_{current_hour}"
        daily_key = f"{account}_{current_date}"
        
        self.hourly_counts[hourly_key] += 1
        self.daily_counts[daily_key] += 1
        self.request_counts[account] += 1
        
        # Check if auto-refresh is needed
        self.auto_refresh_if_needed(account)
    
    def display_console(self):
        """Display the monitoring console"""
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            
            print("=" * 80)
            print("🎬 INSTAGRAM SCRAPER MONITORING CONSOLE")
            print("=" * 80)
            
            # Runtime info
            runtime = datetime.now() - self.start_time
            print(f"⏱️  Runtime: {str(runtime).split('.')[0]}")
            print(f"🕐 Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print()
            
            # API Status
            api_stats = self.get_api_stats()
            print("📡 API STATUS:")
            print(f"   Single Account API: {api_stats['single_api']}")
            print(f"   Multi-Account API:  {api_stats['multi_api']}")
            print()
            
            # Current Account Status
            print(f"👤 CURRENT ACCOUNT: {self.current_account}")
            limits = self.check_rate_limits(self.current_account)
            
            print("📊 RATE LIMIT STATUS:")
            print(f"   Hourly:  {limits['hourly_count']}/{limits['hourly_limit']} ({limits['hourly_remaining']} remaining)")
            print(f"   Daily:   {limits['daily_count']}/{limits['daily_limit']} ({limits['daily_remaining']} remaining)")
            
            # Rate limit bars
            hourly_percent = (limits['hourly_count'] / limits['hourly_limit']) * 100
            daily_percent = (limits['daily_count'] / limits['daily_limit']) * 100
            
            hourly_bar = "█" * int(hourly_percent / 5) + "░" * (20 - int(hourly_percent / 5))
            daily_bar = "█" * int(daily_percent / 5) + "░" * (20 - int(daily_percent / 5))
            
            print(f"   Hourly:  [{hourly_bar}] {hourly_percent:.1f}%")
            print(f"   Daily:   [{daily_bar}] {daily_percent:.1f}%")
            
            # Auto-refresh status
            if limits['needs_refresh']:
                print("   🔄 AUTO-REFRESH: READY TO TRIGGER")
            else:
                remaining_until_refresh = self.rate_limits['auto_refresh_threshold'] - limits['hourly_count']
                print(f"   🔄 AUTO-REFRESH: {remaining_until_refresh} requests until trigger")
            
            print()
            
            # All Accounts Summary
            print("👥 ALL ACCOUNTS SUMMARY:")
            for account_info in self.accounts:
                account = account_info['username']
                acc_limits = self.check_rate_limits(account)
                total_requests = self.request_counts[account]
                
                status = "🟢" if acc_limits['hourly_remaining'] > 10 else "🟡" if acc_limits['hourly_remaining'] > 0 else "🔴"
                
                last_refresh = self.last_refresh_time.get(account, "Never")
                if isinstance(last_refresh, datetime):
                    last_refresh = last_refresh.strftime("%H:%M:%S")
                
                print(f"   {status} {account:<15} | H:{acc_limits['hourly_count']:>2}/{acc_limits['hourly_limit']} | D:{acc_limits['daily_count']:>3}/{acc_limits['daily_limit']} | Total:{total_requests:>3} | Last Refresh: {last_refresh}")
            
            print()
            
            # Multi-Account API Stats
            if api_stats['multi_stats']:
                stats = api_stats['multi_stats']
                print("🔄 MULTI-ACCOUNT API STATS:")
                print(f"   Total Requests: {stats.get('total_requests', 0)}")
                print(f"   Active Accounts: {len([acc for acc in stats.get('accounts', []) if acc.get('is_active')])}")
                print(f"   Average RPM: {stats.get('average_requests_per_minute', 0):.1f}")
                print()
            
            # Instructions
            print("🎮 CONTROLS:")
            print("   Press Ctrl+C to exit")
            print("   Monitor will auto-refresh cookies when limits are reached")
            print("   Current account will auto-switch if rate limited")
            
            print("=" * 80)
            
            time.sleep(5)  # Update every 5 seconds
    
    def start_monitoring(self):
        """Start the monitoring console"""
        print("🚀 Starting Instagram Scraper Monitor...")
        print("   Monitoring rate limits and auto-refresh functionality")
        print("   Press Ctrl+C to stop")
        
        try:
            self.display_console()
        except KeyboardInterrupt:
            print("\n\n👋 Monitoring stopped by user")
            print("📊 Final Statistics:")
            for account in self.accounts:
                username = account['username']
                total = self.request_counts[username]
                if total > 0:
                    print(f"   {username}: {total} total requests")

def main():
    """Main function to run the monitoring console"""
    monitor = ScraperMonitor()
    
    # Simulate some requests for demo (remove in production)
    print("🔧 Initializing monitor...")
    
    monitor.start_monitoring()

if __name__ == "__main__":
    main()