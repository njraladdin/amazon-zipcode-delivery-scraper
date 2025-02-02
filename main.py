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
from concurrent.futures import ThreadPoolExecutor

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
@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_product(request: ScrapeRequest):
    results = []
    failed_locations = set()  # Track failed zipcodes
    
    # Use provided zipcodes or default ones
    zipcodes_to_check = request.zipcodes if request.zipcodes else DEFAULT_ZIPCODES
    
    # Use batch size from config
    zipcode_batches = [
        zipcodes_to_check[i:i + CONFIG["batch_size"]] 
        for i in range(0, len(zipcodes_to_check), CONFIG["batch_size"])
    ]
    
    # Use CONFIG for thread pool only
    thread_pool = ThreadPoolExecutor(max_workers=CONFIG["max_concurrent_zipcode_scrapers"])
    
    async def process_batch(batch_zipcodes: List[str]):
        try:
            # Create one scraper instance per batch
            scraper = AmazonScraper()
            logger.info(f"Starting batch processing for zipcodes: {batch_zipcodes}")
            
            loop = asyncio.get_running_loop()
            # Run the blocking scraper method in thread pool
            batch_results = await loop.run_in_executor(
                thread_pool,
                lambda: asyncio.run(scraper.process_multiple_zipcodes(request.asin, batch_zipcodes))
            )
            
            # Track failed zipcodes from this batch
            successful_zipcodes = {result['zip_code'] for result in batch_results if result}
            failed_zipcodes = set(batch_zipcodes) - successful_zipcodes
            failed_locations.update(failed_zipcodes)
            
            return batch_results
                
        except Exception as e:
            logger.error(f"Error processing batch {batch_zipcodes}: {str(e)}")
            failed_locations.update(batch_zipcodes)  # Mark all zipcodes in failed batch
            return []
    
    try:
        # Create and run all batch tasks concurrently
        batch_tasks = [process_batch(batch) for batch in zipcode_batches]
        batch_results = await asyncio.gather(*batch_tasks)
        
        # Flatten results from all batches
        for batch_result in batch_results:
            if batch_result:
                results.extend(batch_result)
                
    finally:
        thread_pool.shutdown(wait=False)
    
    if not results:
        raise HTTPException(status_code=404, detail="No data could be retrieved for the given ASIN")
    
    return ScrapeResponse(
        asin=request.asin,
        results=results,
        total_locations_processed=len(zipcodes_to_check),
        successful_locations=len(results),
        failed_locations=len(failed_locations)  # Now accurately tracks failed locations
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
