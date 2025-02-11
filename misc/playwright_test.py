from playwright.sync_api import sync_playwright
import time
import json

def get_amazon_product(asin: str):
    """
    Navigate to an Amazon product page using the provided ASIN
    
    Args:
        asin (str): The Amazon Standard Identification Number of the product
        
    Returns:
        page: Playwright page object
    """
    with sync_playwright() as p:
        # Launch the browser
        browser = p.chromium.launch(headless=False)  # Set headless=True in production
        
        # Create a new page
        context = browser.new_context()
        page = context.new_page()
        
        # Load and format cookies from file
        with open('cookies.json', 'r') as f:
            cookies = json.load(f)
            
        # Format cookies for Playwright
        for cookie in cookies:
            # Convert sameSite to the correct format
            if cookie.get('sameSite') == "no_restriction" or cookie.get('sameSite') is None:
                cookie['sameSite'] = "None"
            
            # Remove storeId as it's not needed
            if 'storeId' in cookie:
                del cookie['storeId']
                
            # Convert expirationDate to expires if present
            if 'expirationDate' in cookie:
                cookie['expires'] = int(cookie['expirationDate'])
                del cookie['expirationDate']
                
            # Remove hostOnly if present
            if 'hostOnly' in cookie:
                del cookie['hostOnly']
        
        context.add_cookies(cookies)
        
        # Construct the Amazon URL using the ASIN
        url = f"https://www.amazon.com/dp/{asin}"
        
        # Navigate to the page
        page.goto(url)
        time.sleep(500)

        return page

# Example usage
if __name__ == "__main__":
    test_asin = "B08DK5ZH44"  # Example ASIN
    page = get_amazon_product(test_asin)
    # Keep the browser open for a few seconds to see the result
