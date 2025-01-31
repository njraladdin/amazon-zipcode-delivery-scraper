from amazon_scraper import AmazonScraper
import asyncio
from fastapi import FastAPI, HTTPException
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import uvicorn
import socket

# List of default zipcodes to test
DEFAULT_ZIPCODES = [
    "99501",  # Anchorage, AK
    "33101",  # Miami, FL
    "98101",  # Seattle, WA
    "02108",  # Boston, MA
    "92101",  # San Diego, CA
    "96813",  # Honolulu, HI
    "75201",  # Dallas, TX
    "60601",  # Chicago, IL
    "10001",  # New York, NY
    "80201",  # Denver, CO
    "89101",  # Las Vegas, NV
    "04101",  # Portland, ME
]

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

@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_product(request: ScrapeRequest):
    results = []
    failed_count = 0
    
    # Use provided zipcodes or default ones
    zipcodes_to_check = request.zipcodes if request.zipcodes else DEFAULT_ZIPCODES
    
    # Create a semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(4)
    
    async def process_zipcode(zipcode: str):
        nonlocal failed_count
        async with semaphore:
            try:
                # Create a new scraper instance for each request
                scraper = AmazonScraper()
                # Run the synchronous get_product_info in a thread pool
                result = await asyncio.to_thread(scraper.get_product_info, request.asin, zipcode)
                if result:
                    results.append(result)
                    return True
                else:
                    # Increment failed_count when result is None
                    print(f"Failed to process zipcode {zipcode}: No data returned")
                    failed_count += 1
                    return False
            except Exception as e:
                print(f"Error processing zipcode {zipcode}: {str(e)}")
                failed_count += 1
                return False
            finally:
                await asyncio.sleep(1)  # Add delay between requests
    
    # Create tasks for all zipcodes
    tasks = [process_zipcode(zipcode) for zipcode in zipcodes_to_check]
    
    # Wait for all tasks to complete
    await asyncio.gather(*tasks)
    
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
    
    # Add more logging
    print(f"Starting server...")
    print(f"Hostname: {hostname}")
    print(f"Local IP: {local_ip}")
    print(f"Server will run at: http://{local_ip}:8080")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8080,
        log_level="debug",  # Changed to debug for more verbose logging
        access_log=True,
        workers=1
    )
