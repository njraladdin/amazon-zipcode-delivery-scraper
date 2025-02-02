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

# Constants
MAX_CONCURRENT_ZIPCODE_SCRAPERS = 10  # Maximum number of concurrent zipcode processing operations

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
    failed_count = 0
    
    # Use provided zipcodes or default ones
    zipcodes_to_check = request.zipcodes if request.zipcodes else DEFAULT_ZIPCODES
    
    # Split zipcodes into batches of 5
    BATCH_SIZE = 3
    zipcode_batches = [
        zipcodes_to_check[i:i + BATCH_SIZE] 
        for i in range(0, len(zipcodes_to_check), BATCH_SIZE)
    ]
    
    # Use CONFIG for concurrent scrapers (one per batch)
    semaphore = asyncio.Semaphore(CONFIG["max_concurrent_zipcode_scrapers"])
    thread_pool = ThreadPoolExecutor(max_workers=CONFIG["max_concurrent_zipcode_scrapers"])
    
    async def process_batch(batch_zipcodes: List[str]):
        try:
            async with semaphore:
                # Create one scraper instance per batch
                scraper = AmazonScraper()
                logger.info(f"Starting batch processing for zipcodes: {batch_zipcodes}")
                
                loop = asyncio.get_running_loop()
                # Run the blocking scraper method in thread pool
                batch_results = await loop.run_in_executor(
                    thread_pool,
                    lambda: asyncio.run(scraper.process_multiple_zipcodes(request.asin, batch_zipcodes))
                )
                
                if batch_results:
                    logger.success(f"Successfully processed batch with zipcodes: {batch_zipcodes}")
                    return batch_results
                else:
                    logger.error(f"Failed to process batch with zipcodes: {batch_zipcodes}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error processing batch {batch_zipcodes}: {str(e)}")
            return []
    
    try:
        # Create and run all batch tasks concurrently
        batch_tasks = [process_batch(batch) for batch in zipcode_batches]
        batch_results = await asyncio.gather(*batch_tasks)
        
        # Flatten results from all batches
        for batch_result in batch_results:
            if batch_result:
                results.extend(batch_result)
            else:
                failed_count += 1
                
    finally:
        thread_pool.shutdown(wait=False)
    
    if not results:
        raise HTTPException(status_code=404, detail="No data could be retrieved for the given ASIN")
    
    return ScrapeResponse(
        asin=request.asin,
        results=results,
        total_locations_processed=len(zipcodes_to_check),
        successful_locations=len(results),
        failed_locations=failed_count
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
