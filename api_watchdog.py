"""
Smart API Watchdog - Monitors API health AND view counts
Auto-restarts API and refreshes cookies when views stop working
"""

import subprocess
import time
import requests
import os
import signal
import sys
from datetime import datetime

# Configuration
API_PORT = 8000
API_COMMAND = "python api.py"
HEALTH_URL = f"http://localhost:{API_PORT}/health"
SCRAPE_URL = f"http://localhost:{API_PORT}/scrape"
TEST_REEL = "https://www.instagram.com/p/DSNERZGgYuS/"  # Test reel URL

CHECK_INTERVAL = 60  # seconds between checks
VIEW_CHECK_INTERVAL = 300  # check views every 5 minutes
MAX_HEALTH_FAILURES = 3
RESTART_COOLDOWN = 120  # 2 minutes between restarts

# State
api_process = None
last_restart_time = 0
consecutive_health_failures = 0
consecutive_view_failures = 0
last_view_check = 0


def log(message, level="INFO"):
    """Print timestamped log message"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    emoji = {"INFO": "ℹ️", "SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "❌", "RESTART": "🔄"}.get(level, "")
    print(f"[{timestamp}] {emoji} {message}")


def kill_port(port):
    """Kill any process using the specified port"""
    try:
        if os.name == 'nt':  # Windows
            result = subprocess.run(
                f'netstat -ano | findstr :{port} | findstr LISTENING',
                shell=True, capture_output=True, text=True
            )
            killed_pids = set()
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        if pid != '0' and pid not in killed_pids:
                            try:
                                subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
                                killed_pids.add(pid)
                                log(f"Killed process {pid} on port {port}")
                            except:
                                pass
            # Also kill any python processes that might be stuck
            subprocess.run('taskkill /F /IM python.exe /FI "WINDOWTITLE eq api.py"', shell=True, capture_output=True)
        else:
            subprocess.run(f"lsof -ti:{port} | xargs kill -9", shell=True, capture_output=True)
        time.sleep(1)
    except Exception as e:
        log(f"Error killing port {port}: {e}", "WARNING")


def start_api():
    """Start the API process"""
    global api_process, last_restart_time
    
    log("Starting API...", "RESTART")
    
    # Kill existing processes on port
    kill_port(API_PORT)
    time.sleep(3)
    
    # Start new process - use CREATE_NEW_PROCESS_GROUP on Windows
    if os.name == 'nt':
        api_process = subprocess.Popen(
            ["python", "api.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=os.getcwd(),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    else:
        api_process = subprocess.Popen(
            ["python", "api.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=os.getcwd(),
            start_new_session=True
        )
    
    last_restart_time = time.time()
    log(f"API started (PID: {api_process.pid})", "SUCCESS")
    
    # Wait for API to be ready
    time.sleep(5)
    
    # Verify it started
    for _ in range(5):
        if check_health():
            log("API is responding", "SUCCESS")
            return True
        time.sleep(2)
    
    log("API failed to start properly", "ERROR")
    return False


def check_health():
    """Check if API is responding"""
    try:
        response = requests.get(HEALTH_URL, timeout=10)
        return response.status_code == 200
    except:
        return False


def check_views():
    """Test scraping and check if views are returned"""
    try:
        log(f"Testing views with: {TEST_REEL}")
        response = requests.get(
            SCRAPE_URL,
            params={"url": TEST_REEL},
            timeout=60
        )
        
        if response.status_code != 200:
            log(f"Scrape failed with status {response.status_code}", "ERROR")
            return False, None
        
        data = response.json()
        
        if not data.get("success"):
            log(f"Scrape returned success=false", "ERROR")
            return False, None
        
        engagement = data.get("data", {}).get("engagement", {})
        likes = engagement.get("like_count", 0)
        comments = engagement.get("comment_count", 0)
        views = engagement.get("play_count") or engagement.get("view_count") or 0
        
        log(f"Results - Views: {views}, Likes: {likes}, Comments: {comments}")
        
        # Check if we got data but no views
        if (likes > 0 or comments > 0) and views == 0:
            log("Got likes/comments but NO VIEWS - cookies may be stale!", "WARNING")
            return False, {"likes": likes, "comments": comments, "views": views}
        
        if views > 0:
            log(f"Views working! Got {views} views", "SUCCESS")
            return True, {"likes": likes, "comments": comments, "views": views}
        
        # No data at all
        log("No engagement data returned", "WARNING")
        return False, None
        
    except requests.Timeout:
        log("Scrape request timed out", "ERROR")
        return False, None
    except Exception as e:
        log(f"Error checking views: {e}", "ERROR")
        return False, None


def refresh_cookies():
    """Attempt to refresh cookies for all accounts"""
    log("Attempting to refresh cookies...", "RESTART")
    try:
        from cookie_auto_refresher import refresh_all_accounts
        results = refresh_all_accounts()
        success_count = sum(1 for v in results.values() if v)
        log(f"Cookie refresh complete: {success_count}/{len(results)} accounts", "INFO")
        return success_count > 0
    except Exception as e:
        log(f"Cookie refresh failed: {e}", "ERROR")
        return False


def restart_api():
    """Restart the API"""
    global api_process, consecutive_health_failures, consecutive_view_failures
    
    # Check cooldown
    time_since_restart = time.time() - last_restart_time
    if time_since_restart < RESTART_COOLDOWN:
        remaining = int(RESTART_COOLDOWN - time_since_restart)
        log(f"Cooldown active, waiting {remaining}s...", "WARNING")
        return False
    
    log("Restarting API...", "RESTART")
    
    # Stop existing process
    if api_process:
        try:
            api_process.terminate()
            api_process.wait(timeout=5)
        except:
            try:
                api_process.kill()
            except:
                pass
    
    # Start new process
    success = start_api()
    if success:
        consecutive_health_failures = 0
        consecutive_view_failures = 0
        log("API restarted successfully", "SUCCESS")
    
    return success


def run_watchdog():
    """Main watchdog loop"""
    global consecutive_health_failures, consecutive_view_failures, last_view_check
    
    print("""
╔══════════════════════════════════════════════════════════════╗
║           🐕 SMART API WATCHDOG v2.0                         ║
║  • Auto-restarts API on health failures                      ║
║  • Auto-restarts if views stop working                       ║
║  • Auto-refreshes cookies when needed                        ║
║  Press Ctrl+C to stop                                        ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    log("=" * 60)
    log("WATCHDOG STARTED")
    log(f"Health check interval: {CHECK_INTERVAL}s")
    log(f"View check interval: {VIEW_CHECK_INTERVAL}s")
    log(f"Max failures before restart: {MAX_HEALTH_FAILURES}")
    log("=" * 60)
    
    # Start API
    start_api()
    last_view_check = time.time()
    
    # Initial view check
    time.sleep(5)
    views_ok, _ = check_views()
    if not views_ok:
        log("Initial view check failed - will try cookie refresh", "WARNING")
        refresh_cookies()
        restart_api()
    
    while True:
        try:
            time.sleep(CHECK_INTERVAL)
            
            # 1. Health check
            if check_health():
                consecutive_health_failures = 0
            else:
                consecutive_health_failures += 1
                log(f"Health check failed ({consecutive_health_failures}/{MAX_HEALTH_FAILURES})", "ERROR")
                
                if consecutive_health_failures >= MAX_HEALTH_FAILURES:
                    log("Too many health failures - restarting!", "ERROR")
                    restart_api()
                    continue
            
            # 2. Check if API is actually running (not just process check)
            # The detached process won't show as "died" so we rely on health checks
            if consecutive_health_failures >= 2:
                log("API not responding - will restart", "ERROR")
                restart_api()
                continue
            
            # 3. Periodic view check
            time_since_view_check = time.time() - last_view_check
            if time_since_view_check >= VIEW_CHECK_INTERVAL:
                last_view_check = time.time()
                
                views_ok, data = check_views()
                
                if views_ok:
                    consecutive_view_failures = 0
                    log("View check passed ✓", "SUCCESS")
                else:
                    consecutive_view_failures += 1
                    log(f"View check failed ({consecutive_view_failures}/2)", "WARNING")
                    
                    # If we got likes/comments but no views, cookies are stale
                    if data and data.get("likes", 0) > 0 and data.get("views", 0) == 0:
                        log("Cookies appear stale - refreshing...", "WARNING")
                        refresh_cookies()
                        restart_api()
                        consecutive_view_failures = 0
                    elif consecutive_view_failures >= 2:
                        log("Multiple view failures - restarting API", "ERROR")
                        restart_api()
                        consecutive_view_failures = 0
            
        except KeyboardInterrupt:
            log("Watchdog stopped by user")
            if api_process:
                api_process.terminate()
            break
        except Exception as e:
            log(f"Watchdog error: {e}", "ERROR")
            time.sleep(10)


def signal_handler(sig, frame):
    """Handle Ctrl+C"""
    global api_process
    print("\n")
    log("Shutting down watchdog...")
    if api_process:
        api_process.terminate()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    run_watchdog()
