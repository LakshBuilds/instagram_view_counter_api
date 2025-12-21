# Quick API Reference - Instagram Reel Scraper

## 🚀 How to Find Your Active Tunnel URL

### Step 1: Find Your Tunnel Terminal
Look for the PowerShell/Command Prompt window that shows output like:
```
Your quick Tunnel has been created! Visit it at:
https://[random-name].trycloudflare.com
```

### Step 2: Copy the URL
The URL will look like:
```
https://signatures-imaging-tours-packard.trycloudflare.com
```
or
```
https://distances-agent-varies-sheet.trycloudflare.com
```

## 📡 API Endpoint Format

### Base URL
Replace `[YOUR-TUNNEL-URL]` with the URL from Step 2:
```
https://[YOUR-TUNNEL-URL].trycloudflare.com
```

### Scrape Endpoint
```
GET https://[YOUR-TUNNEL-URL].trycloudflare.com/scrape?url=INSTAGRAM_REEL_URL
```

### Example
```
https://signatures-imaging-tours-packard.trycloudflare.com/scrape?url=https://www.instagram.com/reel/DQOtXDQjJwT/
```

## 💻 Code Examples

### JavaScript/TypeScript
```javascript
const TUNNEL_URL = 'https://[YOUR-TUNNEL-URL].trycloudflare.com';
const reelUrl = 'https://www.instagram.com/reel/DQOtXDQjJwT/';

async function scrapeReel(reelUrl) {
  const response = await fetch(
    `${TUNNEL_URL}/scrape?url=${encodeURIComponent(reelUrl)}`
  );
  const data = await response.json();
  return data;
}

// Usage
scrapeReel(reelUrl).then(data => {
  console.log('Success:', data.success);
  console.log('Views:', data.data?.views);
  console.log('Likes:', data.data?.likes);
});
```

### Python
```python
import requests

TUNNEL_URL = 'https://[YOUR-TUNNEL-URL].trycloudflare.com'

def scrape_reel(reel_url):
    response = requests.get(
        f'{TUNNEL_URL}/scrape',
        params={'url': reel_url}
    )
    return response.json()

# Usage
data = scrape_reel('https://www.instagram.com/reel/DQOtXDQjJwT/')
print(f"Success: {data['success']}")
print(f"Views: {data['data']['views']}")
print(f"Likes: {data['data']['likes']}")
```

### cURL
```bash
curl "https://[YOUR-TUNNEL-URL].trycloudflare.com/scrape?url=https://www.instagram.com/reel/DQOtXDQjJwT/"
```

## ✅ Response Format

### Success Response
```json
{
  "success": true,
  "data": {
    "shortcode": "DQOtXDQjJwT",
    "views": 8144,
    "likes": 12345,
    "comments": 678,
    "video_urls": [...],
    "caption": "...",
    ...
  },
  "shortcode": "DQOtXDQjJwT"
}
```

### Error Response
```json
{
  "success": false,
  "error": "Error message",
  "status_code": 400
}
```

## ⚠️ Important Reminders

1. **Keep Both Terminals Open:**
   - Terminal 1: `cloudflared tunnel` (for public URL)
   - Terminal 2: `python api.py` (for API server)

2. **URL Changes:** Each time you restart the tunnel, you get a new URL

3. **Temporary URLs:** These URLs expire when you close the tunnel terminal

4. **For Production:** Consider setting up a permanent domain

## 🔍 Current Status
- ✅ API Server: Running on port 8000
- ✅ Cookies: Updated and active
- ✅ Scraper: Working (extracting views, likes, comments)
- ⚠️ Tunnel URL: Check your active terminal window




