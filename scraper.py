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
from proxy_config import proxy_rotator, PROXY_CONFIG, get_next_proxy, get_proxy_for_account

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


class RateLimiter:
    """Rate limiter to prevent overwhelming Instagram's servers.

    Configurable via env vars:
      SCRAPER_RATE_MAX_CALLS  (default 2000)
      SCRAPER_RATE_PERIOD_SEC (default 1800)
      SCRAPER_RATE_DISABLED=1 to turn off entirely.
    """
    def __init__(self, max_calls=None, period=None):
        self.max_calls = max_calls if max_calls is not None else int(os.getenv("SCRAPER_RATE_MAX_CALLS", "2000"))
        self.period = period if period is not None else int(os.getenv("SCRAPER_RATE_PERIOD_SEC", "1800"))
        self.disabled = os.getenv("SCRAPER_RATE_DISABLED", "0").lower() in ("1", "true", "yes")
        self.calls = []

    def wait_if_needed(self):
        if self.disabled:
            return
        now = time.time()
        self.calls = [c for c in self.calls if now - c < self.period]

        if len(self.calls) >= self.max_calls:
            sleep_time = self.period - (now - self.calls[0])
            # Cap the wait — long sleeps wedge background jobs and starve the queue.
            cap = float(os.getenv("SCRAPER_RATE_MAX_WAIT_SEC", "10"))
            if sleep_time > cap:
                print(f"Rate limit reached ({len(self.calls)}/{self.max_calls}); "
                      f"would wait {sleep_time:.0f}s, capping at {cap:.0f}s")
                sleep_time = cap
            else:
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
    - https://www.instagram.com/reels/DOvzTywjPGN/  (plural)
    - https://www.instagram.com/username/reel/DOvzTywjPGN/
    - https://www.instagram.com/p/DOvzTywjPGN/
    """
    url = url.split('?')[0]  # Remove query parameters
    # Match both "reel" and "reels" (singular and plural), and "p" for posts
    pattern = r'instagram\.com/(?:[^/]+/)?(?:reels?|p)/([^/?]+)'
    match = re.search(pattern, url)
    
    if not match:
        raise ValueError("Invalid Instagram URL. Please provide a valid Instagram Reel or Post URL.")
    
    return match.group(1)


def create_payload(shortcode, doc_id="24368985919464652"):
    """Create GraphQL payload with properly encoded variables"""
    variables = json.dumps({"shortcode": shortcode})
    encoded_variables = quote(variables)
    return f'variables={encoded_variables}&doc_id={doc_id}'


def graphql_doc_ids_to_try():
    """
    Primary doc_id usually suffices. Set SCRAPER_FAST_GRAPHQL=1 to skip alternate
    GraphQL hashes (saves 1–2 round-trips when the first query works).
    """
    primary = "24368985919464652"
    if os.getenv("SCRAPER_FAST_GRAPHQL", "").lower() in ("1", "true", "yes"):
        return [primary]
    return [
        primary,
        "17888483320059182",
        "17863787109211844",
    ]


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


def reload_session_from_cookie_file(cookie_file=None):
    """
    Rebuild session after cookie refresh or GraphQL retry. Must use the same cookie file as the
    active account (multi-account rotation); plain get_session_cookies() would load INSTAGRAM_COOKIES_FILE / cookies.txt.
    """
    if cookie_file:
        custom = load_cookies_from_file(cookie_file)
        if custom:
            return get_session_cookies(custom)
    return get_session_cookies()


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
        # Check for account-specific cookie file from environment
        cookies_file = os.getenv('INSTAGRAM_COOKIES_FILE', 'cookies.txt')
        custom_cookies = load_cookies_from_file(cookies_file)
    
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
        # Visit Instagram homepage to get cookies (with proxy if enabled)
        proxy = get_next_proxy()
        response = session.get('https://www.instagram.com/', timeout=10, proxies=proxy)
        csrf_token = session.cookies.get('csrftoken', '')
        if proxy and PROXY_CONFIG["enabled"]:
            print(f"✓ Session created with proxy")
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
        d = data.get('data') or {}
        web_info = d.get('xdt_api__v1__media__shortcode__web_info') or {}
        items = web_info.get('items') or []
        if items and len(items) > 0:
            item = items[0] or {}
            # Try 'pk' field first (this is the media ID)
            media_id = item.get('pk')
            if media_id:
                print(f"  ✓ Extracted media ID from GraphQL (pk): {media_id}")
                return str(media_id)
            
            # Try 'id' field (format: media_id_user_id)
            item_id = item.get('id')
            if item_id:
                if '_' in str(item_id):
                    media_id = str(item_id).split('_')[0]
                    print(f"  ✓ Extracted media ID from id field: {media_id}")
                    return media_id
                else:
                    # Sometimes id is just the media_id
                    print(f"  ✓ Using id as media ID: {item_id}")
                    return str(item_id)
            
            # Try 'media_id' field directly
            media_id = item.get('media_id')
            if media_id:
                print(f"  ✓ Extracted media ID from media_id field: {media_id}")
                return str(media_id)
            
            # Try code_to_id conversion (shortcode to media_id)
            shortcode = item.get('code') or item.get('shortcode')
            if shortcode:
                # Instagram shortcode to ID conversion
                try:
                    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
                    media_id = 0
                    for char in shortcode:
                        media_id = media_id * 64 + alphabet.index(char)
                    print(f"  ✓ Converted shortcode to media ID: {media_id}")
                    return str(media_id)
                except:
                    pass
            
            print(f"  ✗ Could not extract media ID from GraphQL item")
            print(f"  Debug: Available item keys: {list(item.keys())[:20]}")
    except Exception as e:
        print(f"  ✗ Failed to extract media ID from GraphQL: {e}")
    
    return None


def get_view_count_from_api(session, media_id, csrf_token, allow_refresh=True, cookie_file=None, account=None):
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
        
        proxy = get_proxy_for_account(account) if account else get_next_proxy()
        
        response = session.get(api_url, headers=headers, timeout=10, proxies=proxy)
        
        if response.status_code == 200:
            data = response.json()
            
            # Extract play_count (view count) - check multiple locations
            if 'items' in data and len(data['items']) > 0:
                item = data['items'][0]
                
                # Check primary fields
                play_count = item.get('play_count')
                view_count = item.get('view_count')
                video_view_count = item.get('video_view_count')
                organic_video_view_count = item.get('organic_video_view_count')
                
                # Check video_versions for play_count
                if play_count is None and 'video_versions' in item:
                    for video in item['video_versions']:
                        if video.get('play_count') is not None:
                            play_count = video.get('play_count')
                            print(f"  ✓ Found play_count in video_versions: {play_count:,}")
                            break
                
                # Check additional fields
                if play_count is None:
                    play_count = item.get('video_play_count') or item.get('reel_view_count') or item.get('viewer_count')
                
                # Check media field if it exists
                if play_count is None and 'media' in item:
                    media = item['media']
                    play_count = media.get('play_count') or media.get('view_count')
                
                # Return whichever is available (prioritize play_count)
                if play_count is not None:
                    print(f"  ✓ Got play_count from API: {play_count:,}")
                    return play_count
                elif view_count is not None:
                    print(f"  ✓ Got view_count from API: {view_count:,}")
                    return view_count
                elif video_view_count is not None:
                    print(f"  ✓ Got video_view_count from API: {video_view_count:,}")
                    return video_view_count
                elif organic_video_view_count is not None:
                    print(f"  ✓ Got organic_video_view_count from API: {organic_video_view_count:,}")
                    return organic_video_view_count
                else:
                    # Debug: Print available keys to help diagnose
                    print(f"  ✗ No view count fields found in API response")
                    print(f"  Debug: Available item keys: {list(item.keys())[:30]}")
                    # If both are missing, optionally try refreshing cookies once
                    if allow_refresh:
                        if auto_refresh_cookies(reason="media_info_no_view_fields"):
                            print("  ↻ Cookies refreshed automatically (no view fields). Retrying view count request...")
                            refreshed_session, refreshed_csrf = reload_session_from_cookie_file(cookie_file)
                            if refreshed_session:
                                return get_view_count_from_api(
                                    refreshed_session, media_id, refreshed_csrf, allow_refresh=False,
                                    cookie_file=cookie_file, account=account,
                                )
            else:
                print(f"  ✗ API response missing 'items' field")
                print(f"  Debug: Response keys: {list(data.keys())}")
        else:
            print(f"  ✗ API returned status {response.status_code}")
            if allow_refresh and response.status_code in (401, 403, 404):
                if auto_refresh_cookies(reason=f"media_info_status_{response.status_code}"):
                    print("  ↻ Cookies refreshed automatically. Retrying view count request...")
                    refreshed_session, refreshed_csrf = reload_session_from_cookie_file(cookie_file)
                    if refreshed_session:
                        return get_view_count_from_api(
                            refreshed_session, media_id, refreshed_csrf, allow_refresh=False,
                            cookie_file=cookie_file, account=account,
                        )
    except Exception as e:
        print(f"  ✗ Failed to get view count from API: {e}")
        if allow_refresh and auto_refresh_cookies(reason=str(e)):
            print("  ↻ Cookies refreshed automatically after exception. Retrying view count request...")
            refreshed_session, refreshed_csrf = reload_session_from_cookie_file(cookie_file)
            if refreshed_session:
                return get_view_count_from_api(
                    refreshed_session, media_id, refreshed_csrf, allow_refresh=False,
                    cookie_file=cookie_file, account=account,
                )
    
    return None


def _views_fallback_when_counts_disabled() -> bool:
    """If True, still run HTML + /api/v1/media/.../info/ when GraphQL sets like_and_view_counts_disabled."""
    return os.getenv("SCRAPER_VIEWS_FALLBACK_WHEN_DISABLED", "1").lower() in ("1", "true", "yes")


def _read_view_fields_from_media_dict(m: dict):
    """Pick best view metric from a media-like dict."""
    if not isinstance(m, dict):
        return None
    for key in ("play_count", "video_view_count", "view_count", "ig_play_count"):
        v = m.get(key)
        if isinstance(v, (int, float)) and v >= 0:
            return int(v)
    return None


def _find_view_count_in_json_obj(obj, shortcode: str, depth: int = 0):
    """
    Recursively find view counts on JSON that belongs to this shortcode.
    Instagram embeds multiple reels in one page; matching shortcode reduces false positives.
    """
    if depth > 48:
        return None
    if isinstance(obj, dict):
        code_ok = obj.get("code") == shortcode or obj.get("shortcode") == shortcode
        if code_ok:
            n = _read_view_fields_from_media_dict(obj)
            if n is not None:
                return n
        for nest_key in ("media", "node", "clip", "xdt_shortcode_media"):
            sub = obj.get(nest_key)
            if isinstance(sub, dict) and (
                sub.get("code") == shortcode or sub.get("shortcode") == shortcode
            ):
                n = _read_view_fields_from_media_dict(sub)
                if n is not None:
                    return n
        if isinstance(obj.get("items"), list):
            for it in obj["items"]:
                if isinstance(it, dict) and it.get("code") == shortcode:
                    n = _read_view_fields_from_media_dict(it)
                    if n is not None:
                        return n
        for v in obj.values():
            got = _find_view_count_in_json_obj(v, shortcode, depth + 1)
            if got is not None:
                return got
    elif isinstance(obj, list):
        for it in obj:
            got = _find_view_count_in_json_obj(it, shortcode, depth + 1)
            if got is not None:
                return got
    return None


def _extract_views_from_embedded_page_json(html: str, shortcode: str):
    """Parse JSON inside script tags and walk for this shortcode's view fields."""
    if not shortcode:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script"):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if len(raw) < 20:
            continue
        if raw[0] not in "{[":
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        got = _find_view_count_in_json_obj(data, shortcode)
        if got is not None:
            print(f"  ✓ Extracted view count from embedded JSON (shortcode-scoped): {got:,}")
            return got
    return None


def _extract_views_near_shortcode_window(html: str, shortcode: str):
    """Search a tight window around the shortcode for play_count / view_count (avoids other reels' metrics)."""
    if not shortcode:
        return None
    needle = f'"code":"{shortcode}"'
    idx = html.find(needle)
    if idx == -1:
        needle = f'"code": "{shortcode}"'
        idx = html.find(needle)
    if idx == -1:
        return None
    window = html[max(0, idx - 12000) : idx + 12000]
    patterns = [
        r'"play_count"\s*:\s*(\d+)',
        r'"video_view_count"\s*:\s*(\d+)',
        r'"view_count"\s*:\s*(\d+)',
    ]
    for pat in patterns:
        m = re.search(pat, window)
        if m:
            v = int(m.group(1))
            print(f"  ✓ Extracted view count from HTML window near shortcode: {v:,}")
            return v
    return None


def extract_view_count_from_html(session, url, shortcode=None):
    """Try to extract view count from reel page HTML (shortcode-scoped when provided)."""
    try:
        response = session.get(url, timeout=15)
        if response.status_code != 200:
            return None

        html = response.text

        if shortcode:
            w = _extract_views_near_shortcode_window(html, shortcode)
            if w is not None:
                return w
            j = _extract_views_from_embedded_page_json(html, shortcode)
            if j is not None:
                return j

        patterns = [
            r'"play_count"\s*:\s*(\d+)',
            r'"view_count"\s*:\s*(\d+)',
            r'"video_view_count"\s*:\s*(\d+)',
            r'(\d+)\s*views',
            r'(\d+)\s*Views',
        ]

        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                view_count = int(match.group(1))
                print(f"  ✓ Extracted view count from HTML (global regex): {view_count:,}")
                return view_count

        soup = BeautifulSoup(html, "html.parser")
        for elem in soup.find_all(["span", "div", "meta"]):
            text = elem.get_text() or elem.get("content", "")
            if "views" in text.lower():
                numbers = re.findall(r"[\d,]+", text)
                if numbers:
                    try:
                        view_count = int(numbers[0].replace(",", ""))
                        if view_count > 0:
                            print(f"  ✓ Extracted view count from HTML text: {view_count:,}")
                            return view_count
                    except Exception:
                        pass

        return None
    except Exception as e:
        print(f"  ✗ Failed to extract view count from HTML: {e}")
        return None


def try_html_parsing(session, url, shortcode):
    """
    Try to extract data from Instagram HTML page as fallback.
    Returns GraphQL-like data structure if successful, None otherwise.
    """
    try:
        response = session.get(url, timeout=15)
        if response.status_code != 200:
            print(f"  ✗ HTML parsing failed: status {response.status_code}")
            return None
        
        html = response.text
        
        # Try to find JSON data in script tags
        import re
        
        # Look for shared data in script
        patterns = [
            r'window\._sharedData\s*=\s*({.+?});</script>',
            r'window\.__additionalDataLoaded\s*\([^,]+,\s*({.+?})\);',
            r'"PostPage":\s*\[({.+?})\]',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    print(f"  ✓ Found data via HTML parsing")
                    # Convert to expected format
                    return {"data": data}
                except json.JSONDecodeError:
                    continue
        
        print(f"  ✗ No data found in HTML")
        return None
        
    except Exception as e:
        print(f"  ✗ HTML parsing error: {e}")
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
def scrape_instagram_reel(url, session=None, save_json=True, cookie_file=None, account=None):
    """
    Scrape Instagram Reel data using GraphQL API
    
    Args:
        url (str): Instagram Reel URL
        session (requests.Session): Optional session object with cookies
        save_json (bool): Whether to save raw JSON data to file (default: True)
        cookie_file (str): Optional path to cookie file (default: None, uses cookies.txt)
        account (str): Optional account name for per-account proxy selection
        
    Returns:
        dict: Dictionary with success status and data or error message
    """
    try:
        # Rate limiting
        rate_limiter.wait_if_needed()
        
        # Get session and CSRF token if not provided
        if session is None:
            # Load cookies from specified file or default
            custom_cookies = None
            if cookie_file:
                custom_cookies = load_cookies_from_file(cookie_file)
            session, csrf_token = get_session_cookies(custom_cookies)
        else:
            csrf_token = session.cookies.get('csrftoken', '')
        
        # Extract shortcode from URL
        shortcode = extract_shortcode_from_url(url)
        print(f"Extracted shortcode: {shortcode}")
        
        # Get proxy for this account (if per-account proxies enabled)
        account_proxy = get_proxy_for_account(account) if account else get_next_proxy()
        
        # Try GraphQL doc_id(s); fast mode uses primary only (see graphql_doc_ids_to_try)
        doc_ids_to_try = graphql_doc_ids_to_try()
        
        data = None
        last_error = None
        cookies_refreshed = False
        
        for doc_id in doc_ids_to_try:
            try:
                # Create payload with different doc_id
                payload = create_payload(shortcode, doc_id=doc_id)
                
                # Use account-specific proxy if available, otherwise use rotating proxy
                proxy = account_proxy
                
                # Make request using session
                response = session.post(
                    "https://www.instagram.com/graphql/query",
                    headers=get_headers(csrf_token),
                    data=payload,
                    timeout=10,
                    proxies=proxy
                )
                
                # Check for authentication errors and try auto-refresh once
                if response.status_code in (401, 403) and not cookies_refreshed:
                    print(f"  ✗ GraphQL request returned {response.status_code}. Attempting cookie refresh...")
                    if auto_refresh_cookies(reason=f"graphql_status_{response.status_code}"):
                        print("  ↻ Cookies refreshed automatically. Retrying GraphQL request...")
                        cookies_refreshed = True
                        session, csrf_token = reload_session_from_cookie_file(cookie_file)
                        response = session.post(
                            "https://www.instagram.com/graphql/query",
                            headers=get_headers(csrf_token),
                            data=payload,
                            timeout=10,
                            proxies=proxy,
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
                timeout=10,
                proxies=account_proxy,
            )
            
            # Check for authentication errors in fallback request
            if response.status_code in (401, 403) and not cookies_refreshed:
                print(f"  ✗ Fallback GraphQL request returned {response.status_code}. Attempting cookie refresh...")
                if auto_refresh_cookies(reason=f"graphql_fallback_status_{response.status_code}"):
                    print("  ↻ Cookies refreshed automatically. Retrying fallback request...")
                    cookies_refreshed = True
                    session, csrf_token = reload_session_from_cookie_file(cookie_file)
                    response = session.post(
                        "https://www.instagram.com/graphql/query",
                        headers=get_headers(csrf_token),
                        data=payload,
                        timeout=10,
                        proxies=account_proxy,
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
        extracted_data = extract_useful_data(
            data, shortcode, session, url, csrf_token, cookie_file=cookie_file, account=account
        )
        
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


def _best_positive_view_metric(*values):
    """Return first int > 0, or None if none."""
    for v in values:
        if v is not None and isinstance(v, (int, float)) and v > 0:
            return int(v)
    return None


def _coalesce_views_engagement(engagement: dict) -> None:
    """
    Set engagement['views'] to the best available count and mirror into play_count when empty.
    Call after GraphQL + any fallbacks so the API/UI can read a single `views` field.
    """
    keys = ("play_count", "view_count", "video_view_count", "organic_video_view_count")
    best = _best_positive_view_metric(*(engagement.get(k) for k in keys))
    if best is None:
        for k in keys:
            v = engagement.get(k)
            if v is not None and isinstance(v, (int, float)):
                best = int(v)
                break
    engagement["views"] = best


def extract_useful_data(data, shortcode, session=None, url=None, csrf_token=None, cookie_file=None, account=None):
    """
    Extract and structure useful data from the raw GraphQL response
    
    cookie_file / account: pass through so view-count fallbacks and cookie reloads stay on the same Instagram account.
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
        # Navigate through the GraphQL response structure (Instagram occasionally returns None for nested keys)
        d = data.get('data') or {}
        web_info = d.get('xdt_api__v1__media__shortcode__web_info') or {}
        items = web_info.get('items') or []

        if not items:
            _coalesce_views_engagement(extracted['engagement'])
            return extracted

        item = items[0] or {}
        
        # Extract video URLs
        video_versions = item.get('video_versions') or []
        for video in video_versions:
            extracted['video_urls'].append({
                "url": video.get('url', ''),
                "width": video.get('width', 0),
                "height": video.get('height', 0),
                "type": video.get('type', 0)
            })

        # Extract thumbnail URLs
        image_versions2 = (item.get('image_versions2') or {}).get('candidates') or []
        for img in image_versions2:
            extracted['thumbnail_urls'].append({
                "url": img.get('url', ''),
                "width": img.get('width', 0),
                "height": img.get('height', 0)
            })
        
        # Check if view counts are disabled by Instagram
        like_and_view_counts_disabled = item.get('like_and_view_counts_disabled', False)
        if like_and_view_counts_disabled:
            print("  ⚠️  Instagram has disabled view counts for this post")
        
        # Extract engagement metrics - check multiple possible locations
        # First check direct fields
        play_count = item.get('play_count')
        view_count = item.get('view_count')
        video_view_count = item.get('video_view_count')
        organic_video_view_count = item.get('organic_video_view_count')
        
        # Check nested structures - Instagram sometimes stores views in different places
        # Check video_versions for play_count
        if play_count is None and video_versions:
            for video in video_versions:
                if video.get('play_count') is not None:
                    play_count = video.get('play_count')
                    print(f"  ✓ Found play_count in video_versions: {play_count:,}")
                    break
        
        # Check additional fields that might contain view counts
        if play_count is None:
            play_count = item.get('video_play_count') or item.get('reel_view_count') or item.get('viewer_count')
        
        # Check in additional_info or insights if available
        additional_info = item.get('additional_info') or {}
        if play_count is None and additional_info:
            play_count = additional_info.get('play_count') or additional_info.get('view_count')

        # Check insights if available (for own posts)
        insights = item.get('insights') or {}
        if play_count is None and insights:
            play_count = insights.get('play_count') or insights.get('video_views')
        
        extracted['engagement'] = {
            "like_count": item.get('like_count', 0),
            "comment_count": item.get('comment_count', 0),
            "play_count": play_count,
            "view_count": view_count,
            "video_view_count": video_view_count,
            "organic_video_view_count": organic_video_view_count,
            "view_counts_disabled": like_and_view_counts_disabled,
        }
        
        # Debug: Print what we found
        if play_count is not None:
            print(f"  ✓ Found play_count in GraphQL: {play_count:,}")
        elif view_count is not None:
            print(f"  ✓ Found view_count in GraphQL: {view_count:,}")
        elif video_view_count is not None:
            print(f"  ✓ Found video_view_count in GraphQL: {video_view_count:,}")
            extracted['engagement']['play_count'] = video_view_count
        elif organic_video_view_count is not None:
            print(f"  ✓ Found organic_video_view_count in GraphQL: {organic_video_view_count:,}")
            extracted['engagement']['play_count'] = organic_video_view_count
        
        likes_n = item.get('like_count') or 0
        comments_n = item.get('comment_count') or 0
        eng = extracted['engagement']
        has_positive_views = _best_positive_view_metric(
            eng.get('play_count'),
            eng.get('view_count'),
            eng.get('video_view_count'),
            eng.get('organic_video_view_count'),
        ) is not None

        # GraphQL often omits views or sends 0/null while likes/comments exist — still try HTML / REST.
        # When like_and_view_counts_disabled is True, Instagram may still embed metrics in page JSON
        # or serve them from /api/v1/media/.../info/ — try unless opted out via env.
        allow_when_disabled = _views_fallback_when_counts_disabled()
        try_view_fallback = (
            session
            and url
            and csrf_token
            and not has_positive_views
            and (likes_n > 0 or comments_n > 0)
            and (not like_and_view_counts_disabled or allow_when_disabled)
        )

        # Try to get view count from Instagram API if not available in GraphQL response
        if try_view_fallback:
            if like_and_view_counts_disabled:
                print(
                    "  Attempting view fallbacks (GraphQL marked view counts disabled; may still recover from HTML/API)..."
                )
            else:
                print("  Attempting to get view count from multiple sources...")

            html_view_count = extract_view_count_from_html(session, url, shortcode=shortcode)
            if html_view_count is not None:
                extracted['engagement']['play_count'] = html_view_count
                print(f"  ✓ Got view count from HTML: {html_view_count:,}")
            else:
                print("  Attempting to get view count from Instagram API...")
                media_id = extract_media_id_from_graphql_data(data)
                if not media_id:
                    print("  Trying HTML parsing to extract media ID...")
                    media_id = extract_media_id_from_html(session, url)

                if media_id:
                    print(f"  Using media ID: {media_id}")
                    view_count = get_view_count_from_api(
                        session, media_id, csrf_token, cookie_file=cookie_file, account=account
                    )
                    if view_count is not None:
                        extracted['engagement']['play_count'] = view_count
                        print(f"  ✓ Got view count from API: {view_count:,}")
                    else:
                        print(f"  ✗ Could not get view count from API (media_id: {media_id})")
                        print(f"  Debug: Checking API response structure...")
                else:
                    print(f"  ✗ Could not extract media ID")
                    print(f"  Debug: Available item keys: {list(item.keys())[:20]}")
        
        _coalesce_views_engagement(extracted['engagement'])
        if extracted['engagement'].get('play_count') is None and extracted['engagement'].get('views') is not None:
            extracted['engagement']['play_count'] = extracted['engagement']['views']

        # Extract user information
        user = item.get('user') or {}
        extracted['user'] = {
            "username": user.get('username', ''),
            "full_name": user.get('full_name', ''),
            "profile_pic_url": user.get('profile_pic_url', ''),
            "is_verified": user.get('is_verified', False),
            "is_private": user.get('is_private', False),
        }

        # Extract caption
        caption = item.get('caption') or {}
        extracted['caption'] = caption.get('text', '') if isinstance(caption, dict) else ''
        
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

