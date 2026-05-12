#!/bin/bash
# Phase B — runs ON the Oracle Ubuntu VM. Sets up swap, Python, cloudflared,
# systemd service. Resumable: each step skips work that's already done.
set -e

PROJECT=~/instagram_view_counter_api
TUNNEL_ID="de67a1d2-5588-44b5-b6ce-1f0f8f006b91"
TUNNEL_NAME="instagram-api"
TUNNEL_HOSTNAME="api.rareme.shop"

echo "=== 0. Sanity checks ==="
test -d "$PROJECT" || { echo "missing $PROJECT — did Phase A finish?"; exit 1; }
test -f ~/cloudflared_cert.pem    || { echo "missing ~/cloudflared_cert.pem"; exit 1; }
test -f ~/cloudflared_tunnel.json || { echo "missing ~/cloudflared_tunnel.json"; exit 1; }

echo "=== 1. Swap file (2 GB) ==="
if [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab > /dev/null
    echo "  swap added"
else
    echo "  swap already configured"
fi
free -m

echo
echo "=== 2. Install system packages ==="
sudo apt-get update -qq
sudo apt-get install -y -q python3-pip python3-venv curl wget
echo "  python3: $(python3 --version)"

echo
echo "=== 3. Install cloudflared (if missing) ==="
if ! command -v cloudflared >/dev/null; then
    ARCH=$(dpkg --print-architecture)   # amd64 on E2.1.Micro
    wget -q "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb" -O /tmp/cloudflared.deb
    sudo dpkg -i /tmp/cloudflared.deb
    rm -f /tmp/cloudflared.deb
fi
echo "  cloudflared: $(cloudflared --version 2>/dev/null | head -1)"

echo
echo "=== 4. Move cloudflared credentials to ~/.cloudflared/ ==="
mkdir -p ~/.cloudflared
mv -f ~/cloudflared_cert.pem  ~/.cloudflared/cert.pem
mv -f ~/cloudflared_tunnel.json ~/.cloudflared/${TUNNEL_ID}.json
chmod 600 ~/.cloudflared/cert.pem ~/.cloudflared/${TUNNEL_ID}.json
ls -la ~/.cloudflared/

echo
echo "=== 5. Python venv + project deps ==="
cd "$PROJECT"
if [ ! -d venv ]; then
    python3 -m venv venv
fi
./venv/bin/pip install --quiet --upgrade pip wheel
./venv/bin/pip install --quiet -r requirements.txt
echo "  venv ready; key pkgs:"
./venv/bin/pip list 2>/dev/null | grep -E "fastapi|uvicorn|requests|beautifulsoup|selenium"

echo
echo "=== 6. systemd service (auto-start on boot, auto-restart on crash) ==="
sudo tee /etc/systemd/system/instagram-scraper.service > /dev/null <<UNIT
[Unit]
Description=Instagram Scraper API + Named Cloudflare Tunnel + Watchdog
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=${PROJECT}
Environment="PATH=${PROJECT}/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="CLOUDFLARE_TUNNEL_NAME=${TUNNEL_NAME}"
Environment="CLOUDFLARE_TUNNEL_HOSTNAME=${TUNNEL_HOSTNAME}"
Environment="FAST_SCRAPE=1"
Environment="SCRAPER_FAST_GRAPHQL=1"
Environment="SCRAPER_VIEWS_FALLBACK_WHEN_DISABLED=1"
Environment="ACCOUNT_WEIGHTS=bhdemo2025=1,hatke_automation=9"
Environment="WATCHDOG_REFRESH_ON_ERROR_SPIKE=1"
Environment="WATCHDOG_ERROR_CHECK_SEC=30"
Environment="WATCHDOG_CHECK_INTERVAL_SEC=30"
Environment="WATCHDOG_VIEW_INTERVAL_SEC=600"
Environment="WATCHDOG_MIN_REFRESH_INTERVAL_SEC=600"
Environment="NO_HTTP_LOGIN=0"
ExecStart=${PROJECT}/venv/bin/python ${PROJECT}/start.py
Restart=always
RestartSec=10
StandardOutput=append:${PROJECT}/systemd.out.log
StandardError=append:${PROJECT}/systemd.err.log

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable instagram-scraper.service
echo "  service enabled (autostart on boot)"

# Stop any previous run before starting fresh
sudo systemctl restart instagram-scraper.service
sleep 5

echo
echo "=== 7. Service status ==="
sudo systemctl status instagram-scraper.service --no-pager | head -15
echo
echo "=== 8. Health checks ==="
echo "Wait ~15s for cloudflared to register tunnel connections..."
sleep 15
echo "Local API:"
curl -sS -m 5 http://127.0.0.1:8002/health -w "\n  HTTP %{http_code}\n" | head -c 250 || echo "  (still warming up)"
echo
echo "Public URL (api.rareme.shop):"
curl -sS -m 8 https://api.rareme.shop/health -w "\n  HTTP %{http_code}\n" | head -c 250 || echo "  (still warming up)"

echo
echo "✅ Phase B done."
echo "    journalctl -u instagram-scraper -f         # follow live logs"
echo "    tail -f ~/instagram_view_counter_api/watchdog.log"
echo "    sudo systemctl restart instagram-scraper   # manual restart"
