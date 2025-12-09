import os
import time
from pathlib import Path
from typing import Dict, List

AUTO_COOKIE_REFRESH_ENABLED = os.getenv("AUTO_COOKIE_REFRESH", "false").lower() in (
    "1",
    "true",
    "yes",
)

COOKIES_FILE = Path(os.getenv("INSTAGRAM_COOKIES_FILE", "cookies.txt"))
LOGIN_URL = "https://www.instagram.com/accounts/login/"

REQUIRED_COOKIES: List[str] = [
    "csrftoken",
    "sessionid",
    "ds_user_id",
    "datr",
    "ig_did",
    "ig_nrcb",
    "ps_l",
    "ps_n",
    "wd",
    "rur",
    "dpr",
]


def _write_cookie_file(cookies: Dict[str, str]) -> None:
    """Persist cookies to cookies.txt in the existing simple KEY=VALUE format."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    ordered_names = REQUIRED_COOKIES + [
        name for name in cookies.keys() if name not in REQUIRED_COOKIES
    ]

    lines = [
        "# Instagram Cookies",
        f"# Automatically refreshed at {timestamp}",
        "# Format: cookie_name=cookie_value",
        "",
    ]

    seen = set()
    for name in ordered_names:
        if name in cookies and name not in seen:
            value = cookies[name]
            lines.append(f"{name}={value}")
            seen.add(name)

    COOKIES_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def auto_refresh_cookies(reason: str = "") -> bool:
    """
    Attempt to refresh cookies by logging into Instagram with Selenium.

    Returns:
        bool: True if cookies were refreshed successfully.
    """
    if not AUTO_COOKIE_REFRESH_ENABLED:
        print(
            "Auto cookie refresh disabled. Set AUTO_COOKIE_REFRESH=1 to enable automatic login."
        )
        return False

    username = (
        os.getenv("INSTAGRAM_USERNAME")
        or os.getenv("INSTA_USERNAME")
        or os.getenv("INSTAGRAM_USER")
    )
    password = (
        os.getenv("INSTAGRAM_PASSWORD")
        or os.getenv("INSTA_PASSWORD")
        or os.getenv("INSTAGRAM_PASS")
    )

    if not username or not password:
        print(
            "Automatic cookie refresh requires INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD environment variables."
        )
        return False

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        print(
            "Selenium is not installed. Please run 'pip install selenium webdriver-manager' to enable auto refresh."
        )
        return False

    print("View count fetch failed. Attempting automatic Instagram login...")
    if reason:
        print(f"   Reason: {reason}")

    # Check if we should show the browser (visible mode)
    show_browser = os.getenv("SHOW_BROWSER", "true").lower() in ("1", "true", "yes")
    if show_browser:
        print("   Opening browser window (visible mode)...")
    
    options = Options()
    if not show_browser:
        options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    if not show_browser:
        options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--window-size=1280,720")
    options.add_argument("--disable-web-security")
    options.add_argument("--disable-features=IsolateOrigins,site-per-process")
    options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        if not show_browser:
            service.creation_flags = 0x08000000  # CREATE_NO_WINDOW on Windows (only in headless)
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(60)
        wait = WebDriverWait(driver, 60)

        print("   Loading Instagram login page...")
        driver.get(LOGIN_URL)
        time.sleep(2)  # Let page load
        
        print("   Entering credentials...")
        wait.until(EC.presence_of_element_located((By.NAME, "username"))).send_keys(
            username
        )
        password_input = wait.until(
            EC.presence_of_element_located((By.NAME, "password"))
        )
        password_input.send_keys(password)
        password_input.send_keys(Keys.ENTER)

        print("   Waiting for login to complete...")
        if show_browser:
            print("   [INFO] Browser is visible - you can manually complete CAPTCHA or security challenges if needed")
        time.sleep(5)  # Initial wait for login processing
        
        # Handle common Instagram popups/dialogs
        try:
            # Cookie consent popup
            cookie_buttons = driver.find_elements(By.XPATH, 
                "//button[contains(text(), 'Allow') or contains(text(), 'Accept') or contains(text(), 'Allow all cookies')]")
            if cookie_buttons:
                cookie_buttons[0].click()
                time.sleep(2)
            
            # "Save Your Login Info?" dialog
            not_now_buttons = driver.find_elements(By.XPATH, 
                "//button[contains(text(), 'Not Now') or contains(text(), 'Not now')]")
            if not_now_buttons:
                not_now_buttons[0].click()
                time.sleep(1)
            
            # "Turn on Notifications" dialog
            not_now_buttons = driver.find_elements(By.XPATH, 
                "//button[contains(text(), 'Not Now') or contains(text(), 'Not now')]")
            if not_now_buttons:
                not_now_buttons[0].click()
                time.sleep(1)
        except:
            pass
        
        # Wait for redirect away from login page or for cookies to appear
        # Longer wait if browser is visible (user might need to complete challenges)
        max_wait = 120 if show_browser else 30
        start_time = time.time()
        check_interval = 3 if show_browser else 1  # Check less frequently if visible (user might be interacting)
        
        while time.time() - start_time < max_wait:
            try:
                if not driver:
                    raise Exception("Browser driver disconnected")
                current_url = driver.current_url
                cookies = driver.get_cookies()
                cookie_names = {c.get("name") for c in cookies}
                
                # Success: we have session cookies
                if "sessionid" in cookie_names and "csrftoken" in cookie_names:
                    print("   [SUCCESS] Session cookies detected!")
                    break
                
                # Success: we're no longer on login page
                if "login" not in current_url.lower() and "accounts" not in current_url.lower():
                    print(f"   [SUCCESS] Redirected to: {current_url}")
                    # Give it a moment to set cookies
                    time.sleep(3)
                    cookies = driver.get_cookies()
                    cookie_names = {c.get("name") for c in cookies}
                    if "sessionid" in cookie_names and "csrftoken" in cookie_names:
                        print("   [SUCCESS] Session cookies found after redirect!")
                        break
                
                # Check for error messages or security challenges
                try:
                    # Check for various error indicators
                    error_selectors = [
                        "[role='alert']",
                        ".error",
                        "#slfErrorAlert",
                        "p[role='alert']",
                        "[data-testid='login-error-message']",
                        "div[role='alert']"
                    ]
                    for selector in error_selectors:
                        error_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        if error_elements:
                            error_text = error_elements[0].text.strip()
                            if error_text and len(error_text) > 3:
                                print(f"   Login error detected: {error_text[:200]}")
                                raise Exception(f"Login failed: {error_text[:200]}")
                    
                    # Check for security challenge indicators
                    challenge_indicators = driver.find_elements(By.CSS_SELECTOR, 
                        "h2, [class*='challenge'], [class*='verify'], [class*='security']")
                    if challenge_indicators:
                        challenge_text = " ".join([e.text for e in challenge_indicators[:3] if e.text])
                        if challenge_text:
                            print(f"   Security challenge detected: {challenge_text[:200]}")
                except Exception as e:
                    if "Login failed" in str(e):
                        raise
                    pass
                
                elapsed = int(time.time() - start_time)
                if show_browser and elapsed % 10 == 0:  # Print status every 10 seconds
                    print(f"   Waiting... ({elapsed}/{max_wait}s) - Check browser window for any challenges")
                time.sleep(check_interval)
            except Exception as e:
                if "session" in str(e).lower() or "disconnected" in str(e).lower():
                    raise
                time.sleep(check_interval)
        
        # Final check
        cookies = driver.get_cookies()
        cookie_names = {c.get("name") for c in cookies}
        if "sessionid" not in cookie_names or "csrftoken" not in cookie_names:
            current_url = driver.current_url
            try:
                page_title = driver.title
                print(f"   Page title: {page_title}")
                # Check for any visible text that might indicate the issue
                body_text = driver.find_element(By.TAG_NAME, "body").text[:300]
                if "challenge" in body_text.lower() or "verify" in body_text.lower():
                    print(f"   Page content suggests security challenge")
            except:
                pass
            raise Exception(f"Failed to get session cookies. Current URL: {current_url}")
        print("   Login successful, extracting cookies...")
        time.sleep(3)  # allow additional cookies to populate

        cookies_dict = {cookie["name"]: cookie["value"] for cookie in driver.get_cookies()}
        _write_cookie_file(cookies_dict)
        print(f"Cookies refreshed automatically and saved to {COOKIES_FILE}")
        return True
    except Exception as exc:
        print(f"Automatic cookie refresh failed: {exc}")
        return False
    finally:
        if driver:
            driver.quit()

                                                                                                                                      