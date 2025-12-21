"""
Monitor the parallel scraper execution
"""
import time
import subprocess

def monitor_progress():
    print("🔍 MONITORING PARALLEL SCRAPER")
    print("="*50)
    
    while True:
        try:
            # Check if process is still running
            result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq python.exe'], 
                                  capture_output=True, text=True)
            
            if 'auto_run_parallel.py' in result.stdout:
                print(f"⏳ {time.strftime('%H:%M:%S')} - Scraper is running...")
            else:
                print("✅ Scraper completed or stopped")
                break
                
            time.sleep(30)  # Check every 30 seconds
            
        except KeyboardInterrupt:
            print("\n🛑 Monitoring stopped")
            break

if __name__ == "__main__":
    monitor_progress()