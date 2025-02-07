from lxml import html
import json
from datetime import datetime, timedelta
import re
import os

def parse_offers(html_text):
    """
    Parses HTML containing Amazon offers and returns a JSON object of the offers data.
    
    Returns:
        tuple: (offers_json, has_prime_filter) where:
            - offers_json is the JSON string of parsed offers
            - has_prime_filter is a boolean indicating if Prime filter is available
    """
    # Ensure output directory exists
    os.makedirs('output', exist_ok=True)
    
    # Save HTML content to output folder
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_path = f'output/offers_{timestamp}.html'
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_text)
    except Exception as e:
        print(f"Warning: Could not save HTML to {output_path}: {str(e)}")
    
    tree = html.fromstring(html_text)
    offers = []

    # Check if Prime filter exists
    filter_list = tree.xpath('//div[@id="aod-filter-list"]')
    has_prime_filter = False
    if filter_list is not None and len(filter_list) > 0:
        # Look for Prime icon in the filter list
        prime_checkbox = filter_list[0].xpath('.//i[contains(@class, "a-icon-prime")]')
        has_prime_filter = len(prime_checkbox) > 0

    # Find the pinned offer first (if present)
    pinned_offer = tree.xpath('//div[@id="aod-pinned-offer"]')
    if pinned_offer:
        offers.append(extract_offer_data(pinned_offer[0], True))

    # Find all offer divs
    offer_divs = tree.xpath('//div[@id="aod-offer"]')
    for offer_div in offer_divs:
        offers.append(extract_offer_data(offer_div, False))

    return json.dumps(offers, indent=2), has_prime_filter

def parse_delivery_days(delivery_estimate):
    """Convert delivery estimate text to earliest and latest days"""
    if not delivery_estimate:
        return None, None, None
        
    # Add debug logging
    print(f"Parsing delivery estimate: {delivery_estimate}")
    
    # Handle overnight delivery, today, and tomorrow with time ranges
    delivery_estimate_lower = delivery_estimate.lower()
    
    # Extract time range if present (e.g., "7 AM - 11 AM")
    time_range = None
    time_match = re.search(r'(\d+(?::\d+)?\s*(?:AM|PM)\s*-\s*\d+(?::\d+)?\s*(?:AM|PM))', delivery_estimate, re.IGNORECASE)
    if time_match:
        time_range = time_match.group(1)
    
    if 'overnight' in delivery_estimate_lower:
        return 0, 0, time_range
    elif 'today' in delivery_estimate_lower:
        return 0, 0, time_range
    elif 'tomorrow' in delivery_estimate_lower:
        return 1, 1, time_range
    
    # Strip time component from today
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    print(f"Today's date: {today}")
    
    months = {
        'January': 1, 'February': 2, 'March': 3, 'April': 4,
        'May': 5, 'June': 6, 'July': 7, 'August': 8,
        'September': 9, 'October': 10, 'November': 11, 'December': 12
    }
    
    # First find which months are mentioned in the estimate
    mentioned_months = [month for month in months if month in delivery_estimate]
    
    if mentioned_months:
        # Extract date range like "February 10 - 13" or "February 24 - March 11"
        dates = re.findall(r'\d+', delivery_estimate)
        if len(dates) >= 2:  # We have a range
            earliest_day = int(dates[0])
            latest_day = int(dates[1])
            
            # If there are two different months mentioned, use them respectively
            if len(mentioned_months) >= 2:
                earliest_month = months[mentioned_months[0]]
                latest_month = months[mentioned_months[1]]
            else:
                earliest_month = latest_month = months[mentioned_months[0]]
            
            year = today.year
            
            # Handle year transition for each date separately
            earliest_year = year
            if earliest_month < today.month:
                earliest_year += 1
                
            latest_year = year
            if latest_month < today.month:
                latest_year += 1
            
            earliest_date = datetime(earliest_year, earliest_month, earliest_day)
            latest_date = datetime(latest_year, latest_month, latest_day)
            
            print(f"Calculated dates - earliest: {earliest_date}, latest: {latest_date}")
            
            earliest_days = (earliest_date - today).days
            latest_days = (latest_date - today).days
            
            print(f"Days calculation - earliest_days: {earliest_days}, latest_days: {latest_days}")
            
            return earliest_days, latest_days, time_range
            
        elif len(dates) == 1:  # Single date
            day = int(dates[0])
            month_num = months[mentioned_months[0]]
            year = today.year
            if month_num < today.month:
                year += 1
            
            delivery_date = datetime(year, month_num, day)
            
            days_until = (delivery_date - today).days
            
            return days_until, days_until, time_range
    
    return None, None, None

def extract_offer_data(offer_div, is_pinned):
    """
    Extracts offer data from a single offer div using lxml.
    """
    
    offer_data = {
        'seller_id': None,
        'buy_box_winner': is_pinned,
        'prime': False,
        'earliest_days': None,
        'latest_days': None,
        'delivery_time_range': None,  # New field for time range
    }

    # Check for Prime badge in the offer
    prime_badge = offer_div.xpath('.//i[contains(@class, "a-icon-prime")]')
    if prime_badge:
        offer_data['prime'] = True

    # Price components
    price_span = offer_div.xpath('.//span[contains(@class, "a-price")]')
    if price_span:
        whole = price_span[0].xpath('.//span[@class="a-price-whole"]/text()')
        fraction = price_span[0].xpath('.//span[@class="a-price-fraction"]/text()')
        if whole and fraction:
            # Add decimal point between whole and fraction
            price_str = whole[0].strip() + '.' + fraction[0].strip()
            price_str = re.sub(r'[^\d.]', '', price_str)
            offer_data['price'] = float(price_str)
            offer_data['total_price'] = offer_data['price']

    # Delivery information
    delivery_promise = offer_div.xpath('.//div[contains(@class, "aod-delivery-promise")]')
    if delivery_promise:
        # First check for fastest delivery option
        fastest_delivery = delivery_promise[0].xpath('.//span[@data-csa-c-content-id="DEXUnifiedCXSDM"]')
        primary_delivery = delivery_promise[0].xpath('.//span[@data-csa-c-content-id="DEXUnifiedCXPDM"]')
        
        delivery_element = None
        if fastest_delivery:
            delivery_element = fastest_delivery[0]
        elif primary_delivery:
            delivery_element = primary_delivery[0]
            
        if delivery_element is not None:
            shipping_cost = delivery_element.get('data-csa-c-delivery-price')
            if shipping_cost == 'FREE':
                offer_data['shipping_cost'] = 0.0
            else:
                shipping_cost = re.sub(r'[^\d.]', '', shipping_cost)
                offer_data['shipping_cost'] = float(shipping_cost) if shipping_cost else 0.0
            
            offer_data['total_price'] = offer_data['price'] + offer_data['shipping_cost']

            delivery_time = delivery_element.xpath('.//span[@class="a-text-bold"]')
            if delivery_time:
                delivery_text = ' '.join([text.strip() for text in delivery_time[0].xpath('.//text()')])
                earliest, latest, time_range = parse_delivery_days(delivery_text)
                
                # Format delivery estimate with time range if available
                if time_range:
                    if 'overnight' in delivery_text.lower():
                        offer_data['delivery_estimate'] = f"Overnight {time_range}"
                    elif 'today' in delivery_text.lower():
                        offer_data['delivery_estimate'] = f"Today {time_range}"
                    else:
                        offer_data['delivery_estimate'] = delivery_text
                else:
                    offer_data['delivery_estimate'] = delivery_text
                
                offer_data['earliest_days'] = earliest
                offer_data['latest_days'] = latest
                offer_data['delivery_time_range'] = time_range

    # Seller information
    sold_by_div = offer_div.xpath('.//div[@id="aod-offer-soldBy"]')
    if sold_by_div:
        # Try to find seller link (third party sellers) or span (Amazon)
        seller_element = (
            sold_by_div[0].xpath('.//a[@class="a-size-small a-link-normal"]') or 
            sold_by_div[0].xpath('.//span[@class="a-size-small a-color-base"]')
        )
        
        if seller_element:
            offer_data['seller_name'] = seller_element[0].text.strip()
            seller_url = seller_element[0].get('href', '1')  # Use '1' as URL for Amazon.com
            offer_data['seller_id'] = extract_seller_id(seller_url)

    return offer_data

def extract_seller_id(seller_url):
    """Extract seller ID from seller URL"""
    if not seller_url:
        return None
    
    # # Special case for Amazon's URL which is just "1"
    # if seller_url == "1":
    #     return "ATVPDKIKX0DER"  # Amazon.com's seller ID
    
    # Look for seller= parameter in URL
    if 'seller=' in seller_url:
        return seller_url.split('seller=')[1].split('&')[0]
    return None