"""
Amazon Scraper Request Flow:
1. Initial homepage request to get cookies
2. Product page request to get first CSRF token + additional cookies
3. Modal HTML request to get second CSRF token
4. Change zipcode request using second CSRF token
5. Product page request with updated location
6. All offers page request
7. Repeat all offers page request with Prime-only filter (if Prime filter available)
"""

import tls_client
import json
import http.cookies
import os
from parsers import parse_offers, parse_product_details
from colorama import init, Fore, Style
import time
import random
import aiohttp
from typing import Dict, Any, List
import threading
from datetime import datetime
from logger import setup_logger
from utils import load_config
import asyncio
from queue import Queue

# Configuration constants
SAVE_OUTPUT = False  # Set to True to save files to output folder

# Initialize colorama
init(autoreset=True)

class AmazonScraper:
    def __init__(self):
        self.logger = setup_logger('AmazonScraper')
        # Read and parse proxies from proxies.txt
        with open('proxies.txt', 'r') as f:
            proxies = [line.strip() for line in f.readlines() if line.strip()]
        
        # Get config
        config = load_config()
        
        if config.get('allow_proxy', True):
            # Randomly select a proxy
            proxy_line = random.choice(proxies)
            ip, port, username, password = proxy_line.split(':')
            
            # Format the proxy string
            self.proxy = f"http://{username}:{password}@{ip}:{port}"
            self.logger.success(f"AmazonScraper initialized with proxy: {ip}:{port}")
        else:
            self.proxy = None
            self.logger.info("AmazonScraper initialized without proxy (disabled in config)")
        
        # Only create output directory if saving is enabled
        self.output_dir = 'output'
        if SAVE_OUTPUT:
            os.makedirs(self.output_dir, exist_ok=True)

        self.session = None
        self.initial_csrf_token = None
        self.is_initialized = False
        self.product_details = None

    def _log_info(self, message):
        self.logger.info(message)

    def _log_success(self, message):
        self.logger.success(message)

    def _log_warning(self, message):
        self.logger.warning(message)

    def _log_error(self, message):
        self.logger.error(message)

    def _create_fresh_session(self):
        """Create a new session with current configuration"""
        self.session = tls_client.Session(
            client_identifier="chrome126",
            random_tls_extension_order=True
        )
        
        # Apply proxy if configured
        if self.proxy:
            self.session.proxies = self.proxy
        
        self._log_info("Created fresh session")

    def _make_initial_product_page_request(self, asin, parse_details=False):
        self._log_info(f"Making initial request for ASIN: {asin}")
        initial_url = "https://www.amazon.com"
        product_url = f"https://www.amazon.com/dp/{asin}"

        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-US,en;q=0.9,be;q=0.8,ar;q=0.7',
            'cache-control': 'max-age=0',
            'device-memory': '8',
            'dnt': '1',
            'downlink': '8.85',
            'dpr': '1',
            'ect': '4g',
            'priority': 'u=0, i',
            'referer': product_url,
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
            'viewport-width': '1120'
        }

        self._log_info("Accessing product page...")
        response = self.session.get(product_url, headers=headers)
        self.session.last_response = response  # Store the response for later use
        
        if response.status_code != 200:
            self._log_error(f"Product page request failed with status code: {response.status_code}")
            return None

        # Save the product page HTML only if we're saving output
        if SAVE_OUTPUT:
            os.makedirs('output', exist_ok=True)
            html_filename = f'output/product_page_{asin}.html'
            with open(html_filename, 'w', encoding='utf-8', errors='ignore') as f:
                f.write(response.text)
                self._log_success(f"Saved product page to {html_filename}")

        # Parse product details only if explicitly requested and if we don't have them
        if parse_details and not self.product_details:
            try:
                self.product_details = parse_product_details(response.text)
                
                # Save product details to JSON file if saving is enabled
                if SAVE_OUTPUT:
                    json_filename = f'output/product_details_{asin}_{time.strftime("%Y%m%d_%H%M%S")}.json'
                    with open(json_filename, 'w', encoding='utf-8') as f:
                        json.dump(self.product_details, f, indent=2, ensure_ascii=False)
                        self._log_success(f"Saved parsed product details to {json_filename}")
            except Exception as e:
                self._log_error(f"Failed to parse or save product details: {str(e)}")

        # Extract CSRF token using string operations
        self._log_info("Extracting CSRF token...")
        extraction_start = time.time()
        html = response.text
        modal_id = 'nav-global-location-data-modal-action'
        
        try:
            # Find the modal element
            modal_start = html.find(f'id="{modal_id}"')
            if modal_start == -1:
                self._log_error(f"Modal element not found (string search)")
                return None
                
            # Find data-a-modal attribute
            data_modal_start = html.find('data-a-modal=\'', modal_start)  # Note: Using single quote here
            if data_modal_start == -1:
                # Try with encoded quotes as fallback
                data_modal_start = html.find('data-a-modal="{', modal_start)
                if data_modal_start == -1:
                    self._log_error("data-a-modal attribute not found (string search)")
                    return None
                
            # Find the start of the JSON content
            json_start = data_modal_start + len('data-a-modal="')
            
            # Find the matching end quote by counting brackets
            bracket_count = 0
            in_quotes = False
            escape_next = False
            json_end = json_start
            
            while json_end < len(html):
                char = html[json_end]
                
                if escape_next:
                    escape_next = False
                elif char == '\\':
                    escape_next = True
                elif char == '"' and not in_quotes:
                    if bracket_count == 0:
                        break
                    in_quotes = True
                elif char == '"' and in_quotes:
                    in_quotes = False
                elif not in_quotes:
                    if char == '{':
                        bracket_count += 1
                    elif char == '}':
                        bracket_count -= 1
                        if bracket_count == 0:
                            json_end += 1
                            break
                
                json_end += 1
            
            if json_end >= len(html):
                self._log_error("Could not find proper end of JSON data")
                return None
                
            # Extract and parse the JSON
            json_str = html[json_start:json_end]
            json_str = json_str.replace('&quot;', '"')  # Handle HTML entities
            
            modal_data = json.loads(json_str)
            
            if 'ajaxHeaders' in modal_data and 'anti-csrftoken-a2z' in modal_data['ajaxHeaders']:
                csrf_token = modal_data['ajaxHeaders']['anti-csrftoken-a2z']
                extraction_time = round((time.time() - extraction_start) * 1000, 2)  # Convert to milliseconds
                self._log_success(f"CSRF token extracted in {extraction_time}ms: {csrf_token[:10]}...")
                return csrf_token
            
            self._log_error("CSRF token not found in modal data")
            return None
            
        except json.JSONDecodeError as e:
            self._log_error(f"Failed to parse modal JSON data: {str(e)}")
            return None
        except Exception as e:
            self._log_error(f"Error extracting CSRF token: {str(e)}")
            return None

    def _make_modal_html_request(self, csrf_token):
        self._log_info("Requesting modal HTML...")
        modal_url = "https://www.amazon.com/portal-migration/hz/glow/get-rendered-address-selections?deviceType=desktop&pageType=Detail&storeContext=photo&actionSource=desktop-modal"
        
        headers = {
            'accept': 'text/html,*/*',
            'accept-language': 'en-US,en;q=0.9',
            'anti-csrftoken-a2z': csrf_token,
            'content-type': 'application/json',
            'device-memory': '8',
            'downlink': '8.85',
            'dpr': '1',
            'ect': '4g',
            'origin': 'https://www.amazon.com',
            'referer': 'https://www.amazon.com/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
            'viewport-width': '1120',
            'x-requested-with': 'XMLHttpRequest'
        }

        response = self.session.get(modal_url, headers=headers)
        
        if response.status_code != 200:
            self._log_error(f"Modal request failed with status code: {response.status_code}")
            return None

        # Extract CSRF token using string operations
        self._log_info("Extracting modal CSRF token...")
        extraction_start = time.time()
        html = response.text

        try:
            # Find the script tag containing CSRF token
            script_start = html.find('<script type="text/javascript">')
            if script_start == -1:
                self._log_error("Script tag not found")
                return None

            # Find CSRF token declaration
            csrf_start = html.find('CSRF_TOKEN : "', script_start)
            if csrf_start == -1:
                self._log_error("CSRF token declaration not found")
                return None

            # Extract the token
            token_start = csrf_start + len('CSRF_TOKEN : "')
            token_end = html.find('"', token_start)
            
            if token_end == -1:
                self._log_error("Could not find end of CSRF token")
                return None

            csrf_token = html[token_start:token_end]
            extraction_time = round((time.time() - extraction_start) * 1000, 2)  # Convert to milliseconds
            self._log_success(f"Modal CSRF token extracted in {extraction_time}ms: {csrf_token[:10]}...")
            return csrf_token

        except Exception as e:
            self._log_error(f"Error extracting modal CSRF token: {str(e)}")
            return None

    def _make_change_zipcode_request(self, csrf_token, zipcode):
        self._log_info(f"Changing zipcode to: {zipcode}")
        url = "https://www.amazon.com/portal-migration/hz/glow/address-change?actionSource=glow"
        payload = json.dumps({
            "locationType": "LOCATION_INPUT",
            "zipCode": zipcode,
            "deviceType": "web",
            "storeContext": "photo",
            "pageType": "Detail",
            "actionSource": "glow"
        })

        headers = {
            'accept': 'text/html,*/*',
            'accept-language': 'en-US,en;q=0.9',
            'anti-csrftoken-a2z': csrf_token,
            'content-type': 'application/json',
            'device-memory': '8',
            'downlink': '8.85',
            'dpr': '1',
            'ect': '4g',
            'origin': 'https://www.amazon.com',
            'referer': 'https://www.amazon.com/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
            'viewport-width': '1120',
            'x-requested-with': 'XMLHttpRequest'
        }

        response = self.session.post(url, headers=headers, data=payload)
        
        # Debug print response
        self._log_info(f"Zipcode change response content: {response.text[:200]}...")
        
        if response.status_code == 200:
            try:
                response_data = json.loads(response.text)
                if response_data.get('successful') == 1:
                    self._log_success(f"Successfully changed zipcode to {zipcode}")
                else:
                    self._log_error(f"Failed to change zipcode. Response indicates failure")
                    return None
            except json.JSONDecodeError:
                self._log_error(f"Failed to parse zipcode change response")
                return None
        else:
            self._log_error(f"Failed to change zipcode. Status code: {response.status_code}")
            return None
        
        return response

    

    def _verify_zipcode_change(self, html_text, zipcode):
        """Verify that the zipcode appears multiple times in the page HTML"""
        occurrences = html_text.count(zipcode)
        if occurrences >= 4:
            self._log_success(f"Zipcode {zipcode} verified ({occurrences} occurrences found)")
            return True
        else:
            self._log_error(f"Zipcode verification failed - only found {occurrences} occurrences of {zipcode}")
            return False

    def _get_offers_page(self, asin, csrf_token, prime_only=False):
        self._log_info(f"Fetching offers page for ASIN: {asin}{' (Prime only)' if prime_only else ''}")
        base_url = f"https://www.amazon.com/gp/product/ajax/ref=dp_aod_ALL_mbc?asin={asin}&m=&qid=&smid=&sourcecustomerorglistid=&sourcecustomerorglistitemid=&sr=&pc=dp&experienceId=aodAjaxMain"
        
        # Add Prime filter if requested
        if prime_only:
            base_url += "&filters=%257B%2522primeEligible%2522%253Atrue%257D"
        else:
            base_url += "&filters=%257B%2522all%2522%253Atrue%257D"
        headers = {
            'accept': 'text/html,*/*',
            'accept-language': 'en-US,en;q=0.9,be;q=0.8,ar;q=0.7',
            'device-memory': '8',
            'dnt': '1',
            'downlink': '8.65',
            'dpr': '1',
            'ect': '4g',
            'priority': 'u=1, i',
            'referer': 'https://www.amazon.com/SanDisk-Extreme-microSDXC-Memory-Adapter/dp/B09X7CRKRZ/136-1912212-8057361?pd_rd_w=YOwz1&content-id=amzn1.sym.53b72ea0-a439-4b9d-9319-7c2ee5c88973&pf_rd_p=53b72ea0-a439-4b9d-9319-7c2ee5c88973&pf_rd_r=VBP362SNAXS96Y4DP9V1&pd_rd_wg=Z1aCo&pd_rd_r=ff18059e-7648-474f-8a5c-4a7ed8d8ba55&pd_rd_i=B09X7CRKRZ&th=1',
            'rtt': '150',
            'sec-ch-device-memory': '8',
            'sec-ch-dpr': '1',
            'sec-ch-ua': '"Not A(Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-ch-ua-platform-version': '"15.0.0"',
            'sec-ch-viewport-width': '1674',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
            'viewport-width': '1674',
            'x-requested-with': 'XMLHttpRequest'
        }
        
        response = self.session.get(base_url, headers=headers)
        
        if response.status_code == 200:
            self._log_success(f"Offers page fetched successfully{' (Prime only)' if prime_only else ''}")
        else:
            self._log_error(f"Failed to fetch offers page{' (Prime only)' if prime_only else ''}. Status code: {response.status_code}")
        
        return response.text

    def _save_to_file(self, data, filename, is_html=False):
        """Helper method to save data to a file"""
        if not SAVE_OUTPUT:
            return
            
        try:
            filepath = os.path.join(self.output_dir, filename)
            mode = 'w' if is_html else 'w'
            encoding = 'utf-8' if is_html else None
            
            with open(filepath, mode, encoding=encoding) as f:
                if is_html:
                    f.write(data)
                else:
                    json.dump(data, f, indent=2)
                    
            self._log_success(f"Data saved to: {filepath}")
        except Exception as e:
            self._log_error(f"Failed to save data to {filename}: {str(e)}")

    def initialize_session(self, test_asin="B09X7CRKRZ"):
        """Initialize a fresh session with cookies and return success status"""
        try:
            self._create_fresh_session()
            self.initial_csrf_token = self._make_initial_product_page_request(test_asin)
            
            if not self.initial_csrf_token:
                self._log_error("Failed to get initial CSRF token")
                return False
            
            self.is_initialized = True
            self._log_success("Session initialized successfully")
            return True
        except Exception as e:
            self._log_error(f"Session initialization failed: {str(e)}")
            return False

    def process_multiple_zipcodes(self, asin: str, zipcodes: List[str]) -> List[Dict[str, Any]]:
        """Process multiple zipcodes using the same session"""
        results = []
        process_start = time.time()
        timings = {
            'session_initialization': 0,
            'zipcodes_processing': []  # Will store timing for each zipcode
        }
        
        # Get product details once at the start
        init_start = time.time()
        try:
            # Get CSRF token and product details for the new product page
            self.initial_csrf_token = self._make_initial_product_page_request(asin, parse_details=True)
            if not self.initial_csrf_token:
                self._log_error("Failed to get CSRF token for new product")
                return results
            
            timings['session_initialization'] = round(time.time() - init_start, 2)
            self._log_info(f"\nProduct page initialization took: {timings['session_initialization']} seconds")
        except Exception as e:
            self._log_error(f"Product page initialization failed: {str(e)}")
            return results

        # Process each zipcode sequentially with the initialized session
        for zipcode in zipcodes:
            zipcode_timing = {
                'zipcode': zipcode,
                'total_time': 0,
                'steps': {}
            }
            
            try:
                self._log_info(f"Processing zipcode {zipcode} with existing session")
                zipcode_start = time.time()
                
                # Time modal request
                modal_start = time.time()
                csrf_token2 = self._make_modal_html_request(self.initial_csrf_token)
                zipcode_timing['steps']['modal_request'] = round(time.time() - modal_start, 2)
                
                if not csrf_token2:
                    self._log_error(f"Failed to get modal CSRF token for zipcode {zipcode}")
                    continue

                # Time zipcode change
                change_start = time.time()
                change_response = self._make_change_zipcode_request(csrf_token2, zipcode)
                zipcode_timing['steps']['zipcode_change'] = round(time.time() - change_start, 2)
                
                if not change_response:
                    self._log_error(f"Failed to change zipcode to {zipcode}")
                    continue

                # Process offers and get result
                result = self._process_zipcode_with_session(asin, zipcode, csrf_token2)
                if result:
                    # Add the internal step timings to our zipcode timing
                    zipcode_timing['steps'].update(result['metadata']['step_timings'])
                    zipcode_timing['total_time'] = round(time.time() - zipcode_start, 2)
                    timings['zipcodes_processing'].append(zipcode_timing)
                    results.append(result)
                    
                    # Log timing breakdown for this zipcode
                    self._log_info(f"\nTiming breakdown for zipcode {zipcode}:")
                    for step, duration in zipcode_timing['steps'].items():
                        self._log_info(f"  {step}: {duration} seconds")
                    self._log_info(f"  Total zipcode processing time: {zipcode_timing['total_time']} seconds")
                
            except Exception as e:
                self._log_error(f"Error processing zipcode {zipcode}: {str(e)}")
                continue

        # Log timing breakdown for all zipcodes
        self._log_info("\nTiming breakdown for all zipcodes:")
        for timing in timings['zipcodes_processing']:  # timing is already a dict with 'zipcode' key
            self._log_info(f"Zipcode {timing['zipcode']}:")
            for step, duration in timing['steps'].items():
                self._log_info(f"  {step}: {duration} seconds")
            self._log_info(f"  Total zipcode processing time: {timing['total_time']} seconds")

        self._log_info(f"\nTotal time for all zipcodes: {round(time.time() - process_start, 2)} seconds")
        
        return results

    def _process_zipcode_with_session(self, asin: str, zipcode: str, csrf_token: str) -> Dict[str, Any]:
        """Process a single zipcode with the existing session"""
        try:
            self._log_info(f"Starting product info collection for ASIN: {asin} in zipcode: {zipcode}")
            
            # Initialize final data object
            final_data = {
                "asin": asin,
                "zip_code": zipcode,
                "timestamp": int(time.time()),
                "offers_data": None,
                "product_details": self.product_details
            }
            
            # Get and parse offers pages
            self._log_info("Parsing offers pages...")
            
            all_offers_html = self._get_offers_page(asin, csrf_token)
            
            try:
                offers_json, has_prime_filter = parse_offers(all_offers_html)
                all_offers_data = json.loads(offers_json)
                
                self._log_success(f"All offers page parsed successfully - Found {len(all_offers_data)} offers")
                self._log_info(f"Prime filter available: {has_prime_filter}")
                
                prime_offers_data = []
                # Only make Prime-only request if Prime filter exists
                if has_prime_filter:
                    prime_offers_html = self._get_offers_page(asin, csrf_token, prime_only=True)
                    try:
                        prime_offers_json, _ = parse_offers(prime_offers_html)
                        prime_offers_data = json.loads(prime_offers_json)
                        self._log_success(f"Prime offers page parsed successfully - Found {len(prime_offers_data)} Prime eligible offers")
                    except Exception as e:
                        self._log_error(f"Failed to parse Prime offers page: {str(e)}")
                else:
                    self._log_info("No Prime filter available - skipping Prime-only request")

                # Merge offers data
                offers_data = []
                prime_seller_ids = {offer['seller_id'] for offer in prime_offers_data}
                
                for offer in all_offers_data:
                    offer['prime'] = offer['seller_id'] in prime_seller_ids
                    offers_data.append(offer)
                
                # Update final data
                final_data["offers_data"] = offers_data
                
                return final_data

            except Exception as e:
                self._log_error(f"Failed to parse all offers page: {str(e)}")
                return None

        except Exception as e:
            self._log_error(f"Unexpected error for zipcode {zipcode}: {str(e)}")
            raise

# Example usage:
if __name__ == "__main__":
    try:
        scraper = AmazonScraper()
        asin = "B09X7CRKRZ"
        zipcodes = ["98101", "98102", "98103"]
        
        results = asyncio.run(scraper.process_multiple_zipcodes(asin, zipcodes))
        if results:
            print(f"\n{Fore.GREEN}[SUCCESS] Data collection completed successfully!{Style.RESET_ALL}")
            for result in results:
                print(f"Total offers: {result['metadata']['total_offers']}")
                print(f"Prime eligible offers: {result['metadata']['prime_eligible_offers']}")
        else:
            print(f"\n{Fore.RED}[ERROR] Failed to collect data{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}[ERROR] An unexpected error occurred: {str(e)}{Style.RESET_ALL}")
    
