"""
Session Management System Overview:

We pre-create Amazon sessions in advance so when we need to scrape ASIN offers, it's much faster.
(A session is an authenticated Amazon connection using tls_client, with cookies, CSRF tokens, etc.)

1. Pool Initialization:
   - Creates initial_session_pool_size sessions at startup
   - Sessions are cached to disk for faster restarts

2. Session Factory:
   - Background thread continuously maintains minimum pool size
   - Automatically creates new sessions when pool runs low

3. Request Handling:
   - Calculates needed sessions based on zipcode batch size
   - Gets all required sessions upfront before processing
   - Sessions are locked (via Queue) when in use
   - Returns sessions to pool after use


"""

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
from resource_monitor import ResourceMonitor
from concurrent.futures import ThreadPoolExecutor
import time
from session_pool import SessionPool
from amazon_bigquery import AmazonBigQuery
from fastapi.background import BackgroundTasks

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

# Initialize session pool
session_pool = None

# Load configuration
CONFIG = load_config()
MAX_CONCURRENT_SCRAPERS = CONFIG.get("max_concurrent_zipcode_scrapers", 200)

# Constants for session pool
INITIAL_POOL_SIZE = CONFIG.get("initial_session_pool_size", 200)
REFILL_THRESHOLD = CONFIG.get("session_pool_refill_threshold", 100) # start refilling when number of available sessions is less than this

# Add after other global variables
bq_client = None

@app.on_event("startup")
async def startup_event():
    global session_pool, bq_client
    session_pool = SessionPool()
    session_pool.initialize_pool()
    logger.info(f"Started server with {session_pool.get_pool_size()} pre-initialized sessions")
    session_pool.start_background_workers()  # Start both factory and health checker
    
    # Initialize BigQuery client only if enabled in config
    if CONFIG.get("allow_bigquery", False):
        for attempt in range(3):  # Try 3 times
            try:
                bq_client = AmazonBigQuery('google-service-account.json')
                logger.info("Successfully initialized BigQuery client")
                break
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed to initialize BigQuery client: {e}")
                if attempt == 2:  # Last attempt
                    logger.error("All attempts to initialize BigQuery client failed")
                    bq_client = None
                await asyncio.sleep(1)  # Wait before retry
    else:
        logger.info("BigQuery uploads disabled in configuration")
        bq_client = None

@app.on_event("shutdown")
async def shutdown_event():
    if session_pool:
        session_pool.shutdown()

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

# After imports
resource_monitor = ResourceMonitor()

# After CONFIG loading
thread_pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_SCRAPERS)

# Add this function to handle BigQuery upload
def upload_to_bigquery(data: dict):
    if not CONFIG.get("allow_bigquery", False):
        logger.info("Skipping BigQuery upload - disabled in configuration")
        return
        
    try:
        if bq_client:
            logger.info(f"Attempting to upload {len(data['results'])} results to BigQuery")
            logger.debug(f"First result sample: {json.dumps(data['results'][0] if data['results'] else 'No results')}")
            
            # Log the first offer data as sample
            if data['results'] and data['results'][0]['offers_data']:
                logger.debug(f"First offer sample: {json.dumps(data['results'][0]['offers_data'][0])}")
            
            success = bq_client.load_offers(data)
            if success:
                logger.success(f"Successfully uploaded data to BigQuery for ASIN {data['asin']}")
            else:
                logger.error(f"Failed to upload data to BigQuery for ASIN {data['asin']}")
    except Exception as e:
        logger.error(f"Error uploading to BigQuery: {str(e)}")
        logger.exception("Full traceback:")  # This will log the full stack trace

@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_product(request: ScrapeRequest, background_tasks: BackgroundTasks):
    resource_monitor = ResourceMonitor(monitor_interval=0.1)
    resource_monitor.start()
    
    try:
        zipcodes_to_check = request.zipcodes if request.zipcodes else DEFAULT_ZIPCODES
        batch_size = CONFIG.get("batch_size", 5)
        
        # Calculate how many sessions we need for this request
        needed_sessions = min(
            len(zipcodes_to_check) // batch_size + (1 if len(zipcodes_to_check) % batch_size else 0),
            CONFIG.get("max_concurrent_zipcode_scrapers", 200)
        )
        
        # Get all needed sessions upfront
        try:
            sessions = session_pool.get_sessions(needed_sessions)
            logger.info(f"Got {len(sessions)} sessions for processing")
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Session pool error: {str(e)}")
        
        try:
            results = []
            failed_locations = set()
            
            def process_batch(batch_zipcodes: List[str]) -> tuple:
                try:
                    # Get a session from the list
                    scraper = sessions.pop(0)  # Remove and get session
                    logger.info(f"Processing zipcodes: {batch_zipcodes}")
                    
                    try:
                        batch_results = scraper.process_multiple_zipcodes(request.asin, batch_zipcodes)
                        if batch_results:  # Only return session to pool if successful
                            session_pool.return_sessions([scraper])
                            return batch_results, batch_zipcodes
                        else:
                            logger.warning(f"Batch failed, discarding session")
                            return None, batch_zipcodes
                    except Exception as e:
                        logger.error(f"Error processing batch {batch_zipcodes}: {str(e)}")
                        logger.warning(f"Batch failed, discarding session")
                        return None, batch_zipcodes
                        
                except Exception as e:
                    logger.error(f"Error processing batch {batch_zipcodes}: {str(e)}")
                    return None, batch_zipcodes

            # Create batches
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
                    stats = resource_monitor.get_statistics_summary()
                    download_usage = stats.get('download_usage_pct', {}).get('current', 0)
                    cpu_usage = stats.get('cpu_percent', {}).get('current', 0)
                    
                    # More aggressive CPU threshold (85% instead of 50%)
                    if download_usage < 80 and cpu_usage < 85:  
                        # Use scale_increment instead of incrementing by 1
                        current_concurrent = min(max_concurrent, 
                                              current_concurrent + scale_increment)
                        last_scale_up = current_time
                        # logger.info(f"Scaling up to {current_concurrent} concurrent requests "
                        #           f"(download: {download_usage:.1f}%, CPU: {cpu_usage:.1f}%)")
                    elif cpu_usage >= 85:
                        # Only scale down by 1 to be less reactive
                        current_concurrent = max(1, current_concurrent - 1)
                        logger.warning(f"Scaling down to {current_concurrent} due to high CPU "
                                     f"usage ({cpu_usage:.1f}%)")

                # Submit new batches if we have capacity
                while (batch_index < len(zipcode_batches) and 
                       len(active_futures) < current_concurrent):
                    future = thread_pool.submit(process_batch, zipcode_batches[batch_index])
                    active_futures.add(future)
                    futures.append(future)
                    batch_index += 1

                await asyncio.sleep(0.1)  # Small delay to prevent CPU spinning

        finally:
            # Always return sessions to the pool
            session_pool.return_sessions(sessions)

        # Prepare response
        response_data = ScrapeResponse(
            asin=request.asin,
            results=results,
            total_locations_processed=len(zipcodes_to_check),
            successful_locations=len(results),
            failed_locations=len(failed_locations)
        )

        if not results:
            raise HTTPException(status_code=404, detail="No data could be retrieved for the given ASIN")

        # Add BigQuery upload as background task with raw data
        background_tasks.add_task(upload_to_bigquery, response_data.dict())
        
        return response_data

    finally:
        resource_monitor.stop()

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
