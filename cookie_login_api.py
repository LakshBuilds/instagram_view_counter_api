"""
HTTP-only Instagram login — no browser, no Selenium, no Chrome.

Replicates what a browser does when you submit the login form:
  1. GET /accounts/login/ → receive `csrftoken` + `mid` cookies
  2. POST /api/v1/web/accounts/login/ajax/ with the `enc_password` field
  3. If `authenticated: true` → grab the session cookies that Instagram set

Memory footprint: a few MB (vs Selenium's ~500-700 MB for headless Chromium).
Suitable for the 1 GB VM where running Chrome is risky.

Limitations vs Selenium:
  - Cannot complete checkpoint flows (email/SMS OTP, "tap to confirm on phone").
    When the account is in checkpoint state, Instagram returns
    `checkpoint_url` in the JSON response — we surface that as a clear error
    so the operator knows to log in once from a phone to clear it.
  - Cannot fill 2FA prompts.

For the Instagram-side password "encryption": we use the v0 plaintext form
(`#PWD_INSTAGRAM_BROWSER:0:<ts>:<plaintext>`). Instagram's web frontend still
accepts this on the AJAX login endpoint. If they tighten this to require
libsodium-encrypted passwords, we can add PyNaCl encryption — the encryption
key is exposed in the `/data/shared_data/` JSON.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests

INSTAGRAM_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
INSTAGRAM_APP_ID = "936619743392459"  # public web app id
LOGIN_PAGE_URL = "https://www.instagram.com/accounts/login/"
LOGIN_AJAX_URL = "https://www.instagram.com/api/v1/web/accounts/login/ajax/"

# Same set scraper expects when validating a cookie file.
REQUIRED_COOKIES = ("sessionid", "csrftoken", "ds_user_id", "mid", "ig_did")


class LoginResult:
    __slots__ = ("ok", "cookies", "reason", "raw")

    def __init__(
        self,
        ok: bool,
        cookies: Optional[Dict[str, str]] = None,
        reason: Optional[str] = None,
        raw: Optional[dict] = None,
    ):
        self.ok = ok
        self.cookies = cookies or {}
        self.reason = reason
        self.raw = raw or {}

    def __repr__(self):
        return f"LoginResult(ok={self.ok}, reason={self.reason!r}, cookies={len(self.cookies)} entries)"


def login_via_api(username: str, password: str, *, timeout: int = 20) -> LoginResult:
    """HTTP-only login. Returns LoginResult with cookies on success, reason on failure."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": INSTAGRAM_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "*/*",
        }
    )

    # Step 1 — touch the login page so Instagram sets csrftoken + mid
    try:
        r = session.get(LOGIN_PAGE_URL, timeout=timeout)
    except requests.RequestException as e:
        return LoginResult(False, reason=f"GET login page network error: {e}")
    if r.status_code != 200:
        return LoginResult(False, reason=f"GET login page returned HTTP {r.status_code}")

    csrf = session.cookies.get("csrftoken")
    if not csrf:
        return LoginResult(False, reason="No csrftoken cookie received from login page")

    # Step 2 — POST credentials. v0 password format = plaintext (still accepted by web AJAX).
    enc_password = f"#PWD_INSTAGRAM_BROWSER:0:{int(time.time())}:{password}"
    headers = {
        "X-CSRFToken": csrf,
        "X-IG-App-ID": INSTAGRAM_APP_ID,
        "X-Requested-With": "XMLHttpRequest",
        "X-Instagram-AJAX": "1",
        "Referer": LOGIN_PAGE_URL,
        "Origin": "https://www.instagram.com",
    }
    data = {
        "username": username,
        "enc_password": enc_password,
        "queryParams": "{}",
        "optIntoOneTap": "false",
        "trustedDeviceRecords": "{}",
    }

    try:
        r = session.post(LOGIN_AJAX_URL, headers=headers, data=data, timeout=timeout)
    except requests.RequestException as e:
        return LoginResult(False, reason=f"POST login network error: {e}")

    try:
        body = r.json()
    except json.JSONDecodeError:
        snippet = r.text[:200].replace("\n", " ")
        return LoginResult(
            False,
            reason=f"Login response not JSON (HTTP {r.status_code}): {snippet}",
        )

    if body.get("authenticated") is True:
        cookies = {c.name: c.value for c in session.cookies}
        # Sanity check — sessionid is the bare minimum we need
        if not cookies.get("sessionid"):
            return LoginResult(
                False,
                reason="authenticated=true but no sessionid cookie set",
                raw=body,
            )
        return LoginResult(True, cookies=cookies, raw=body)

    # Friendly failure modes
    if body.get("checkpoint_url"):
        return LoginResult(
            False,
            reason=(
                f"checkpoint_required — Instagram needs human verification for {username}. "
                f"Log in from the IG phone app once to clear it. "
                f"checkpoint_url={body.get('checkpoint_url')}"
            ),
            raw=body,
        )
    if body.get("two_factor_required"):
        return LoginResult(
            False,
            reason=f"2FA required for {username} — HTTP login cannot complete this flow.",
            raw=body,
        )
    if body.get("message"):
        # e.g. "Please wait a few minutes before you try again."
        return LoginResult(False, reason=f"{body.get('message')}", raw=body)
    if body.get("error_type"):
        return LoginResult(False, reason=f"error_type={body.get('error_type')}", raw=body)

    return LoginResult(False, reason=f"login failed: {json.dumps(body)[:300]}", raw=body)


def _write_cookie_file(cookies: Dict[str, str], path: Path) -> None:
    """Write cookies in the same format that cookie_auto_refresher uses."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# Instagram Cookies",
        f"# Automatically refreshed at {timestamp} (via HTTP login)",
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
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def refresh_via_api(username: str, password: str, cookie_file: Optional[Path] = None) -> bool:
    """Drop-in HTTP-only replacement for cookie_auto_refresher.auto_refresh_cookies.

    On success, writes the cookies to `cookies_<username>.txt` (or the path
    you pass in) and returns True. On failure prints the reason and returns False.
    """
    target = cookie_file or Path(f"cookies_{username}.txt")
    print(f"🔐 HTTP login for {username} …")
    result = login_via_api(username, password)
    if result.ok:
        _write_cookie_file(result.cookies, target)
        print(f"   ✅ HTTP login succeeded — cookies written to {target}")
        return True
    print(f"   ❌ HTTP login failed for {username}: {result.reason}")
    return False


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: python3 cookie_login_api.py <username> <password>")
        sys.exit(1)
    ok = refresh_via_api(sys.argv[1], sys.argv[2])
    sys.exit(0 if ok else 1)
