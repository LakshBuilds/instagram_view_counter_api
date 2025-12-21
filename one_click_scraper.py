"""
ONE-CLICK PARALLEL SCRAPER
Jab aap yeh run karo:
- 60 reels ko 3 accounts mein divide (20 each)
- Teeno accounts ek saath start (parallel)
- Har account 15s delay ke saath apni reels process kare
- 60 reels complete → 5 minute wait → repeat
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
    print("🎬 ONE-CLICK PARALLEL SCRAPER")
    print("="*60)
    print("✅ 60 reels → 3 accounts (20 each)")
    print("✅ Teeno accounts ek saath start")
    print("✅ Har account 15s delay")
    print("✅ 60 complete → 5min wait → repeat")
    print("="*60)
    
    # Initialize scraper
    scraper = MultiAccountScraper(
        accounts=BALANCED_CONFIG["accounts"],
        requests_per_cycle=20,      # 20 reels per account
        delay_between_requests=15,  # 15 seconds delay
        global_wait_minutes=5       # 5 minutes global wait
    )
    
    # Setup accounts
    print("\n🔧 Setting up accounts...")
    for account in scraper.accounts:
        success = scraper.setup_account_session(account)
        print(f"   {account.username}: {'✅ Ready' if success else '❌ Failed'}")
    
    active_count = len([acc for acc in scraper.accounts if acc.is_active])
    if active_count == 0:
        print("❌ No accounts active. Check credentials!")
        return
    
    # Load URLs
    urls = load_urls()
    print(f"\n📋 Loaded {len(urls)} reels")
    print(f"🎯 Distribution: {len(urls)//3} reels per account")
    
    def url_generator():
        return urls
    
    print(f"\n🚀 STARTING PARALLEL EXECUTION...")
    print(f"Press Ctrl+C to stop anytime")
    print("="*60)
    
    # Run infinite cycles (until user stops)
    scraper.run_continuous_cycle(url_generator, max_cycles=None)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Stopped by user!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        input("Press Enter to exit...")