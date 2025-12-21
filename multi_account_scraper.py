"""
Multi-Account Instagram Scraper
Manages multiple Instagram accounts for parallel scraping with rate limiting
Uses SMART DELAYS to avoid detection (random, human-like timing)
"""
import time
import random
import threading
from datetime import datetime
from typing import List, Dict, Callable, Optional, Tuple
from dataclasses import dataclass, field
import os
from scraper import scrape_instagram_reel, get_session_cookies


class SmartDelay:
    """Human-like delay system to avoid Instagram detection"""
    
    def __init__(self, 
                 min_delay: float = 1.5,
                 max_delay: float = 4.0,
                 burst_threshold: int = 5,
                 long_pause_chance: float = 0.1,
                 long_pause_range: Tuple[float, float] = (8.0, 15.0)):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.burst_threshold = burst_threshold
        self.long_pause_chance = long_pause_chance
        self.long_pause_range = long_pause_range
        self.request_times = []
        self.total_requests = 0
        self.delays_used = []
        
    def get_delay(self) -> Tuple[float, str]:
        """Get a human-like random delay"""
        self.total_requests += 1
        now = time.time()
        
        # Clean old request times (keep last 60 seconds)
        self.request_times = [t for t in self.request_times if now - t < 60]
        self.request_times.append(now)
        
        # Check for burst
        recent_requests = len(self.request_times)
        burst_penalty = 0
        
        if recent_requests > self.burst_threshold:
            burst_penalty = (recent_requests - self.burst_threshold) * 0.5
            
        # Random chance of long pause
        if random.random() < self.long_pause_chance:
            delay = random.uniform(*self.long_pause_range)
            delay_type = "long_pause"
        else:
            # Triangular distribution - more natural
            base_delay = random.triangular(self.min_delay, self.max_delay)
            jitter = random.uniform(-0.3, 0.3)
            delay = base_delay + jitter + burst_penalty
            delay_type = "normal" if burst_penalty == 0 else "burst_adjusted"
        
        delay = max(self.min_delay, delay)
        self.delays_used.append(delay)
        
        return delay, delay_type
    
    def wait(self, verbose: bool = True) -> float:
        """Wait for a human-like delay"""
        delay, delay_type = self.get_delay()
        
        if verbose:
            if delay_type == "long_pause":
                print(f"   ⏳ Taking a break... ({delay:.1f}s)")
            elif delay_type == "burst_adjusted":
                print(f"   ⏳ Slowing down... ({delay:.1f}s)")
            else:
                print(f"   ⏳ Waiting {delay:.1f}s...")
        
        time.sleep(delay)
        return delay
    
    def get_stats(self) -> dict:
        """Get delay statistics"""
        if not self.delays_used:
            return {"total_requests": 0}
        return {
            "total_requests": self.total_requests,
            "avg_delay": sum(self.delays_used) / len(self.delays_used),
            "min_delay_used": min(self.delays_used),
            "max_delay_used": max(self.delays_used),
        }

@dataclass
class Account:
    """Represents an Instagram account for scraping"""
    username: str
    password: str
    session: Optional[object] = None
    csrf_token: str = ""
    is_active: bool = False
    request_count: int = 0
    last_request_time: Optional[datetime] = None
    smart_delay: Optional[SmartDelay] = field(default=None, repr=False)
    
    def __post_init__(self):
        """Initialize account after creation"""
        self.cookies_file = f"cookies_{self.username}.txt"
        # Each account gets its own smart delay instance
        self.smart_delay = SmartDelay(
            min_delay=1.5,
            max_delay=4.0,
            burst_threshold=5,
            long_pause_chance=0.1,
            long_pause_range=(8.0, 15.0)
        )

class MultiAccountScraper:
    """
    Multi-account Instagram scraper with parallel execution and rate limiting
    
    EXACT BEHAVIOR:
    - acc1 → 20 requests (parallel)
    - acc2 → 20 requests (parallel) 
    - acc3 → 20 requests (parallel)
    - ALL 3 ACCOUNTS START SIMULTANEOUSLY
    - GLOBAL WAIT 5 minutes
    - REPEAT
    """
    
    def __init__(self, accounts: List[Dict], requests_per_cycle: int = 20, 
                 delay_between_requests: float = 2.0, global_wait_minutes: float = 5.0,
                 use_smart_delay: bool = True,
                 min_delay: float = 1.5, max_delay: float = 4.0):
        """
        Initialize multi-account scraper
        
        Args:
            accounts: List of account dictionaries with username/password
            requests_per_cycle: Number of requests per account per cycle
            delay_between_requests: Base delay (used if smart_delay is disabled)
            global_wait_minutes: Minutes to wait between cycles
            use_smart_delay: Use random human-like delays (recommended)
            min_delay: Minimum delay for smart delay
            max_delay: Maximum delay for smart delay
        """
        self.accounts = [Account(**acc) for acc in accounts]
        self.requests_per_cycle = requests_per_cycle
        self.delay_between_requests = delay_between_requests
        self.global_wait_minutes = global_wait_minutes
        self.use_smart_delay = use_smart_delay
        
        # Configure smart delay for each account
        if use_smart_delay:
            for acc in self.accounts:
                acc.smart_delay = SmartDelay(
                    min_delay=min_delay,
                    max_delay=max_delay,
                    burst_threshold=5,
                    long_pause_chance=0.1,
                    long_pause_range=(8.0, 15.0)
                )
        
        # Statistics
        self.total_requests = 0
        self.current_cycle = 0
        self.start_time = datetime.now()
        
        print(f"🔧 Initialized scraper with {len(self.accounts)} accounts")
        print(f"   Requests per cycle: {requests_per_cycle}")
        if use_smart_delay:
            print(f"   Smart delay: {min_delay}s - {max_delay}s (random, human-like)")
        else:
            print(f"   Fixed delay: {delay_between_requests}s")
        print(f"   Global wait: {global_wait_minutes}min")
    
    def setup_account_session(self, account: Account) -> bool:
        """Setup session for a specific account"""
        try:
            # Set environment variables for this account
            os.environ['INSTAGRAM_USERNAME'] = account.username
            os.environ['INSTAGRAM_PASSWORD'] = account.password
            os.environ['INSTAGRAM_COOKIES_FILE'] = account.cookies_file
            
            # Get session and CSRF token
            session, csrf_token = get_session_cookies()
            
            if session:
                account.session = session
                account.csrf_token = csrf_token
                account.is_active = True
                print(f"✅ Account {account.username} session ready")
                return True
            else:
                print(f"❌ Account {account.username} session failed")
                account.is_active = False
                return False
                
        except Exception as e:
            print(f"❌ Account {account.username} setup error: {e}")
            account.is_active = False
            return False
    
    def scrape_account_batch(self, account: Account, urls: List[str]) -> List[Dict]:
        """
        Scrape a batch of URLs for a specific account with delays
        
        Args:
            account: Account to use for scraping
            urls: List of URLs to scrape
            
        Returns:
            List of scraping results
        """
        if not account.is_active:
            print(f"⚠️ Account {account.username} is not active, skipping")
            return []
        
        results = []
        account_urls = urls[:self.requests_per_cycle]  # Limit to requests_per_cycle
        
        print(f"🔍 Account {account.username} starting {len(account_urls)} requests...")
        
        for i, url in enumerate(account_urls, 1):
            try:
                # Record request time
                account.last_request_time = datetime.now()
                
                # Scrape the URL
                print(f"   {account.username} [{i}/{len(account_urls)}]: {url}")
                result = scrape_instagram_reel(url, session=account.session, save_json=False)
                
                # Add account info to result
                result['account'] = account.username
                result['request_number'] = i
                result['timestamp'] = account.last_request_time.isoformat()
                
                results.append(result)
                account.request_count += 1
                self.total_requests += 1
                
                # Log result
                if result.get('success'):
                    shortcode = result.get('shortcode', 'N/A')
                    print(f"   ✅ {account.username} [{i}/{len(account_urls)}]: {shortcode}")
                else:
                    error = result.get('error', 'Unknown error')
                    print(f"   ❌ {account.username} [{i}/{len(account_urls)}]: {error}")
                
                # Delay between requests (except for last request)
                if i < len(account_urls):
                    if self.use_smart_delay and account.smart_delay:
                        # Use smart random delay
                        account.smart_delay.wait(verbose=True)
                    else:
                        # Use fixed delay
                        print(f"   ⏳ {account.username} waiting {self.delay_between_requests}s...")
                        time.sleep(self.delay_between_requests)
                    
            except Exception as e:
                print(f"   ❌ {account.username} [{i}/{len(account_urls)}]: Exception - {e}")
                results.append({
                    'success': False,
                    'error': str(e),
                    'account': account.username,
                    'request_number': i,
                    'timestamp': datetime.now().isoformat()
                })
        
        print(f"✅ Account {account.username} completed {len(results)} requests")
        return results
    
    def scrape_batch_parallel(self, urls: List[str]) -> List[Dict]:
        """
        Scrape URLs using all active accounts in parallel
        
        EXACT BEHAVIOR:
        - All accounts start simultaneously
        - Each account processes its share of URLs with delays
        - Returns combined results from all accounts
        
        Args:
            urls: List of URLs to scrape
            
        Returns:
            Combined results from all accounts
        """
        active_accounts = [acc for acc in self.accounts if acc.is_active]
        
        if not active_accounts:
            print("❌ No active accounts available")
            return []
        
        print(f"\n🚀 PARALLEL EXECUTION - {len(active_accounts)} accounts")
        print(f"📋 Total URLs: {len(urls)}")
        print(f"🎯 URLs per account: {self.requests_per_cycle}")
        
        # Distribute URLs among accounts
        account_url_batches = []
        for i, account in enumerate(active_accounts):
            # Each account gets requests_per_cycle URLs
            start_idx = i * self.requests_per_cycle
            end_idx = start_idx + self.requests_per_cycle
            account_urls = urls[start_idx:end_idx]
            account_url_batches.append((account, account_urls))
            
            print(f"   {account.username}: {len(account_urls)} URLs (indices {start_idx}-{end_idx-1})")
        
        # Start all accounts simultaneously using threads
        threads = []
        results_by_account = {}
        
        def account_worker(account, account_urls):
            """Worker function for each account thread"""
            results_by_account[account.username] = self.scrape_account_batch(account, account_urls)
        
        print(f"\n⚡ ALL {len(active_accounts)} ACCOUNTS STARTING SIMULTANEOUSLY...")
        start_time = time.time()
        
        # Create and start threads for all accounts
        for account, account_urls in account_url_batches:
            thread = threading.Thread(
                target=account_worker,
                args=(account, account_urls),
                name=f"Account-{account.username}"
            )
            threads.append(thread)
            thread.start()
            print(f"   🚀 Started thread for {account.username}")
        
        # Wait for all threads to complete
        print(f"\n⏳ Waiting for all accounts to complete...")
        for thread in threads:
            thread.join()
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Combine results from all accounts
        all_results = []
        for account_name, account_results in results_by_account.items():
            all_results.extend(account_results)
        
        print(f"\n✅ PARALLEL EXECUTION COMPLETE")
        print(f"   Duration: {duration:.1f}s ({duration/60:.1f}min)")
        print(f"   Total results: {len(all_results)}")
        print(f"   Results per account:")
        
        for account_name, account_results in results_by_account.items():
            successful = len([r for r in account_results if r.get('success')])
            print(f"     {account_name}: {successful}/{len(account_results)} successful")
        
        return all_results
    
    def run_continuous_cycle(self, url_generator: Callable, max_cycles: Optional[int] = None):
        """
        Run continuous cycles with the exact behavior requested
        
        BEHAVIOR:
        - acc1 → 20 requests (parallel)
        - acc2 → 20 requests (parallel) 
        - acc3 → 20 requests (parallel)
        - ALL 3 ACCOUNTS START SIMULTANEOUSLY
        - GLOBAL WAIT 5 minutes
        - REPEAT
        
        Args:
            url_generator: Function that returns list of URLs for each cycle
            max_cycles: Maximum number of cycles (None for infinite)
        """
        print(f"\n🔄 STARTING CONTINUOUS CYCLES")
        print(f"🎯 Max cycles: {'Infinite' if max_cycles is None else max_cycles}")
        print(f"⏱️ Global wait between cycles: {self.global_wait_minutes} minutes")
        
        cycle = 1
        
        try:
            while max_cycles is None or cycle <= max_cycles:
                self.current_cycle = cycle
                
                print(f"\n" + "="*60)
                print(f"🔄 CYCLE {cycle}")
                print("="*60)
                
                # Get URLs for this cycle
                urls = url_generator()
                if not urls:
                    print("❌ No URLs provided by generator")
                    break
                
                print(f"📋 Cycle {cycle}: Processing {len(urls)} URLs")
                
                # Execute parallel batch
                cycle_start = time.time()
                results = self.scrape_batch_parallel(urls)
                cycle_end = time.time()
                
                # Cycle statistics
                cycle_duration = cycle_end - cycle_start
                successful = len([r for r in results if r.get('success')])
                failed = len(results) - successful
                
                print(f"\n📊 CYCLE {cycle} RESULTS:")
                print(f"   ✅ Successful: {successful}")
                print(f"   ❌ Failed: {failed}")
                print(f"   📈 Success Rate: {(successful/len(results)*100):.1f}%")
                print(f"   ⏱️ Duration: {cycle_duration:.1f}s ({cycle_duration/60:.1f}min)")
                
                # Check if we should continue
                if max_cycles is not None and cycle >= max_cycles:
                    print(f"\n✅ Completed {max_cycles} cycles as requested")
                    break
                
                # Global wait between cycles
                print(f"\n⏳ GLOBAL WAIT: {self.global_wait_minutes} minutes before next cycle...")
                print(f"   Next cycle will start at: {datetime.now().strftime('%H:%M:%S')}")
                
                # Wait with progress updates
                wait_seconds = self.global_wait_minutes * 60
                for remaining in range(int(wait_seconds), 0, -30):  # Update every 30 seconds
                    if remaining > 30:
                        print(f"   ⏳ {remaining//60}m {remaining%60}s remaining...")
                        time.sleep(30)
                    else:
                        print(f"   ⏳ {remaining}s remaining...")
                        time.sleep(remaining)
                        break
                
                cycle += 1
                
        except KeyboardInterrupt:
            print(f"\n\n🛑 Stopped by user (Ctrl+C)")
        except Exception as e:
            print(f"\n❌ Error in continuous cycle: {e}")
            import traceback
            traceback.print_exc()
        
        # Final statistics
        self.print_final_stats()
    
    def get_stats(self) -> Dict:
        """Get current statistics"""
        runtime = datetime.now() - self.start_time
        runtime_minutes = runtime.total_seconds() / 60
        
        return {
            'total_requests': self.total_requests,
            'current_cycle': self.current_cycle,
            'total_time_minutes': runtime_minutes,
            'average_requests_per_minute': self.total_requests / runtime_minutes if runtime_minutes > 0 else 0,
            'accounts': [
                {
                    'username': acc.username,
                    'is_active': acc.is_active,
                    'request_count': acc.request_count,
                    'last_request': acc.last_request_time.isoformat() if acc.last_request_time else None
                }
                for acc in self.accounts
            ]
        }
    
    def print_final_stats(self):
        """Print final statistics"""
        stats = self.get_stats()
        
        print(f"\n" + "="*60)
        print(f"📊 FINAL STATISTICS")
        print("="*60)
        print(f"🕐 Total Runtime: {stats['total_time_minutes']:.1f} minutes")
        print(f"🔄 Total Cycles: {stats['current_cycle']}")
        print(f"📈 Total Requests: {stats['total_requests']}")
        print(f"⚡ Average Rate: {stats['average_requests_per_minute']:.1f} requests/minute")
        
        print(f"\n👥 ACCOUNT BREAKDOWN:")
        for acc_stat in stats['accounts']:
            status = "✅ Active" if acc_stat['is_active'] else "❌ Inactive"
            print(f"   {acc_stat['username']}: {acc_stat['request_count']} requests - {status}")
        
        print("="*60)