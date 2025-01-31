from amazon_scraper import AmazonScraper
import time
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
    scraper = AmazonScraper()
    results = []
    failed_count = 0
    
    # Use provided zipcodes or default ones
    zipcodes_to_check = request.zipcodes if request.zipcodes else DEFAULT_ZIPCODES
    
    for zipcode in zipcodes_to_check:
        try:
            result = scraper.get_product_info(request.asin, zipcode)
            
            if result:
                results.append(result)
            
            # Add a delay between requests to avoid rate limiting
            time.sleep(1)
            
        except Exception as e:
            failed_count += 1
            continue
    
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
    print(f"\nServer running at: http://{local_ip}:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
