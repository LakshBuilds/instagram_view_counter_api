"""
Simple Request Tracker for Instagram Scraper
Tracks requests and triggers auto-refresh when needed
"""
import json
import os
from datetime import datetime, timedelta
from cookie_auto_refresher import auto_refresh_cookies

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
                    'hourly_requests': {},
                    'daily_requests': {},
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
    
    def log_request(self, success=True):
        """Log a request and check if refresh is needed"""
        hour_key = self.get_current_hour_key()
        day_key = self.get_current_day_key()
        
        # Update counters
        self.stats['total_requests'] += 1
        self.stats['hourly_requests'][hour_key] = self.stats['hourly_requests'].get(hour_key, 0) + 1
        self.stats['daily_requests'][day_key] = self.stats['daily_requests'].get(day_key, 0) + 1
        
        # Clean old data (keep only last 24 hours and 7 days)
        self.cleanup_old_data()
        
        # Save stats
        self.save_stats()
        
        # Check if refresh is needed
        current_hourly = self.stats['hourly_requests'].get(hour_key, 0)
        current_daily = self.stats['daily_requests'].get(day_key, 0)
        
        print(f"📊 Request logged: {current_hourly}/50 this hour, {current_daily}/500 today")
        
        # Auto-refresh at 40 requests per hour
        if current_hourly >= 40:
            print(f"🔄 AUTO-REFRESH TRIGGERED: {current_hourly} requests this hour")
            self.auto_refresh_cookies()
            return True
            
        return False
    
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
                'bhdemo2025': 'passpass',
                'candy_shopbuy': 'pass@@@123',
                'elmasedoyle': 'yash1234',
                'ravi108794': 'sharks10',
                'raviram8274': 'sharks11'
            }
            
            password = accounts.get(self.account_name)
            if not password:
                print(f"❌ No password found for account {self.account_name}")
                return False
            
            # Set environment variables
            os.environ['AUTO_COOKIE_REFRESH'] = '1'
            os.environ['INSTAGRAM_USERNAME'] = self.account_name
            os.environ['INSTAGRAM_PASSWORD'] = password
            os.environ['SHOW_BROWSER'] = 'false'  # Headless for auto-refresh
            
            print(f"🔐 Refreshing cookies for {self.account_name}...")
            success = auto_refresh_cookies(f"Auto-refresh after rate limit")
            
            if success:
                print(f"✅ Cookie refresh successful!")
                self.stats['last_refresh'] = datetime.now().isoformat()
                
                # Reset hourly counter after successful refresh
                hour_key = self.get_current_hour_key()
                self.stats['hourly_requests'][hour_key] = 0
                self.save_stats()
                
                return True
            else:
                print(f"❌ Cookie refresh failed!")
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
            'hourly_remaining': max(0, 50 - current_hourly),
            'daily_remaining': max(0, 500 - current_daily),
            'last_refresh': self.stats['last_refresh'],
            'needs_refresh_soon': current_hourly >= 35
        }
    
    def print_status(self):
        """Print current status to console"""
        status = self.get_status()
        
        print("\n" + "="*60)
        print(f"📊 REQUEST TRACKER - {status['account'].upper()}")
        print("="*60)
        print(f"⏱️  Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📈 Total Requests: {status['total_requests']}")
        print(f"🕐 This Hour: {status['hourly_requests']}/50 ({status['hourly_remaining']} remaining)")
        print(f"📅 Today: {status['daily_requests']}/500 ({status['daily_remaining']} remaining)")
        
        if status['last_refresh']:
            refresh_time = datetime.fromisoformat(status['last_refresh'])
            print(f"🔄 Last Refresh: {refresh_time.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print(f"🔄 Last Refresh: Never")
        
        if status['needs_refresh_soon']:
            print(f"⚠️  WARNING: Approaching rate limit! Auto-refresh will trigger at 40 requests.")
        
        # Progress bars
        hourly_percent = (status['hourly_requests'] / 50) * 100
        daily_percent = (status['daily_requests'] / 500) * 100
        
        hourly_bar = "█" * int(hourly_percent / 5) + "░" * (20 - int(hourly_percent / 5))
        daily_bar = "█" * int(daily_percent / 5) + "░" * (20 - int(daily_percent / 5))
        
        print(f"📊 Hourly:  [{hourly_bar}] {hourly_percent:.1f}%")
        print(f"📊 Daily:   [{daily_bar}] {daily_percent:.1f}%")
        print("="*60)

# Global tracker instance
tracker = RequestTracker("bhdemo2025")

def log_api_request(success=True):
    """Function to call from API to log requests"""
    return tracker.log_request(success)

def get_request_status():
    """Get current request status"""
    return tracker.get_status()

def print_request_status():
    """Print current status"""
    tracker.print_status()

if __name__ == "__main__":
    # Demo usage
    tracker.print_status()