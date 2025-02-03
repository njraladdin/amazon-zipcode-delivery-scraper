from amazon_scraper import AmazonScraper
import asyncio
from fastapi import FastAPI, HTTPException
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import uvicorn
import socket
import json
from pathlib import Path
from logger import setup_logger
from utils import load_config
from asyncio import Semaphore
from resource_monitor import ResourceMonitor
from concurrent.futures import ThreadPoolExecutor
import threading
import time

# Load default zipcodes from JSON file
def load_default_zipcodes():
    json_path = Path(__file__).parent / "zipcodes.json"
    try:
        with open(json_path, "r") as f:
            data = json.load(f)
            return data["default_zipcodes"]
    except Exception as e:
        print(f"Error loading zipcodes.json: {e}")
        return DEFAULT_ZIPCODES  # Fall back to hardcoded list if file can't be loaded

# Replace the hardcoded DEFAULT_ZIPCODES with the function call
DEFAULT_ZIPCODES = load_default_zipcodes()

# Create FastAPI app
app = FastAPI()

# Define request and response models
class ScrapeRequest(BaseModel):
    asin: str
    zipcodes: Optional[List[str]] = None

class ScrapeResponse(BaseModel):
    asin: str
    results: List[Dict[str, Any]]
    total_locations_processed: int
    successful_locations: int
    failed_locations: int

# After imports
logger = setup_logger('FastAPI')

# Load configuration
CONFIG = load_config()
print(CONFIG)

# After imports
resource_monitor = ResourceMonitor()

# After CONFIG loading
MAX_CONCURRENT_SCRAPERS = CONFIG.get("max_concurrent_zipcode_scrapers", 10)
thread_pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_SCRAPERS)

@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_product(request: ScrapeRequest):
    resource_monitor = ResourceMonitor(monitor_interval=0.1)
    resource_monitor.start()
    
    try:
        results = []
        failed_locations = set()
        zipcodes_to_check = request.zipcodes if request.zipcodes else DEFAULT_ZIPCODES

        def process_batch(batch_zipcodes: List[str]) -> tuple:
            try:
                scraper = AmazonScraper()
                logger.info(f"Processing zipcodes: {batch_zipcodes}")
                batch_results = scraper.process_multiple_zipcodes(request.asin, batch_zipcodes)
                return batch_results, batch_zipcodes
            except Exception as e:
                logger.error(f"Error processing batch {batch_zipcodes}: {str(e)}")
                return None, batch_zipcodes

        # Create batches
        batch_size = CONFIG.get("batch_size", 5)
        zipcode_batches = [
            zipcodes_to_check[i:i + batch_size] 
            for i in range(0, len(zipcodes_to_check), batch_size)
        ]
        
        # Initialize futures list
        futures = []
        active_futures = set()
        
        # Load scaling settings from config
        scaling_config = CONFIG.get("concurrent_requests_control", {})
        initial_concurrent = scaling_config.get("initial_concurrent", 20)
        max_concurrent = CONFIG.get("max_concurrent_zipcode_scrapers", 200)
        current_concurrent = initial_concurrent
        scale_up_delay = scaling_config.get("scale_up_delay", 0.2)
        scale_increment = scaling_config.get("scale_increment", 10)
        
        # Process batches with dynamic concurrency
        batch_index = 0
        last_scale_up = time.time()
        while batch_index < len(zipcode_batches) or active_futures:
            current_time = time.time()
            
            # Clean up completed futures
            done_futures = {f for f in active_futures if f.done()}
            for future in done_futures:
                try:
                    result, batch_zipcodes = future.result()
                    if result:
                        results.extend(result)
                        successful_zipcodes = {r['zip_code'] for r in result if r}
                        failed_zipcodes = set(batch_zipcodes) - successful_zipcodes
                        failed_locations.update(failed_zipcodes)
                    else:
                        failed_locations.update(batch_zipcodes)
                except Exception as e:
                    logger.error(f"Error processing future: {str(e)}")
                active_futures.remove(future)

            # Simple scaling check
            if (current_time - last_scale_up > scale_up_delay and 
                current_concurrent < max_concurrent):
                usage = resource_monitor.get_statistics_summary().get('download_usage_pct', {}).get('current', 0)
                if usage < 80:  # Hardcoded threshold
                    current_concurrent = min(current_concurrent + scale_increment, max_concurrent)
                    last_scale_up = current_time
                    logger.info(f"Scaling up to {current_concurrent} concurrent requests (usage: {usage:.1f}%)")

            # Submit new batches if we have capacity
            while (batch_index < len(zipcode_batches) and 
                   len(active_futures) < current_concurrent):
                future = thread_pool.submit(process_batch, zipcode_batches[batch_index])
                active_futures.add(future)
                futures.append(future)
                batch_index += 1

            await asyncio.sleep(0.1)  # Small delay to prevent CPU spinning

    finally:
        resource_monitor.stop()
    
    if not results:
        raise HTTPException(status_code=404, detail="No data could be retrieved for the given ASIN")
    
    return ScrapeResponse(
        asin=request.asin,
        results=results,
        total_locations_processed=len(zipcodes_to_check),
        successful_locations=len(results),
        failed_locations=len(failed_locations)
    )

if __name__ == "__main__":
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    
    logger.info("Starting server...")
    logger.info(f"Hostname: {hostname}")
    logger.info(f"Local IP: {local_ip}")
    logger.info(f"Server will run at: http://{local_ip}:{CONFIG['port']}")
    
    uvicorn.run(
        app, 
        host="0.0.0.0",
        port=CONFIG["port"],
        log_level="debug",
        access_log=True
    )
