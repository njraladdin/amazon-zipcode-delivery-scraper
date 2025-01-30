from bs4 import BeautifulSoup
import json

def parse_offers(html_text):
    """
    Parses HTML containing Amazon offers and returns a JSON object of the offers data.
    """
    soup = BeautifulSoup(html_text, 'html.parser')
    offers = []

    # Find the pinned offer first (if present)
    pinned_offer_div = soup.find('div', id='aod-pinned-offer')
    if pinned_offer_div:
        offers.append(extract_offer_data(pinned_offer_div, True))

    # Find all offer divs
    offer_divs = soup.find_all('div', id='aod-offer')
    for offer_div in offer_divs:
        offers.append(extract_offer_data(offer_div, False))

    return json.dumps(offers, indent=2)

def extract_offer_data(offer_div, is_pinned):
    """
    Extracts offer data from a single offer div.
    """
    offer_data = {
        'seller_id': None,
        'buy_box_winner': is_pinned,
        'prime_eligible': 'TODO',  # Need to detect Prime badge
    }

    # Price components
    price_span = offer_div.find('span', class_='a-price')
    if price_span:
        price = price_span.find('span', class_='a-price-whole').text.strip() + price_span.find('span', class_='a-price-fraction').text.strip()
        offer_data['item_price'] = price
        offer_data['total_price'] = price  # Will need to add shipping if not free

    # Delivery information
    delivery_info = {}
    delivery_promise = offer_div.find('div', class_='aod-delivery-promise')
    if delivery_promise:
        primary_delivery = delivery_promise.find('span', {'data-csa-c-content-id': 'DEXUnifiedCXPDM'})
        if primary_delivery:
            shipping_cost = primary_delivery.get('data-csa-c-delivery-price')
            offer_data['shipping_cost'] = 'FREE' if shipping_cost == 'FREE' else shipping_cost
            delivery_time = primary_delivery.find('span', class_="a-text-bold").text.strip()
            offer_data['delivery_estimate'] = delivery_time
            # TODO: Add earliest_days and latest_days calculation from delivery_time

    # Seller information
    sold_by_div = offer_div.find('div', id='aod-offer-soldBy')
    if sold_by_div:
        seller_link = sold_by_div.find('a', class_='a-size-small a-link-normal')
        if seller_link:
            offer_data['seller_name'] = seller_link.text.strip()
            seller_url = seller_link.get('href')
            offer_data['seller_id'] = extract_seller_id(seller_url)

    return offer_data

def parse_product_page(html_text):
    """
    Parses HTML of an Amazon product page and returns product data.
    """
    soup = BeautifulSoup(html_text, 'html.parser')
    product_data = {
        'asin': 'TODO',  # Should be passed as parameter
        'buy_box_winner': {
            'seller_name': None,
            'seller_id': None,
            'price': None,
            'shipping_cost': None,
            'prime_eligible': 'TODO',
            'delivery_estimate': None,
            'buy_box_winner': True
        }
    }

    # Extract seller information
    seller_info = soup.find('div', {'id': 'merchant-info'})
    if seller_info:
        seller_link = seller_info.find('a')
        if seller_link:
            product_data['buy_box_winner']['seller_name'] = seller_link.text.strip()
            seller_url = seller_link.get('href')
            product_data['buy_box_winner']['seller_id'] = extract_seller_id(seller_url)

    # Extract price for buy box
    price_element = soup.find('span', class_='a-price')
    if price_element:
        price = price_element.find('span', class_='a-offscreen')
        if price:
            product_data['buy_box_winner']['price'] = price.text.strip()

    # Extract delivery information
    delivery_element = soup.find('div', id='mir-layout-DELIVERY_BLOCK')
    if delivery_element:
        primary_delivery = delivery_element.find('span', {'data-csa-c-content-id': 'DEXUnifiedCXPDM'})
        if primary_delivery:
            product_data['buy_box_winner']['shipping_cost'] = primary_delivery.get('data-csa-c-delivery-price')
            product_data['buy_box_winner']['delivery_estimate'] = primary_delivery.get('data-csa-c-delivery-time')

    return json.dumps(product_data, indent=2)

def extract_seller_id(seller_url):
    """Extract seller ID from seller URL"""
    if not seller_url:
        return None
    # Look for seller= parameter in URL
    if 'seller=' in seller_url:
        return seller_url.split('seller=')[1].split('&')[0]
    return None