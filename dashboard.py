"""
Simple Dashboard for Instagram Scraper
Shows real-time request statistics and allows manual controls
"""
import requests
import time
import os
from datetime import datetime

class ScraperDashboard:
    def __init__(self):
        self.api_url = "http://127.0.0.1:8000"
        self.tunnel_url = "https://shaft-fashion-survivors-med.trycloudflare.com"
        
    def get_stats(self):
        """Get current statistics from API"""
        try:
            response = requests.get(f"{self.api_url}/stats", timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "error": "API not responding"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_health(self):
        """Get API health status"""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                return {"status": "unhealthy", "error": "API not responding"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    def refresh_cookies(self):
        """Manually trigger cookie refresh"""
        try:
            response = requests.post(f"{self.api_url}/refresh-cookies", timeout=30)
            return response.json()
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def test_scrape(self, url="https://www.instagram.com/p/DR2PrGvkgdN/"):
        """Test scraping with a sample URL"""
        try:
            response = requests.get(f"{self.api_url}/api/internal/scrape", 
                                  params={"url": url}, timeout=30)
            return {
                "success": response.status_code == 200,
                "status_code": response.status_code,
                "response": response.json() if response.status_code == 200 else response.text
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def display_dashboard(self):
        """Display the main dashboard"""
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            
            print("=" * 80)
            print("🎬 INSTAGRAM SCRAPER DASHBOARD")
            print("=" * 80)
            print(f"🕐 Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print()
            
            # API Health
            health = self.get_health()
            status_icon = "✅" if health.get("status") == "healthy" else "❌"
            print(f"📡 API Status: {status_icon} {health.get('status', 'unknown').upper()}")
            
            if health.get("request_stats"):
                stats = health["request_stats"]
                print(f"👤 Account: {stats.get('account', 'unknown')}")
                print()
            
            # Request Statistics
            stats_data = self.get_stats()
            if stats_data.get("success"):
                stats = stats_data["stats"]
                limits = stats_data["rate_limits"]
                
                print("📊 REQUEST STATISTICS:")
                print(f"   Total Requests: {stats['total_requests']}")
                print(f"   This Hour: {stats['hourly_requests']}/{limits['hourly_limit']} ({stats['hourly_remaining']} remaining)")
                print(f"   Today: {stats['daily_requests']}/{limits['daily_limit']} ({stats['daily_remaining']} remaining)")
                
                # Progress bars
                hourly_percent = (stats['hourly_requests'] / limits['hourly_limit']) * 100
                daily_percent = (stats['daily_requests'] / limits['daily_limit']) * 100
                
                hourly_bar = "█" * int(hourly_percent / 5) + "░" * (20 - int(hourly_percent / 5))
                daily_bar = "█" * int(daily_percent / 5) + "░" * (20 - int(daily_percent / 5))
                
                print(f"   Hourly:  [{hourly_bar}] {hourly_percent:.1f}%")
                print(f"   Daily:   [{daily_bar}] {daily_percent:.1f}%")
                
                # Auto-refresh status
                if stats['needs_refresh_soon']:
                    print("   ⚠️  WARNING: Approaching rate limit!")
                
                if stats['last_refresh']:
                    refresh_time = datetime.fromisoformat(stats['last_refresh'])
                    print(f"   🔄 Last Refresh: {refresh_time.strftime('%H:%M:%S')}")
                else:
                    print("   🔄 Last Refresh: Never")
                
            else:
                print("❌ Could not get statistics")
                print(f"   Error: {stats_data.get('error', 'Unknown error')}")
            
            print()
            
            # URLs
            print("🌐 API ENDPOINTS:")
            print(f"   Local:  {self.api_url}")
            print(f"   Public: {self.tunnel_url}")
            print()
            
            # Controls
            print("🎮 CONTROLS:")
            print("   [1] Test Scrape")
            print("   [2] Manual Cookie Refresh")
            print("   [3] View Full Stats")
            print("   [Q] Quit")
            print()
            print("   Auto-refresh will trigger at 40 requests/hour")
            print("   Dashboard updates every 10 seconds")
            print("=" * 80)
            
            # Wait for input or auto-refresh
            try:
                import select
                import sys
                
                # Check if input is available (non-blocking)
                if os.name == 'nt':  # Windows
                    import msvcrt
                    if msvcrt.kbhit():
                        choice = msvcrt.getch().decode('utf-8').lower()
                        self.handle_input(choice)
                else:  # Unix/Linux
                    if select.select([sys.stdin], [], [], 0.1)[0]:
                        choice = sys.stdin.readline().strip().lower()
                        self.handle_input(choice)
                
                time.sleep(10)  # Update every 10 seconds
                
            except KeyboardInterrupt:
                print("\n\n👋 Dashboard stopped by user")
                break
    
    def handle_input(self, choice):
        """Handle user input"""
        if choice == '1':
            print("\n🧪 Testing scrape...")
            result = self.test_scrape()
            if result["success"]:
                print("✅ Test successful!")
                data = result["response"].get("data", {})
                print(f"   Shortcode: {data.get('shortcode', 'N/A')}")
                print(f"   Video URLs: {len(data.get('video_urls', []))} found")
            else:
                print("❌ Test failed!")
                print(f"   Error: {result.get('error', 'Unknown error')}")
            input("\nPress Enter to continue...")
            
        elif choice == '2':
            print("\n🔄 Refreshing cookies...")
            result = self.refresh_cookies()
            if result.get("success"):
                print("✅ Cookie refresh successful!")
            else:
                print("❌ Cookie refresh failed!")
                print(f"   Error: {result.get('error', 'Unknown error')}")
            input("\nPress Enter to continue...")
            
        elif choice == '3':
            print("\n📊 Full Statistics:")
            stats_data = self.get_stats()
            if stats_data.get("success"):
                import json
                print(json.dumps(stats_data, indent=2))
            else:
                print(f"❌ Error: {stats_data.get('error', 'Unknown error')}")
            input("\nPress Enter to continue...")
            
        elif choice == 'q':
            print("\n👋 Goodbye!")
            exit()

def main():
    """Main function"""
    dashboard = ScraperDashboard()
    print("🚀 Starting Instagram Scraper Dashboard...")
    print("   Monitoring API status and request statistics")
    print("   Press Ctrl+C to stop")
    time.sleep(2)
    
    dashboard.display_dashboard()

if __name__ == "__main__":
    main()