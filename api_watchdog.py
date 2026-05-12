"""
Smart API Watchdog - Monitors API health; refreshes cookies only when scraping stops returning views.

By default we do NOT re-probe views on a timer (GraphQL already validates real traffic). After each API
start, we run one /scrape per configured Instagram account (from GET /stats) so round-robin is exercised.
Override count with WATCHDOG_VIEW_PROBE_COUNT. Set WATCHDOG_VIEW_INTERVAL_SEC for optional periodic checks.

Error-rate spikes alone do not refresh cookies unless WATCHDOG_REFRESH_ON_ERROR_SPIKE=1 (often transient).
"""

import subprocess
import time
import requests
import os
import signal
import sys
import shutil
from datetime import datetime


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).lower() in ("1", "true", "yes")


# Configuration
API_PORT = _env_int("API_PORT", 8002)
API_COMMAND = "python3 api.py"
HEALTH_URL = f"http://localhost:{API_PORT}/health"
SCRAPE_URL = f"http://localhost:{API_PORT}/scrape"
STATS_URL = f"http://localhost:{API_PORT}/stats"
ERROR_STATS_URL = f"http://localhost:{API_PORT}/error-stats"
TEST_REEL = os.getenv(
    "WATCHDOG_TEST_REEL_URL",
    "https://www.instagram.com/p/DSNERZGgYuS/",
)

CHECK_INTERVAL = _env_int("WATCHDOG_CHECK_INTERVAL_SEC", 60)
# 0 = only the initial view probe after each API start/restart (no periodic scrape tests)
VIEW_CHECK_INTERVAL = _env_int("WATCHDOG_VIEW_INTERVAL_SEC", 0)
INITIAL_VIEW_CHECK_INTERVAL = _env_int("WATCHDOG_INITIAL_VIEW_CHECK_SEC", 10)
MAX_HEALTH_FAILURES = 1
RESTART_COOLDOWN = 120  # 2 minutes between restarts

REFRESH_ON_ERROR_SPIKE = _env_bool("WATCHDOG_REFRESH_ON_ERROR_SPIKE", False)
error_check_interval = _env_int("WATCHDOG_ERROR_CHECK_SEC", 60)
# Minimum gap between auto cookie refreshes. Without this, when Instagram throttles
# by IP (which is common), every fresh cookie gets throttled again within minutes →
# refresh loops every 2 min, hammering Instagram's login endpoint and getting the
# account flagged. 30 min default is enough for IP-level throttles to often clear.
MIN_REFRESH_INTERVAL_SEC = _env_int("WATCHDOG_MIN_REFRESH_INTERVAL_SEC", 600)
last_auto_refresh = 0.0


def _try_refresh_cookies(reason: str) -> bool:
    """refresh_cookies() guarded by MIN_REFRESH_INTERVAL_SEC."""
    global last_auto_refresh
    now = time.time()
    elapsed = now - last_auto_refresh
    if elapsed < MIN_REFRESH_INTERVAL_SEC:
        wait_remaining = int(MIN_REFRESH_INTERVAL_SEC - elapsed)
        log(
            f"🚫 Skipping cookie refresh ({reason}) — last refresh was "
            f"{int(elapsed)}s ago; min gap {MIN_REFRESH_INTERVAL_SEC}s "
            f"(retry in {wait_remaining}s)",
            "WARNING",
        )
        return False
    last_auto_refresh = now
    log(f"🍪 Auto cookie refresh triggered ({reason})", "RESTART")
    return refresh_cookies()

# State
api_process = None
# True when we adopted an existing server — never SIGKILL/restart it from this process.
monitoring_external_api = False
last_restart_time = 0
consecutive_health_failures = 0
consecutive_view_failures = 0
last_view_check = 0
is_first_view_check = True  # Track if this is the first view check after startup
error_spike_detected = False
last_error_check = 0
consecutive_restart_cycles = 0  # Track "first check OK, periodic fails" pattern
REFRESH_AFTER_CYCLES = 2  # Refresh cookies after this many failed cycles


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


def start_api(adopt_existing: bool = True):
    """Start the API process, or adopt one that is already listening on API_PORT."""
    global api_process, last_restart_time, monitoring_external_api

    if adopt_existing:
        for attempt in range(3):
            if check_health():
                log(
                    "API already healthy on port — monitoring existing server (will not kill it on watchdog exit)",
                    "SUCCESS",
                )
                api_process = None
                monitoring_external_api = True
                last_restart_time = time.time()
                return True
            if attempt < 2:
                time.sleep(2)

    monitoring_external_api = False

    log("Starting API...", "RESTART")

    # Kill existing processes on port (skipped above when we adopted a healthy server)
    kill_port(API_PORT)
    time.sleep(3)
    
    # Start new process - use CREATE_NEW_PROCESS_GROUP on Windows
    if os.name == 'nt':
        api_process = subprocess.Popen(
            ["python3", "api.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=os.getcwd(),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    else:
        api_process = subprocess.Popen(
            ["python3", "api.py"],
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


def check_error_rate():
    """Check error rate and detect spikes"""
    global error_spike_detected
    try:
        response = requests.get(ERROR_STATS_URL, timeout=10)
        if response.status_code == 200:
            data = response.json()
            error_rate = data.get('error_rate_5min', 0.0)
            is_spike = data.get('is_error_spike', False)
            total_errors = data.get('total_errors', 0)
            total_success = data.get('total_success', 0)
            
            # Lower threshold to 30% for more sensitive detection
            if is_spike and error_rate > 30.0:
                if not error_spike_detected:
                    log(f"🚨 ERROR SPIKE DETECTED: {error_rate:.1f}% error rate in last 5 minutes!", "ERROR")
                    log(f"   Errors: {total_errors}, Success: {total_success}", "ERROR")
                    error_spike_detected = True
                return True, error_rate, data.get('recent_errors', [])
            else:
                if error_spike_detected:
                    log(f"✅ Error rate normalized: {error_rate:.1f}%", "SUCCESS")
                    error_spike_detected = False
                return False, error_rate, []
        else:
            # API might not be ready yet, don't treat as error
            return False, 0.0, []
    except requests.exceptions.ConnectionError:
        # API not ready yet, log but don't treat as error
        log("   ⚠️  API not ready for error stats check (will retry)", "WARNING")
        return False, 0.0, []
    except Exception as e:
        # Log all errors for debugging
        log(f"   ⚠️  Error checking error stats: {e}", "WARNING")
        return False, 0.0, []


def _view_probe_count():
    """
    One /scrape per Instagram account (API round-robins). Override with WATCHDOG_VIEW_PROBE_COUNT.
    """
    raw = os.getenv("WATCHDOG_VIEW_PROBE_COUNT")
    if raw is not None and raw.strip() != "":
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    try:
        r = requests.get(STATS_URL, timeout=10)
        if r.status_code == 200:
            j = r.json()
            accounts = (j.get("multi_account") or {}).get("accounts")
            if accounts:
                return len(accounts)
    except Exception:
        pass
    return 1


def _check_views_once():
    """Single /scrape probe (one account in rotation)."""
    try:
        response = requests.get(
            SCRAPE_URL,
            params={"url": TEST_REEL},
            timeout=60
        )

        if response.status_code != 200:
            try:
                error_data = response.json()
                error_msg = error_data.get('detail', {}).get('error', 'Unknown error')
                account_used = error_data.get('detail', {}).get('account_used', 'unknown')
                log(f"Scrape failed with status {response.status_code} (account: {account_used})", "ERROR")
                log(f"   Error: {error_msg[:100]}", "ERROR")
            except Exception:
                log(f"Scrape failed with status {response.status_code}", "ERROR")
            return False, None

        data = response.json()
        account_used = data.get("account_used", "unknown")

        if not data.get("success"):
            error_msg = data.get('error', 'Unknown error')
            log(f"Scrape returned success=false (account: {account_used})", "ERROR")
            log(f"   Error: {error_msg[:100]}", "ERROR")
            return False, None

        engagement = data.get("data", {}).get("engagement", {})
        likes = engagement.get("like_count", 0)
        comments = engagement.get("comment_count", 0)
        views = (
            engagement.get("views")
            or engagement.get("play_count")
            or engagement.get("view_count")
            or 0
        )

        log(f"Results - Views: {views}, Likes: {likes}, Comments: {comments} (account: {account_used})")

        if (likes > 0 or comments > 0) and views == 0:
            log(f"Got likes/comments but NO VIEWS from {account_used} - cookies may be stale!", "WARNING")
            return False, {"likes": likes, "comments": comments, "views": views, "account": account_used}

        if views > 0:
            log(f"Views working! Got {views} views from {account_used}", "SUCCESS")
            return True, {"likes": likes, "comments": comments, "views": views, "account": account_used}

        log(f"No engagement data returned from {account_used}", "WARNING")
        return False, {"account": account_used}

    except requests.Timeout:
        log("Scrape request timed out", "ERROR")
        return False, None
    except Exception as e:
        log(f"Error checking views: {e}", "ERROR")
        return False, None


def check_views():
    """Test scraping: one request per configured account (round-robin advances each time)."""
    n = _view_probe_count()
    log(f"Testing views with: {TEST_REEL} ({n} probe(s) — one per rotated account)")
    last_ok = True
    last_data = None
    for i in range(n):
        if n > 1:
            log(f"  Account probe {i + 1}/{n}...", "INFO")
        ok, last_data = _check_views_once()
        last_ok = last_ok and ok
        if not ok:
            return False, last_data
    if n > 1:
        log(f"All {n} account view probe(s) passed", "SUCCESS")
    return last_ok, last_data


def refresh_cookies():
    """Attempt to refresh cookies for all accounts with improved error handling"""
    log("Attempting to refresh cookies...", "RESTART")
    
    # First, verify ChromeDriver can be initialized
    try:
        log("Verifying ChromeDriver availability...", "INFO")
        from cookie_auto_refresher import _create_realistic_chrome_driver
        test_driver = _create_realistic_chrome_driver()
        test_driver.quit()
        log("ChromeDriver verified successfully", "SUCCESS")
    except Exception as e:
        error_msg = str(e)
        log(f"ChromeDriver initialization failed: {error_msg}", "ERROR")
        
        # Provide helpful troubleshooting
        if "chromedriver" in error_msg.lower() or "webdriver" in error_msg.lower():
            log("Troubleshooting ChromeDriver:", "WARNING")
            log("  1. Clearing webdriver-manager cache...", "INFO")
            try:
                cache_dir = os.path.expanduser("~/.wdm")
                if os.path.exists(cache_dir):
                    shutil.rmtree(cache_dir, ignore_errors=True)
                    log("  ✅ Cache cleared", "SUCCESS")
                else:
                    log("  ℹ️  No cache to clear", "INFO")
            except Exception as cache_error:
                log(f"  ⚠️  Cache clear failed: {cache_error}", "WARNING")
            
            log("  2. Retrying ChromeDriver initialization...", "INFO")
            try:
                test_driver = _create_realistic_chrome_driver()
                test_driver.quit()
                log("  ✅ ChromeDriver works after cache clear!", "SUCCESS")
            except Exception as retry_error:
                log(f"  ❌ Still failing: {retry_error}", "ERROR")
                log("  💡 Try: brew install chromedriver", "INFO")
                return False
        else:
            return False
    
    # Now attempt cookie refresh
    max_retries = 2
    for attempt in range(max_retries):
        try:
            log(f"Cookie refresh attempt {attempt + 1}/{max_retries}...", "INFO")
            from cookie_auto_refresher import refresh_all_accounts
            results = refresh_all_accounts()
            success_count = sum(1 for v in results.values() if v)
            total_count = len(results)
            
            log(f"Cookie refresh complete: {success_count}/{total_count} accounts", "INFO")
            
            # Log individual account results
            for username, success in results.items():
                status = "✅" if success else "❌"
                log(f"  {status} {username}", "INFO" if success else "WARNING")
            
            if success_count > 0:
                return True
            elif attempt < max_retries - 1:
                log(f"Retrying cookie refresh in 10 seconds...", "WARNING")
                time.sleep(10)
            else:
                log("All cookie refresh attempts failed", "ERROR")
                return False
                
        except Exception as e:
            error_msg = str(e)
            log(f"Cookie refresh attempt {attempt + 1} failed: {error_msg}", "ERROR")
            
            # Check for specific ChromeDriver errors
            if "chromedriver" in error_msg.lower() or "webdriver" in error_msg.lower():
                log("ChromeDriver error detected - may need manual intervention", "ERROR")
                if attempt < max_retries - 1:
                    log("Waiting 15 seconds before retry...", "INFO")
                    time.sleep(15)
                else:
                    return False
            else:
                if attempt < max_retries - 1:
                    time.sleep(10)
                else:
                    return False
    
    return False


def restart_api():
    """Restart the API"""
    global api_process, consecutive_health_failures, consecutive_view_failures, is_first_view_check, consecutive_restart_cycles, monitoring_external_api

    # Check cooldown
    time_since_restart = time.time() - last_restart_time
    if time_since_restart < RESTART_COOLDOWN:
        remaining = int(RESTART_COOLDOWN - time_since_restart)
        log(f"Cooldown active, waiting {remaining}s...", "WARNING")
        return False

    if monitoring_external_api:
        log(
            "Monitoring adopted/external API — skipping automated restart (won't SIGKILL your server). "
            "Fix broken accounts/cookies or restart api.py yourself.",
            "WARNING",
        )
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
    
    # Start new process (never adopt here—we need a fresh server after restart)
    success = start_api(adopt_existing=False)
    if success:
        consecutive_health_failures = 0
        consecutive_view_failures = 0
        error_spike_detected = False  # Reset error spike flag after restart
        is_first_view_check = True  # Reset to first check after restart
        log("API restarted successfully", "SUCCESS")
        log("   ⏳ Waiting 10 seconds for API to fully initialize...", "INFO")
        time.sleep(10)  # Give API time to initialize before next checks
    
    return success


def run_watchdog():
    """Main watchdog loop"""
    global consecutive_health_failures, consecutive_view_failures, last_view_check, last_error_check, error_spike_detected, is_first_view_check, consecutive_restart_cycles
    
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
    if VIEW_CHECK_INTERVAL > 0:
        log(f"Periodic view probe: every {VIEW_CHECK_INTERVAL}s (plus one initial probe)")
    else:
        log("Periodic view probe: disabled (initial probe only after each API start)")
    log(f"Refresh cookies on error spike: {REFRESH_ON_ERROR_SPIKE}")
    log(f"Max failures before restart: {MAX_HEALTH_FAILURES}")
    log("=" * 60)
    log("💡 TIP: Run 'python tunnel_monitor.py' to auto-manage tunnel URL", "INFO")
    log("=" * 60)
    
    # Initialize global variables
    is_first_view_check = True  # Set flag for first check
    
    # Start API
    start_api()
    last_view_check = time.time()
    
    log(f"Initial view check will happen in {INITIAL_VIEW_CHECK_INTERVAL} seconds...", "INFO")
    
    loop_count = 0
    while True:
        try:
            loop_count += 1
            time.sleep(CHECK_INTERVAL)
            
            # Log periodic status (every 5 loops = ~5 minutes)
            if loop_count % 5 == 0:
                log(f"Watchdog running... (loop #{loop_count})", "INFO")
            
            current_time = time.time()

            # 0a. Hard signal — both accounts on cooldown means Instagram is throttling
            # everything. Try a cookie refresh (rate-limited to once per
            # MIN_REFRESH_INTERVAL_SEC); if we just refreshed, do nothing and let the
            # 15-min cooldown elapse naturally — running Selenium login every 2 min
            # gets the account flagged for "automated behavior".
            try:
                resp = requests.get(STATS_URL, timeout=5)
                if resp.status_code == 200:
                    ma = (resp.json() or {}).get("multi_account") or {}
                    if ma.get("all_cooled_down"):
                        log("🚨 All accounts on cooldown", "ERROR")
                        if _try_refresh_cookies("all accounts cooled down"):
                            restart_api()
                            loop_count = 0
                            continue
            except Exception:
                pass

            # 0b. Optional error-spike handling (off by default — spikes are often rate limits, not bad cookies)
            if REFRESH_ON_ERROR_SPIKE and current_time - last_error_check >= error_check_interval:
                last_error_check = current_time
                log("🔍 Checking error rate...", "INFO")
                is_spike, error_rate, recent_errors = check_error_rate()
                
                if is_spike:
                    log(f"🚨 ERROR SPIKE DETECTED: {error_rate:.1f}% error rate!", "ERROR")
                    log(f"   Total errors detected: {len(recent_errors)}", "ERROR")
                    if recent_errors:
                        log(f"   Showing last 5 errors:", "ERROR")
                        for err in recent_errors[-5:]:  # Show last 5 errors
                            error_msg = err.get('error', 'Unknown')
                            timestamp = err.get('timestamp', '')[:19] if err.get('timestamp') else ''
                            log(f"   [{timestamp}] {error_msg[:150]}", "ERROR")
                    
                    log("⏸️  PAUSING: Waiting 60 seconds before retry...", "WARNING")
                    time.sleep(60)
                    
                    log("🔍 Re-checking error rate after wait...", "INFO")
                    is_spike_after_wait, error_rate_after, _ = check_error_rate()
                    if is_spike_after_wait and error_rate_after > 30.0:
                        log(f"   🔄 Error spike persists ({error_rate_after:.1f}%)", "RESTART")
                        if _try_refresh_cookies(f"error spike {error_rate_after:.1f}%"):
                            restart_api()
                            error_spike_detected = False
                            loop_count = 0
                            continue
                    else:
                        log(f"   ✅ Error rate improved to {error_rate_after:.1f}%", "SUCCESS")
                elif error_rate > 0:
                    log(f"   Error rate: {error_rate:.1f}% ({len(recent_errors)} recent errors)", "INFO")
                else:
                    log(f"   ✅ No errors detected (0%)", "SUCCESS")
            
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
            
            # 3. View probe: once shortly after startup/restart; optional periodic if VIEW_CHECK_INTERVAL > 0
            skip_view_probes = VIEW_CHECK_INTERVAL == 0 and not is_first_view_check
            if not skip_view_probes:
                current_check_interval = (
                    INITIAL_VIEW_CHECK_INTERVAL if is_first_view_check else VIEW_CHECK_INTERVAL
                )
                time_since_view_check = time.time() - last_view_check
                if time_since_view_check >= current_check_interval:
                    last_view_check = time.time()

                    was_first_check = is_first_view_check

                    if was_first_check:
                        log(f"🔍 First view check (after {INITIAL_VIEW_CHECK_INTERVAL}s)...", "INFO")
                        is_first_view_check = False
                    else:
                        log(f"🔍 Periodic view check (every {VIEW_CHECK_INTERVAL}s)...", "INFO")

                    views_ok, data = check_views()

                    if views_ok:
                        consecutive_view_failures = 0
                        if was_first_check:
                            log(
                                f"View check passed ✓ (first check, cycle counter: {consecutive_restart_cycles})",
                                "SUCCESS",
                            )
                        else:
                            if consecutive_restart_cycles > 0:
                                log(
                                    f"✅ Periodic view check PASSED - resetting restart cycle counter (was {consecutive_restart_cycles})",
                                    "SUCCESS",
                                )
                                consecutive_restart_cycles = 0
                            else:
                                log("View check passed ✓", "SUCCESS")
                    else:
                        consecutive_view_failures += 1
                        log(f"View check failed ({consecutive_view_failures}/1)", "WARNING")

                        if data and data.get("likes", 0) > 0 and data.get("views", 0) == 0:
                            log("🍪 Cookies appear stale (got likes but no views)", "WARNING")
                            _try_refresh_cookies("stale cookies (likes ok, views 0)")
                            restart_api()
                            consecutive_view_failures = 0
                            consecutive_restart_cycles = 0
                        elif consecutive_view_failures >= 1:
                            if not was_first_check:
                                consecutive_restart_cycles += 1
                                log(
                                    f"⚠️ Periodic view check failed (cycle {consecutive_restart_cycles}/{REFRESH_AFTER_CYCLES})",
                                    "WARNING",
                                )
                                if consecutive_restart_cycles >= REFRESH_AFTER_CYCLES:
                                    log(
                                        f"🍪 Pattern: {consecutive_restart_cycles} cycles of 'first OK, periodic fails'",
                                        "ERROR",
                                    )
                                    _try_refresh_cookies("repeated view-probe failures")
                                    consecutive_restart_cycles = 0
                            else:
                                log("❌ First view check failed - restarting API", "ERROR")

                            restart_api()
                            consecutive_view_failures = 0
                            loop_count = 0
                            continue
            
        except KeyboardInterrupt:
            log("Watchdog stopped by user")
            log("API server left running", "INFO")
            break
        except Exception as e:
            log(f"Watchdog error: {e}", "ERROR")
            time.sleep(10)


def signal_handler(sig, frame):
    """Handle Ctrl+C — exit watchdog only; do not stop api.py."""
    print("\n")
    log("Shutting down watchdog...")
    log("API server left running", "INFO")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    run_watchdog()
