# Instagram Reel Scraper API - Endpoints

## Base URL
**Current Public URL:** Check your active Cloudflare tunnel terminal for the latest URL
(Format: `https://[random-name].trycloudflare.com`)

## API Endpoints

### 1. Health Check
```
GET /health
```
**Response:**
```json
{
  "status": "healthy",
  "message": "API is ready",
  "version": "1.0.0"
}
```

### 2. Scrape Single Reel (GET)
```
GET /scrape?url=INSTAGRAM_REEL_URL
```

**Example:**
```
https://your-tunnel-url.trycloudflare.com/scrape?url=https://www.instagram.com/reel/DQOtXDQjJwT/
```

### 3. Scrape Single Reel (POST)
```
POST /scrape?url=INSTAGRAM_REEL_URL
```

### 4. Scrape Multiple Reels (Batch)
```
POST /scrape/batch?urls=URL1&urls=URL2&urls=URL3
```

**Example:**
```
POST https://your-tunnel-url.trycloudflare.com/scrape/batch?urls=https://www.instagram.com/reel/ABC123/&urls=https://www.instagram.com/reel/XYZ789/
```

## Response Format

**Success Response:**
```json
{
  "success": true,
  "data": {
    "shortcode": "DQOtXDQjJwT",
    "video_urls": [...],
    "likes": 12345,
    "comments": 678,
    "views": 98765,
    ...
  },
  "shortcode": "DQOtXDQjJwT",
  "filename": "DQOtXDQjJwT_data.json"
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Error message",
  "status_code": 400
}
```

## Usage in Your Project

### JavaScript/TypeScript Example:
```javascript
const apiUrl = 'https://your-tunnel-url.trycloudflare.com';
const reelUrl = 'https://www.instagram.com/reel/DQOtXDQjJwT/';

fetch(`${apiUrl}/scrape?url=${encodeURIComponent(reelUrl)}`)
  .then(response => response.json())
  .then(data => console.log(data))
  .catch(error => console.error('Error:', error));
```

### Python Example:
```python
import requests

api_url = 'https://your-tunnel-url.trycloudflare.com'
reel_url = 'https://www.instagram.com/reel/DQOtXDQjJwT/'

response = requests.get(f'{api_url}/scrape', params={'url': reel_url})
data = response.json()
print(data)
```

### cURL Example:
```bash
curl "https://your-tunnel-url.trycloudflare.com/scrape?url=https://www.instagram.com/reel/DQOtXDQjJwT/"
```

## Important Notes

⚠️ **Temporary URLs**: The `trycloudflare.com` URLs are temporary and expire when you close the tunnel terminal.

⚠️ **Keep Running**: You must keep both terminals running:
1. The `cloudflared tunnel` terminal (for public access)
2. The `python api.py` terminal (for the API server)

⚠️ **For Production**: Consider setting up a permanent domain with Cloudflare Zero Trust for a stable URL.

## Current Status
- API Server: Running on `http://127.0.0.1:8000`
- Cookies: Updated and active
- Tunnel: Check active terminal for current URL




