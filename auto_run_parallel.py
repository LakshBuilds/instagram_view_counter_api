"""
Automated Parallel Instagram Scraper
Runs with EXACT behavior as requested:
- acc1 → 20 requests (parallel)
- acc2 → 20 requests (parallel) 
- acc3 → 20 requests (parallel)
- ALL 3 ACCOUNTS START SIMULTANEOUSLY
- GLOBAL WAIT 5 minutes
- REPEAT
"""
import time
from multi_account_scraper import MultiAccountScraper
from multi_account_config import BALANCED_CONFIG, PROXY_LIST
from proxy_config import add_proxies, PROXY_CONFIG

def load_urls_from_file(filename):
    """Load URLs from file"""
    with open(filename, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip()]
    return urls

def main():
    print("🎬 AUTOMATED PARALLEL INSTAGRAM SCRAPER")
    print("="*60)
    print("EXACT BEHAVIOR:")
    print("  - 3 accounts run in parallel")
    print("  - Each account: 20 requests with 15s delays")
    print("  - Global wait: 5 minutes between cycles")
    print("  - All accounts start simultaneously")
    print("="*60)
    
    # Load proxies if configured
    if PROXY_LIST:
        add_proxies(PROXY_LIST)
        print(f"🔄 Proxy rotation: ENABLED ({len(PROXY_LIST)} proxies)")
    else:
        print("🔄 Proxy rotation: DISABLED (add proxies to multi_account_config.py)")
    
    # Initialize scraper
    print("\n🔧 Initializing scraper...")
    scraper = MultiAccountScraper(
        accounts=BALANCED_CONFIG["accounts"],
        requests_per_cycle=20,      # 20 requests per account
        delay_between_requests=15,  # 15 seconds between requests
        global_wait_minutes=5       # 5 minutes global wait
    )
    
    # Setup accounts
    print("🔧 Setting up accounts...")
    for account in scraper.accounts:
        success = scraper.setup_account_session(account)
        print(f"   {account.username}: {'✅ Ready' if success else '❌ Failed'}")
    
    active_count = len([acc for acc in scraper.accounts if acc.is_active])
    print(f"✅ {active_count}/{len(scraper.accounts)} accounts ready\n")
    
    if active_count == 0:
        print("❌ No accounts are active. Exiting.")
        return
    
    # Load URLs
    print("📋 Loading URLs from real_urls.txt...")
    urls = load_urls_from_file('real_urls.txt')
    print(f"✅ Loaded {len(urls)} URLs\n")
    
    # Define URL generator for continuous cycles
    def url_generator():
        return urls
    
    # Default to 3 cycles for automated runs
    max_cycles = 3
    print(f"\n🚀 Starting {max_cycles} cycles...")
    
    if max_cycles:
        print(f"\n🚀 Starting {max_cycles} cycles...")
    else:
        print(f"\n🚀 Starting infinite cycles (press Ctrl+C to stop)...")
    
    print("\n" + "="*60)
    print("EXECUTION STARTING NOW")
    print("="*60)
    
    # Run continuous cycles
    scraper.run_continuous_cycle(url_generator, max_cycles)
    
    # Final stats
    print("\n" + "="*60)
    print("EXECUTION COMPLETE")
    print("="*60)
    
    stats = scraper.get_stats()
    print(f"\n📊 FINAL STATISTICS:")
    print(f"   Total Requests: {stats['total_requests']}")
    print(f"   Total Cycles: {stats['current_cycle']}")
    print(f"   Runtime: {stats['total_time_minutes']:.1f} minutes")
    print(f"   Average Rate: {stats['average_requests_per_minute']:.1f} req/min")
    
    for acc_stat in stats['accounts']:
        print(f"   {acc_stat['username']}: {acc_stat['request_count']} requests")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Stopped by user (Ctrl+C)")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()