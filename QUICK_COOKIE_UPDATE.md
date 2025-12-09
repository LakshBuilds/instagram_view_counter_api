# Quick Guide: Update Instagram Cookies

## When to Update:
- ❌ Getting "403 Forbidden" errors
- ❌ Getting "Rate limited" errors repeatedly  
- ❌ Scraper stops working suddenly
- ❌ Instagram logged you out

## Quick Steps:

### 1. Log in to Instagram
- Open https://www.instagram.com in your browser
- Make sure you're logged in

### 2. Get Cookies from Browser

**Chrome/Edge:**
1. Press `F12` (or `Ctrl+Shift+I`)
2. Click **Application** tab
3. Left sidebar: **Cookies** → **https://www.instagram.com**
4. Find and copy these cookies:
   - `csrftoken`
   - `sessionid` ⚠️ **MOST IMPORTANT**
   - `ds_user_id`

**Firefox:**
1. Press `F12` (or `Ctrl+Shift+I`)
2. Click **Storage** tab
3. Left sidebar: **Cookies** → **https://www.instagram.com**
4. Copy the same cookies as above

### 3. Update cookies.txt

Open `cookies.txt` and replace the values:

```
csrftoken=PASTE_YOUR_NEW_CSRF_TOKEN
sessionid=PASTE_YOUR_NEW_SESSIONID
ds_user_id=PASTE_YOUR_NEW_USER_ID
```

**Keep other cookies if they exist, or copy all cookies from browser.**

### 4. Test

```bash
python scraper.py "https://www.instagram.com/reel/DRggP2gilrS/"
```

If it works, you're done! ✅

## Most Important Cookie:
**`sessionid`** - This is the authentication cookie. Without it, nothing works!

## Security Warning:
⚠️ Never share your `cookies.txt` file - it gives full access to your Instagram account!








