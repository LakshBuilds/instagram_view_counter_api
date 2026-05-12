"""
Fallback scraper using instagrapi (mobile/private API endpoints).

Used by api.py when our primary GraphQL path fails (401 cookies-stale, or
returns no views). instagrapi hits `i.instagram.com/api/v1/...` which has
a different throttle counter than the web GraphQL — so when web is blocked,
mobile sometimes still works, and vice versa.

Engagement payload returned matches our standard shape:
    {
        "like_count": int,
        "comment_count": int,
        "play_count": int|None,
        "view_count": int|None,
        "video_view_count": int|None,
        "organic_video_view_count": int|None,
        "views": int|None
    }

Plus shortcode, user, caption, timestamp, video_urls.

This module is import-time-safe even when instagrapi isn't installed —
all imports are inside the functions, and the loaders catch ImportError
and return None.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional


def _shortcode_from_url(url: str) -> Optional[str]:
    m = re.search(r"instagram\.com/(?:[^/]+/)?(?:reels?|p)/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else None


def _load_session_cookies(cookie_file: str) -> Dict[str, str]:
    """Parse our flat cookies_<account>.txt file into a dict."""
    cookies: Dict[str, str] = {}
    path = Path(cookie_file)
    if not path.exists():
        return cookies
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        cookies[k.strip()] = v.strip()
    return cookies


def _build_client(cookie_file: str):
    """Construct an authenticated instagrapi Client from our cookie file."""
    from instagrapi import Client

    cookies = _load_session_cookies(cookie_file)
    sid = cookies.get("sessionid")
    if not sid:
        return None

    cl = Client()
    # instagrapi accepts a settings dict that includes the cookie jar.
    # The mobile API needs at minimum: sessionid, csrftoken, ds_user_id.
    settings = {
        "cookies": {
            "sessionid": sid,
            "csrftoken": cookies.get("csrftoken", ""),
            "ds_user_id": cookies.get("ds_user_id", ""),
            "mid": cookies.get("mid", ""),
            "ig_did": cookies.get("ig_did", ""),
        },
        "authorization_data": {
            "ds_user_id": cookies.get("ds_user_id", ""),
            "sessionid": sid,
        },
        "user_agent": "Instagram 269.0.0.18.75 Android (33/13; 420dpi; 1080x2400; samsung; SM-S908E; b0q; qcom; en_US; 314665256)",
    }
    try:
        cl.set_settings(settings)
        # Don't call cl.login() — that does a full re-auth.
        # set_settings populates the session; we then use the public methods directly.
    except Exception:
        pass
    return cl


def fetch_engagement(url: str, cookie_file: str, account: str = "") -> Optional[dict]:
    """Try to fetch engagement via instagrapi. Returns None on failure."""
    try:
        from instagrapi.exceptions import LoginRequired, ChallengeRequired, ClientError
    except ImportError:
        print("  ⚠️  instagrapi not installed — skipping mobile-API fallback")
        return None

    shortcode = _shortcode_from_url(url)
    if not shortcode:
        return None

    cl = _build_client(cookie_file)
    if cl is None:
        print("  ⚠️  No usable cookies for instagrapi fallback")
        return None

    print(f"  📱 Trying mobile API (instagrapi) for {shortcode} via {account or 'default'}")
    try:
        media = cl.media_info_by_shortcode(shortcode)
    except (LoginRequired, ChallengeRequired) as e:
        print(f"  ✗ instagrapi auth failed: {type(e).__name__}")
        return None
    except ClientError as e:
        print(f"  ✗ instagrapi client error: {e}")
        return None
    except Exception as e:
        print(f"  ✗ instagrapi error: {e}")
        return None

    # `media` is a pydantic model — pull the fields we care about
    def _g(name):
        return getattr(media, name, None)

    play_count = _g("play_count") or _g("video_play_count") or _g("view_count")
    like_count = _g("like_count") or 0
    comment_count = _g("comment_count") or 0
    user = _g("user")
    username = getattr(user, "username", None) if user else None

    video_urls: List[dict] = []
    vu = _g("video_url")
    if vu:
        video_urls.append({"url": vu, "type": 101})

    extracted = {
        "shortcode": shortcode,
        "engagement": {
            "like_count": like_count,
            "comment_count": comment_count,
            "play_count": play_count,
            "view_count": play_count,
            "video_view_count": _g("video_view_count"),
            "organic_video_view_count": None,
            "views": play_count,
        },
        "user": {
            "username": username or "",
            "full_name": getattr(user, "full_name", "") if user else "",
            "profile_pic_url": str(getattr(user, "profile_pic_url", "") or "") if user else "",
            "is_verified": getattr(user, "is_verified", False) if user else False,
            "is_private": getattr(user, "is_private", False) if user else False,
        },
        "caption": (_g("caption_text") or "")[:5000],
        "timestamp": int(_g("taken_at").timestamp()) if _g("taken_at") else None,
        "video_urls": video_urls,
        "thumbnail_urls": [],
    }
    print(f"  ✓ instagrapi returned views={play_count} likes={like_count}")
    return extracted


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: scraper_instagrapi.py <reel_url> <cookie_file>")
        sys.exit(1)
    out = fetch_engagement(sys.argv[1], sys.argv[2])
    print(json.dumps(out, indent=2, default=str) if out else "no result")
