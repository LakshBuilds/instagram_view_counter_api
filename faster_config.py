"""
FASTER CONFIGURATION (Slightly Risky)
Reduces delay to 12 seconds for faster processing
"""

FASTER_CONFIG = {
    "accounts": [
        {"username": "candy_shopbuy", "password": "pass@@@123"},
        {"username": "bhdemo2025", "password": "passpass"},
        {"username": "elmasedoyle", "password": "yash1234"}
    ],
    "requests_per_cycle": 20,
    "delay_between_requests": 12.0,  # 12 seconds (5 req/min per account)
    "global_wait_minutes": 5.0,
}

# Time calculation:
# 20 reels × 12 seconds = 240 seconds (4 minutes per cycle)
# 60 reels in 4 minutes instead of 5 minutes