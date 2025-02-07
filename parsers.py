from lxml import html
import json
from datetime import datetime, timedelta
import re

def parse_offers(html_text):
    """
    Parses HTML containing Amazon offers and returns a JSON object of the offers data.
    
    Returns:
        tuple: (offers_json, has_prime_filter) where:
            - offers_json is the JSON string of parsed offers
            - has_prime_filter is a boolean indicating if Prime filter is available
    """
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
        return None, None
        
    # Add debug logging
    print(f"Parsing delivery estimate: {delivery_estimate}")
    
    # Handle overnight delivery and today
    delivery_estimate_lower = delivery_estimate.lower()
    if delivery_estimate_lower == 'overnight':
        return 0, 0
    elif delivery_estimate_lower == 'today':
        return 0, 0
    
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
            
            return earliest_days, latest_days
            
        elif len(dates) == 1:  # Single date
            day = int(dates[0])
            month_num = months[mentioned_months[0]]
            year = today.year
            if month_num < today.month:
                year += 1
            
            delivery_date = datetime(year, month_num, day)
            print(f"Single date calculation - delivery date: {delivery_date}")
            
            days_until = (delivery_date - today).days
            print(f"Days until delivery: {days_until}")
            
            return days_until, days_until
    
    return None, None

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
                delivery_text = delivery_time[0].text.strip()
                offer_data['delivery_estimate'] = delivery_text
                earliest, latest = parse_delivery_days(delivery_text)
                offer_data['earliest_days'] = earliest
                offer_data['latest_days'] = latest

    # Seller information
    sold_by_div = offer_div.xpath('.//div[@id="aod-offer-soldBy"]')
    if sold_by_div:
        seller_link = sold_by_div[0].xpath('.//a[@class="a-size-small a-link-normal"]')
        if seller_link:
            # Try to get seller name from aria-label first, then fallback to text content
            aria_label = seller_link[0].get('aria-label', '')
            if aria_label:
                # Remove the ". Opens a new page" suffix if present
                offer_data['seller_name'] = aria_label.split('. ')[0].strip()
            else:
                offer_data['seller_name'] = seller_link[0].text.strip()
            
            seller_url = seller_link[0].get('href')
            # Special case for Amazon as seller
            if seller_url == '1' or 'Amazon.com' in offer_data['seller_name']:
                offer_data['seller_id'] = 'ATVPDKIKX0DER'  # Amazon.com's seller ID
            else:
                offer_data['seller_id'] = extract_seller_id(seller_url)
            
            if offer_data['seller_id'] is None:
                seller_html = html.tostring(sold_by_div[0], pretty_print=True, encoding='unicode')
                print(f"Warning: Could not extract seller ID from HTML:\n{seller_html}\nURL was: {seller_url}")

    return offer_data

def extract_seller_id(seller_url):
    """Extract seller ID from seller URL"""
    if not seller_url:
        return None
    # Look for seller= parameter in URL
    if 'seller=' in seller_url:
        return seller_url.split('seller=')[1].split('&')[0]
    return None