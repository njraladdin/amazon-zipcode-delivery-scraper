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
    resource_monitor.start()
    
    try:
        results = []
        failed_locations = set()
        zipcodes_to_check = request.zipcodes if request.zipcodes else DEFAULT_ZIPCODES

        def process_batch(batch_zipcodes: List[str]) -> tuple:
            try:
                # Create scraper instance per thread
                scraper = AmazonScraper()
                logger.info(f"Processing zipcodes: {batch_zipcodes}")
                
                # Run the sync code directly without asyncio
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
        
        # Submit all batches to thread pool and wait for completion
        futures = [thread_pool.submit(process_batch, batch) for batch in zipcode_batches]
        
        # Process results as they complete
        for future in futures:
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
                continue

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
