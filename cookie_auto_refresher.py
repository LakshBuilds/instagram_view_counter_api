"""
Instagram Cookie Auto Refresher - Updated for 2025/2026
Uses Selenium with realistic browser profile to avoid Instagram detection
"""

import os
import time
import random
from pathlib import Path
from typing import Dict, List, Optional

AUTO_COOKIE_REFRESH_ENABLED = os.getenv("AUTO_COOKIE_REFRESH", "false").lower() in (
    "1", "true", "yes",
)

REQUIRED_COOKIES: List[str] = [
    "csrftoken",
    "sessionid", 
    "ds_user_id",
    "mid",
    "ig_did",
    "ig_nrcb",
    "rur",
    "datr",
]


def get_cookie_file_path(username: Optional[str] = None) -> Path:
    """Get the cookie file path for a specific account or default"""
    if username:
        return Path(f"cookies_{username}.txt")
    return Path(os.getenv("INSTAGRAM_COOKIES_FILE", "cookies.txt"))


def _write_cookie_file(cookies: Dict[str, str], cookie_file: Path) -> None:
    """Persist cookies to file in KEY=VALUE format."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    
    lines = [
        "# Instagram Cookies",
        f"# Automatically refreshed at {timestamp}",
        "# Format: cookie_name=cookie_value",
        "",
    ]

    seen = set()
    for name in REQUIRED_COOKIES:
        if name in cookies and name not in seen:
            lines.append(f"{name}={cookies[name]}")
            seen.add(name)
    
    for name, value in cookies.items():
        if name not in seen:
            lines.append(f"{name}={value}")
            seen.add(name)

    cookie_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"   ✅ Cookies saved to {cookie_file}")


def human_delay(min_sec: float = 0.5, max_sec: float = 2.0):
    """Random human-like delay"""
    time.sleep(random.uniform(min_sec, max_sec))


def human_typing(element, text: str, min_delay: float = 0.08, max_delay: float = 0.18):
    """Type text with human-like delays"""
    for char in text:
        element.send_keys(char)
        delay = random.uniform(min_delay, max_delay)
        if random.random() < 0.1:
            delay += random.uniform(0.3, 0.6)
        time.sleep(delay)


def _create_realistic_chrome_driver():
    """
    Create Chrome driver with realistic browser profile.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    
    options = Options()
    
    # Window size like real user
    options.add_argument("--window-size=1366,768")
    options.add_argument("--start-maximized")
    
    # Disable automation flags
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # Real Chrome user agent (Chrome 131 - latest stable)
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
    
    # Performance and stability
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    
    # Language settings
    options.add_argument("--lang=en-US")
    options.add_experimental_option('prefs', {
        'intl.accept_languages': 'en-US,en',
        'credentials_enable_service': False,
        'profile.password_manager_enabled': False
    })
    
    # Check headless mode
    show_browser = os.getenv("SHOW_BROWSER", "true").lower() in ("1", "true", "yes")
    if not show_browser:
        options.add_argument("--headless=new")
    
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
    except:
        service = None
    
    if service:
        driver = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)
    
    # Execute stealth scripts to hide automation
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            // Remove webdriver property
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            
            // Add plugins (real browsers have plugins)
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
                    {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
                    {name: 'Native Client', filename: 'internal-nacl-plugin'}
                ]
            });
            
            // Set languages
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            
            // Add chrome runtime
            window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}};
            
            // Fix permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // Add realistic screen properties
            Object.defineProperty(screen, 'availWidth', {get: () => 1366});
            Object.defineProperty(screen, 'availHeight', {get: () => 728});
            Object.defineProperty(screen, 'width', {get: () => 1366});
            Object.defineProperty(screen, 'height', {get: () => 768});
            Object.defineProperty(screen, 'colorDepth', {get: () => 24});
            Object.defineProperty(screen, 'pixelDepth', {get: () => 24});
        """
    })
    
    driver.set_page_load_timeout(60)
    print("   ✅ Created realistic Chrome browser profile")
    return driver


def auto_refresh_cookies(
    username: Optional[str] = None,
    password: Optional[str] = None,
    reason: str = ""
) -> bool:
    """
    Refresh Instagram cookies using Selenium with realistic browser profile.
    """
    
    username = username or os.getenv("INSTAGRAM_USERNAME") or os.getenv("INSTA_USERNAME")
    password = password or os.getenv("INSTAGRAM_PASSWORD") or os.getenv("INSTA_PASSWORD")
    
    if not username or not password:
        print("❌ Missing credentials. Set INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD env vars.")
        return False
    
    cookie_file = get_cookie_file_path(username)
    
    print(f"\n🔄 Starting cookie refresh for: {username}")
    if reason:
        print(f"   Reason: {reason}")
    
    driver = None
    try:
        driver = _create_realistic_chrome_driver()
    except Exception as e:
        print(f"   ❌ Failed to create browser: {e}")
        return False
    
    try:
        success = _perform_login(driver, username, password)
        if success:
            cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
            _write_cookie_file(cookies, cookie_file)
            print(f"✅ Cookies refreshed successfully for {username}!")
            return True
        else:
            print(f"❌ Login failed for {username}")
            return False
    except Exception as e:
        print(f"❌ Error during login: {e}")
        return False
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


def _perform_login(driver, username: str, password: str) -> bool:
    """Perform the actual Instagram login with human-like behavior"""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.action_chains import ActionChains
    
    LOGIN_URL = "https://www.instagram.com/accounts/login/"
    
    print("   📱 Loading Instagram...")
    
    # First visit Instagram homepage to get initial cookies
    driver.get("https://www.instagram.com/")
    human_delay(3, 5)
    
    # Now go to login page
    print("   📱 Going to login page...")
    driver.get(LOGIN_URL)
    human_delay(4, 6)
    
    wait = WebDriverWait(driver, 30)
    
    # Handle cookie consent popup (EU)
    try:
        cookie_buttons = driver.find_elements(By.XPATH, 
            "//button[contains(text(), 'Allow') or contains(text(), 'Accept') or contains(text(), 'Only allow essential') or contains(text(), 'Decline optional')]")
        if cookie_buttons:
            human_delay(1, 2)
            cookie_buttons[0].click()
            human_delay(2, 3)
            print("   ✅ Handled cookie consent")
    except:
        pass
    
    # Random mouse movements to simulate human
    try:
        actions = ActionChains(driver)
        for _ in range(3):
            actions.move_by_offset(random.randint(-50, 50), random.randint(-50, 50))
            actions.pause(random.uniform(0.1, 0.3))
        actions.perform()
        actions.reset_actions()
    except:
        pass
    
    # Find username field - Updated for Instagram's new 2025/2026 interface
    print("   ⌨️ Entering username...")
    username_field = None
    
    # New Instagram interface uses different selectors
    selectors = [
        (By.CSS_SELECTOR, "input[autocomplete='username']"),
        (By.CSS_SELECTOR, "input[name='username']"),
        (By.CSS_SELECTOR, "input[aria-label*='Phone number, username']"),
        (By.CSS_SELECTOR, "input[aria-label*='phone']"),
        (By.CSS_SELECTOR, "input[aria-label*='email']"),
        (By.CSS_SELECTOR, "input[type='text']"),
        (By.XPATH, "//input[@autocomplete='username']"),
        (By.XPATH, "//input[contains(@aria-label, 'Phone')]"),
        (By.XPATH, "//input[contains(@aria-label, 'username')]"),
        (By.XPATH, "//form//input[@type='text']"),
    ]
    
    # Wait for page to fully load
    human_delay(2, 3)
    
    for by, selector in selectors:
        try:
            elements = driver.find_elements(by, selector)
            for elem in elements:
                if elem.is_displayed() and elem.is_enabled():
                    username_field = elem
                    print(f"   ✅ Found username field with: {selector}")
                    break
            if username_field:
                break
        except Exception as e:
            continue
    
    # Last resort - find first visible text input
    if not username_field:
        try:
            all_inputs = driver.find_elements(By.TAG_NAME, "input")
            for inp in all_inputs:
                if inp.is_displayed() and inp.get_attribute("type") in ["text", "email", "tel"]:
                    username_field = inp
                    print(f"   ✅ Found input field by tag")
                    break
        except:
            pass
    
    if not username_field:
        print("   ❌ Could not find username field")
        # Take screenshot for debugging
        try:
            driver.save_screenshot("login_page_debug.png")
            print("   📸 Screenshot saved to login_page_debug.png")
        except:
            pass
        return False
    
    # Click and type username with human behavior
    human_delay(0.5, 1)
    username_field.click()
    human_delay(0.3, 0.6)
    username_field.clear()
    human_typing(username_field, username)
    human_delay(0.8, 1.5)
    
    # Find password field - Updated for new interface
    print("   ⌨️ Entering password...")
    password_field = None
    
    pwd_selectors = [
        (By.CSS_SELECTOR, "input[autocomplete='current-password']"),
        (By.CSS_SELECTOR, "input[name='password']"),
        (By.CSS_SELECTOR, "input[type='password']"),
        (By.XPATH, "//input[@type='password']"),
        (By.XPATH, "//input[@autocomplete='current-password']"),
    ]
    
    human_delay(0.5, 1)
    
    for by, selector in pwd_selectors:
        try:
            elements = driver.find_elements(by, selector)
            for elem in elements:
                if elem.is_displayed() and elem.is_enabled():
                    password_field = elem
                    print(f"   ✅ Found password field")
                    break
            if password_field:
                break
        except:
            continue
    
    if not password_field:
        print("   ❌ Could not find password field")
        return False
    
    human_delay(0.5, 1)
    password_field.click()
    human_delay(0.3, 0.6)
    password_field.clear()
    human_typing(password_field, password)
    human_delay(1, 2)
    
    # Click login button
    print("   🔐 Clicking login button...")
    try:
        login_button = None
        btn_selectors = [
            (By.XPATH, "//button[@type='submit']"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.XPATH, "//button[contains(text(), 'Log in') or contains(text(), 'Log In')]"),
        ]
        
        for by, selector in btn_selectors:
            try:
                login_button = driver.find_element(by, selector)
                if login_button and login_button.is_enabled():
                    break
            except:
                continue
        
        if login_button:
            human_delay(0.5, 1)
            login_button.click()
        else:
            password_field.send_keys(Keys.ENTER)
    except Exception as e:
        print(f"   ⚠️ Click failed, using Enter key: {e}")
        password_field.send_keys(Keys.ENTER)
    
    print("   ⏳ Waiting for login to complete...")
    print("   📺 If CAPTCHA appears, complete it manually in the browser window")
    print("   ⏰ You have 3 minutes to complete any challenges...")
    
    # Wait for login
    max_wait = 180
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        try:
            current_url = driver.current_url
            cookies = driver.get_cookies()
            cookie_names = {c.get("name") for c in cookies}
            
            if "sessionid" in cookie_names and "csrftoken" in cookie_names:
                print("   ✅ Session cookies detected!")
                print("   ⏳ Waiting 10 seconds for all cookies to load...")
                time.sleep(10)
                # Navigate to home page to get more cookies
                try:
                    driver.get("https://www.instagram.com/")
                    time.sleep(5)
                except:
                    pass
                return True
            
            if "login" not in current_url.lower() and "challenge" not in current_url.lower() and "accounts" not in current_url.lower():
                human_delay(2, 3)
                cookies = driver.get_cookies()
                cookie_names = {c.get("name") for c in cookies}
                if "sessionid" in cookie_names:
                    print("   ✅ Login successful!")
                    print("   ⏳ Waiting 10 seconds for all cookies to load...")
                    time.sleep(10)
                    # Navigate to home page to get more cookies
                    try:
                        driver.get("https://www.instagram.com/")
                        time.sleep(5)
                    except:
                        pass
                    return True
            
            # Handle popups
            try:
                not_now = driver.find_elements(By.XPATH, 
                    "//button[contains(text(), 'Not Now') or contains(text(), 'Not now')]")
                if not_now:
                    human_delay(0.5, 1)
                    not_now[0].click()
                    human_delay(1, 2)
            except:
                pass
            
            elapsed = int(time.time() - start_time)
            if elapsed % 15 == 0:
                print(f"   ⏳ Waiting... ({elapsed}s/{max_wait}s)")
            
            time.sleep(2)
            
        except Exception as e:
            if "disconnected" in str(e).lower():
                print(f"   ❌ Browser disconnected: {e}")
                return False
            time.sleep(2)
    
    print("   ❌ Login timed out")
    return False


def refresh_all_accounts() -> Dict[str, bool]:
    """Refresh cookies for all configured accounts"""
    try:
        from multi_account_config import MULTI_ACCOUNT_CONFIG
        accounts = MULTI_ACCOUNT_CONFIG.get("accounts", [])
    except ImportError:
        print("❌ Could not import multi_account_config")
        return {}
    
    results = {}
    for account in accounts:
        username = account.get("username")
        password = account.get("password")
        if username and password:
            print(f"\n{'='*50}")
            success = auto_refresh_cookies(username, password, "Batch refresh")
            results[username] = success
            human_delay(5, 10)
    
    print(f"\n{'='*50}")
    print("📊 Refresh Results:")
    for username, success in results.items():
        status = "✅" if success else "❌"
        print(f"   {status} {username}")
    
    return results


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        username = sys.argv[1]
        password = sys.argv[2] if len(sys.argv) > 2 else None
        auto_refresh_cookies(username, password, "Manual refresh")
    else:
        refresh_all_accounts()
