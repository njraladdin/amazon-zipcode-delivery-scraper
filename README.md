# Amazon Zipcode Delivery Scraper

REST API service that retrieves Amazon product offers (prices, delivery estimates, availability) for given ASINs across multiple zip codes.

## Performance
Processes 200 zip codes for a single ASIN in under 20 seconds using concurrent sessions.

## Prerequisites
- Python 3.9+
- Google Cloud account
- Proxies (for production use)

## Setup Overview

1. Google Cloud Services Setup
   - BigQuery for data storage
   - Compute Engine VM (for production)
2. Local Development Setup
3. Production Deployment

## Google Cloud Setup

1. BigQuery Setup
    1. Go to [Google Cloud Console](https://console.cloud.google.com/)
    2. Create a new project or select an existing one
    3. Enable the BigQuery API for your project
    4. Create Service Account:
        1. Go to "IAM & Admin" > "Service Accounts"
        2. Click "Create Service Account"
        3. Fill in service account details:
           - Name: `amazon-offers-bigquery`
           - Description: `Service account for Amazon offers data`
        4. Grant these roles:
           - `BigQuery Data Editor`
           - `BigQuery Job User`
        5. Click "Done"
    5. Generate Credentials:
        1. Find your service account in the list
        2. Click on the service account name
        3. Go to "Keys" tab
        4. Click "Add Key" > "Create new key"
        5. Choose JSON format
        6. Download the key file

2. Compute Engine Setup (for production)
    1. Go to Google Cloud Console > Compute Engine
    2. Click "Create Instance"
    3. Choose VM type based on your performance requirements and budget
    4. Under "Boot disk", click "Change"
       - Select Ubuntu as operating system
    5. Under "Networking", in Firewall rules:
       - Allow HTTP traffic
       - Allow HTTPS traffic
    6. Click Create

## Installation and Setup

1. Project Installation
```bash
# Clone repository
git clone https://github.com/njraladdin/amazon-zipcode-delivery-scraper.git
cd amazon-zipcode-delivery-scraper

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

2. Add BigQuery Credentials
    - For Local Development:
        1. Rename the downloaded key file to `google-service-account.json`
        2. Place it in the project root directory

    - For Production Server:
        1. Connect to your server and create the credentials file:
        ```bash
        nano google-service-account.json
        ```
        2. Paste the contents of your downloaded JSON key file
        3. Save and exit:
           - Press `CTRL + X`
           - Press `Y` to confirm
           - Press `Enter` to save

3. Verify BigQuery Setup
    ```bash
    python amazon_bigquery.py
    ```
    You should see successful test results including data insertion and queries.

4. Server Deployment
    1. Start Service with PM2
        ```bash
        # Start the Python script with PM2 (using venv python)
        pm2 start main.py --name "amazon-scraper" --interpreter ./venv/bin/python

        # Save PM2 configuration (for auto-restart)
        pm2 save

        # Setup PM2 to start on system boot
        pm2 startup
        ```

    2. PM2 Commands
        ```bash
        # Check status
        pm2 status

        # View logs
        pm2 logs amazon-scraper

        # Restart service
        pm2 restart amazon-scraper

        # Stop service
        pm2 stop amazon-scraper
        ```

## Configuration

Two config files are provided:
- `config.development.json`: Less intense scraping, lower concurrency limits, no proxy 
- `config.production.json`: More intense scraping, higher concurrency limits, proxy support enabled

## Proxies
Add proxies to `proxies.txt` in the following format:
```
ip:port:username:password
198.23.239.134:6540:user:pass
207.244.217.165:6712:user:pass
```

Currently, the project uses datacenter proxies from [Webshare.io](https://www.webshare.io/). While these proxies are functional, you may experience some request failures due to the nature of datacenter IPs. Using higher quality proxies (such as residential or ISP proxies) could significantly reduce failure rates

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
    "asin": "B0054WTPBY",
    "results": [
        {
            "asin": "B0054WTPBY",
            "zip_code": "27107",
            "timestamp": 1738892111,
            "offers_data": [
                {
                    "seller_id": "AZLEWEBSPAY9I",
                    "buy_box_winner": true,
                    "prime": true,
                    "earliest_days": 0,
                    "latest_days": 0,
                    "delivery_time_range": "7 AM - 11 AM",
                    "price": 22.99,
                    "total_price": 22.99,
                    "shipping_cost": 0.0,
                    "delivery_estimate": "Overnight 7 AM - 11 AM",
                    "seller_name": "Neato"
                },
                {
                    "seller_id": "ATVPDKIKX0DER",
                    "buy_box_winner": false,
                    "prime": true,
                    "earliest_days": 6,
                    "latest_days": 10,
                    "delivery_time_range": null,
                    "price": 22.74,
                    "total_price": 22.74,
                    "shipping_cost": 0.0,
                    "delivery_estimate": "February 13 - 17",
                    "seller_name": "Amazon.com"
                },
                {
                    "seller_id": "A3QWMWV62I3HZ5",
                    "buy_box_winner": false,
                    "prime": true,
                    "earliest_days": 17,
                    "latest_days": 31,
                    "delivery_time_range": null,
                    "price": 22.97,
                    "total_price": 22.97,
                    "shipping_cost": 0.0,
                    "delivery_estimate": "February 24 - March 10",
                    "seller_name": "Ravenclaw Supply"
                }
            ]
        }
    ],
    "total_locations_processed": 1,
    "successful_locations": 1,
    "failed_locations": 0
}
```

## How It Works

### Session Management
- Pre-creates authenticated Amazon sessions for faster ASIN offer scraping
- Maintains a pool of ready-to-use sessions with cookies and CSRF tokens
- Background thread automatically refills pool when running low
- Sessions are cached to disk for faster restarts
- Dynamic concurrency scaling based on CPU and network usage
- Sessions are locked while in use and returned to pool after