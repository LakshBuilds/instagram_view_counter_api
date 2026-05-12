"""
FastAPI wrapper for Instagram Reel Scraper
Expose the scraper as a REST API with request tracking and auto-refresh
Includes async job queue to prevent Render 30s timeout
"""
import os
import time
import random
import math
import uuid
import threading
import json
import re
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict
from scraper import scrape_instagram_reel, get_session_cookies
from request_tracker import log_api_request, get_request_status, get_error_stats
import uvicorn

API_PORT = int(os.getenv("API_PORT", "8002"))

# ============== ASYNC JOB QUEUE ==============
# Prevents Render 30s timeout by using polling pattern.
# JOB_TIMEOUT counts only ACTIVE processing time (set when status flips to
# "processing"). Pending-in-queue jobs aren't subject to it.
JOB_TIMEOUT = int(os.getenv("JOB_TIMEOUT_SEC", "120"))

class JobQueue:
    """
    Async job queue for long-running scrape requests.
    Dashboard submits job → gets ID instantly → polls for result
    """
    def __init__(self):
        self.jobs: Dict[str, dict] = {}
        self.lock = threading.Lock()
    
    def create_job(self, url: str) -> str:
        """Create a new job and return job ID"""
        job_id = f"job_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}"
        with self.lock:
            self.jobs[job_id] = {
                "status": "pending",
                "url": url,
                "result": None,
                "error": None,
                "created_at": time.time(),
                "started_at": None
            }
        return job_id
    
    def update_job(self, job_id: str, status: str, result=None, error=None):
        """Update job status and result"""
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id]["status"] = status
                self.jobs[job_id]["result"] = result
                self.jobs[job_id]["error"] = error
                if status == "processing":
                    self.jobs[job_id]["started_at"] = time.time()
    
    def get_job(self, job_id: str) -> Optional[dict]:
        """Get job by ID, auto-fail if stuck too long"""
        with self.lock:
            job = self.jobs.get(job_id)
            if job and job["status"] == "processing":
                # Check if job is stuck (processing for too long)
                started_at = job.get("started_at")
                if started_at and (time.time() - started_at) > JOB_TIMEOUT:
                    print(f"⚠️ Job {job_id} timed out after {JOB_TIMEOUT}s - marking as failed")
                    job["status"] = "failed"
                    job["error"] = f"Job timed out after {JOB_TIMEOUT} seconds"
            return job
    
    def cleanup_old_jobs(self, max_age: int = 1800):
        """Remove jobs older than max_age seconds (default 30min so queued bursts
        don't get garbage-collected before the trickle gate reaches them)."""
        now = time.time()
        with self.lock:
            old_jobs = [jid for jid, job in self.jobs.items() 
                       if now - job["created_at"] > max_age]
            for jid in old_jobs:
                del self.jobs[jid]
    
    def get_stuck_jobs_count(self) -> int:
        """Count jobs stuck in processing"""
        now = time.time()
        with self.lock:
            return sum(1 for job in self.jobs.values() 
                      if job["status"] == "processing" 
                      and job.get("started_at")
                      and (now - job["started_at"]) > JOB_TIMEOUT)


# Global job queue
job_queue = JobQueue()


# ============== GLOBAL TRICKLE PIPELINE ==============
# All actual Instagram requests go through this single queue. A worker pulls one
# item every GLOBAL_SCRAPE_INTERVAL_SEC and processes it. Result: even if 100 users
# submit 100 reels simultaneously, IG sees one request every N seconds — the
# stampede that triggered today's IP throttle becomes impossible.
import queue as _q

GLOBAL_SCRAPE_INTERVAL_SEC = float(os.getenv("GLOBAL_SCRAPE_INTERVAL_SEC", "6"))
MAX_PENDING_JOBS = int(os.getenv("MAX_PENDING_JOBS", "5000"))

_scrape_queue: "_q.Queue[str]" = _q.Queue(maxsize=MAX_PENDING_JOBS)


# ============== PERSISTENT CACHE + TRICKLE BACKFILL ==============
# Every reel ever scraped is auto-tracked. A background "trickle" worker picks
# the stalest one and refreshes it via the same global queue — so reels stay
# fresh even when nobody opens the dashboard.
TRACKED_FILE = "tracked_reels.json"
CACHE_FILE = "reel_cache.json"
TRICKLE_ENABLED = os.getenv("TRICKLE_ENABLED", "1") == "1"
# Hours between automatic re-refresh of a tracked reel. Once a day = 24.
TRICKLE_REFRESH_AGE_HOURS = float(os.getenv("TRICKLE_REFRESH_AGE_HOURS", "24"))

_cache_lock = threading.Lock()


def _load_json(path: str, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json_atomic(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def _shortcode_of(url: str) -> Optional[str]:
    m = re.search(r"instagram\.com/(?:[^/]+/)?(?:reels?|p)/([A-Za-z0-9_-]+)", url or "")
    return m.group(1) if m else None


def track_reel(url: str) -> None:
    """Register a reel for future trickle refresh."""
    sc = _shortcode_of(url)
    if not sc:
        return
    with _cache_lock:
        tracked = _load_json(TRACKED_FILE, {})
        if sc not in tracked:
            tracked[sc] = {"url": url, "first_seen": datetime.utcnow().isoformat()}
            _save_json_atomic(TRACKED_FILE, tracked)


def cache_reel_data(url: str, engagement: dict, user: dict) -> None:
    """Persist latest scrape result so reads survive API restarts and queue jams."""
    sc = _shortcode_of(url)
    if not sc:
        return
    with _cache_lock:
        cache = _load_json(CACHE_FILE, {})
        cache[sc] = {
            "url": url,
            "engagement": engagement or {},
            "user": user or {},
            "refreshed_at": datetime.utcnow().isoformat(),
        }
        _save_json_atomic(CACHE_FILE, cache)


def get_cached_reel(url: str) -> Optional[dict]:
    sc = _shortcode_of(url)
    if not sc:
        return None
    with _cache_lock:
        return _load_json(CACHE_FILE, {}).get(sc)


def _trickle_worker():
    """Pick the stalest tracked reel and refresh it once per
    GLOBAL_SCRAPE_INTERVAL_SEC × N. Runs forever in background. The actual scrape
    goes through the same global pipeline, so user traffic always has priority
    (trickle just queues alongside)."""
    print(f"🌱 Trickle backfill worker started "
          f"(refresh age threshold: {TRICKLE_REFRESH_AGE_HOURS}h)")
    # Walk slower than the main pipeline — we never want trickle to starve user requests
    trickle_interval = max(GLOBAL_SCRAPE_INTERVAL_SEC * 2, 15.0)
    while True:
        try:
            time.sleep(trickle_interval)
            tracked = _load_json(TRACKED_FILE, {})
            if not tracked:
                continue
            cache = _load_json(CACHE_FILE, {})
            threshold = datetime.utcnow().timestamp() - TRICKLE_REFRESH_AGE_HOURS * 3600
            stalest_sc = None
            stalest_ts = None
            for sc, meta in tracked.items():
                cached = cache.get(sc, {})
                refreshed_at = cached.get("refreshed_at")
                ts = 0.0
                if refreshed_at:
                    try:
                        ts = datetime.fromisoformat(refreshed_at).timestamp()
                    except Exception:
                        ts = 0.0
                if ts < threshold and (stalest_ts is None or ts < stalest_ts):
                    stalest_sc = sc
                    stalest_ts = ts
            if not stalest_sc:
                continue  # nothing stale — keep waiting
            url = tracked[stalest_sc]["url"]
            # Enqueue as a real job — goes through the same pipeline, gets cached on success
            job_id = job_queue.create_job(url)
            print(f"🌱 Trickle refresh: {stalest_sc} (job {job_id})")
            threading.Thread(
                target=process_scrape_job, args=(job_id, url), daemon=True
            ).start()
        except Exception as e:
            print(f"⚠️  Trickle worker error: {e}")
            time.sleep(30)


def _start_background_workers_once():
    """Start trickle once, even if uvicorn imports api.py multiple times."""
    if getattr(_start_background_workers_once, "_started", False):
        return
    _start_background_workers_once._started = True
    if TRICKLE_ENABLED:
        threading.Thread(target=_trickle_worker, daemon=True).start()


class HumanLikeDelay:
    """
    Human-like delay generator to avoid detection.
    Mimics natural browsing patterns with variable delays.
    Now with async job queue, we can use proper human-like delays!
    """
    def __init__(self):
        self.request_count = 0
        self.session_start = time.time()
        
    def get_delay(self) -> float:
        """
        Generate human-like delay to avoid Instagram detection.
        Safe delays that won't get us blocked.
        """
        self.request_count += 1
        
        # Human-like delays (2-5 seconds)
        delay = random.uniform(2.0, 5.0)
        print(f"🕐 Human delay: {delay:.1f}s (request #{self.request_count})")
        return delay
    
    def reset_session(self):
        """Reset for new session"""
        self.request_count = 0
        self.session_start = time.time()


# Global delay generator
human_delay = HumanLikeDelay()

# Legacy env vars (still supported but human-like is default)
HUMAN_LIKE_DELAY = os.getenv('HUMAN_LIKE_DELAY', '1') == '1'  # Enable by default
MIN_REQUEST_DELAY = float(os.getenv('MIN_REQUEST_DELAY', '1'))
MAX_REQUEST_DELAY = float(os.getenv('MAX_REQUEST_DELAY', '3'))
# Opt-in: skip multi-second "human" waits (set FAST_SCRAPE=1). Uses tiny jitter only.
FAST_SCRAPE = os.getenv('FAST_SCRAPE', '0').lower() in ('1', 'true', 'yes')
FAST_SCRAPE_JITTER = float(os.getenv('FAST_SCRAPE_JITTER', '0.2'))  # max extra seconds before scrape


class MultiAccountRotator:
    """
    Rotates between multiple Instagram accounts to distribute load.
    Each account has its own cookie file, request counter, and rate-limit cooldown.
    Park an account temporarily after a 429 / non-JSON response so a single throttled
    account doesn't poison every other request.
    """
    COOLDOWN_SEC = int(os.getenv("ACCOUNT_COOLDOWN_SEC", "900"))  # 15 min default
    # Minimum gap between consecutive requests to the same account. Prevents a frontend
    # burst from hammering one account 20 times in 5 seconds (instant IG throttle).
    MIN_INTERVAL_SEC = float(os.getenv("ACCOUNT_MIN_INTERVAL_SEC", "3"))

    def __init__(self):
        # Accounts must match multi_account_config.py so cookie auto-refresh covers both
        all_accounts = ['bhdemo2025', 'hatke_automation']
        # DISABLED_ACCOUNTS env var lets us park an account temporarily without code edits —
        # useful when Instagram throttles a specific username at the account layer (the
        # "We suspect automated behavior" warning), since fresh cookies don't help.
        disabled = {a.strip() for a in os.getenv('DISABLED_ACCOUNTS', '').split(',') if a.strip()}
        self.accounts = [a for a in all_accounts if a not in disabled] or all_accounts
        if disabled:
            print(f"⚠️  Disabled accounts (skipped by rotator): {sorted(disabled & set(all_accounts))}")

        # Per-account weights — higher = more traffic. Useful when one account is partially
        # throttled (e.g., bhdemo2025 with IG's "automated behavior" warning) but we still
        # want it to take a trickle of requests so it can recover when IG's flag decays.
        # Defaults: equal weight. Override via ACCOUNT_WEIGHTS="bhdemo2025=1,hatke_automation=9"
        weights_env = os.getenv('ACCOUNT_WEIGHTS', '')
        self.weights = {a: 1 for a in self.accounts}
        if weights_env:
            for pair in weights_env.split(','):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    k = k.strip()
                    try:
                        w = max(0, int(v.strip()))
                    except ValueError:
                        continue
                    if k in self.weights:
                        self.weights[k] = w
            if any(self.weights.values()):
                print(f"⚖️  Account weights: {self.weights}")
        # Build a weighted round-robin order (e.g., weights 1+9 → "B H H H H H H H H H")
        self._order: list[str] = []
        for acc in self.accounts:
            self._order.extend([acc] * self.weights.get(acc, 1))
        if not self._order:
            self._order = list(self.accounts)  # all weights 0 → fall back to equal

        self.current_index = 0
        self.request_counts = {acc: 0 for acc in self.accounts}
        self.cooldown_until = {acc: 0.0 for acc in self.accounts}
        self.last_used_at = {acc: 0.0 for acc in self.accounts}
        self.lock = threading.Lock()

    def get_next_account(self) -> str:
        """Weighted round-robin; skip cooled-down accounts; pace each account at MIN_INTERVAL_SEC."""
        chosen = None
        wait_until = 0.0
        with self.lock:
            now = time.time()
            for _ in range(len(self._order)):
                account = self._order[self.current_index]
                self.current_index = (self.current_index + 1) % len(self._order)
                if self.cooldown_until.get(account, 0) <= now:
                    chosen = account
                    next_ok_at = self.last_used_at.get(account, 0) + self.MIN_INTERVAL_SEC
                    if next_ok_at > now:
                        wait_until = next_ok_at
                    self.last_used_at[account] = max(now, next_ok_at)
                    self.request_counts[account] += 1
                    break
            if chosen is None:
                # All cooled down — pick the one whose cooldown expires soonest
                chosen = min(self.accounts, key=lambda a: self.cooldown_until[a])
                next_ok_at = self.last_used_at.get(chosen, 0) + self.MIN_INTERVAL_SEC
                if next_ok_at > now:
                    wait_until = next_ok_at
                self.last_used_at[chosen] = max(now, next_ok_at)
                self.request_counts[chosen] += 1
                print(
                    f"⚠️  All accounts on cooldown — using {chosen} anyway "
                    f"(expires in {max(0, int(self.cooldown_until[chosen] - now))}s)"
                )

        # Sleep OUTSIDE the lock so other requests aren't blocked.
        if wait_until > 0:
            sleep_for = wait_until - time.time()
            if sleep_for > 0:
                print(f"⏳ Pacing {chosen}: sleeping {sleep_for:.1f}s (min interval {self.MIN_INTERVAL_SEC}s)")
                time.sleep(sleep_for)
        print(f"🔄 Using account: {chosen} (request #{self.request_counts[chosen]})")
        return chosen

    def mark_rate_limited(self, account: str) -> None:
        """Park an account for COOLDOWN_SEC after we see a rate-limit signal."""
        with self.lock:
            self.cooldown_until[account] = time.time() + self.COOLDOWN_SEC
        print(f"🚫 Cooling down {account} for {self.COOLDOWN_SEC}s (rate limit detected)")

    def all_cooled_down(self) -> bool:
        """True if every account is currently throttled. Watchdog uses this to trigger refresh."""
        now = time.time()
        with self.lock:
            return all(self.cooldown_until.get(a, 0) > now for a in self.accounts)

    def get_cookie_file(self, account: str) -> str:
        """Get cookie file path for account"""
        return f"cookies_{account}.txt"

    def get_stats(self) -> dict:
        """Get stats for all accounts"""
        now = time.time()
        # current_index points into self._order (the weighted slot list), not self.accounts —
        # using self.accounts[current_index] would IndexError once weights make _order longer.
        current = self._order[self.current_index] if self._order else (self.accounts[0] if self.accounts else None)
        return {
            "accounts": self.accounts,
            "current_account": current,
            "weights": self.weights,
            "request_counts": self.request_counts,
            "total_requests": sum(self.request_counts.values()),
            "cooldown_remaining_sec": {
                acc: max(0, int(self.cooldown_until[acc] - now)) for acc in self.accounts
            },
            "all_cooled_down": all(self.cooldown_until.get(a, 0) > now for a in self.accounts)
        }


# Global account rotator
account_rotator = MultiAccountRotator()
MULTI_ACCOUNT_ENABLED = os.getenv('MULTI_ACCOUNT', '1') == '1'  # Enable by default

app = FastAPI(
    title="Instagram Reel Scraper API",
    description="API to scrape Instagram Reel data including view counts",
    version="1.0.0"
)

# Add CORS middleware to allow direct browser access from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (dashboard can be anywhere)
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods including OPTIONS
    allow_headers=["*"],  # Allow all headers
)


@app.on_event("startup")
def _on_startup():
    _start_background_workers_once()


@app.get("/reel-info")
async def reel_info(url: str = Query(..., description="Instagram reel URL")):
    """Read latest cached engagement (does NOT hit Instagram). Returns whatever
    the most recent successful scrape stored — useful for dashboards that just
    want to display the latest known views without paying the IG round-trip."""
    track_reel(url)  # also register for trickle refresh
    cached = get_cached_reel(url)
    if not cached:
        return JSONResponse(
            status_code=202,
            content={
                "success": True,
                "cached": False,
                "message": "No cached data yet. Reel registered for trickle refresh "
                           "and will be populated within the day. Or POST /api/async/scrape "
                           "for an immediate scrape."
            },
        )
    return {"success": True, "cached": True, **cached}


@app.post("/track")
async def track_reels(urls: List[str] = Query(..., description="Reel URLs to keep refreshed")):
    """Register reels for the daily trickle refresh. Doesn't scrape immediately —
    the background worker will pick them up as it walks the tracked set."""
    added = 0
    for u in urls:
        if _shortcode_of(u):
            track_reel(u)
            added += 1
    return {"success": True, "added": added, "total_tracked": len(_load_json(TRACKED_FILE, {}))}


@app.get("/track")
async def list_tracked():
    """Snapshot of all tracked reels + their last-refresh timestamp."""
    tracked = _load_json(TRACKED_FILE, {})
    cache = _load_json(CACHE_FILE, {})
    return {
        "total": len(tracked),
        "reels": [
            {
                "shortcode": sc,
                "url": meta.get("url"),
                "first_seen": meta.get("first_seen"),
                "last_refresh": (cache.get(sc) or {}).get("refreshed_at"),
                "views": ((cache.get(sc) or {}).get("engagement") or {}).get("views"),
            }
            for sc, meta in tracked.items()
        ],
    }


@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "message": "Instagram Reel Scraper API",
        "version": "1.0.0",
        "endpoints": {
            "/scrape": "POST - Scrape a single reel",
            "/scrape/batch": "POST - Scrape multiple reels",
            "/health": "GET - Health check"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint with request statistics"""
    try:
        status = get_request_status()
        return {
            "status": "healthy",
            "message": "API is ready",
            "version": "1.0.0",
            "request_stats": status
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@app.get("/api/internal/scrape")
async def internal_scrape_get(
    background_tasks: BackgroundTasks,
    url: str = Query(..., description="Instagram Reel URL")
):
    """
    Internal API endpoint for frontend (GET method)
    Now uses async job queue to prevent timeout!
    """
    # Use async pattern to prevent 524 timeout
    job_id = f"job_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}"
    job_queue.jobs[job_id] = {
        "status": "pending",
        "url": url,
        "result": None,
        "error": None,
        "created_at": time.time()
    }
    background_tasks.add_task(process_scrape_job, job_id, url)
    
    return JSONResponse(
        status_code=202,
        content={
            "success": True,
            "job_id": job_id,
            "status": "processing",
            "message": "Job submitted. Poll /api/async/status/{job_id} for result.",
            "poll_url": f"/api/async/status/{job_id}"
        }
    )


@app.post("/api/internal/scrape")
async def internal_scrape_post(
    background_tasks: BackgroundTasks,
    url: str = Query(..., description="Instagram Reel URL")
):
    """
    Internal API endpoint for frontend (POST method)
    Now uses async job queue to prevent timeout!
    """
    # Use async pattern to prevent 524 timeout
    job_id = f"job_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}"
    job_queue.jobs[job_id] = {
        "status": "pending",
        "url": url,
        "result": None,
        "error": None,
        "created_at": time.time()
    }
    background_tasks.add_task(process_scrape_job, job_id, url)
    
    return JSONResponse(
        status_code=202,
        content={
            "success": True,
            "job_id": job_id,
            "status": "processing",
            "message": "Job submitted. Poll /api/async/status/{job_id} for result.",
            "poll_url": f"/api/async/status/{job_id}"
        }
    )


@app.get("/stats")
async def get_request_stats():
    """
    Get current request statistics and rate limit status
    """
    from request_tracker import HOURLY_LIMIT, DAILY_LIMIT, REFRESH_THRESHOLD
    try:
        status = get_request_status()
        multi_account_stats = account_rotator.get_stats() if MULTI_ACCOUNT_ENABLED else None
        return {
            "success": True,
            "stats": status,
            "rate_limits": {
                "hourly_limit": HOURLY_LIMIT,
                "daily_limit": DAILY_LIMIT,
                "auto_refresh_threshold": REFRESH_THRESHOLD
            },
            "multi_account": multi_account_stats,
            "human_like_delay": HUMAN_LIKE_DELAY,
            "fast_scrape": FAST_SCRAPE,
            "fast_scrape_jitter_max_sec": FAST_SCRAPE_JITTER,
            "scraper_fast_graphql": os.getenv('SCRAPER_FAST_GRAPHQL', '0') in ('1', 'true', 'yes'),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": f"Failed to get stats: {str(e)}"
            }
        )


@app.get("/error-stats")
async def get_error_statistics():
    """Get error statistics for watchdog monitoring"""
    try:
        error_stats = get_error_stats()
        return {
            "success": True,
            "error_rate_5min": error_stats['error_rate_5min'],
            "total_errors": error_stats['total_errors'],
            "total_success": error_stats['total_success'],
            "is_error_spike": error_stats['is_error_spike'],
            "recent_errors": error_stats['recent_errors']
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": f"Failed to get error stats: {str(e)}"
            }
        )


@app.post("/refresh-cookies")
async def manual_refresh_cookies():
    """
    Manually trigger cookie refresh
    """
    try:
        from request_tracker import tracker
        success = tracker.auto_refresh_cookies()
        
        return {
            "success": success,
            "message": "Cookie refresh successful" if success else "Cookie refresh failed",
            "stats": get_request_status()
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": f"Failed to refresh cookies: {str(e)}"
            }
        )
                


@app.post("/scrape")
def scrape_reel(url: str = Query(..., description="Instagram Reel URL")):
    """
    Scrape a single Instagram Reel with request tracking
    
    Args:
        url: Instagram Reel URL (e.g., https://www.instagram.com/reel/ABC123/)
    
    Returns:
        JSON with scraped data including view count, likes, comments, etc.
    """
    try:
        # Pre-request delay (2–5s human-like is slow; FAST_SCRAPE uses ~0–JITTER s)
        if FAST_SCRAPE:
            j = random.uniform(0, max(0.0, FAST_SCRAPE_JITTER))
            if j > 0:
                print(f"⚡ Fast mode: {j:.2f}s jitter before request")
                time.sleep(j)
        elif HUMAN_LIKE_DELAY:
            delay = human_delay.get_delay()
            time.sleep(delay)
        elif MAX_REQUEST_DELAY > 0:
            delay = random.uniform(MIN_REQUEST_DELAY, MAX_REQUEST_DELAY)
            print(f"⏳ Waiting {delay:.1f}s before request...")
            time.sleep(delay)
        
        # Select account for this request (rotate between accounts)
        if MULTI_ACCOUNT_ENABLED:
            account = account_rotator.get_next_account()
            cookie_file = account_rotator.get_cookie_file(account)
        else:
            account = 'bhdemo2025'
            cookie_file = 'cookies_bhdemo2025.txt'
        
        # Don't save JSON files when using API (data is returned in response)
        # Pass account for per-account proxy selection
        result = scrape_instagram_reel(url, save_json=False, cookie_file=cookie_file, account=account)
        
        if result.get('success'):
            refresh_triggered = log_api_request(success=True)
            if refresh_triggered:
                print("🔄 Request-tracker triggered cookie refresh (rate threshold)")
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "data": result.get('extracted', {}),
                    "shortcode": result.get('shortcode'),
                    "filename": result.get('filename'),
                    "request_stats": get_request_status(),
                    "account_used": account if MULTI_ACCOUNT_ENABLED else 'bhdemo2025'
                }
            )
        else:
            # Log failed request with error message
            error_msg = result.get('error', 'Unknown error')
            log_api_request(success=False, error_msg=error_msg)
            
            # Check if this is an authentication error (401/403) - return 503 for retry
            status_code = result.get('status_code', 0)
            if status_code in (401, 403):
                raise HTTPException(
                    status_code=503,
                    detail={
                        "success": False,
                        "error": "Authentication failed - cookies may be stale. Please retry.",
                        "retry": True,
                        "request_stats": get_request_status()
                    }
                )
            
            # For other errors, return 400 (client error)
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": result.get('error', 'Unknown error'),
                    "status_code": status_code,
                    "request_stats": get_request_status()
                }
            )
    
    except HTTPException as http_exc:
        # Log HTTP exceptions (400, 500, etc.) as failed requests
        error_detail = http_exc.detail
        if isinstance(error_detail, dict):
            error_msg = error_detail.get('error', f'HTTP {http_exc.status_code}')
        else:
            error_msg = str(error_detail)
        log_api_request(success=False, error_msg=f"HTTP {http_exc.status_code}: {error_msg}")
        # Re-raise to let FastAPI handle it
        raise
    except Exception as e:
        # Log failed request with error message
        error_msg = str(e)
        log_api_request(success=False, error_msg=f"Exception: {error_msg}")
        
        # Only unexpected exceptions become 500s
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": f"Internal server error: {str(e)}",
                "request_stats": get_request_status()
            }
        )


@app.post("/scrape/batch")
def scrape_batch(urls: List[str] = Query(..., description="List of Instagram Reel URLs")):
    """
    Scrape multiple Instagram Reels
    
    Args:
        urls: List of Instagram Reel URLs
    
    Returns:
        JSON with results for all reels
    """
    from scraper import get_session_cookies
    import time
    
    session, _ = get_session_cookies()
    results = {
        "success": [],
        "failed": []
    }
    
    for i, url in enumerate(urls, 1):
        try:
            result = scrape_instagram_reel(url, session=session)
            
            if result.get('success'):
                results["success"].append({
                    "url": url,
                    "shortcode": result.get('shortcode'),
                    "data": result.get('extracted', {}),
                    "filename": result.get('filename')
                })
            else:
                results["failed"].append({
                    "url": url,
                    "error": result.get('error', 'Unknown error')
                })
            
            # Add delay between requests
            if i < len(urls):
                time.sleep(3)
        
        except Exception as e:
            results["failed"].append({
                "url": url,
                "error": str(e)
            })
    
    return JSONResponse(
        status_code=200,
        content={
            "total": len(urls),
            "successful": len(results["success"]),
            "failed": len(results["failed"]),
            "results": results
        }
    )


@app.get("/scrape")
def scrape_reel_get(url: str = Query(..., description="Instagram Reel URL")):
    """Scrape a single Instagram Reel (GET method for easy browser testing)."""
    return scrape_reel(url)


# ============== ASYNC JOB ENDPOINTS ==============
# These endpoints prevent Render 30s timeout by using polling

def process_scrape_job(job_id: str, url: str):
    """Background task to process scrape job.

    All work serializes through `_pipeline_lock` + `GLOBAL_SCRAPE_INTERVAL_SEC` —
    so 100 concurrent submissions become 100 sequential ones at IG's safe pace.
    """
    try:
        # ---- Global trickle gate: serialize everything, pace at safe interval ----
        global _pipeline_last_run
        with _pipeline_lock:
            now = time.time()
            wait = (_pipeline_last_run + GLOBAL_SCRAPE_INTERVAL_SEC) - now
            if wait > 0:
                print(f"⏳ Trickle gate: holding job {job_id} for {wait:.1f}s "
                      f"(min interval {GLOBAL_SCRAPE_INTERVAL_SEC}s)")
                time.sleep(wait)
            _pipeline_last_run = time.time()
            # Process inside the lock so each pipeline tick is a complete scrape.
            _do_process_scrape_job(job_id, url)
        # auto-track every reel ever scraped, for the daily trickle backfill
        track_reel(url)
        return
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Exception in job {job_id}: {error_msg}")
        log_api_request(success=False, error_msg=error_msg)
        job_queue.update_job(job_id, "failed", error=f"Internal error: {error_msg}")


_pipeline_lock = threading.Lock()
_pipeline_last_run = 0.0


def _do_process_scrape_job(job_id: str, url: str):
    """The actual scrape work — only runs while holding the pipeline lock."""
    try:
        print(f"🔄 Processing job {job_id} for URL: {url}")
        # Mark job as processing now (not earlier — so JOB_TIMEOUT only counts
        # actual processing time, not queue-wait time).
        job_queue.update_job(job_id, "processing")
        
        if FAST_SCRAPE:
            j = random.uniform(0, max(0.0, FAST_SCRAPE_JITTER))
            if j > 0:
                print(f"⚡ Fast mode jitter: {j:.2f}s")
                time.sleep(j)
        elif HUMAN_LIKE_DELAY:
            delay = human_delay.get_delay()
            print(f"⏳ Human-like delay: {delay:.1f}s")
            time.sleep(delay)
        
        # Select account
        if MULTI_ACCOUNT_ENABLED:
            account = account_rotator.get_next_account()
            cookie_file = account_rotator.get_cookie_file(account)
        else:
            account = 'bhdemo2025'
            cookie_file = 'cookies_bhdemo2025.txt'

        print(f"👤 Using account: {account}")

        # Scrape with account for per-account proxy
        result = scrape_instagram_reel(url, save_json=False, cookie_file=cookie_file, account=account)

        # If this account just hit a rate limit (429 / non-JSON HTML), park it and retry
        # immediately on the next available account. One in-job retry keeps the frontend
        # from seeing a transient failure when one account is throttled.
        if MULTI_ACCOUNT_ENABLED and not result.get('success'):
            status_code = result.get('status_code', 0)
            error_msg = result.get('error', '')
            is_rate_limited = (
                status_code == 429
                or (status_code == 200 and "Invalid JSON" in error_msg)
            )
            is_auth_failure = status_code in (401, 403)

            # On auth failure (cookies invalid for this IP), refresh cookies for THIS
            # account from THIS host's IP via the HTTP login path — the new sessionid
            # gets bound to the host's IP and Instagram accepts it. Same-host refresh
            # is the only thing that fixes IP-mismatch invalidation on cookies copied
            # between machines (e.g., Mac → VM deployment).
            if is_auth_failure:
                try:
                    from cookie_login_api import refresh_via_api as _http_refresh
                    from multi_account_config import MULTI_ACCOUNT_CONFIG as _CFG
                    pw = next(
                        (a.get('password') for a in _CFG.get('accounts', [])
                         if a.get('username') == account),
                        None,
                    )
                    if pw:
                        print(f"🔑 Auth failure on {account} (HTTP {status_code}) — refreshing cookies inline")
                        if _http_refresh(account, pw):
                            print(f"   ↻ Retrying job {job_id} on {account} with fresh cookies")
                            result = scrape_instagram_reel(
                                url, save_json=False, cookie_file=cookie_file, account=account
                            )
                except Exception as e:
                    print(f"   ⚠️  Inline cookie refresh failed: {e}")

            # Still failed after auth-refresh attempt? Try the other account once.
            if not result.get('success') and (is_rate_limited or is_auth_failure):
                if is_rate_limited:
                    account_rotator.mark_rate_limited(account)
                alt = account_rotator.get_next_account()
                if alt != account:
                    print(f"↻ Retrying job {job_id} on {alt} (after {account} failed)")
                    account = alt
                    cookie_file = account_rotator.get_cookie_file(account)
                    result = scrape_instagram_reel(url, save_json=False, cookie_file=cookie_file, account=account)

            # Tier-2 fallback: instagrapi (mobile API). Different endpoint, different
            # throttle counter — sometimes works when web GraphQL is being blocked.
            if not result.get('success'):
                try:
                    from scraper_instagrapi import fetch_engagement as _ig_mobile
                    ig_data = _ig_mobile(url, cookie_file, account)
                    if ig_data and (ig_data.get('engagement') or {}).get('like_count') is not None:
                        print(f"📱 Mobile-API fallback recovered {url}")
                        result = {
                            "success": True,
                            "shortcode": ig_data.get("shortcode"),
                            "extracted": ig_data,
                            "filename": None,
                        }
                except Exception as e:
                    print(f"   ⚠️  Mobile-API fallback errored: {e}")
        
        if result.get('success'):
            extracted = result.get('extracted', {}) or {}
            engagement = extracted.get('engagement') or {}
            # Drop the view_counts_disabled flag so the frontend can't accidentally
            # short-circuit on it — every reel is treated the same.
            if isinstance(engagement, dict):
                engagement.pop('view_counts_disabled', None)
                extracted['engagement'] = engagement
            user_info = extracted.get('user') or {}
            video_urls = extracted.get('video_urls') or []
            # Treat as failure if Instagram returned nothing actionable: no user, no video, no engagement counts.
            has_engagement_signal = any(
                engagement.get(k) is not None
                for k in ("like_count", "comment_count", "play_count", "view_count",
                          "video_view_count", "organic_video_view_count")
            )
            if not user_info and not video_urls and not has_engagement_signal:
                log_api_request(success=False, error_msg="Empty extraction — Instagram returned no usable data")
                print(f"❌ Job {job_id} returned empty extraction — marking failed")
                job_queue.update_job(job_id, "failed",
                                     error="Instagram returned no usable data for this reel")
            else:
                log_api_request(success=True)
                print(f"✅ Job {job_id} completed successfully")
                # Persist to cache so future reads work even when API is throttled.
                cache_reel_data(url, extracted.get('engagement') or {}, extracted.get('user') or {})
                job_queue.update_job(job_id, "completed", result={
                    "success": True,
                    "data": extracted,
                    "shortcode": result.get('shortcode'),
                    "account_used": account
                })
        else:
            # Check if this is an authentication error (401/403)
            status_code = result.get('status_code', 0)
            error_msg = result.get('error', 'Unknown error')
            print(f"❌ Job {job_id} failed: {error_msg} (status: {status_code})")

            # Park rate-limited / challenge-page accounts so other accounts keep serving.
            # Signals: 429, or "Invalid JSON" with status 200 (Instagram returns an HTML
            # rate-limit / challenge page instead of GraphQL JSON).
            is_rate_limited = (
                status_code == 429
                or (status_code == 200 and "Invalid JSON" in error_msg)
            )
            if is_rate_limited and MULTI_ACCOUNT_ENABLED:
                account_rotator.mark_rate_limited(account)

            if status_code in (401, 403):
                log_api_request(success=False, error_msg=error_msg)
                job_queue.update_job(job_id, "failed", error="Authentication failed - cookies may be stale. Please retry.")
            else:
                log_api_request(success=False, error_msg=error_msg)
                job_queue.update_job(job_id, "failed", error=error_msg)
    
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Exception in job {job_id}: {error_msg}")
        log_api_request(success=False, error_msg=error_msg)
        job_queue.update_job(job_id, "failed", error=f"Internal error: {error_msg}")


def _check_capacity_or_503():
    """When every account is throttled, reject incoming jobs with 503 + Retry-After.
    Lets the frontend's retry loop back off instead of stampeding Instagram while
    we're already getting "Invalid JSON" on every call — that's what makes IG escalate
    the "automated behavior" flag.
    """
    if MULTI_ACCOUNT_ENABLED and account_rotator.all_cooled_down():
        # Smallest remaining cooldown — that's when we'll have capacity again
        now = time.time()
        with account_rotator.lock:
            soonest = min(account_rotator.cooldown_until.values()) - now
        retry_after = max(30, int(soonest))
        raise HTTPException(
            status_code=503,
            detail={
                "success": False,
                "error": "All Instagram accounts are temporarily rate-limited. Try again later.",
                "retry_after_sec": retry_after
            },
            headers={"Retry-After": str(retry_after)}
        )


@app.post("/api/async/scrape")
async def async_scrape_submit_post(
    background_tasks: BackgroundTasks,
    url: str = Query(..., description="Instagram Reel URL")
):
    """
    Submit async scrape job - returns immediately with job ID.
    Use /api/async/status/{job_id} to poll for result.
    Returns 503 when all accounts are cooled down (frontend should back off).
    """
    _check_capacity_or_503()
    try:
        job_id = job_queue.create_job(url)
        background_tasks.add_task(process_scrape_job, job_id, url)

        return JSONResponse(
            status_code=202,
            content={
                "success": True,
                "job_id": job_id,
                "status": "pending",
                "message": "Job submitted. Poll /api/async/status/{job_id} for result.",
                "poll_url": f"/api/async/status/{job_id}",
                "poll_interval_ms": 5000
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error creating async job: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": f"Failed to create job: {str(e)}"
            }
        )


@app.get("/api/async/scrape")
async def async_scrape_submit_get(
    background_tasks: BackgroundTasks,
    url: str = Query(..., description="Instagram Reel URL")
):
    """
    Submit async scrape job (GET method for easier browser testing).
    Returns immediately with job ID.
    Use /api/async/status/{job_id} to poll for result.
    """
    _check_capacity_or_503()
    try:
        job_id = job_queue.create_job(url)
        background_tasks.add_task(process_scrape_job, job_id, url)

        return JSONResponse(
            status_code=202,
            content={
                "success": True,
                "job_id": job_id,
                "status": "pending",
                "message": "Job submitted. Poll /api/async/status/{job_id} for result.",
                "poll_url": f"/api/async/status/{job_id}",
                "poll_interval_ms": 5000
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error creating async job: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": f"Failed to create job: {str(e)}"
            }
        )


@app.get("/api/async/status/{job_id}")
async def async_scrape_status(job_id: str):
    """
    Check status of async scrape job.
    Returns result when completed.
    """
    try:
        job = job_queue.get_job(job_id)
        
        if not job:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": f"Job {job_id} not found. It may have expired or never existed.",
                    "job_id": job_id
                }
            )
        
        if job["status"] == "pending":
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "job_id": job_id,
                    "status": "pending",
                    "message": "Job queued, waiting to start...",
                    "url": job.get("url", "unknown")
                }
            )
        elif job["status"] == "processing":
            elapsed = time.time() - job.get("started_at", time.time()) if job.get("started_at") else 0
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "job_id": job_id,
                    "status": "processing",
                    "message": "Job is being processed...",
                    "elapsed_seconds": int(elapsed),
                    "url": job.get("url", "unknown")
                }
            )
        elif job["status"] == "completed":
            # Cleanup old jobs periodically
            job_queue.cleanup_old_jobs()
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "job_id": job_id,
                    "status": "completed",
                    "result": job["result"],
                    "url": job.get("url", "unknown")
                }
            )
        else:  # failed
            return JSONResponse(
                status_code=200,
                content={
                    "success": False,
                    "job_id": job_id,
                    "status": "failed",
                    "error": job.get("error", "Unknown error"),
                    "url": job.get("url", "unknown")
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error checking job status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": f"Internal error checking job status: {str(e)}",
                "job_id": job_id
            }
        )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=API_PORT)

