from bs4 import BeautifulSoup
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
    soup = BeautifulSoup(html_text, 'html.parser')
    offers = []

    # Check if Prime filter exists
    filter_list = soup.find('div', id='aod-filter-list')
    has_prime_filter = False
    if filter_list:
        prime_checkbox = filter_list.find('i', {'class': 'a-icon-prime', 'role': 'img'})
        has_prime_filter = prime_checkbox is not None

    # Find the pinned offer first (if present)
    pinned_offer_div = soup.find('div', id='aod-pinned-offer')
    if pinned_offer_div:
        offers.append(extract_offer_data(pinned_offer_div, True))

    # Find all offer divs
    offer_divs = soup.find_all('div', id='aod-offer')
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
    Extracts offer data from a single offer div.
    """
    offer_data = {
        'seller_id': None,
        'buy_box_winner': is_pinned,
        'prime': False,  # Renamed from prime_eligible
        'earliest_days': None,
        'latest_days': None,
        'debug': {
            'full_offer_text': offer_div.get_text(separator=' ', strip=True),
            # 'offer_html': str(offer_div)
        }
    }

    # Price components
    price_span = offer_div.find('span', class_='a-price')
    if price_span:
        whole = price_span.find('span', class_='a-price-whole')
        fraction = price_span.find('span', class_='a-price-fraction')
        if whole and fraction:
            price_str = whole.text.strip() + fraction.text.strip()
            # Remove any non-numeric characters except decimal point
            price_str = re.sub(r'[^\d.]', '', price_str)
            offer_data['price'] = float(price_str)  # Renamed from item_price
            offer_data['total_price'] = offer_data['price']  # Will add shipping cost later

    # Delivery information
    delivery_promise = offer_div.find('div', class_='aod-delivery-promise')
    if delivery_promise:
        primary_delivery = delivery_promise.find('span', {'data-csa-c-content-id': 'DEXUnifiedCXPDM'})
        if primary_delivery:
            shipping_cost = primary_delivery.get('data-csa-c-delivery-price')
            # Convert shipping cost to float, FREE becomes 0.0
            if shipping_cost == 'FREE':
                offer_data['shipping_cost'] = 0.0
            else:
                # Remove currency symbol and convert to float
                shipping_cost = re.sub(r'[^\d.]', '', shipping_cost)
                offer_data['shipping_cost'] = float(shipping_cost) if shipping_cost else 0.0
            
            # Calculate total price including shipping
            offer_data['total_price'] = offer_data['price'] + offer_data['shipping_cost']

            delivery_time = primary_delivery.find('span', class_="a-text-bold")
            if delivery_time:
                delivery_text = delivery_time.text.strip()
                offer_data['delivery_estimate'] = delivery_text
                earliest, latest = parse_delivery_days(delivery_text)
                offer_data['earliest_days'] = earliest
                offer_data['latest_days'] = latest

    # Seller information
    sold_by_div = offer_div.find('div', id='aod-offer-soldBy')
    if sold_by_div:
        seller_link = sold_by_div.find('a', class_='a-size-small a-link-normal')
        if seller_link:
            offer_data['seller_name'] = seller_link.text.strip()
            seller_url = seller_link.get('href')
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