"""
Proxy Configuration for Instagram Scraper
Supports rotating proxies for each request to avoid IP-based detection
"""
import random
from typing import Optional, Dict, List

# Proxy list - Add your proxies here
# Format: "protocol://user:pass@host:port" or "protocol://host:port"
PROXY_LIST: List[str] = [
    # Example proxies (replace with your actual proxies):
    # "http://user:pass@proxy1.example.com:8080",
    # "http://user:pass@proxy2.example.com:8080",
    # "socks5://user:pass@proxy3.example.com:1080",
]

# Proxy rotation settings
PROXY_CONFIG = {
    "enabled": False,  # Set to True when you add proxies
    "rotate_per_request": True,  # Change proxy for each request
    "retry_on_fail": True,  # Retry with different proxy on failure
    "max_retries": 3,  # Max retries with different proxies
}


class ProxyRotator:
    """Manages proxy rotation for requests"""
    
    def __init__(self, proxies: List[str] = None):
        self.proxies = proxies or PROXY_LIST
        self.current_index = 0
        self.failed_proxies = set()
        
    def get_proxy(self) -> Optional[Dict[str, str]]:
        """Get next proxy in rotation"""
        if not self.proxies or not PROXY_CONFIG["enabled"]:
            return None
        
        # Filter out failed proxies
        available = [p for p in self.proxies if p not in self.failed_proxies]
        
        if not available:
            # Reset failed proxies if all have failed
            self.failed_proxies.clear()
            available = self.proxies
        
        if not available:
            return None
        
        # Random selection for better distribution
        proxy = random.choice(available)
        
        # Format for requests library
        return {
            "http": proxy,
            "https": proxy
        }
    
    def get_random_proxy(self) -> Optional[Dict[str, str]]:
        """Get a random proxy"""
        if not self.proxies or not PROXY_CONFIG["enabled"]:
            return None
        
        proxy = random.choice(self.proxies)
        return {
            "http": proxy,
            "https": proxy
        }
    
    def mark_failed(self, proxy_url: str):
        """Mark a proxy as failed"""
        self.failed_proxies.add(proxy_url)
        print(f"   ⚠️ Proxy marked as failed: {proxy_url[:30]}...")
    
    def reset(self):
        """Reset failed proxies"""
        self.failed_proxies.clear()
    
    def get_stats(self) -> Dict:
        """Get proxy statistics"""
        return {
            "total_proxies": len(self.proxies),
            "failed_proxies": len(self.failed_proxies),
            "available_proxies": len(self.proxies) - len(self.failed_proxies),
            "enabled": PROXY_CONFIG["enabled"]
        }


# Global proxy rotator instance
proxy_rotator = ProxyRotator()


def get_next_proxy() -> Optional[Dict[str, str]]:
    """Convenience function to get next proxy"""
    return proxy_rotator.get_proxy()


def add_proxies(proxy_list: List[str]):
    """Add proxies to the rotator"""
    global proxy_rotator
    proxy_rotator.proxies.extend(proxy_list)
    PROXY_CONFIG["enabled"] = True
    print(f"✅ Added {len(proxy_list)} proxies. Total: {len(proxy_rotator.proxies)}")


def enable_proxies():
    """Enable proxy rotation"""
    PROXY_CONFIG["enabled"] = True
    print("✅ Proxy rotation enabled")


def disable_proxies():
    """Disable proxy rotation"""
    PROXY_CONFIG["enabled"] = False
    print("❌ Proxy rotation disabled")
