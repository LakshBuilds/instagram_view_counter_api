import re
from scraper import scrape_instagram_reel, extract_shortcode_from_url
import time
import sys


def extract_urls_from_file(filename):
    """Extract Instagram URLs from a text file"""
    urls = []
    
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find all Instagram URLs in the file using regex
    url_pattern = r'https://www\.instagram\.com/[^\s|\)]+'
    matches = re.findall(url_pattern, content)
    
    for url in matches:
        url = url.rstrip('/').rstrip(')')  # Clean up URL
        if url not in urls:  # Avoid duplicates
            urls.append(url)
    
    return urls


def get_already_processed_shortcodes():
    """Get list of shortcodes that have already been processed"""
    import glob
    import os
    processed = set()
    json_files = glob.glob('*_data.json')
    for filename in json_files:
        # Extract shortcode from filename (format: SHORTCODE_data.json)
        shortcode = filename.replace('_data.json', '')
        processed.add(shortcode)
    return processed


def batch_scrape(urls, limit=10, skip_processed=True):
    """Scrape multiple Instagram Reels"""
    print("="*60)
    print("BATCH INSTAGRAM REEL SCRAPER")
    print("="*60)
    
    # Check for already processed files
    if skip_processed:
        processed = get_already_processed_shortcodes()
        if processed:
            print(f"\nFound {len(processed)} already processed reels. Will skip them.")
    
    print(f"\nProcessing {min(limit, len(urls))} reels...\n")
    
    # Get session once for all requests
    from scraper import get_session_cookies, extract_shortcode_from_url
    session, _ = get_session_cookies()
    print()  # Empty line after cookie message
    
    results = {
        "success": [],
        "failed": []
    }
    
    processed_count = 0
    skipped_count = 0
    
    for i, url in enumerate(urls[:limit], 1):
        # Check if already processed
        if skip_processed:
            try:
                shortcode = extract_shortcode_from_url(url)
                if shortcode in processed:
                    print(f"\n[{i}/{min(limit, len(urls))}] Skipping {url} (already processed)")
                    skipped_count += 1
                    continue
            except:
                pass  # Continue if URL parsing fails
        
        print(f"\n[{i}/{min(limit, len(urls))}] Processing: {url}")
        print("-" * 60)
        
        try:
            result = scrape_instagram_reel(url, session=session)
            
            if result.get('success'):
                print(f"✅ SUCCESS - Saved to: {result['filename']}")
                results["success"].append({
                    "url": url,
                    "shortcode": result.get('shortcode'),
                    "filename": result.get('filename')
                })
            else:
                error = result.get('error', 'Unknown error')
                status_code = result.get('status_code', 0)
                print(f"❌ FAILED: {error}")
                
                # Handle rate limiting with longer wait
                if status_code == 429 or 'rate limit' in error.lower():
                    print("⚠️ Rate limited detected. Waiting 60 seconds...")
                    time.sleep(60)
                    # Try once more after waiting
                    print("Retrying after rate limit wait...")
                    result = scrape_instagram_reel(url, session=session)
                    if result.get('success'):
                        print(f"✅ SUCCESS after retry - Saved to: {result['filename']}")
                        results["success"].append({
                            "url": url,
                            "shortcode": result.get('shortcode'),
                            "filename": result.get('filename')
                        })
                    else:
                        results["failed"].append({
                            "url": url,
                            "error": error
                        })
                else:
                    results["failed"].append({
                        "url": url,
                        "error": error
                    })
        
        except KeyboardInterrupt:
            print("\n\n⚠️ Process interrupted by user")
            print(f"Processed {i-1} out of {min(limit, len(urls))} reels")
            print("You can resume by running the scraper again - it will skip already processed files")
            break
        except Exception as e:
            print(f"❌ EXCEPTION: {str(e)}")
            results["failed"].append({
                "url": url,
                "error": str(e)
            })
            # Continue processing even if one fails
            continue
        
        # Add delay between requests to be respectful
        if i < min(limit, len(urls)):
            print("Waiting 3 seconds before next request...")
            time.sleep(3)
    
    # Print summary
    print("\n" + "="*60)
    print("BATCH PROCESSING SUMMARY")
    print("="*60)
    print(f"\n✅ Successful: {len(results['success'])}")
    print(f"❌ Failed: {len(results['failed'])}")
    if skip_processed and skipped_count > 0:
        print(f"⏭️  Skipped (already processed): {skipped_count}")
    
    if results['success']:
        print("\n✅ Successfully scraped:")
        for item in results['success']:
            print(f"   - {item['shortcode']}: {item['filename']}")
    
    if results['failed']:
        print("\n❌ Failed URLs:")
        for item in results['failed']:
            print(f"   - {item['url']}: {item['error']}")
    
    return results


if __name__ == "__main__":
    import sys
    
    filename = "reels.txt"
    limit = 10
    
    # Allow custom limit from command line
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            print(f"Invalid limit: {sys.argv[1]}. Using default: 10")
    
    # Extract URLs from file
    print(f"Reading URLs from: {filename}")
    urls = extract_urls_from_file(filename)
    
    if not urls:
        print("❌ No URLs found in file!")
        sys.exit(1)
    
    print(f"Found {len(urls)} URLs in file")
    print(f"Will process first {min(limit, len(urls))} URLs\n")
    
    # Process URLs
    batch_scrape(urls, limit=limit)

