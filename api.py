"""
FastAPI wrapper for Instagram Reel Scraper
Expose the scraper as a REST API with request tracking and auto-refresh
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional, List
from scraper import scrape_instagram_reel, get_session_cookies
from request_tracker import log_api_request, get_request_status, print_request_status
import uvicorn

app = FastAPI(
    title="Instagram Reel Scraper API",
    description="API to scrape Instagram Reel data including view counts",
    version="1.0.0"
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
async def internal_scrape_get(url: str = Query(..., description="Instagram Reel URL")):
    """
    Internal API endpoint for frontend (GET method)
    Compatible with frontend expectations
    """
    return await scrape_reel(url)


@app.post("/api/internal/scrape")
async def internal_scrape_post(url: str = Query(..., description="Instagram Reel URL")):
    """
    Internal API endpoint for frontend (POST method)
    Compatible with frontend expectations
    """
    return await scrape_reel(url)


@app.get("/stats")
async def get_request_stats():
    """
    Get current request statistics and rate limit status
    """
    try:
        status = get_request_status()
        return {
            "success": True,
            "stats": status,
            "rate_limits": {
                "hourly_limit": 50,
                "daily_limit": 500,
                "auto_refresh_threshold": 40
            }
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
        # Log the request and check for auto-refresh
        refresh_triggered = log_api_request()
        
        # Print current status to console
        print_request_status()
        
        if refresh_triggered:
            print("🔄 Cookies were refreshed - retrying request...")
        
        # Don't save JSON files when using API (data is returned in response)
        result = scrape_instagram_reel(url, save_json=False)
        
        if result.get('success'):
            # Log successful request
            log_api_request(success=True)
            
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "data": result.get('extracted', {}),
                    "shortcode": result.get('shortcode'),
                    "filename": result.get('filename'),
                    "request_stats": get_request_status()
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


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

