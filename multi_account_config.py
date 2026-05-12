"""
Multi-Account Configuration for Instagram Scraper
Defines account credentials and rate limiting settings
"""

# Account credentials - UPDATE WITH YOUR ACTUAL ACCOUNTS
MULTI_ACCOUNT_CONFIG = {
    "accounts": [
        {"username": "bhdemo2025", "password": "pass@@"},
        {"username": "hatke_automation", "password": "pass@@@123P"},
    ],
    "requests_per_cycle": 20,        # Requests per account per cycle
    "delay_between_requests": 15.0,  # Seconds between requests (4 req/min per account)
    "global_wait_minutes": 5.0,      # Minutes to wait between cycles
}

# Proxy Configuration - Add your proxies here
PROXY_LIST = []

# Configuration 1: Conservative (Safest)
CONSERVATIVE_CONFIG = {
    "accounts": MULTI_ACCOUNT_CONFIG["accounts"],
    "requests_per_cycle": 15,
    "delay_between_requests": 20.0,
    "global_wait_minutes": 6.0,
}

# Configuration 2: Aggressive (Higher throughput, higher risk)
AGGRESSIVE_CONFIG = {
    "accounts": MULTI_ACCOUNT_CONFIG["accounts"],
    "requests_per_cycle": 25,
    "delay_between_requests": 12.0,
    "global_wait_minutes": 4.0,
}

# Configuration 3: Balanced (Recommended)
BALANCED_CONFIG = MULTI_ACCOUNT_CONFIG

def validate_config(config):
    """Validate configuration parameters"""
    required_keys = ["accounts", "requests_per_cycle", "delay_between_requests", "global_wait_minutes"]
    
    for key in required_keys:
        if key not in config:
            raise ValueError(f"Missing required config key: {key}")
    
    if not config["accounts"]:
        raise ValueError("At least one account must be configured")
    
    for account in config["accounts"]:
        if "username" not in account or "password" not in account:
            raise ValueError("Each account must have username and password")
    
    return True
