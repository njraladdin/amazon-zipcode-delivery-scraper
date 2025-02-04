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
    if filter_list:
        prime_checkbox = tree.xpath('.//i[@class="a-icon-prime" and @role="img"]')
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
        
    # Handle "February 10 - 13" style dates
    today = datetime.now()
    months = {
        'January': 1, 'February': 2, 'March': 3, 'April': 4,
        'May': 5, 'June': 6, 'July': 7, 'August': 8,
        'September': 9, 'October': 10, 'November': 11, 'December': 12
    }
    
    for month in months:
        if month in delivery_estimate:
            # Extract date range like "February 10 - 13"
            dates = re.findall(r'\d+', delivery_estimate)
            if len(dates) >= 2:  # We have a range
                earliest_day = int(dates[0])
                latest_day = int(dates[1])
                month_num = months[month]
                year = today.year
                
                # If the month is earlier than current month, it must be next year
                if month_num < today.month:
                    year += 1
                
                earliest_date = datetime(year, month_num, earliest_day)
                latest_date = datetime(year, month_num, latest_day)
                
                earliest_days = (earliest_date - today).days
                latest_days = (latest_date - today).days
                
                return earliest_days, latest_days
            elif len(dates) == 1:  # Single date
                day = int(dates[0])
                month_num = months[month]
                year = today.year
                if month_num < today.month:
                    year += 1
                
                delivery_date = datetime(year, month_num, day)
                days_until = (delivery_date - today).days
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

    # Price components
    price_span = offer_div.xpath('.//span[contains(@class, "a-price")]')
    if price_span:
        whole = price_span[0].xpath('.//span[@class="a-price-whole"]/text()')
        fraction = price_span[0].xpath('.//span[@class="a-price-fraction"]/text()')
        if whole and fraction:
            price_str = whole[0].strip() + fraction[0].strip()
            price_str = re.sub(r'[^\d.]', '', price_str)
            offer_data['price'] = float(price_str)
            offer_data['total_price'] = offer_data['price']

    # Delivery information
    delivery_promise = offer_div.xpath('.//div[contains(@class, "aod-delivery-promise")]')
    if delivery_promise:
        primary_delivery = delivery_promise[0].xpath('.//span[@data-csa-c-content-id="DEXUnifiedCXPDM"]')
        if primary_delivery:
            shipping_cost = primary_delivery[0].get('data-csa-c-delivery-price')
            if shipping_cost == 'FREE':
                offer_data['shipping_cost'] = 0.0
            else:
                shipping_cost = re.sub(r'[^\d.]', '', shipping_cost)
                offer_data['shipping_cost'] = float(shipping_cost) if shipping_cost else 0.0
            
            offer_data['total_price'] = offer_data['price'] + offer_data['shipping_cost']

            delivery_time = primary_delivery[0].xpath('.//span[@class="a-text-bold"]')
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
            offer_data['seller_name'] = seller_link[0].text.strip()
            seller_url = seller_link[0].get('href')
            offer_data['seller_id'] = extract_seller_id(seller_url)

    return offer_data

def extract_seller_id(seller_url):
    """Extract seller ID from seller URL"""
    if not seller_url:
        return None
    # Look for seller= parameter in URL
    if 'seller=' in seller_url:
        return seller_url.split('seller=')[1].split('&')[0]
    return None