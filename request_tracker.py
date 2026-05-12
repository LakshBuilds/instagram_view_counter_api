"""
Simple Request Tracker for Instagram Scraper
Tracks requests and triggers auto-refresh when needed
"""
import json
import os
from datetime import datetime, timedelta
from cookie_auto_refresher import auto_refresh_cookies

# Configurable rate limits via environment variables
# DISABLED LIMITS - No restrictions!
HOURLY_LIMIT = int(os.getenv('HOURLY_LIMIT', '999999999'))  # Effectively unlimited
DAILY_LIMIT = int(os.getenv('DAILY_LIMIT', '999999999'))     # Effectively unlimited
REFRESH_THRESHOLD = int(os.getenv('REFRESH_THRESHOLD', '999999999'))  # Effectively disabled

class RequestTracker:
    def __init__(self, account_name="bhdemo2025"):
        self.account_name = account_name
        self.stats_file = f"request_stats_{account_name}.json"
        self.load_stats()
        
    def load_stats(self):
        """Load existing stats from file"""
        try:
            if os.path.exists(self.stats_file):
                with open(self.stats_file, 'r') as f:
                    data = json.load(f)
                    self.stats = data
            else:
                self.stats = {
                    'total_requests': 0,
                    'successful_requests': 0,
                    'failed_requests': 0,
                    'hourly_requests': {},
                    'daily_requests': {},
                    'recent_errors': [],  # Track last 50 errors
                    'error_rate_5min': 0.0,  # Error rate in last 5 minutes
                    'last_refresh': None,
                    'account': self.account_name
                }
        except:
            self.stats = {
                'total_requests': 0,
                'hourly_requests': {},
                'daily_requests': {},
                'last_refresh': None,
                'account': self.account_name
            }
    
    def save_stats(self):
        """Save stats to file"""
        try:
            with open(self.stats_file, 'w') as f:
                json.dump(self.stats, f, indent=2)
        except Exception as e:
            print(f"Error saving stats: {e}")
    
    def get_current_hour_key(self):
        """Get current hour key for tracking"""
        now = datetime.now()
        return f"{now.date()}_{now.hour}"
    
    def get_current_day_key(self):
        """Get current day key for tracking"""
        return str(datetime.now().date())
    
    def log_request(self, success=True, error_msg=None):
        """Log a request and check if refresh is needed"""
        hour_key = self.get_current_hour_key()
        day_key = self.get_current_day_key()
        
        # Initialize error tracking if not present
        if 'successful_requests' not in self.stats:
            self.stats['successful_requests'] = 0
        if 'failed_requests' not in self.stats:
            self.stats['failed_requests'] = 0
        if 'recent_errors' not in self.stats:
            self.stats['recent_errors'] = []
        
        # Update counters
        self.stats['total_requests'] += 1
        self.stats['hourly_requests'][hour_key] = self.stats['hourly_requests'].get(hour_key, 0) + 1
        self.stats['daily_requests'][day_key] = self.stats['daily_requests'].get(day_key, 0) + 1
        
        if success:
            self.stats['successful_requests'] += 1
        else:
            self.stats['failed_requests'] += 1
            # Track recent errors (keep last 50)
            if error_msg:
                error_entry = {
                    'timestamp': datetime.now().isoformat(),
                    'error': error_msg[:200]  # Truncate long errors
                }
                self.stats['recent_errors'].append(error_entry)
                if len(self.stats['recent_errors']) > 50:
                    self.stats['recent_errors'].pop(0)
        
        # Calculate error rate for last 5 minutes
        self._calculate_error_rate()
        
        # Clean old data (keep only last 24 hours and 7 days)
        self.cleanup_old_data()
        
        # Save stats
        self.save_stats()
        
        # Check if refresh is needed
        current_hourly = self.stats['hourly_requests'].get(hour_key, 0)
        current_daily = self.stats['daily_requests'].get(day_key, 0)
        
        print(f"📊 Request logged: {current_hourly}/{HOURLY_LIMIT} this hour, {current_daily}/{DAILY_LIMIT} today")
        
        # Auto-refresh at threshold
        if current_hourly >= REFRESH_THRESHOLD:
            print(f"🔄 AUTO-REFRESH TRIGGERED: {current_hourly} requests this hour")
            self.auto_refresh_cookies()
            return True
            
        return False
    
    def _calculate_error_rate(self):
        """Calculate error rate for last 5 minutes using actual request counts"""
        now = datetime.now()
        cutoff = now - timedelta(minutes=5)
        
        recent_error_count = 0
        for error in self.stats.get('recent_errors', []):
            try:
                error_time = datetime.fromisoformat(error['timestamp'])
                if error_time >= cutoff:
                    recent_error_count += 1
            except:
                pass
        
        total_success = self.stats.get('successful_requests', 0)
        total_fail = self.stats.get('failed_requests', 0)
        total_all = total_success + total_fail
        
        # Use actual totals: if there are recent errors, calculate against
        # a reasonable denominator (at least 1 to avoid division by zero)
        hour_key = self.get_current_hour_key()
        hourly_requests = self.stats['hourly_requests'].get(hour_key, 0)
        recent_total_estimate = max(hourly_requests // 12, 1)
        recent_total_count = max(recent_error_count, recent_total_estimate)
        
        if recent_total_count > 0:
            self.stats['error_rate_5min'] = (recent_error_count / recent_total_count) * 100
        else:
            self.stats['error_rate_5min'] = 0.0
        
        # Also track overall error rate for visibility
        if total_all > 0:
            self.stats['overall_error_rate'] = (total_fail / total_all) * 100
        else:
            self.stats['overall_error_rate'] = 0.0
    
    def get_error_stats(self):
        """Get error statistics"""
        return {
            'error_rate_5min': self.stats.get('error_rate_5min', 0.0),
            'total_errors': self.stats.get('failed_requests', 0),
            'total_success': self.stats.get('successful_requests', 0),
            'recent_errors': self.stats.get('recent_errors', [])[-10:],  # Last 10 errors
            'is_error_spike': self.stats.get('error_rate_5min', 0.0) > 30.0  # More than 30% errors (lowered threshold)
        }
    
    def cleanup_old_data(self):
        """Remove old data to keep file size manageable"""
        now = datetime.now()
        
        # Keep only last 24 hours for hourly data
        cutoff_time = now - timedelta(hours=24)
        old_hour_keys = []
        for hour_key in self.stats['hourly_requests']:
            try:
                date_str, hour_str = hour_key.split('_')
                key_datetime = datetime.strptime(f"{date_str} {hour_str}", "%Y-%m-%d %H")
                if key_datetime < cutoff_time:
                    old_hour_keys.append(hour_key)
            except:
                old_hour_keys.append(hour_key)  # Remove malformed keys
        
        for key in old_hour_keys:
            del self.stats['hourly_requests'][key]
        
        # Keep only last 7 days for daily data
        cutoff_date = now.date() - timedelta(days=7)
        old_day_keys = []
        for day_key in self.stats['daily_requests']:
            try:
                key_date = datetime.strptime(day_key, "%Y-%m-%d").date()
                if key_date < cutoff_date:
                    old_day_keys.append(day_key)
            except:
                old_day_keys.append(day_key)  # Remove malformed keys
        
        for key in old_day_keys:
            del self.stats['daily_requests'][key]
    
    def auto_refresh_cookies(self):
        """Automatically refresh cookies"""
        try:
            # Get account credentials
            accounts = {
                'bhdemo2025': 'pass@@',
                'candy_shopbuy': 'pass@@@123',
                'elmasedoyle': 'yash1234',
                'ravi108794': 'sharks10',
                'hatke_automation': 'pass@@@123P',
            }
            
            password = accounts.get(self.account_name)
            if not password:
                print(f"❌ No password found for account {self.account_name}")
                return False
            
            # Enable auto cookie refresh
            os.environ['AUTO_COOKIE_REFRESH'] = '1'
            os.environ['INSTAGRAM_USERNAME'] = self.account_name
            os.environ['INSTAGRAM_PASSWORD'] = password
            os.environ['SHOW_BROWSER'] = 'true'  # Show browser for manual CAPTCHA if needed
            os.environ['INSTAGRAM_COOKIES_FILE'] = f'cookies_{self.account_name}.txt'
            
            print(f"🔐 Refreshing cookies for {self.account_name}...")
            print(f"   Browser will open - complete any CAPTCHA/security challenges if needed")
            
            success = auto_refresh_cookies(f"Auto-refresh after rate limit")
            
            if success:
                print(f"✅ Cookie refresh successful for {self.account_name}!")
                self.stats['last_refresh'] = datetime.now().isoformat()
                
                # Reset hourly counter after successful refresh
                hour_key = self.get_current_hour_key()
                self.stats['hourly_requests'][hour_key] = 0
                self.save_stats()
                
                return True
            else:
                print(f"❌ Cookie refresh failed for {self.account_name}!")
                return False
                
        except Exception as e:
            print(f"❌ Error during auto-refresh: {e}")
            return False
    
    def get_status(self):
        """Get current status"""
        hour_key = self.get_current_hour_key()
        day_key = self.get_current_day_key()
        
        current_hourly = self.stats['hourly_requests'].get(hour_key, 0)
        current_daily = self.stats['daily_requests'].get(day_key, 0)
        
        return {
            'account': self.account_name,
            'total_requests': self.stats['total_requests'],
            'hourly_requests': current_hourly,
            'daily_requests': current_daily,
            'hourly_remaining': max(0, HOURLY_LIMIT - current_hourly),
            'daily_remaining': max(0, DAILY_LIMIT - current_daily),
            'last_refresh': self.stats['last_refresh'],
            'needs_refresh_soon': current_hourly >= (REFRESH_THRESHOLD - 20),
            'error_stats': self.get_error_stats()
        }
    
    def print_status(self):
        """Print current status to console"""
        status = self.get_status()
        
        print("\n" + "="*60)
        print(f"📊 REQUEST TRACKER - {status['account'].upper()}")
        print("="*60)
        print(f"⏱️  Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📈 Total Requests: {status['total_requests']}")
        print(f"🕐 This Hour: {status['hourly_requests']}/{HOURLY_LIMIT} ({status['hourly_remaining']} remaining)")
        print(f"📅 Today: {status['daily_requests']}/{DAILY_LIMIT} ({status['daily_remaining']} remaining)")
        
        if status['last_refresh']:
            refresh_time = datetime.fromisoformat(status['last_refresh'])
            print(f"🔄 Last Refresh: {refresh_time.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print(f"🔄 Last Refresh: Never")
        
        if status['needs_refresh_soon']:
            print(f"⚠️  WARNING: Approaching rate limit! Auto-refresh will trigger at {REFRESH_THRESHOLD} requests.")
        
        # Progress bars
        hourly_percent = (status['hourly_requests'] / HOURLY_LIMIT) * 100
        daily_percent = (status['daily_requests'] / DAILY_LIMIT) * 100
        
        hourly_bar = "█" * int(hourly_percent / 5) + "░" * (20 - int(hourly_percent / 5))
        daily_bar = "█" * int(daily_percent / 5) + "░" * (20 - int(daily_percent / 5))
        
        print(f"📊 Hourly:  [{hourly_bar}] {hourly_percent:.1f}%")
        print(f"📊 Daily:   [{daily_bar}] {daily_percent:.1f}%")
        print("="*60)

# Global tracker instance
tracker = RequestTracker("bhdemo2025")

def log_api_request(success=True, error_msg=None):
    """Function to call from API to log requests"""
    return tracker.log_request(success, error_msg)

def get_request_status():
    """Get current request status"""
    return tracker.get_status()

def get_error_stats():
    """Get error statistics"""
    return tracker.get_error_stats()

def print_request_status():
    """Print current status"""
    tracker.print_status()

if __name__ == "__main__":
    # Demo usage
    tracker.print_status()