"""
Multi-Account Configuration for Instagram Scraper
Defines account credentials and rate limiting settings
"""

# Account credentials - UPDATE WITH YOUR ACTUAL ACCOUNTS
MULTI_ACCOUNT_CONFIG = {
    "accounts": [
        {"username": "candy_shopbuy", "password": "pass@@@123"},
        {"username": "bhdemo2025", "password": "passpass"},
        {"username": "elmasedoyle", "password": "yash1234"}
    ],
    "requests_per_cycle": 20,        # Requests per account per cycle
    "delay_between_requests": 15.0,  # Seconds between requests (4 req/min per account)
    "global_wait_minutes": 5.0,      # Minutes to wait between cycles
}

# Proxy Configuration - Add your proxies here
# Format: "http://user:pass@host:port" or "socks5://user:pass@host:port"
PROXY_LIST = [
    # Example proxies (uncomment and replace with your actual proxies):
    # "http://user:pass@proxy1.example.com:8080",
    # "http://user:pass@proxy2.example.com:8080",
    # "socks5://user:pass@proxy3.example.com:1080",
]

# Configuration 1: Conservative (Safest)
CONSERVATIVE_CONFIG = {
    "accounts": MULTI_ACCOUNT_CONFIG["accounts"],
    "requests_per_cycle": 15,        # Reduced requests per cycle
    "delay_between_requests": 20.0,  # Longer delays (3 req/min per account)
    "global_wait_minutes": 6.0,      # Longer global wait
}

# Configuration 2: Aggressive (Higher throughput, higher risk)
AGGRESSIVE_CONFIG = {
    "accounts": MULTI_ACCOUNT_CONFIG["accounts"],
    "requests_per_cycle": 25,        # More requests per cycle
    "delay_between_requests": 12.0,  # Shorter delays (5 req/min per account)
    "global_wait_minutes": 4.0,      # Shorter global wait
}

# Configuration 3: Balanced (Recommended)
BALANCED_CONFIG = MULTI_ACCOUNT_CONFIG  # Use the default config

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
    
    if config["requests_per_cycle"] <= 0:
        raise ValueError("requests_per_cycle must be positive")
    
    if config["delay_between_requests"] <= 0:
        raise ValueError("delay_between_requests must be positive")
    
    if config["global_wait_minutes"] <= 0:
        raise ValueError("global_wait_minutes must be positive")
    
    return True