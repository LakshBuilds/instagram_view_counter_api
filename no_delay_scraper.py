"""
NO DELAY SCRAPER - MAXIMUM SPEED
⚡ 60 reels in ~30 seconds instead of 5 minutes
⚠️ WARNING: High risk of account ban
"""
import time
from multi_account_scraper import MultiAccountScraper
from multi_account_config import BALANCED_CONFIG

def load_urls():
    """Load URLs from real_urls.txt"""
    with open('real_urls.txt', 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip()]
    return urls

def main():
    print("⚡ PARALLEL SCRAPER - 1 SECOND DELAY")
    print("="*60)
    print("✅ 60 reels: 20 per account (3 accounts parallel)")
    print("✅ 1 second delay between requests")
    print("✅ 5 minutes global wait between cycles")
    print("="*60)
    
    # Initialize scraper with 1 SECOND DELAY
    scraper = MultiAccountScraper(
        accounts=BALANCED_CONFIG["accounts"],
        requests_per_cycle=20,      # 20 reels per account
        delay_between_requests=1.0, # 1 second between requests (as requested)
        global_wait_minutes=5       # 5 minutes global wait
    )
    
    # Setup accounts
    print("\n🔧 Setting up accounts...")
    for account in scraper.accounts:
        success = scraper.setup_account_session(account)
        print(f"   {account.username}: {'✅ Ready' if success else '❌ Failed'}")
    
    active_count = len([acc for acc in scraper.accounts if acc.is_active])
    if active_count == 0:
        print("❌ No accounts active!")
        return
    
    # Load URLs
    urls = load_urls()
    print(f"\n📋 Loaded {len(urls)} reels")
    print(f"⚡ Expected time: ~20 seconds for 60 reels (20 requests × 1s delay per account)")
    
    def url_generator():
        return urls
    
    print(f"\n🚀 STARTING MAXIMUM SPEED EXECUTION...")
    print(f"⚠️  Risk: Accounts may get rate limited/banned")
    print("="*60)
    
    # Run cycles
    scraper.run_continuous_cycle(url_generator, max_cycles=None)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Stopped by user!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        input("Press Enter to exit...")