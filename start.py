#!/usr/bin/env python3
"""
One-click launcher (macOS / Linux):
  - Starts the FastAPI server (api.py) on $API_PORT (default 8002)
  - Starts a Cloudflare quick tunnel and prints the public URL
  - Starts api_watchdog.py in the same terminal

Run:    python3 start.py
Stop:   Ctrl+C  (cleanly stops API + tunnel + watchdog)
"""
import atexit
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from shutil import which

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

API_PORT = int(os.getenv("API_PORT", "8002"))
PYTHON = sys.executable or "python3"
TUNNEL_LOG = ROOT / "tunnel_output.log"
API_LOG = ROOT / "api.log"
WATCHDOG_LOG = ROOT / "watchdog.log"
URL_FILE = ROOT / "tunnel_url.txt"

URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

# Named-tunnel config. Set CLOUDFLARE_TUNNEL_NAME to a tunnel that's already been
# created with `cloudflared tunnel create <name>` and routed with
# `cloudflared tunnel route dns <name> <hostname>`. When both env vars are set
# (and ~/.cloudflared/cert.pem exists), we run that fixed tunnel — URL stops rotating.
# Falls back to anonymous quick-tunnel when not configured.
TUNNEL_NAME = os.getenv("CLOUDFLARE_TUNNEL_NAME", "instagram-api")
TUNNEL_HOSTNAME = os.getenv("CLOUDFLARE_TUNNEL_HOSTNAME", "api.rareme.shop")
CLOUDFLARED_CERT = Path.home() / ".cloudflared" / "cert.pem"


def use_named_tunnel() -> bool:
    return CLOUDFLARED_CERT.exists() and bool(TUNNEL_NAME) and bool(TUNNEL_HOSTNAME)

api_proc = None
tunnel_proc = None
watchdog_proc = None


def log(msg, kind="INFO"):
    icon = {"INFO": "•", "OK": "✓", "WARN": "!", "ERR": "✗", "RUN": ">"}.get(kind, "·")
    print(f"[{datetime.now():%H:%M:%S}] {icon} {msg}", flush=True)


def port_in_use(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def kill_port(port):
    try:
        out = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}"], capture_output=True, text=True
        ).stdout.strip()
        if out:
            for pid in out.splitlines():
                subprocess.run(["kill", "-9", pid], capture_output=True)
            time.sleep(1)
    except Exception:
        pass


def kill_existing_cloudflared():
    subprocess.run(["pkill", "-f", "cloudflared tunnel"], capture_output=True)
    time.sleep(0.5)


def start_api():
    global api_proc
    if port_in_use(API_PORT):
        log(f"Port {API_PORT} busy — killing previous API", "WARN")
        kill_port(API_PORT)

    log(f"Starting API on http://127.0.0.1:{API_PORT}", "RUN")
    api_log = open(API_LOG, "a", buffering=1)
    api_log.write(f"\n===== API start {datetime.now()} =====\n")
    api_env = os.environ.copy()
    # Skip the 2-5s human-like delay so the sync /scrape endpoint stays under 10s
    # (typical browser fetch timeout). Async endpoint already protects us from timeouts.
    api_env.setdefault("FAST_SCRAPE", "1")
    api_env.setdefault("SCRAPER_FAST_GRAPHQL", "1")
    # bhdemo2025 has been flagged by Instagram ("automated behavior" warning) — but we
    # still want it to take a trickle of traffic so it can come back online when IG's flag
    # decays. Give hatke_automation 9× weight; bhdemo2025 gets 1 in every 10 requests.
    # When bhdemo2025 fails the 15-min cooldown auto-parks it; once that expires it gets
    # another shot. Adjust ratio via ACCOUNT_WEIGHTS env if needed.
    api_env.setdefault("ACCOUNT_WEIGHTS", "bhdemo2025=1,hatke_automation=9")
    # Keep HTML/REST view fallbacks ON — when Instagram flags `view_counts_disabled: true`,
    # the REST `/api/v1/media/{id}/info/` endpoint still returns play_count for many reels.
    # Without this, every view-disabled reel comes back with views=null even though we
    # could recover the number.
    api_env.setdefault("SCRAPER_VIEWS_FALLBACK_WHEN_DISABLED", "1")
    api_proc = subprocess.Popen(
        [PYTHON, "api.py"],
        stdout=api_log,
        stderr=subprocess.STDOUT,
        cwd=str(ROOT),
        env=api_env,
    )

    for i in range(30):
        if port_in_use(API_PORT):
            log(f"API ready (PID {api_proc.pid})", "OK")
            return True
        if api_proc.poll() is not None:
            log("API exited unexpectedly — see api.log", "ERR")
            return False
        time.sleep(1)
    log("API failed to start in 30s", "ERR")
    return False


def start_tunnel():
    global tunnel_proc
    if which("cloudflared") is None:
        log("cloudflared not found. Install with: brew install cloudflared", "ERR")
        return None

    kill_existing_cloudflared()
    if TUNNEL_LOG.exists():
        TUNNEL_LOG.unlink()

    if use_named_tunnel():
        # Stable named tunnel — fixed hostname, no URL rotation.
        public_url = f"https://{TUNNEL_HOSTNAME}"
        log(f"Starting named tunnel '{TUNNEL_NAME}' → {public_url}", "RUN")
        log_fp = open(TUNNEL_LOG, "w", buffering=1)
        tunnel_proc = subprocess.Popen(
            ["cloudflared", "tunnel",
             "--url", f"http://127.0.0.1:{API_PORT}",
             "--protocol", "http2",
             "--no-autoupdate",
             "run", TUNNEL_NAME],
            stdout=log_fp,
            stderr=subprocess.STDOUT,
            cwd=str(ROOT),
        )
        # Wait until cloudflared registers a tunnel connection — that's when traffic flows.
        deadline = time.time() + 30
        while time.time() < deadline:
            if tunnel_proc.poll() is not None:
                log("cloudflared exited — see tunnel_output.log", "ERR")
                return None
            try:
                content = TUNNEL_LOG.read_text(errors="ignore")
                if "Registered tunnel connection" in content:
                    URL_FILE.write_text(public_url)
                    log(f"Tunnel ready (PID {tunnel_proc.pid})", "OK")
                    return public_url
            except FileNotFoundError:
                pass
            time.sleep(0.5)
        log("Named tunnel started but no connection registered yet", "WARN")
        URL_FILE.write_text(public_url)
        return public_url

    # Fallback: anonymous quick tunnel (random *.trycloudflare.com hostname).
    log("Starting Cloudflare quick tunnel (anonymous)", "RUN")
    log_fp = open(TUNNEL_LOG, "w", buffering=1)
    tunnel_proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{API_PORT}",
         "--protocol", "http2", "--no-autoupdate"],
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        cwd=str(ROOT),
    )

    deadline = time.time() + 30
    while time.time() < deadline:
        if tunnel_proc.poll() is not None:
            log("cloudflared exited — see tunnel_output.log", "ERR")
            return None
        try:
            content = TUNNEL_LOG.read_text(errors="ignore")
            m = URL_RE.findall(content)
            if m:
                url = m[-1]
                URL_FILE.write_text(url)
                log(f"Tunnel ready (PID {tunnel_proc.pid})", "OK")
                return url
        except FileNotFoundError:
            pass
        time.sleep(0.5)

    log("Tunnel started but URL not detected within 30s", "WARN")
    return None


def tunnel_unauthorized():
    """True if cloudflared has lost its tunnel and is stuck retrying with no edge."""
    try:
        tail = TUNNEL_LOG.read_text(errors="ignore")[-2000:]
    except FileNotFoundError:
        return False
    return ("Unauthorized: Tunnel not found" in tail
            and "Registered tunnel connection" not in tail.split(
                "Unauthorized: Tunnel not found")[-1])


_public_fail_streak = 0


def public_health_ok():
    """Hit the public tunnel URL. Used to detect Cloudflare-side breakage (HTTP 530, DNS, timeout)."""
    try:
        url = URL_FILE.read_text().strip()
    except FileNotFoundError:
        return True  # no URL yet — let provisioning logic handle it
    if not url:
        return True
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(url + "/health", headers={"User-Agent": "start.py-probe"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        # 5xx from Cloudflare edge = tunnel broken
        return e.code < 500
    except Exception:
        return False


def _stream_to_console(proc, prefix, log_path):
    """Stream child stdout to terminal (with prefix) and append to log file."""
    log_fp = open(log_path, "a", buffering=1)
    log_fp.write(f"\n===== {prefix} start {datetime.now()} =====\n")
    try:
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip("\n")
            print(f"[{prefix}] {line}", flush=True)
            log_fp.write(line + "\n")
    except Exception:
        pass
    finally:
        try:
            log_fp.close()
        except Exception:
            pass


def start_watchdog():
    global watchdog_proc
    log("Starting watchdog (output streamed to console)", "RUN")
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    # Self-healing defaults — the watchdog autonomously refreshes cookies + restarts API
    # when Instagram starts throttling, so the user doesn't have to babysit.
    env.setdefault("WATCHDOG_REFRESH_ON_ERROR_SPIKE", "1")  # refresh cookies when error_rate_5min > 30%
    env.setdefault("WATCHDOG_ERROR_CHECK_SEC", "30")        # check error-stats every 30s (was 60)
    env.setdefault("WATCHDOG_VIEW_INTERVAL_SEC", "600")     # periodic view probe every 10 min
    env.setdefault("WATCHDOG_CHECK_INTERVAL_SEC", "30")     # health check every 30s (was 60)
    watchdog_proc = subprocess.Popen(
        [PYTHON, "-u", "api_watchdog.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(ROOT),
        env=env,
    )
    threading.Thread(
        target=_stream_to_console,
        args=(watchdog_proc, "watchdog", WATCHDOG_LOG),
        daemon=True,
    ).start()
    log(f"Watchdog running (PID {watchdog_proc.pid})", "OK")


_shutting_down = False


def shutdown(*_):
    global _shutting_down
    if _shutting_down:
        return
    _shutting_down = True
    print()
    log("Shutting down…", "WARN")
    for p in (watchdog_proc, tunnel_proc, api_proc):
        if p and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass
    deadline = time.time() + 5
    for p in (watchdog_proc, tunnel_proc, api_proc):
        if p and p.poll() is None:
            try:
                p.wait(timeout=max(0.1, deadline - time.time()))
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
    kill_existing_cloudflared()
    kill_port(API_PORT)
    log("Stopped", "OK")
    sys.exit(0)


def banner(url):
    bar = "═" * 64
    print(f"\n{bar}")
    print("  Instagram Reel Scraper — running")
    print(bar)
    print(f"  Local API   : http://127.0.0.1:{API_PORT}")
    if url:
        print(f"  Public URL  : {url}")
        print(f"  Health      : {url}/health")
        print(f"  Scrape      : {url}/scrape?url=REEL_URL")
    print(f"  Logs        : api.log · tunnel_output.log · watchdog.log")
    print(f"{bar}")
    print("  Ctrl+C to stop everything\n")


def main():
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGHUP, shutdown)
    atexit.register(shutdown)

    if not start_api():
        shutdown()

    url = start_tunnel()
    start_watchdog()
    banner(url)

    global _public_fail_streak
    while True:
        time.sleep(15)
        if api_proc and api_proc.poll() is not None:
            log("API process exited — restarting", "WARN")
            start_api()

        rotate_tunnel = False
        named = use_named_tunnel()
        if tunnel_proc and tunnel_proc.poll() is not None:
            log("Tunnel process exited — restarting", "WARN")
            rotate_tunnel = True
        elif not named and tunnel_unauthorized():
            log("Quick tunnel invalidated by Cloudflare — provisioning a fresh one", "WARN")
            rotate_tunnel = True
        elif not named and not public_health_ok():
            _public_fail_streak += 1
            log(f"Public URL unreachable ({_public_fail_streak}/2)", "WARN")
            if _public_fail_streak >= 2:
                log("Public URL has been broken for 2 checks — rotating tunnel", "WARN")
                rotate_tunnel = True
                _public_fail_streak = 0
        else:
            _public_fail_streak = 0

        if rotate_tunnel:
            try:
                if tunnel_proc:
                    tunnel_proc.terminate()
                    tunnel_proc.wait(timeout=3)
            except Exception:
                pass
            kill_existing_cloudflared()
            url = start_tunnel()
            if url:
                log(f"New public URL: {url}", "OK")

        if watchdog_proc and watchdog_proc.poll() is not None:
            log("Watchdog exited — restarting", "WARN")
            start_watchdog()


if __name__ == "__main__":
    main()
