"""
Smart Delay System - Human-like random delays to avoid detection

Features:
1. Random delays within a range (e.g., 1.5s to 3.5s instead of fixed 2s)
2. Occasional longer "thinking" pauses
3. Burst detection - slow down if too many requests too fast
4. Time-of-day awareness (optional)
"""
import random
import time
from datetime import datetime
from typing import Tuple

class SmartDelay:
    """Human-like delay system to avoid Instagram detection"""
    
    def __init__(self, 
                 min_delay: float = 1.5,
                 max_delay: float = 4.0,
                 burst_threshold: int = 5,
                 long_pause_chance: float = 0.1,
                 long_pause_range: Tuple[float, float] = (8.0, 15.0)):
        """
        Initialize smart delay system
        
        Args:
            min_delay: Minimum delay in seconds
            max_delay: Maximum delay in seconds
            burst_threshold: Number of fast requests before forcing longer delay
            long_pause_chance: Probability of taking a longer "thinking" pause
            long_pause_range: Range for long pauses (min, max) in seconds
        """
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.burst_threshold = burst_threshold
        self.long_pause_chance = long_pause_chance
        self.long_pause_range = long_pause_range
        
        # Tracking
        self.request_times = []
        self.total_requests = 0
        self.delays_used = []
        
    def get_delay(self) -> float:
        """
        Get a human-like random delay
        
        Returns:
            Delay in seconds
        """
        self.total_requests += 1
        now = time.time()
        
        # Clean old request times (keep last 60 seconds)
        self.request_times = [t for t in self.request_times if now - t < 60]
        self.request_times.append(now)
        
        # Check for burst - if too many requests recently, add extra delay
        recent_requests = len(self.request_times)
        burst_penalty = 0
        
        if recent_requests > self.burst_threshold:
            # Add penalty for burst behavior
            burst_penalty = (recent_requests - self.burst_threshold) * 0.5
            
        # Random chance of long pause (simulates human "thinking" or distraction)
        if random.random() < self.long_pause_chance:
            delay = random.uniform(*self.long_pause_range)
            delay_type = "long_pause"
        else:
            # Normal random delay with some variation
            # Use triangular distribution - more likely to be in the middle
            base_delay = random.triangular(self.min_delay, self.max_delay)
            
            # Add small random jitter
            jitter = random.uniform(-0.3, 0.3)
            
            delay = base_delay + jitter + burst_penalty
            delay_type = "normal" if burst_penalty == 0 else "burst_adjusted"
        
        # Ensure minimum delay
        delay = max(self.min_delay, delay)
        
        self.delays_used.append(delay)
        
        return delay, delay_type
    
    def wait(self, verbose: bool = True) -> float:
        """
        Wait for a human-like delay
        
        Args:
            verbose: Print delay information
            
        Returns:
            Actual delay used
        """
        delay, delay_type = self.get_delay()
        
        if verbose:
            if delay_type == "long_pause":
                print(f"   ⏳ Taking a break... ({delay:.1f}s)")
            elif delay_type == "burst_adjusted":
                print(f"   ⏳ Slowing down... ({delay:.1f}s)")
            else:
                print(f"   ⏳ Waiting {delay:.1f}s...")
        
        time.sleep(delay)
        return delay
    
    def get_stats(self) -> dict:
        """Get delay statistics"""
        if not self.delays_used:
            return {"total_requests": 0}
        
        return {
            "total_requests": self.total_requests,
            "avg_delay": sum(self.delays_used) / len(self.delays_used),
            "min_delay_used": min(self.delays_used),
            "max_delay_used": max(self.delays_used),
            "total_wait_time": sum(self.delays_used),
        }


# Preset configurations
CONSERVATIVE_DELAY = SmartDelay(
    min_delay=3.0,
    max_delay=6.0,
    burst_threshold=3,
    long_pause_chance=0.15,
    long_pause_range=(10.0, 20.0)
)

BALANCED_DELAY = SmartDelay(
    min_delay=1.5,
    max_delay=4.0,
    burst_threshold=5,
    long_pause_chance=0.1,
    long_pause_range=(8.0, 15.0)
)

AGGRESSIVE_DELAY = SmartDelay(
    min_delay=0.8,
    max_delay=2.0,
    burst_threshold=8,
    long_pause_chance=0.05,
    long_pause_range=(5.0, 10.0)
)


def demo():
    """Demo the smart delay system"""
    print("🧪 SMART DELAY DEMO")
    print("="*60)
    
    delay_system = BALANCED_DELAY
    
    print("Simulating 10 requests with human-like delays:\n")
    
    for i in range(1, 11):
        print(f"📤 Request {i}/10")
        delay_system.wait()
        print()
    
    stats = delay_system.get_stats()
    print("="*60)
    print("📊 DELAY STATISTICS:")
    print(f"   Total requests: {stats['total_requests']}")
    print(f"   Average delay: {stats['avg_delay']:.2f}s")
    print(f"   Min delay used: {stats['min_delay_used']:.2f}s")
    print(f"   Max delay used: {stats['max_delay_used']:.2f}s")
    print(f"   Total wait time: {stats['total_wait_time']:.1f}s")


if __name__ == "__main__":
    demo()