import tls_client
from bs4 import BeautifulSoup
import json
import http.cookies

# Create a session with tls_client instead of requests
session = tls_client.Session(
    client_identifier="chrome126",
    random_tls_extension_order=True
)

def make_product_page_requet(asin):
    # First, let's try hitting the main Amazon page first
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
    print("Making initial request...")
    initial_response = session.get(initial_url, headers=headers)

    # Then make the product page request
    print("\nMaking product request...")
    response = session.get(product_url, headers=headers)

    # Parse the HTML and get CSRF token from modal data
    soup = BeautifulSoup(response.text, "html.parser")
    location_modal = soup.find(id="nav-global-location-data-modal-action")
    if location_modal:
        data_modal = location_modal.get('data-a-modal')
        if data_modal:
            modal_data = json.loads(data_modal)
            if 'ajaxHeaders' in modal_data and 'anti-csrftoken-a2z' in modal_data['ajaxHeaders']:
                return modal_data['ajaxHeaders']['anti-csrftoken-a2z']
    return None



def make_modal_html_request(csrf_token):

    modal_url = "https://www.amazon.com/portal-migration/hz/glow/get-rendered-address-selections?deviceType=desktop&pageType=Detail&storeContext=photo&actionSource=desktop-modal"
    
    # Debug: Print all cookies before making request
    print("\nAvailable cookies before modal request:")
    for cookie_name, cookie_value in session.cookies.items():
        print(f"{cookie_name}: {cookie_value}")

    # Create cookie header manually
    cookie_header = '; '.join([f"{name}={value}" for name, value in session.cookies.items()])
    
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


    response = session.get(modal_url, headers=headers)
    
    # Parse the response to get CSRF token
    soup = BeautifulSoup(response.text, 'html.parser')
    script = soup.find('script', {'type': 'text/javascript'})
    
    if script:
        # Find the text that contains GLUXWidget
        script_text = script.string
        
        # Look for CSRF_TOKEN in the text
        if 'CSRF_TOKEN' in script_text:
            # Extract the token using string manipulation
            start_index = script_text.find('CSRF_TOKEN : "') + len('CSRF_TOKEN : "')
            end_index = script_text.find('"', start_index)
            csrf_token = script_text[start_index:end_index]
            print(f"\nExtracted CSRF Token: {csrf_token}")
            return csrf_token
    
    print("Could not find CSRF token in response")
    return None

def make_change_zipcode_request(csrf_token):
    url = "https://www.amazon.com/portal-migration/hz/glow/address-change?actionSource=glow"
    payload = json.dumps({
        "locationType": "LOCATION_INPUT",
        "zipCode": "46204",
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

    response = session.post(url, headers=headers, data=payload)
    print(response.text)
    
def refresh_product_page(asin, csrf_token):
    """Makes a fresh request to the product page using the existing session and saves the HTML."""
    product_url = f"https://www.amazon.com/dp/{asin}"  # ASIN should be accessible
    
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
    
    print("\nRefreshing product page...")
    response = session.get(product_url, headers=headers)
    
    # Save the HTML response to a file
    with open('updated_product_page.html', 'w', encoding='utf-8') as f:
        f.write(response.text)
    print("Updated product page saved to 'updated_product_page.html'")
    
    return response.text

def parse_product_page(html_content):
    """Parse Amazon product page HTML using DetailParser."""
    from parsers import DetailParser
    parser = DetailParser(html_content)
    parsed_data = parser.parse()
    
    # Print some key information from the parsed data
    print("\nParsed Product Information:")
    print(f"Title: {parsed_data['title']}")
    print(f"Price: {parsed_data['details'].get('Price', 'N/A')}")
    print(f"Star Rating: {parsed_data['star']}")
    print(f"Number of Reviews: {parsed_data['reviews']}")

    
    
    return parsed_data

def test_parsing():
    """Test parsing using saved HTML file."""
    try:
        with open('updated_product_page.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        parsed_data = parse_product_page(html_content)
        print("\nTest parsing completed successfully")
        return parsed_data
    except FileNotFoundError:
        print("Error: updated_product_page.html not found. Please run the main function first.")
        return None

def main():
    ASIN = 'B08DK5ZH44'
    csrf_token1 = make_product_page_requet(ASIN)
    csrf_token2 = make_modal_html_request(csrf_token1)
    print(f"Final CSRF Token: {csrf_token2}")
    make_change_zipcode_request(csrf_token2)
    
    # Refresh the product page
    html_content = refresh_product_page(ASIN, csrf_token2)
    
    # Parse the refreshed content
    parsed_data = parse_product_page(html_content)
    print("\nProduct page refreshed and parsed successfully")

if __name__ == "__main__":
    #main()
    
    # Uncomment the following line to test parsing with saved HTML file
    test_parsing()