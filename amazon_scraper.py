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
from bs4 import BeautifulSoup
import json
import http.cookies
import os
from parsers import parse_offers
from colorama import init, Fore, Style
import time
import random
import aiohttp
from typing import Dict, Any
import threading
from datetime import datetime
from logger import setup_logger

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
        
        # Randomly select a proxy
        proxy_line = random.choice(proxies)
        ip, port, username, password = proxy_line.split(':')
        
        # Format the proxy string
        proxy = f"http://{username}:{password}@{ip}:{port}"
        
        self.session = tls_client.Session(
            client_identifier="chrome126",
            random_tls_extension_order=True
        )
        # Set proxy directly on the session
        #self.session.proxies = proxy
        
        # Only create output directory if saving is enabled
        self.output_dir = 'output'
        if SAVE_OUTPUT:
            os.makedirs(self.output_dir, exist_ok=True)
        self.logger.success(f"AmazonScraper initialized with proxy: {ip}:{port}")

    def _log_info(self, message):
        self.logger.info(message)

    def _log_success(self, message):
        self.logger.success(message)

    def _log_warning(self, message):
        self.logger.warning(message)

    def _log_error(self, message):
        self.logger.error(message)

    def _make_initial_product_page_request(self, asin):
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

        # Make initial request to amazon.com
        self._log_info("Accessing amazon.com homepage...")
        initial_response = self.session.get(initial_url, headers=headers)
        
        if initial_response.status_code != 200:
            self._log_error(f"Homepage request failed with status code: {initial_response.status_code}")
            return None

        # Then make the product page request
        self._log_info("Accessing product page...")
        response = self.session.get(product_url, headers=headers)
        
        if response.status_code != 200:
            self._log_error(f"Product page request failed with status code: {response.status_code}")
            return None

        # Debug print for cookies after both requests
        self._log_info("Current session cookies after initial requests:")
        for cookie_name, cookie_value in self.session.cookies.get_dict().items():
            print(f"{Fore.CYAN}[DEBUG] Cookie: {cookie_name} = {cookie_value[:20]}...{Style.RESET_ALL}")

        # Parse the HTML and get CSRF token from modal data
        self._log_info("Extracting CSRF token...")
        soup = BeautifulSoup(response.text, "html.parser")
        location_modal = soup.find(id="nav-global-location-data-modal-action")
        if location_modal:
            data_modal = location_modal.get('data-a-modal')
            if data_modal:
                modal_data = json.loads(data_modal)
                if 'ajaxHeaders' in modal_data and 'anti-csrftoken-a2z' in modal_data['ajaxHeaders']:
                    csrf_token = modal_data['ajaxHeaders']['anti-csrftoken-a2z']
                    self._log_success(f"CSRF token extracted: {csrf_token[:10]}...")
                    return csrf_token
        
        self._log_error("Failed to extract CSRF token")
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

        soup = BeautifulSoup(response.text, 'html.parser')
        script = soup.find('script', {'type': 'text/javascript'})
        
        if script and script.string and 'CSRF_TOKEN' in script.string:
            start_index = script.string.find('CSRF_TOKEN : "') + len('CSRF_TOKEN : "')
            end_index = script.string.find('"', start_index)
            csrf_token = script.string[start_index:end_index]
            self._log_success(f"Modal CSRF token extracted: {csrf_token[:10]}...")
            return csrf_token
        
        self._log_error("Failed to extract modal CSRF token")
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

    def _get_product_page(self, asin, csrf_token):
        self._log_info(f"Fetching product page for ASIN: {asin}")
        product_url = f"https://www.amazon.com/dp/{asin}"
        
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-US,en;q=0.9',
            'anti-csrftoken-a2z': csrf_token,
            'cache-control': 'no-cache',
            'device-memory': '8',
            'dpr': '1',
            'ect': '4g',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
            'viewport-width': '1120'
        }
        
        response = self.session.get(product_url, headers=headers)
        
        if response.status_code == 200:
            self._log_success("Product page fetched successfully")
        else:
            self._log_error(f"Failed to fetch product page. Status code: {response.status_code}")
        
        return response.text

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

    def get_product_info(self, asin: str, zipcode: str) -> Dict[str, Any]:
        """
        Get product and offers information for a specific ASIN and zipcode.
        
        Args:
            asin (str): The Amazon ASIN
            zipcode (str): The zipcode to check prices for
            
        Returns:
            dict: Final data including offers and metadata
        """
        try:
            start_time = time.time()
            self._log_info(f"Starting product info collection for ASIN: {asin} in zipcode: {zipcode}")
            
            # Get CSRF tokens and change zipcode
            csrf_token1 = self._make_initial_product_page_request(asin)
            if not csrf_token1:
                self._log_error(f"Failed to get initial CSRF token for zipcode {zipcode}")
                return None

            csrf_token2 = self._make_modal_html_request(csrf_token1)
            if not csrf_token2:
                self._log_error(f"Failed to get modal CSRF token for zipcode {zipcode}")
                return None

            # Add more detailed logging for each step
            self._log_info(f"Changing zipcode to {zipcode} with token {csrf_token2[:10]}...")
            change_response = self._make_change_zipcode_request(csrf_token2, zipcode)
            if not change_response:
                self._log_error(f"Failed to change zipcode to {zipcode}")
                return None
            
            # # Get and save product page HTML after zipcode change
            # product_page_html = self._get_product_page(asin, csrf_token2)
            
            # # Verify zipcode change
            # if not self._verify_zipcode_change(product_page_html, zipcode):
            #     self._log_error("Zipcode change verification failed - aborting")
            #     return None

            # self._save_to_file(product_page_html, f'product_page_{asin}_{zipcode}.html', is_html=True)

            # Initialize final data object
            final_data = {
                "asin": asin,
                "zip_code": zipcode,
                "timestamp": int(time.time()),
                "offers_data": None,
                "metadata": {
                    "total_offers": 0,
                    "prime_eligible_offers": 0,
                    "collection_time_seconds": 0
                }
            }
            
            # Get and parse offers pages
            self._log_info("Parsing offers pages...")
            
            # Get all offers
            all_offers_html = self._get_offers_page(asin, csrf_token2)
            try:
                
                # Parse offers and get prime filter status
                offers_json, has_prime_filter = parse_offers(all_offers_html)
                all_offers_data = json.loads(offers_json)
                self._log_success(f"All offers page parsed successfully - Found {len(all_offers_data)} offers")
                
                # Debug print for Prime filter status
                self._log_info(f"Prime filter available: {has_prime_filter}")
                
                prime_offers_data = []
                # Only make Prime-only request if Prime filter exists
                if has_prime_filter:
                    # Get Prime-only offers
                    prime_offers_html = self._get_offers_page(asin, csrf_token2, prime_only=True)
                    try:
                        # Save Prime offers HTML for debugging
                        self._save_to_file(prime_offers_html, f'offers_html_prime_{asin}_{zipcode}.html', is_html=True)
                        
                        # Parse prime offers
                        prime_offers_json, _ = parse_offers(prime_offers_html)
                        prime_offers_data = json.loads(prime_offers_json)
                        self._log_success(f"Prime offers page parsed successfully - Found {len(prime_offers_data)} Prime eligible offers")
                    except Exception as e:
                        self._log_error(f"Failed to parse Prime offers page: {str(e)}")
                else:
                    self._log_info("No Prime filter available - skipping Prime-only request")

            except Exception as e:
                self._log_error(f"Failed to parse all offers page: {str(e)}")
                return None

            # Merge and mark Prime eligible offers
            offers_data = []
            prime_seller_ids = {offer['seller_id'] for offer in prime_offers_data}
            
            for offer in all_offers_data:
                offer['prime'] = offer['seller_id'] in prime_seller_ids
                offers_data.append(offer)
            
            # Update final data
            final_data["offers_data"] = offers_data
            final_data["metadata"].update({
                "total_offers": len(offers_data),
                "prime_eligible_offers": len(prime_seller_ids),
                "collection_time_seconds": round(time.time() - start_time, 2)
            })

            self._save_to_file(
                final_data, 
                f'final_{asin}_{zipcode}_{time.strftime("%Y%m%d_%H%M%S")}.json'
            )
            
            elapsed_time = time.time() - start_time
            self._log_success(f"Data collection completed in {elapsed_time:.2f} seconds")
            return final_data

        except Exception as e:
            self._log_error(f"Unexpected error for zipcode {zipcode}: {str(e)}")
            raise  # Re-raise the exception to be caught by the caller

# Example usage:
if __name__ == "__main__":
    try:
        scraper = AmazonScraper()
        asin = "B09X7CRKRZ"
        zipcode = "98101"
        
        result = scraper.get_product_info(asin, zipcode)
        if result:
            print(f"\n{Fore.GREEN}[SUCCESS] Data collection completed successfully!{Style.RESET_ALL}")
            print(f"Total offers: {result['metadata']['total_offers']}")
            print(f"Prime eligible offers: {result['metadata']['prime_eligible_offers']}")
        else:
            print(f"\n{Fore.RED}[ERROR] Failed to collect data{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}[ERROR] An unexpected error occurred: {str(e)}{Style.RESET_ALL}")
    
