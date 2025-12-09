import requests
import json
import re
import time
import sys
import os
import io
from urllib.parse import quote, unquote
from functools import wraps
from bs4 import BeautifulSoup

from cookie_auto_refresher import auto_refresh_cookies

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


class RateLimiter:
    """Rate limiter to prevent overwhelming Instagram's servers"""
    def __init__(self, max_calls=100, period=1800):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
    
    def wait_if_needed(self):
        now = time.time()
        self.calls = [c for c in self.calls if now - c < self.period]
        
        if len(self.calls) >= self.max_calls:
            sleep_time = self.period - (now - self.calls[0])
            print(f"Rate limit reached. Waiting {sleep_time:.0f} seconds...")
            time.sleep(sleep_time)
        
        self.calls.append(now)


# Global rate limiter instance
rate_limiter = RateLimiter()


def retry(max_attempts=3, delay=2):
    """Decorator for retry logic"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except requests.RequestException as e:
                    if attempt == max_attempts - 1:
                        raise
                    print(f"Attempt {attempt + 1} failed. Retrying in {delay}s...")
                    time.sleep(delay)
            return None
        return wrapper
    return decorator


def extract_shortcode_from_url(url):
    """
    Extract shortcode from various Instagram URL formats
    
    Examples:
    - https://www.instagram.com/reel/DOvzTywjPGN/
    - https://www.instagram.com/username/reel/DOvzTywjPGN/
    - https://www.instagram.com/p/DOvzTywjPGN/
    """
    url = url.split('?')[0]  # Remove query parameters
    pattern = r'instagram\.com/(?:[^/]+/)?(?:reel|p)/([^/?]+)'
    match = re.search(pattern, url)
    
    if not match:
        raise ValueError("Invalid Instagram URL. Please provide a valid Instagram Reel or Post URL.")
    
    return match.group(1)


def create_payload(shortcode, doc_id="24368985919464652"):
    """Create GraphQL payload with properly encoded variables"""
    variables = json.dumps({"shortcode": shortcode})
    encoded_variables = quote(variables)
    return f'variables={encoded_variables}&doc_id={doc_id}'


def load_cookies_from_file(filename='cookies.txt'):
    """Load cookies from a text file"""
    cookies = {}
    if not os.path.exists(filename):
        return None
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                # Parse cookie_name=cookie_value
                if '=' in line:
                    parts = line.split('=', 1)
                    cookie_name = parts[0].strip()
                    cookie_value = parts[1].strip().strip('"')
                    cookies[cookie_name] = cookie_value
        return cookies if cookies else None
    except Exception as e:
        print(f"Warning: Could not load cookies from file: {e}")
        return None


def get_session_cookies(custom_cookies=None):
    """Get session cookies and CSRF token from Instagram homepage or use custom cookies"""
    session = requests.Session()
    session.headers.update({
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'accept-language': 'en-US,en;q=0.9',
    })
    
    # Try to load cookies from file first
    if custom_cookies is None:
        custom_cookies = load_cookies_from_file()
    
    # If custom cookies provided, use them
    if custom_cookies:
        for cookie_name, cookie_value in custom_cookies.items():
            # Unquote URL-encoded values
            if '%' in cookie_value:
                cookie_value = unquote(cookie_value)
            session.cookies.set(cookie_name, cookie_value, domain='.instagram.com')
        csrf_token = custom_cookies.get('csrftoken', '')
        print("✓ Using provided cookies for authentication")
        return session, csrf_token
    
    try:
        # Visit Instagram homepage to get cookies
        response = session.get('https://www.instagram.com/', timeout=10)
        csrf_token = session.cookies.get('csrftoken', '')
        return session, csrf_token
    except Exception as e:
        print(f"Warning: Could not get session cookies: {e}")
        return session, ''


def extract_media_id_from_html(session, url):
    """Extract media ID from Instagram reel HTML page using meta tags"""
    try:
        response = session.get(url, timeout=10)
        if response.status_code == 200:
            html = response.text
            
            # Look for meta tag with instagram://media?id=
            # Pattern: <meta content="instagram://media?id=2783638179615141877" ...>
            meta_pattern = r'<meta[^>]*content=["\']instagram://media\?id=(\d+)["\']'
            match = re.search(meta_pattern, html)
            
            if match:
                media_id = match.group(1)
                print(f"  ✓ Extracted media ID: {media_id}")
                return media_id
            
            # Alternative: look in all meta tags
            soup = BeautifulSoup(html, 'html.parser')
            metas = soup.find_all('meta')
            for meta in metas:
                content = meta.get('content', '')
                if 'instagram://media?id=' in content:
                    media_id = content.split('id=')[1].split('&')[0].split('"')[0].split("'")[0]
                    print(f"  ✓ Extracted media ID from meta: {media_id}")
                    return media_id
                    
    except Exception as e:
        print(f"  ✗ Failed to extract media ID from HTML: {e}")
    
    return None


def extract_media_id_from_graphql_data(data):
    """Extract media ID from GraphQL response data"""
    try:
        items = data.get('data', {}).get('xdt_api__v1__media__shortcode__web_info', {}).get('items', [])
        if items and len(items) > 0:
            item = items[0]
            # Try 'pk' field first (this is the media ID)
            media_id = item.get('pk')
            if media_id:
                print(f"  ✓ Extracted media ID from GraphQL: {media_id}")
                return str(media_id)
            # Try 'id' field (format: media_id_user_id)
            item_id = item.get('id')
            if item_id and '_' in str(item_id):
                media_id = str(item_id).split('_')[0]
                print(f"  ✓ Extracted media ID from id field: {media_id}")
                return media_id
    except Exception as e:
        print(f"  ✗ Failed to extract media ID from GraphQL: {e}")
    
    return None


def get_view_count_from_api(session, media_id, csrf_token, allow_refresh=True):
    """Get view count from Instagram API using media ID"""
    try:
        api_url = f"https://i.instagram.com/api/v1/media/{media_id}/info/"
        
        headers = {
            'Accept-Encoding': 'identity',
            'user-agent': session.headers.get('user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'),
            'x-csrftoken': csrf_token,
            'x-ig-app-id': '936619743392459',
            'referer': 'https://www.instagram.com/',
        }
        
        # Add cookies from session
        cookie_string = '; '.join([f'{k}={v}' for k, v in session.cookies.items()])
        if cookie_string:
            headers['cookie'] = cookie_string
        
        response = session.get(api_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Extract play_count (view count)
            if 'items' in data and len(data['items']) > 0:
                item = data['items'][0]
                play_count = item.get('play_count')
                view_count = item.get('view_count')
                
                # Return whichever is available
                if play_count is not None:
                    return play_count
                elif view_count is not None:
                    return view_count
                # If both are missing, optionally try refreshing cookies once
                elif allow_refresh:
                    if auto_refresh_cookies(reason="media_info_no_view_fields"):
                        print("  ↻ Cookies refreshed automatically (no view fields). Retrying view count request...")
                        refreshed_session, refreshed_csrf = get_session_cookies()
                        if refreshed_session:
                            return get_view_count_from_api(
                                refreshed_session, media_id, refreshed_csrf, allow_refresh=False
                            )
        else:
            print(f"  ✗ API returned status {response.status_code}")
            if allow_refresh and response.status_code in (401, 403, 404):
                if auto_refresh_cookies(reason=f"media_info_status_{response.status_code}"):
                    print("  ↻ Cookies refreshed automatically. Retrying view count request...")
                    refreshed_session, refreshed_csrf = get_session_cookies()
                    if refreshed_session:
                        return get_view_count_from_api(
                            refreshed_session, media_id, refreshed_csrf, allow_refresh=False
                        )
    except Exception as e:
        print(f"  ✗ Failed to get view count from API: {e}")
        if allow_refresh and auto_refresh_cookies(reason=str(e)):
            print("  ↻ Cookies refreshed automatically after exception. Retrying view count request...")
            refreshed_session, refreshed_csrf = get_session_cookies()
            if refreshed_session:
                return get_view_count_from_api(
                    refreshed_session, media_id, refreshed_csrf, allow_refresh=False
                )
    
    return None


def get_headers(csrf_token=''):
    """Get headers that mimic a browser request"""
    headers = {
        'content-type': 'application/x-www-form-urlencoded',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'x-ig-app-id': '936619743392459',
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'origin': 'https://www.instagram.com',
        'referer': 'https://www.instagram.com/',
    }
    
    if csrf_token:
        headers['x-csrftoken'] = csrf_token
    
    return headers


@retry(max_attempts=3, delay=2)
def scrape_instagram_reel(url, session=None, save_json=True):
    """
    Scrape Instagram Reel data using GraphQL API
    
    Args:
        url (str): Instagram Reel URL
        session (requests.Session): Optional session object with cookies
        save_json (bool): Whether to save raw JSON data to file (default: True)
        
    Returns:
        dict: Dictionary with success status and data or error message
    """
    try:
        # Rate limiting
        rate_limiter.wait_if_needed()
        
        # Get session and CSRF token if not provided
        if session is None:
            session, csrf_token = get_session_cookies()
        else:
            csrf_token = session.cookies.get('csrftoken', '')
        
        # Extract shortcode from URL
        shortcode = extract_shortcode_from_url(url)
        print(f"Extracted shortcode: {shortcode}")
        
        # Try multiple GraphQL queries to get view counts
        # Different doc_ids might return different data
        doc_ids_to_try = [
            "24368985919464652",  # Standard web info query
            "17888483320059182",  # Alternative query (media info)
            "17863787109211844",  # Another alternative
        ]
        
        data = None
        last_error = None
        cookies_refreshed = False
        
        for doc_id in doc_ids_to_try:
            try:
                # Create payload with different doc_id
                payload = create_payload(shortcode, doc_id=doc_id)
                
                # Make request using session
                response = session.post(
                    "https://www.instagram.com/graphql/query",
                    headers=get_headers(csrf_token),
                    data=payload,
                    timeout=10
                )
                
                # Check for authentication errors and try auto-refresh once
                if response.status_code in (401, 403) and not cookies_refreshed:
                    print(f"  ✗ GraphQL request returned {response.status_code}. Attempting cookie refresh...")
                    if auto_refresh_cookies(reason=f"graphql_status_{response.status_code}"):
                        print("  ↻ Cookies refreshed automatically. Retrying GraphQL request...")
                        cookies_refreshed = True
                        # Reload session with new cookies
                        session, csrf_token = get_session_cookies()
                        # Retry this doc_id
                        response = session.post(
                            "https://www.instagram.com/graphql/query",
                            headers=get_headers(csrf_token),
                            data=payload,
                            timeout=10
                        )
                
                if response.status_code == 200:
                    try:
                        test_data = response.json()
                        # Check if this response has view count data
                        if test_data and 'data' in test_data:
                            data = test_data
                            print(f"✓ Got data with doc_id: {doc_id}")
                            break
                    except json.JSONDecodeError:
                        continue
            except Exception as e:
                last_error = e
                continue
        
        # If no data from GraphQL, try HTML parsing as fallback
        if data is None:
            print("Trying HTML parsing as fallback...")
            html_data = try_html_parsing(session, url, shortcode)
            if html_data:
                data = html_data
        
        if data is None:
            # Fallback to original query
            payload = create_payload(shortcode)
            response = session.post(
                "https://www.instagram.com/graphql/query",
                headers=get_headers(csrf_token),
                data=payload,
                timeout=10
            )
            
            # Check for authentication errors in fallback request
            if response.status_code in (401, 403) and not cookies_refreshed:
                print(f"  ✗ Fallback GraphQL request returned {response.status_code}. Attempting cookie refresh...")
                if auto_refresh_cookies(reason=f"graphql_fallback_status_{response.status_code}"):
                    print("  ↻ Cookies refreshed automatically. Retrying fallback request...")
                    cookies_refreshed = True
                    # Reload session with new cookies
                    session, csrf_token = get_session_cookies()
                    # Retry fallback request
                    response = session.post(
                        "https://www.instagram.com/graphql/query",
                        headers=get_headers(csrf_token),
                        data=payload,
                        timeout=10
                    )
        else:
            # Use the data we got, create a mock response object
            class MockResponse:
                status_code = 200
                def json(self):
                    return data
            response = MockResponse()
        
        # Handle rate limiting
        if response.status_code == 429:
            return {"error": "Rate limited. Try again later.", "status_code": 429}
        
        # Handle not found
        if response.status_code == 404:
            return {"error": "Reel not found or private.", "status_code": 404}
        
        # Handle authentication errors (after refresh attempt)
        if response.status_code in (401, 403):
            return {
                "error": f"Authentication failed (status {response.status_code}). Cookies may be invalid.",
                "status_code": response.status_code
            }
        
        # Handle other errors
        if response.status_code != 200:
            return {
                "error": f"Request failed with status code {response.status_code}",
                "status_code": response.status_code
            }
        
        # Parse JSON response
        try:
            data = response.json()
        except json.JSONDecodeError:
            return {"error": "Invalid JSON response from Instagram", "status_code": 200}
        
        # Check if data is valid
        if not data or 'data' not in data:
            return {"error": "No data found in response", "status_code": 200}
        
        # Save to file (optional)
        filename = None
        if save_json:
            filename = f'{shortcode}_data.json'
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
            except Exception as e:
                print(f"Warning: Could not save JSON file: {e}")
        
        # Extract useful information
        extracted_data = extract_useful_data(data, shortcode, session, url, csrf_token)
        
        return {
            "success": True,
            "shortcode": shortcode,
            "filename": filename,
            "data": data,
            "extracted": extracted_data
        }
    
    except requests.Timeout:
        return {"error": "Request timeout. Please try again."}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


def extract_useful_data(data, shortcode, session=None, url=None, csrf_token=None):
    """
    Extract and structure useful data from the raw GraphQL response
    
    Returns a simplified dictionary with key information
    """
    extracted = {
        "shortcode": shortcode,
        "video_urls": [],
        "thumbnail_urls": [],
        "engagement": {},
        "user": {},
        "caption": "",
        "timestamp": None,
    }
    
    try:
        # Navigate through the GraphQL response structure
        items = data.get('data', {}).get('xdt_api__v1__media__shortcode__web_info', {}).get('items', [])
        
        if not items:
            return extracted
        
        item = items[0]
        
        # Extract video URLs
        video_versions = item.get('video_versions', [])
        for video in video_versions:
            extracted['video_urls'].append({
                "url": video.get('url', ''),
                "width": video.get('width', 0),
                "height": video.get('height', 0),
                "type": video.get('type', 0)
            })
        
        # Extract thumbnail URLs
        image_versions2 = item.get('image_versions2', {}).get('candidates', [])
        for img in image_versions2:
            extracted['thumbnail_urls'].append({
                "url": img.get('url', ''),
                "width": img.get('width', 0),
                "height": img.get('height', 0)
            })
        
        # Extract engagement metrics
        extracted['engagement'] = {
            "like_count": item.get('like_count', 0),
            "comment_count": item.get('comment_count', 0),
            "play_count": item.get('play_count', None),
            "view_count": item.get('view_count', None),
            "video_view_count": item.get('video_view_count', None),
            "organic_video_view_count": item.get('organic_video_view_count', None),
        }
        
        # Try to get view count from Instagram API if not available in GraphQL response
        if session and url and csrf_token:
            if extracted['engagement']['play_count'] is None and extracted['engagement']['view_count'] is None:
                print("  Attempting to get view count from Instagram API...")
                # First try to get media ID from GraphQL data
                media_id = extract_media_id_from_graphql_data(data)
                # If not found, try HTML parsing
                if not media_id:
                    media_id = extract_media_id_from_html(session, url)
                
                if media_id:
                    view_count = get_view_count_from_api(session, media_id, csrf_token)
                    if view_count is not None:
                        extracted['engagement']['play_count'] = view_count
                        print(f"  ✓ Got view count from API: {view_count:,}")
                    else:
                        print(f"  ✗ Could not get view count from API")
                else:
                    print(f"  ✗ Could not extract media ID")
        
        # Extract user information
        user = item.get('user', {})
        extracted['user'] = {
            "username": user.get('username', ''),
            "full_name": user.get('full_name', ''),
            "profile_pic_url": user.get('profile_pic_url', ''),
            "is_verified": user.get('is_verified', False),
            "is_private": user.get('is_private', False),
        }
        
        # Extract caption
        caption = item.get('caption', {})
        extracted['caption'] = caption.get('text', '') if caption else ''
        
        # Extract timestamp
        extracted['timestamp'] = item.get('taken_at', None)
        
    except Exception as e:
        print(f"Warning: Could not extract all data: {e}")
    
    return extracted


def print_summary(extracted_data):
    """Print a human-readable summary of the scraped data"""
    print("\n" + "="*60)
    print("SCRAPING SUMMARY")
    print("="*60)
    
    print(f"\n📹 Shortcode: {extracted_data.get('shortcode', 'N/A')}")
    
    # User info
    user = extracted_data.get('user', {})
    if user.get('username'):
        print(f"\n👤 User: @{user.get('username')}")
        print(f"   Name: {user.get('full_name', 'N/A')}")
        print(f"   Verified: {'✓' if user.get('is_verified') else '✗'}")
    
    # Engagement
    engagement = extracted_data.get('engagement', {})
    print(f"\n📊 Engagement:")
    print(f"   Likes: {engagement.get('like_count', 0):,}")
    print(f"   Comments: {engagement.get('comment_count', 0):,}")
    
    # View counts (check all possible fields)
    view_count = engagement.get('view_count')
    play_count = engagement.get('play_count')
    video_view_count = engagement.get('video_view_count')
    organic_video_view_count = engagement.get('organic_video_view_count')
    
    if view_count is not None:
        print(f"   View Count: {view_count:,}")
    if play_count is not None:
        print(f"   Play Count: {play_count:,}")
    if video_view_count is not None:
        print(f"   Video View Count: {video_view_count:,}")
    if organic_video_view_count is not None:
        print(f"   Organic Video View Count: {organic_video_view_count:,}")
    
    # Video URLs
    video_urls = extracted_data.get('video_urls', [])
    if video_urls:
        print(f"\n🎥 Video URLs ({len(video_urls)} qualities):")
        for i, video in enumerate(video_urls[:3], 1):  # Show first 3
            print(f"   {i}. {video.get('width')}x{video.get('height')} - {video.get('url', '')[:50]}...")
        if len(video_urls) > 3:
            print(f"   ... and {len(video_urls) - 3} more")
    
    # Caption preview
    caption = extracted_data.get('caption', '')
    if caption:
        caption_preview = caption[:100] + "..." if len(caption) > 100 else caption
        print(f"\n📝 Caption: {caption_preview}")
    
    print("\n" + "="*60)


def main():
    """Main CLI interface"""
    print("Instagram Reel Scraper")
    print("="*60)
    
    # Get URL from command line or prompt
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = input("Enter Instagram Reel URL: ").strip()
    
    if not url:
        print("Error: No URL provided")
        sys.exit(1)
    
    print(f"\nScraping: {url}")
    print("Please wait...\n")
    
    # Scrape the reel
    result = scrape_instagram_reel(url)
    
    # Display results
    if result.get('success'):
        print("✅ SUCCESS!")
        print(f"📁 Data saved to: {result['filename']}")
        
        # Print summary
        if result.get('extracted'):
            print_summary(result['extracted'])
        
        print("\n✅ Scraping completed successfully!")
    else:
        print(f"❌ FAILED: {result.get('error', 'Unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()

