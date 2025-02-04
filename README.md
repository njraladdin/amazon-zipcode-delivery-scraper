# Amazon ASIN Zipcode Scraper

REST API service that retrieves Amazon product offers (prices, delivery estimates, availability) for given ASINs across multiple zip codes.

## Performance
Processes 200 zip codes for a single ASIN in under 20 seconds using concurrent sessions.

## How It Works

### Session Management
- Pre-creates authenticated Amazon sessions for faster ASIN offer scraping
- Maintains a pool of ready-to-use sessions with cookies and CSRF tokens
- Background thread automatically refills pool when running low
- Sessions are cached to disk for faster restarts
- Dynamic concurrency scaling based on CPU and network usage
- Sessions are locked while in use and returned to pool after

## Setup

### Prerequisites
- Python 3.9+
- pip

### Production
```bash
git clone [repository-url]
cd amazon-asin-zipcode-scraper
pip install -r requirements.txt
cp config.production.json config.json
python main.py
```

### Development
```bash
git clone [repository-url]
cd amazon-asin-zipcode-scraper
pip install -r requirements.txt
cp config.development.json config.json
python main.py
```

## Configuration

Two config files are provided:
- `config.development.json`: Lower concurrency limits, no proxy support
- `config.production.json`: Higher limits, proxy support enabled

Adjust settings in the config files as needed to experiment with performance.

## Proxies
Add proxies to `proxies.txt` in the following format:
```
ip:port:username:password
198.23.239.134:6540:user:pass
207.244.217.165:6712:user:pass
```

## API Usage

```bash
POST /scrape
{
    "asin": "B01EXAMPLE",
    "zipcodes": ["10001", "90210"]  # Optional, uses default 200 zip codes list if omitted
}
```

Response:
```json
{
    "asin": "B01EXAMPLE",
    "results": [
        {
            "zip_code": "10001",
            "price": "29.99",
            "delivery_estimate": "2 days",
            "available": true
        }
    ],
    "total_locations_processed": 2,
    "successful_locations": 1,
    "failed_locations": 1
}
```