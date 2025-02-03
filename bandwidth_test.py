import speedtest
import time
import json
from pathlib import Path
from logger import setup_logger
from datetime import datetime, timedelta

logger = setup_logger('BandwidthTest')

CACHE_FILE = Path(__file__).parent / "bandwidth_cache.json"
CACHE_EXPIRY_HOURS = 24  # Cache results for 24 hours

def load_cached_bandwidth():
    """Load bandwidth results from cache if still valid"""
    try:
        if not CACHE_FILE.exists():
            return None
            
        with open(CACHE_FILE, 'r') as f:
            cache = json.load(f)
            
        # Check if cache has expired
        cached_time = datetime.fromisoformat(cache['timestamp'])
        if datetime.now() - cached_time > timedelta(hours=CACHE_EXPIRY_HOURS):
            logger.info("Cached bandwidth results have expired")
            return None
            
        logger.info("Using cached bandwidth results")
        return {
            'download_mbps': cache['download_mbps'],
            'upload_mbps': cache['upload_mbps']
        }
        
    except Exception as e:
        logger.error(f"Error loading bandwidth cache: {str(e)}")
        return None

def save_bandwidth_cache(results):
    """Save bandwidth results to cache"""
    try:
        cache_data = {
            'timestamp': datetime.now().isoformat(),
            'download_mbps': results['download_mbps'],
            'upload_mbps': results['upload_mbps']
        }
        
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache_data, f)
            
    except Exception as e:
        logger.error(f"Error saving bandwidth cache: {str(e)}")

def measure_bandwidth(force_test=False):
    """Measure current bandwidth capabilities"""
    if not force_test:
        cached_results = load_cached_bandwidth()
        if cached_results:
            return cached_results
    
    logger.info("Starting bandwidth measurement test...")
    try:
        st = speedtest.Speedtest()
        st.get_best_server()
        
        # Measure download speed (bits/s)
        download_speed = st.download()
        # Measure upload speed (bits/s)
        upload_speed = st.upload()
        
        # Convert to Mbps
        download_mbps = download_speed / 1_000_000
        upload_mbps = upload_speed / 1_000_000
        
        results = {
            'download_mbps': download_mbps,
            'upload_mbps': upload_mbps
        }
        
        logger.info(f"Download speed: {download_mbps:.2f} Mbps")
        logger.info(f"Upload speed: {upload_mbps:.2f} Mbps")
        
        # Cache the results
        save_bandwidth_cache(results)
        
        return results
    
    except Exception as e:
        logger.error(f"Error measuring bandwidth: {str(e)}")
        return None

if __name__ == "__main__":
    # Use force_test=True to force a new measurement
    measure_bandwidth(force_test=True) 