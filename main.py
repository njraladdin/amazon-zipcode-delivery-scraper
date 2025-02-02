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
    
    # Use CONFIG instead of hardcoded value
    semaphore = asyncio.Semaphore(CONFIG["max_concurrent_zipcode_scrapers"])
    
    # Create a ThreadPoolExecutor with max_workers matching our semaphore limit
    from concurrent.futures import ThreadPoolExecutor
    thread_pool = ThreadPoolExecutor(max_workers=CONFIG["max_concurrent_zipcode_scrapers"])
    
    async def process_zipcode(zipcode: str):
        try:
            async with semaphore:
                logger.info(f"Starting processing for zipcode: {zipcode}")
                scraper = AmazonScraper()
                # Use the thread pool directly
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    thread_pool,
                    scraper.get_product_info,
                    request.asin,
                    zipcode
                )
                if result:
                    results.append(result)
                    logger.success(f"Completed processing for zipcode: {zipcode}")
                    return True
                else:
                    logger.error(f"Failed processing for zipcode: {zipcode}: No data returned")
                    failed_count += 1
                    return False
        except Exception as e:
            logger.error(f"Error processing zipcode {zipcode}: {str(e)}")
            failed_count += 1
            return False
        finally:
            await asyncio.sleep(1)
    
    # Create all tasks immediately - they'll wait on the semaphore internally
    tasks = [process_zipcode(zipcode) for zipcode in zipcodes_to_check]
    
    try:
        # Wait for all tasks to complete
        await asyncio.gather(*tasks)
    finally:
        # Make sure we clean up the thread pool
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
