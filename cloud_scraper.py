"""
Cloud-compatible Instagram Scraper
Runs without Selenium - uses pre-saved cookies only
Designed for GitHub Actions / Cloud deployment
"""
import os
import sys
import time
import json
import random
from datetime import datetime

# Disable auto cookie refresh in cloud (no browser)
os.environ['AUTO_COOKIE_REFRESH'] = '0'

from multi_account_scraper import MultiAccountScraper
from multi_account_config import BALANCED_CONFIG


def load_urls_from_file(filename):
    """Load URLs from file"""
    if not os.path.exists(filename):
        print(f"❌ URL file not found: {filename}")
        return []
    with open(filename, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    return urls


def check_cookies_exist():
    """Check if cookie files exist"""
    accounts = BALANCED_CONFIG["accounts"]
    ready = []
    missing = []
    
    for acc in accounts:
        cookie_file = f"cookies_{acc['username']}.txt"
        if os.path.exists(cookie_file):
            ready.append(acc['username'])
        else:
            missing.append(acc['username'])
    
    return ready, missing


def save_results(results, cycle_num):
    """Save scraping results to JSON file"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"results_cycle{cycle_num}_{timestamp}.json"
    
    # Extract key data
    output = []
    for r in results:
        if r.get('success'):
            extracted = r.get('extracted', {})
            output.append({
                'shortcode': r.get('shortcode'),
                'account': r.get('account'),
                'timestamp': r.get('timestamp'),
                'views': extracted.get('engagement', {}).get('play_count'),
                'likes': extracted.get('engagement', {}).get('like_count'),
                'comments': extracted.get('engagement', {}).get('comment_count'),
                'username': extracted.get('user', {}).get('username'),
            })
        else:
            output.append({
                'shortcode': r.get('shortcode', 'unknown'),
                'account': r.get('account'),
                'error': r.get('error'),
                'success': False
            })
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"📁 Results saved to: {filename}")
    return filename


def main():
    print("☁️ CLOUD INSTAGRAM SCRAPER")
    print("="*60)
    print(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # Check cookies
    ready, missing = check_cookies_exist()
    print(f"\n📋 Account Status:")
    for acc in ready:
        print(f"   ✅ {acc} - Ready")
    for acc in missing:
        print(f"   ❌ {acc} - Missing cookies")
    
    if not ready:
        print("\n❌ No accounts with cookies found. Exiting.")
        sys.exit(1)
    
    # Filter config to only include accounts with cookies
    active_accounts = [
        acc for acc in BALANCED_CONFIG["accounts"] 
        if acc['username'] in ready
    ]
    
    print(f"\n✅ {len(active_accounts)} accounts ready for scraping")
    
    # Load URLs
    urls = load_urls_from_file('real_urls.txt')
    if not urls:
        print("❌ No URLs found in real_urls.txt")
        sys.exit(1)
    print(f"📋 Loaded {len(urls)} URLs")
    
    # Initialize scraper
    scraper = MultiAccountScraper(
        accounts=active_accounts,
        requests_per_cycle=20,
        delay_between_requests=15,
        global_wait_minutes=5,
        use_smart_delay=True,
        min_delay=2.0,
        max_delay=5.0
    )
    
    # Setup sessions
    print("\n🔧 Setting up account sessions...")
    for account in scraper.accounts:
        success = scraper.setup_account_session(account)
        status = "✅ Ready" if success else "❌ Failed"
        print(f"   {account.username}: {status}")
    
    active_count = len([acc for acc in scraper.accounts if acc.is_active])
    if active_count == 0:
        print("\n❌ No active accounts. Cookies may be expired.")
        print("💡 Re-run login locally to refresh cookies.")
        sys.exit(1)
    
    # Get cycles from env or default to 1
    max_cycles = int(os.getenv('SCRAPER_CYCLES', '1'))
    print(f"\n🚀 Running {max_cycles} cycle(s)...")
    
    # Run scraping
    def url_generator():
        return urls
    
    all_results = []
    
    for cycle in range(1, max_cycles + 1):
        print(f"\n{'='*60}")
        print(f"🔄 CYCLE {cycle}/{max_cycles}")
        print("="*60)
        
        results = scraper.scrape_batch_parallel(urls)
        all_results.extend(results)
        
        # Save results after each cycle
        save_results(results, cycle)
        
        # Stats
        successful = len([r for r in results if r.get('success')])
        print(f"\n📊 Cycle {cycle} Results: {successful}/{len(results)} successful")
        
        # Wait between cycles (except last)
        if cycle < max_cycles:
            wait_mins = scraper.global_wait_minutes
            print(f"\n⏳ Waiting {wait_mins} minutes before next cycle...")
            time.sleep(wait_mins * 60)
    
    # Final summary
    print("\n" + "="*60)
    print("📊 FINAL SUMMARY")
    print("="*60)
    total_success = len([r for r in all_results if r.get('success')])
    print(f"✅ Total Successful: {total_success}/{len(all_results)}")
    print(f"📈 Success Rate: {(total_success/len(all_results)*100):.1f}%")
    print(f"🕐 Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Stopped")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
