import os
import time
import random
from pathlib import Path
from typing import Dict, List

AUTO_COOKIE_REFRESH_ENABLED = os.getenv("AUTO_COOKIE_REFRESH", "false").lower() in (
    "1",
    "true",
    "yes",
)


def human_like_mouse_move(driver, element):
    """Move mouse to element with human-like curve movement using multiple intermediate points"""
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        
        # Get element location
        element_location = element.location
        element_size = element.size
        target_x = element_location['x'] + element_size['width'] // 2
        target_y = element_location['y'] + element_size['height'] // 2
        
        # Get viewport size
        viewport_width = driver.execute_script("return window.innerWidth")
        viewport_height = driver.execute_script("return window.innerHeight")
        
        # Start from a random position in viewport
        current_x = random.randint(50, min(viewport_width - 50, 500))
        current_y = random.randint(50, min(viewport_height - 50, 400))
        
        # Move mouse through multiple intermediate points (Bezier-like curve)
        actions = ActionChains(driver)
        
        # Calculate intermediate points for curved movement
        num_points = random.randint(3, 6)
        for i in range(num_points):
            progress = (i + 1) / num_points
            
            # Add some randomness to create curve
            curve_offset_x = random.randint(-30, 30) * (1 - progress)
            curve_offset_y = random.randint(-30, 30) * (1 - progress)
            
            # Interpolate position
            next_x = int(current_x + (target_x - current_x) * progress + curve_offset_x)
            next_y = int(current_y + (target_y - current_y) * progress + curve_offset_y)
            
            # Move by offset from current position
            move_x = next_x - current_x
            move_y = next_y - current_y
            
            # Execute small movement
            driver.execute_script(f"""
                var event = new MouseEvent('mousemove', {{
                    'view': window,
                    'bubbles': true,
                    'cancelable': true,
                    'clientX': {next_x},
                    'clientY': {next_y}
                }});
                document.elementFromPoint({next_x}, {next_y})?.dispatchEvent(event);
            """)
            
            current_x = next_x
            current_y = next_y
            
            # Random pause between movements
            time.sleep(random.uniform(0.02, 0.08))
        
        # Final move to element using ActionChains
        actions = ActionChains(driver)
        actions.move_to_element(element)
        
        # Small random offset (humans don't click exactly center)
        offset_x = random.randint(-5, 5)
        offset_y = random.randint(-5, 5)
        actions.move_by_offset(offset_x, offset_y)
        actions.pause(random.uniform(0.1, 0.25))
        actions.perform()
        
        print(f"   🖱️ Mouse moved to element")
        
    except Exception as e:
        print(f"   Mouse movement fallback: {e}")
        # Fallback: just move to element directly
        try:
            from selenium.webdriver.common.action_chains import ActionChains
            actions = ActionChains(driver)
            actions.move_to_element(element).perform()
        except:
            pass


def human_like_typing(element, text, min_delay=0.05, max_delay=0.15):
    """Type text with human-like random delays between keystrokes"""
    for char in text:
        element.send_keys(char)
        # Random delay between keystrokes
        delay = random.uniform(min_delay, max_delay)
        # Occasionally add longer pause (like thinking)
        if random.random() < 0.1:
            delay += random.uniform(0.2, 0.5)
        time.sleep(delay)


def random_scroll(driver):
    """Perform random small scroll to simulate human behavior"""
    try:
        scroll_amount = random.randint(-50, 50)
        driver.execute_script(f"window.scrollBy(0, {scroll_amount})")
        time.sleep(random.uniform(0.1, 0.3))
    except:
        pass


def random_mouse_wiggle(driver):
    """Small random mouse movements to simulate human behavior"""
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        
        actions = ActionChains(driver)
        
        # Small random movements
        for _ in range(random.randint(2, 5)):
            x_offset = random.randint(-20, 20)
            y_offset = random.randint(-20, 20)
            actions.move_by_offset(x_offset, y_offset)
            actions.pause(random.uniform(0.05, 0.15))
        
        actions.perform()
        actions.reset_actions()
    except:
        pass

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
        time.sleep(random.uniform(2, 4))  # Random wait for page load
        
        # Random mouse movements before interacting
        print("   Simulating human behavior...")
        random_mouse_wiggle(driver)
        time.sleep(random.uniform(0.5, 1.5))
        random_scroll(driver)
        
        print("   Entering credentials with human-like typing...")
        
        # Find and interact with username field
        username_field = wait.until(EC.presence_of_element_located((By.NAME, "username")))
        human_like_mouse_move(driver, username_field)
        time.sleep(random.uniform(0.3, 0.7))
        username_field.click()
        time.sleep(random.uniform(0.2, 0.5))
        
        # Type username with human-like delays
        human_like_typing(username_field, username)
        time.sleep(random.uniform(0.5, 1.0))
        
        # Random mouse wiggle between fields
        random_mouse_wiggle(driver)
        
        # Find and interact with password field
        password_input = wait.until(EC.presence_of_element_located((By.NAME, "password")))
        human_like_mouse_move(driver, password_input)
        time.sleep(random.uniform(0.3, 0.7))
        password_input.click()
        time.sleep(random.uniform(0.2, 0.5))
        
        # Type password with human-like delays
        human_like_typing(password_input, password)
        time.sleep(random.uniform(0.5, 1.5))
        
        # Random pause before clicking login (like human reviewing)
        random_mouse_wiggle(driver)
        time.sleep(random.uniform(0.5, 1.0))
        
        # Find and click login button instead of pressing Enter
        try:
            login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
            human_like_mouse_move(driver, login_button)
            time.sleep(random.uniform(0.2, 0.5))
            login_button.click()
        except:
            # Fallback to Enter key
            password_input.send_keys(Keys.ENTER)

        print("   Waiting for login to complete...")
        if show_browser:
            print("   [INFO] Browser is visible - you can manually complete CAPTCHA or security challenges if needed")
        time.sleep(5)  # Initial wait for login processing
        
        # Handle common Instagram popups/dialogs with human-like behavior
        try:
            time.sleep(random.uniform(1, 2))
            
            # Cookie consent popup
            cookie_buttons = driver.find_elements(By.XPATH, 
                "//button[contains(text(), 'Allow') or contains(text(), 'Accept') or contains(text(), 'Allow all cookies')]")
            if cookie_buttons:
                human_like_mouse_move(driver, cookie_buttons[0])
                time.sleep(random.uniform(0.3, 0.7))
                cookie_buttons[0].click()
                time.sleep(random.uniform(1.5, 3))
            
            # "Save Your Login Info?" dialog
            not_now_buttons = driver.find_elements(By.XPATH, 
                "//button[contains(text(), 'Not Now') or contains(text(), 'Not now')]")
            if not_now_buttons:
                random_mouse_wiggle(driver)
                time.sleep(random.uniform(0.5, 1.5))
                human_like_mouse_move(driver, not_now_buttons[0])
                time.sleep(random.uniform(0.2, 0.5))
                not_now_buttons[0].click()
                time.sleep(random.uniform(1, 2))
            
            # "Turn on Notifications" dialog
            not_now_buttons = driver.find_elements(By.XPATH, 
                "//button[contains(text(), 'Not Now') or contains(text(), 'Not now')]")
            if not_now_buttons:
                random_mouse_wiggle(driver)
                time.sleep(random.uniform(0.5, 1.0))
                human_like_mouse_move(driver, not_now_buttons[0])
                time.sleep(random.uniform(0.2, 0.5))
                not_now_buttons[0].click()
                time.sleep(random.uniform(1, 2))
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

                                                                                                                                      