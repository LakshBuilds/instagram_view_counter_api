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
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict
from scraper import scrape_instagram_reel, get_session_cookies
from request_tracker import log_api_request, get_request_status, print_request_status
import uvicorn


# ============== ASYNC JOB QUEUE ==============
# Prevents Render 30s timeout by using polling pattern
JOB_TIMEOUT = 60  # Max seconds a job can be in "processing" state

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
    
    def cleanup_old_jobs(self, max_age: int = 300):
        """Remove jobs older than max_age seconds"""
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


class MultiAccountRotator:
    """
    Rotates between multiple Instagram accounts to distribute load.
    Each account has its own cookie file and request counter.
    """
    def __init__(self):
        # Using candy_shopbuy and raviram8274 accounts
        self.accounts = ['candy_shopbuy', 'raviram8274']
        self.current_index = 0
        self.request_counts = {acc: 0 for acc in self.accounts}
        
    def get_next_account(self) -> str:
        """Round-robin account selection"""
        account = self.accounts[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.accounts)
        self.request_counts[account] += 1
        print(f"🔄 Using account: {account} (request #{self.request_counts[account]})")
        return account
    
    def get_cookie_file(self, account: str) -> str:
        """Get cookie file path for account"""
        return f"cookies_{account}.txt"
    
    def get_stats(self) -> dict:
        """Get stats for all accounts"""
        return {
            "accounts": self.accounts,
            "current_account": self.accounts[self.current_index],
            "request_counts": self.request_counts,
            "total_requests": sum(self.request_counts.values())
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
                "daily_limit": 500,
                "auto_refresh_threshold": 40
            },
            "multi_account": multi_account_stats,
            "human_like_delay": HUMAN_LIKE_DELAY
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": f"Failed to get stats: {str(e)}"
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
async def scrape_reel(url: str = Query(..., description="Instagram Reel URL")):
    """
    Scrape a single Instagram Reel with request tracking
    
    Args:
        url: Instagram Reel URL (e.g., https://www.instagram.com/reel/ABC123/)
    
    Returns:
        JSON with scraped data including view count, likes, comments, etc.
    """
    try:
        # Apply human-like delay to avoid detection
        if HUMAN_LIKE_DELAY:
            delay = human_delay.get_delay()
            time.sleep(delay)
        elif MAX_REQUEST_DELAY > 0:
            # Fallback to simple random delay
            delay = random.uniform(MIN_REQUEST_DELAY, MAX_REQUEST_DELAY)
            print(f"⏳ Waiting {delay:.1f}s before request...")
            time.sleep(delay)
        
        # Log the request and check for auto-refresh
        refresh_triggered = log_api_request()
        
        # Print current status to console
        print_request_status()
        
        if refresh_triggered:
            print("🔄 Cookies were refreshed - retrying request...")
        
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
            # Check if views are null - treat as failure (stale cookies)
            extracted = result.get('extracted', {})
            engagement = extracted.get('engagement', {})
            play_count = engagement.get('play_count')
            view_count = engagement.get('view_count')
            
            # If both play_count and view_count are null, cookies are stale
            if play_count is None and view_count is None:
                log_api_request(success=False)
                raise HTTPException(
                    status_code=503,
                    detail={
                        "success": False,
                        "error": "Views data unavailable - cookies may be stale. Please retry.",
                        "retry": True,
                        "request_stats": get_request_status()
                    }
                )
            
            # Log successful request
            log_api_request(success=True)
            
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "data": extracted,
                    "shortcode": result.get('shortcode'),
                    "filename": result.get('filename'),
                    "request_stats": get_request_status(),
                    "account_used": account if MULTI_ACCOUNT_ENABLED else 'bhdemo2025'
                }
            )
        else:
            # Log failed request
            log_api_request(success=False)
            
            # Bubble up a clean 4xx response when Instagram returns an error
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": result.get('error', 'Unknown error'),
                    "status_code": result.get('status_code', 0),
                    "request_stats": get_request_status()
                }
            )
    
    except HTTPException:
        # Let FastAPI handle HTTPException without wrapping it as a 500
        raise
    except Exception as e:
        # Log failed request
        log_api_request(success=False)
        
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
async def scrape_batch(urls: List[str] = Query(..., description="List of Instagram Reel URLs")):
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
async def scrape_reel_get(url: str = Query(..., description="Instagram Reel URL")):
    """
    Scrape a single Instagram Reel (GET method for easy browser testing)
    
    Args:
        url: Instagram Reel URL
    
    Returns:
        JSON with scraped data
    """
    return await scrape_reel(url)


# ============== ASYNC JOB ENDPOINTS ==============
# These endpoints prevent Render 30s timeout by using polling

def process_scrape_job(job_id: str, url: str):
    """Background task to process scrape job"""
    try:
        # Mark job as processing immediately
        job_queue.update_job(job_id, "processing")
        
        # Apply human-like delay
        if HUMAN_LIKE_DELAY:
            delay = human_delay.get_delay()
            time.sleep(delay)
        
        # Log request
        log_api_request()
        
        # Select account
        if MULTI_ACCOUNT_ENABLED:
            account = account_rotator.get_next_account()
            cookie_file = account_rotator.get_cookie_file(account)
        else:
            account = 'bhdemo2025'
            cookie_file = 'cookies_bhdemo2025.txt'
        
        # Scrape with account for per-account proxy
        result = scrape_instagram_reel(url, save_json=False, cookie_file=cookie_file, account=account)
        
        if result.get('success'):
            # Check if views are null - treat as failure (stale cookies)
            extracted = result.get('extracted', {})
            engagement = extracted.get('engagement', {})
            play_count = engagement.get('play_count')
            view_count = engagement.get('view_count')
            
            # If both play_count and view_count are null, cookies are stale
            if play_count is None and view_count is None:
                log_api_request(success=False)
                job_queue.update_job(job_id, "failed", error="Views data unavailable - cookies may be stale. Please retry.")
            else:
                log_api_request(success=True)
                job_queue.update_job(job_id, "completed", result={
                    "success": True,
                    "data": extracted,
                    "shortcode": result.get('shortcode'),
                    "account_used": account
                })
        else:
            log_api_request(success=False)
            job_queue.update_job(job_id, "failed", error=result.get('error', 'Unknown error'))
    
    except Exception as e:
        log_api_request(success=False)
        job_queue.update_job(job_id, "failed", error=str(e))


@app.post("/api/async/scrape")
async def async_scrape_submit(
    background_tasks: BackgroundTasks,
    url: str = Query(..., description="Instagram Reel URL")
):
    """
    Submit async scrape job - returns immediately with job ID.
    Use /api/async/status/{job_id} to poll for result.
    This prevents Render 30s timeout!
    """
    job_id = job_queue.create_job(url)
    background_tasks.add_task(process_scrape_job, job_id, url)
    
    return JSONResponse(
        status_code=202,
        content={
            "success": True,
            "job_id": job_id,
            "status": "pending",
            "message": "Job submitted. Poll /api/async/status/{job_id} for result.",
            "poll_interval_ms": 5000
        }
    )


@app.get("/api/async/status/{job_id}")
async def async_scrape_status(job_id: str):
    """
    Check status of async scrape job.
    Returns result when completed.
    """
    job = job_queue.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail={"error": "Job not found"})
    
    if job["status"] == "pending":
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "job_id": job_id,
                "status": "pending",
                "message": "Job queued, waiting to start..."
            }
        )
    elif job["status"] == "processing":
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "job_id": job_id,
                "status": "processing",
                "message": "Job is being processed..."
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
                "result": job["result"]
            }
        )
    else:  # failed
        return JSONResponse(
            status_code=200,
            content={
                "success": False,
                "job_id": job_id,
                "status": "failed",
                "error": job["error"]
            }
        )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

