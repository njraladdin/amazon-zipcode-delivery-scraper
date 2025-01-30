import tls_client
from bs4 import BeautifulSoup
import json
import http.cookies
import os
from parsers import parse_offers, parse_product_page
from colorama import init, Fore, Style
import time

# Initialize colorama
init(autoreset=True)

class AmazonScraper:
    def __init__(self):
        self.session = tls_client.Session(
            client_identifier="chrome126",
            random_tls_extension_order=True
        )
        self.output_dir = 'output'
        os.makedirs(self.output_dir, exist_ok=True)
        print(f"{Fore.GREEN}[+] AmazonScraper initialized successfully{Style.RESET_ALL}")

    def _log_info(self, message):
        print(f"{Fore.CYAN}[INFO] {message}{Style.RESET_ALL}")

    def _log_success(self, message):
        print(f"{Fore.GREEN}[SUCCESS] {message}{Style.RESET_ALL}")

    def _log_warning(self, message):
        print(f"{Fore.YELLOW}[WARNING] {message}{Style.RESET_ALL}")

    def _log_error(self, message):
        print(f"{Fore.RED}[ERROR] {message}{Style.RESET_ALL}")

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
        
        if response.status_code == 200:
            self._log_success(f"Successfully changed zipcode to {zipcode}")
        else:
            self._log_error(f"Failed to change zipcode. Status code: {response.status_code}")
        
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

    def _get_offers_page(self, asin, csrf_token):
        self._log_info(f"Fetching offers page for ASIN: {asin}")
        offers_url = f"https://www.amazon.com/gp/product/ajax/ref=dp_aod_ALL_mbc?asin={asin}&m=&qid=&smid=&sourcecustomerorglistid=&sourcecustomerorglistitemid=&sr=&pc=dp&experienceId=aodAjaxMain"
        
        headers = {
            'accept': 'text/html,*/*',
            'accept-language': 'en-US,en;q=0.9',
            'device-memory': '8',
            'downlink': '9.55',
            'dpr': '1',
            'ect': '4g',
            'priority': 'u=1, i',
            'referer': f'https://www.amazon.com/dp/{asin}',
            'rtt': '150',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
            'viewport-width': '1446',
            'x-requested-with': 'XMLHttpRequest',
            'anti-csrftoken-a2z': csrf_token
        }
        
        response = self.session.get(offers_url, headers=headers)
        
        if response.status_code == 200:
            self._log_success("Offers page fetched successfully")
        else:
            self._log_error(f"Failed to fetch offers page. Status code: {response.status_code}")
        
        return response.text

    def get_product_info(self, asin, zipcode, save_to_file=True):
        """
        Get product and offers information for a specific ASIN and zipcode.
        
        Args:
            asin (str): The Amazon ASIN
            zipcode (str): The zipcode to check prices for
            save_to_file (bool): Whether to save results to files
            
        Returns:
            tuple: (product_data, offers_data) as dictionaries
        """
        start_time = time.time()
        self._log_info(f"Starting product info collection for ASIN: {asin} in zipcode: {zipcode}")
        
        # Get CSRF tokens and change zipcode
        csrf_token1 = self._make_initial_product_page_request(asin)
        if not csrf_token1:
            self._log_error("Failed to get initial CSRF token")
            return None, None

        csrf_token2 = self._make_modal_html_request(csrf_token1)
        if not csrf_token2:
            self._log_error("Failed to get modal CSRF token")
            return None, None

        self._make_change_zipcode_request(csrf_token2, zipcode)
        
        # Get and parse product page
        self._log_info("Parsing product page...")
        product_html = self._get_product_page(asin, csrf_token2)
        try:
            product_data = json.loads(parse_product_page(product_html))
            self._log_success("Product page parsed successfully")
        except Exception as e:
            self._log_error(f"Failed to parse product page: {str(e)}")
            return None, None
        
        # Get and parse offers page
        self._log_info("Parsing offers page...")
        offers_html = self._get_offers_page(asin, csrf_token2)
        try:
            offers_data = json.loads(parse_offers(offers_html))
            self._log_success("Offers page parsed successfully")
        except Exception as e:
            self._log_error(f"Failed to parse offers page: {str(e)}")
            return product_data, None
        
        if save_to_file:
            try:
                # Save product data
                product_file = os.path.join(self.output_dir, f'product_{asin}_{zipcode}.json')
                with open(product_file, 'w') as f:
                    json.dump(product_data, f, indent=2)
                self._log_success(f"Product data saved to: {product_file}")
                
                # Save offers data
                offers_file = os.path.join(self.output_dir, f'offers_{asin}_{zipcode}.json')
                with open(offers_file, 'w') as f:
                    json.dump(offers_data, f, indent=2)
                self._log_success(f"Offers data saved to: {offers_file}")
            except Exception as e:
                self._log_error(f"Failed to save data to files: {str(e)}")
        
        elapsed_time = time.time() - start_time
        self._log_success(f"Data collection completed in {elapsed_time:.2f} seconds")
        return product_data, offers_data

# Example usage:
if __name__ == "__main__":
    try:
        scraper = AmazonScraper()
        asin = "B08DK5ZH44"
        zipcode = "94102"
        
        product_data, offers_data = scraper.get_product_info(asin, zipcode)
        if product_data or offers_data:
            print(f"\n{Fore.GREEN}[SUCCESS] Data collection completed successfully!{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.RED}[ERROR] Failed to collect data{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}[ERROR] An unexpected error occurred: {str(e)}{Style.RESET_ALL}")
    
