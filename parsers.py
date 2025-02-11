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


def parse_product_details(html_text):
    """
    Parses ALL product details from the main product HTML section.

    Args:
        html_text: The HTML content of the product page.

    Returns:
        A dictionary containing the parsed product details.  Returns an empty
        dictionary if the main product details section is not found.
    """
    tree = html.fromstring(html_text)
    product_details = {}
    main_product_details_section = {}  # Renamed from main_product_section_details

    # Find the main product details section
    center_col = tree.xpath('//div[@id="centerCol"]')
    if not center_col:
        return {}  # Return empty dict if main section not found

    center_col = center_col[0]

    # --- Basic Details ---
    title_element = center_col.xpath('.//span[@id="productTitle"]')
    if title_element:
        main_product_details_section['product_title'] = title_element[0].text.strip()

    brand_element = center_col.xpath('.//a[@id="bylineInfo"]')
    if brand_element:
        brand_text = brand_element[0].text.strip()
        if brand_text.startswith("Visit the ") and brand_text.endswith(" Store"):
            brand_text = brand_text[len("Visit the "):-len(" Store")]
        main_product_details_section['brand'] = brand_text

    rating_element = center_col.xpath('.//span[@id="acrPopover"]')
    if rating_element:
        rating_title = rating_element[0].get('title')
        if rating_title:
            main_product_details_section['average_rating'] = float(rating_title.split()[0])

    num_ratings_element = center_col.xpath('.//span[@id="acrCustomerReviewText"]')
    if num_ratings_element:
        num_ratings_text = num_ratings_element[0].text.strip()
        if num_ratings_text:
            main_product_details_section['number_of_ratings'] = int(num_ratings_text.split()[0].replace(',', ''))

    price_element = center_col.xpath('.//span[contains(@class, "priceToPay")]')
    if price_element:
        whole = price_element[0].xpath('.//span[@class="a-price-whole"]/text()')
        fraction = price_element[0].xpath('.//span[@class="a-price-fraction"]/text()')
        if whole and fraction:
            price_str = whole[0].strip() + '.' + fraction[0].strip()
            main_product_details_section['price'] = float(price_str)

    # --- "About this item" Bullets ---
    about_item_bullets = []
    for li in center_col.xpath('.//div[@id="feature-bullets"]//ul/li/span[@class="a-list-item"]'):
        bullet_text = li.text.strip()
        if bullet_text:  # Avoid empty strings
            about_item_bullets.append(bullet_text)
    if about_item_bullets:
        main_product_details_section['feature_bullets'] = about_item_bullets

    # --- Available Options/Variations ---
    options = []
    option_elements = tree.xpath('//div[@id="inline-twister-expander-content-size_name"]//li[contains(@class, "swatch-list-item-text")]')
    
    for option in option_elements:
        option_data = {}
        
        # Get the ASIN
        option_data['asin'] = option.get('data-asin')
        
        # Get the size/capacity
        size_element = option.xpath('.//span[contains(@class, "swatch-title-text")]/text()')
        if size_element:
            option_data['size'] = size_element[0].strip()
        
        # Get the price
        price_element = option.xpath('.//span[@class="a-price a-text-price"]//span[@aria-hidden="true"]/text()')
        if price_element:
            # Remove $ and convert to float
            price_str = price_element[0].replace('$', '').strip()
            try:
                option_data['price'] = float(price_str)
            except ValueError:
                option_data['price'] = None
        
        # Get availability
        availability = option.xpath('.//span[@id="twisterAvailability"]/text()')
        if availability:
            option_data['availability'] = availability[0].strip()
        
        # Check if this is the selected option
        option_data['selected'] = 'a-button-selected' in option.xpath('.//span[contains(@class, "a-button")]/@class')[0]
        
        options.append(option_data)
    
    if options:
        main_product_details_section['available_options'] = options

    # --- Product Media ---
    media = {
        'images': [],
        'videos': []
    }
    
    # Find the ImageBlockATF script that contains the image data
    image_script = tree.xpath('//script[contains(text(), "ImageBlockATF")]/text()')
    
    if image_script:
        try:
            script_text = image_script[0]
            # Find the colorImages data structure
            start_idx = script_text.find("'colorImages': { 'initial': [")
            if start_idx != -1:
                # Find the end of the array by matching brackets
                data_str = script_text[start_idx:]
                bracket_count = 0
                end_idx = 0
                in_string = False
                quote_char = None
                
                for i, char in enumerate(data_str):
                    if char in ["'", '"'] and (i == 0 or data_str[i-1] != '\\'):
                        if not in_string:
                            in_string = True
                            quote_char = char
                        elif quote_char == char:
                            in_string = False
                    elif not in_string:
                        if char == '[':
                            bracket_count += 1
                        elif char == ']':
                            bracket_count -= 1
                            if bracket_count == 0:
                                end_idx = i + 1
                                break
                
                if end_idx > 0:
                    # Extract just the array of image data
                    data_str = data_str[:end_idx]
                    # Get just the array part
                    array_start = data_str.find('[')
                    data_str = data_str[array_start:]
                    
                    # Clean up the JSON string
                    data_str = data_str.replace("'", '"')
                    # Handle the 'main' object by preserving its structure
                    data_str = re.sub(r'("main":)\s*({[^}]+})', r'\1\2', data_str)
                    
                    # Parse the image array
                    images = json.loads(data_str)
                    for img in images:
                        if 'hiRes' in img and img['hiRes']:
                            image_data = {
                                'url': img['hiRes'],
                                'high_res': True,
                                'thumbnail': img.get('thumb', ''),
                                'variant': img.get('variant', '')
                            }
                            # Add large version if available
                            if 'large' in img:
                                image_data['large'] = img['large']
                            media['images'].append(image_data)
                            
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Could not parse image data from script: {str(e)}")
            if hasattr(e, 'pos'):
                print(f"Problem area: {data_str[max(0, e.pos-50):min(len(data_str), e.pos+50)]}")
            else:
                print(f"Full error: {str(e)}")
    
    # Extract product videos
    video_elements = tree.xpath('//div[contains(@class, "vse-player-container")]')
    for video in video_elements:
        # Extract video data from the state script
        video_state = video.xpath('.//script[@type="a-state"]/text()')
        if video_state:
            try:
                video_data = json.loads(video_state[0])
                if 'videoUrl' in video_data:
                    media['videos'].append({
                        'url': video_data['videoUrl'],
                        'thumbnail': video_data.get('imageUrl'),
                        'title': video_data.get('title', '')
                    })
            except json.JSONDecodeError:
                pass  # Skip if JSON parsing fails
    
    if media['images'] or media['videos']:
        main_product_details_section['media'] = media

    # Update all the section assignments
    if main_product_details_section:
        product_details['main_product_details_section'] = main_product_details_section

    # --- Product Information ---
    product_info = {}
    
    # Parse detailed review histogram
    review_histogram = tree.xpath('//div[@id="cm_cr_dp_d_rating_histogram"]')
    if review_histogram:
        reviews_data = {
            'average_rating': None,
            'total_ratings': None,
            'distribution': {}
        }
        
        # Get average rating
        avg_rating = review_histogram[0].xpath('.//span[@data-hook="rating-out-of-text"]/text()')
        if avg_rating:
            reviews_data['average_rating'] = float(avg_rating[0].split()[0])
            
        # Get total ratings
        total_ratings = review_histogram[0].xpath('.//span[@data-hook="total-review-count"]/text()')
        if total_ratings:
            count_text = total_ratings[0].strip()
            reviews_data['total_ratings'] = int(''.join(filter(str.isdigit, count_text.replace(',', ''))))
        
        # Get distribution percentages
        histogram_rows = review_histogram[0].xpath('.//ul[@id="histogramTable"]//li')
        for row in histogram_rows:
            # Get star rating from aria-label
            aria_label = row.xpath('.//a/@aria-label')
            if not aria_label:
                continue
                
            label = aria_label[0]
            if 'percent of reviews have' not in label:
                continue
                
            # Extract star count and percentage
            parts = label.split()
            percentage = int(parts[0])
            stars = int(parts[-2])
            
            reviews_data['distribution'][stars] = {
                'percentage': percentage,
                'count': int((percentage / 100.0) * reviews_data['total_ratings'])
            }
        
        if reviews_data['distribution']:
            product_details['reviews_histogram_section'] = reviews_data

    # Additional Information and Product Details
    info_rows = tree.xpath('//table[@id="productDetails_detailBullets_sections1"]//tr')
    for row in info_rows:
        key = row.xpath('.//th/text()')
        if not key:
            continue
        
        key = key[0].strip()
        
        if key == 'Customer Reviews':
            # Special handling for customer reviews
            rating = row.xpath('.//span[@class="a-size-base a-color-base"]/text()')
            num_ratings = row.xpath('.//span[contains(text(), "ratings")]/text()')
            
            if rating and num_ratings:
                rating_text = rating[0].strip()
                num_ratings_text = num_ratings[0].strip()
                product_info['Customer Reviews'] = {
                    'rating': float(rating_text),
                    'count': int(num_ratings_text.split()[0].replace(',', ''))
                }
        
        elif key == 'Best Sellers Rank':
            # Extract rank text with category links
            ranks = []
            rank_spans = row.xpath('.//td//span')
            for span in rank_spans:
                rank_text = span.text_content().strip()
                if '#' in rank_text:
                    # Get the category from the following link if present
                    category_link = span.xpath('.//a/text()')
                    if category_link:
                        category = category_link[0].strip()
                        rank_text = f"{rank_text.split(' ')[0]} in {category}"
                    ranks.append(rank_text)
            if ranks:
                product_info['Best Sellers Rank'] = ranks[0]  # Take first rank if multiple exist
        
        else:
            # For other fields, get clean text content
            value = row.xpath('.//td')
            if value:
                # Get text content and clean it
                value_text = ' '.join(value[0].xpath('.//text()')).strip()
                if value_text:
                    # Add directly to product_info instead of additional_info
                    product_info[key] = value_text

    # Remove the additional_information section since we're adding fields directly
    # to product_info now
    if 'additional_information' in product_info:
        del product_info['additional_information']

    # Warranty & Support (if present)
    warranty_section = tree.xpath('//div[contains(@id, "warranty")]')
    if warranty_section:
        warranty_info = {}
        warranty_rows = warranty_section[0].xpath('.//tr')
        for row in warranty_rows:
            key = row.xpath('.//th/text()')
            value = row.xpath('.//td/text()')
            if key and value:
                key = key[0].strip()
                value = value[0].strip()
                if value:
                    warranty_info[key] = value
            
        if warranty_info:
            product_info['warranty'] = warranty_info

    # Important Information section (if present)
    important_info = tree.xpath('//div[@id="important-information"]//div[@class="content"]')
    if important_info:
        product_info['important_information'] = important_info[0].text_content().strip()

    if product_info:
        product_details['product_information_section'] = product_info

    # --- A+ Content Section ---
    aplus_content = []
    # Only get A+ content that's NOT inside the brand story section
    aplus_sections = tree.xpath('//div[contains(@class, "aplus-v2") and not(ancestor::div[@id="aplusBrandStory_feature_div"])]')
    
    if aplus_sections:
        for section in aplus_sections:
            # Process content sequentially
            for element in section.xpath('.//*'):
                content = {}
                
                # Images
                if element.tag == 'img' and not 'grey-pixel.gif' in element.get('src', ''):
                    image_url = element.get('data-src') or element.get('src')
                    if image_url:
                        content['type'] = 'image'
                        content['url'] = image_url
                        content['alt'] = element.get('alt', '').strip()
                
                # Headings
                elif element.tag in ['h1', 'h2', 'h3', 'h4']:
                    text = element.text_content().strip()
                    if text:
                        content['type'] = 'heading'
                        content['text'] = text
                
                # Paragraphs
                elif element.tag == 'p':
                    text = element.text_content().strip()
                    if text:
                        content['type'] = 'text'
                        content['text'] = text
                
                # Add non-empty content
                if content and len(content) > 1:  # More than just type
                    aplus_content.append(content)
    
    if aplus_content:
        product_details['aplus_content'] = aplus_content

    # --- Brand Story Section ---
    brand_story_section = {}
    brand_story_div = tree.xpath('//div[@id="aplusBrandStory_feature_div"]')
    
    if brand_story_div:
        # Get the hero image and its details
        hero_image = brand_story_div[0].xpath('.//div[contains(@class, "apm-brand-story-hero")]//img')
        if hero_image:
            brand_story_section['hero_image'] = {
                'url': hero_image[0].get('src'),
                'alt': hero_image[0].get('alt', '')
            }
        
        # Get the carousel cards content
        carousel_cards = []
        cards = brand_story_div[0].xpath('.//li[contains(@class, "apm-brand-story-carousel-card")]')
        
        for card in cards:
            card_data = {}
            
            # Get logo image if present
            logo_img = card.xpath('.//div[@class="apm-brand-story-logo-image"]//img')
            if logo_img:
                card_data['logo'] = {
                    'url': logo_img[0].get('src'),
                    'alt': logo_img[0].get('alt', '')
                }
            
            # Get slogan/text content
            slogan_text = card.xpath('.//div[@class="apm-brand-story-slogan-text"]//p/text()')
            if slogan_text:
                card_data['slogan'] = slogan_text[0].strip()
            
            # Get background image if present
            bg_image = card.xpath('.//div[@class="apm-brand-story-background-image"]//img')
            if bg_image:
                card_data['background_image'] = {
                    'url': bg_image[0].get('src'),
                    'alt': bg_image[0].get('alt', '')
                }
            
            # Get bottom text content if present
            bottom_text = card.xpath('.//div[@class="apm-brand-story-text-bottom"]')
            if bottom_text:
                text_content = {}
                
                heading = bottom_text[0].xpath('.//h3/text()')
                if heading:
                    text_content['heading'] = heading[0].strip()
                
                paragraph = bottom_text[0].xpath('.//p/text()')
                if paragraph:
                    text_content['text'] = paragraph[0].strip()
                
                if text_content:
                    card_data['bottom_content'] = text_content
            
            # Only add cards that have content
            if card_data:
                carousel_cards.append(card_data)
        
        if carousel_cards:
            brand_story_section['carousel_cards'] = carousel_cards
    
    # Add brand story section to product details if content was found
    if brand_story_section:
        product_details['brand_story_section'] = brand_story_section

    return product_details

if __name__ == "__main__":
    # Test parse_product_details with the specified file
    test_file = 'output/product_page_B09X7CRKRZ.html'
    try:
        with open(test_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        product_details = parse_product_details(html_content)
        print("\nParsed Product Details:")
        for key, value in product_details.items():
            print(f"{key}: {value}")
            
    except FileNotFoundError:
        print(f"Error: File not found at {test_file}")
    except Exception as e:
        print(f"Error occurred: {str(e)}")


