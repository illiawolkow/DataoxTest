from bs4 import BeautifulSoup
import httpx
import asyncio
import re
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin
import os

from app.config import settings, logger


async def parse_car_listing_page(html: str) -> List[str]:
    """
    Parse a listing page and extract all car detail URLs
    """
    soup = BeautifulSoup(html, "lxml")
    car_links = []
    
    # Log some page structure info
    page_title = soup.title.text if soup.title else "No title"
    logger.info(f"Page title: {page_title}")
    
    # Check if the page might be a CAPTCHA challenge or anti-bot page
    if "captcha" in html.lower() or "robot" in html.lower() or "detection" in html.lower():
        logger.warning("Possible anti-bot protection detected on the page")
    
    # Approach 1: Try multiple ways to find the car listings
    selectors_to_try = [
        "section.ticket-item",                 # Classic format
        "div.ticket-item",                     # Alternative format
        "div.content-ticket",                  # Alternative format
        "div.content-bar",                     # Container format
        ".search-result .ticket-item",         # Nested format
        "div.app-catalog .app-catalog-item",   # Modern app format
        ".content-bar",                        # Container only
        ".app-catalog a[href*='auto_']"        # Direct links in modern format
    ]
    
    for selector in selectors_to_try:
        elements = soup.select(selector)
        logger.info(f"Found {len(elements)} elements with selector '{selector}'")
        
        if elements:
            for element in elements:
                try:
                    # Extract URL from different possible locations
                    car_url = None
                    
                    # First check if the element itself is a link
                    if element.name == 'a' and element.get('href') and 'auto_' in element.get('href'):
                        car_url = element.get('href')
                    else:
                        # Try to find links inside the element
                        # First look for direct auto_ links
                        link_element = element.select_one('a[href*="auto_"]')
                        if link_element:
                            car_url = link_element.get('href')
                        else:
                            # Try data-link-to-view attribute
                            data_link = element.select_one('[data-link-to-view]')
                            if data_link:
                                car_url = data_link.get('data-link-to-view')
                            else:
                                # Try address class links
                                address_link = element.select_one('a.address')
                                if address_link:
                                    car_url = address_link.get('href')
                                else:
                                    # Try photo links
                                    photo_link = element.select_one('.ticket-photo a')
                                    if photo_link:
                                        car_url = photo_link.get('href')
                    
                    # Process URL if found
                    if car_url:
                        if not car_url.startswith('http'):
                            car_url = urljoin("https://auto.ria.com", car_url)
                        
                        if car_url not in car_links:
                            car_links.append(car_url)
                            logger.debug(f"Found car URL: {car_url}")
                except Exception as e:
                    logger.error(f"Error processing car element: {e}")
    
    # Approach 2: If no car links found yet, look for any auto_*.html links in the page
    if not car_links:
        logger.info("No car links found with selectors, trying regex pattern matching")
        # Use regex to find all auto_*.html links in the HTML
        auto_links = re.findall(r'(?:href|link|url)=[\"\']?([^\"\'\s>]+auto_[^\"\']+\.html)', html)
        for link in auto_links:
            if not link.startswith('http'):
                link = urljoin("https://auto.ria.com", link)
            if link not in car_links:
                car_links.append(link)
    
    # Filter out duplicate links
    car_links = list(set(car_links))
    
    logger.info(f"Successfully extracted {len(car_links)} car links from page")
    # Log the first few links for debugging
    if car_links:
        for i, link in enumerate(car_links[:3]):
            logger.info(f"Link {i+1}: {link}")
    
    return car_links


def extract_price_usd(car_soup: BeautifulSoup) -> Optional[float]:
    """Extract price in USD"""
    try:
        # Try different selectors for price in USD
        price_element = None
        
        # Try listing page price format first
        price_element = car_soup.select_one('.price-ticket .bold[data-currency="USD"]')
        
        # Try detail page price format
        if not price_element:
            price_element = car_soup.select_one('.price_value strong')
        
        # Try generic price element with USD currency
        if not price_element:
            price_element = car_soup.select_one('[data-currency="USD"]')
            
        if price_element:
            price_text = price_element.text.strip()
            # Extract digits only
            price_digits = re.sub(r'[^\d]', '', price_text)
            if price_digits:
                return float(price_digits)
    except Exception as e:
        logger.error(f"Error extracting price: {e}")
    return None


def extract_odometer(car_soup: BeautifulSoup) -> Optional[int]:
    """Extract odometer value in km"""
    try:
        # First try from listing page format (li.item-char.js-race)
        odometer_element = car_soup.select_one('li.item-char.js-race')
        if odometer_element:
            odometer_text = odometer_element.text.strip()
            # Look for "тис. км" pattern
            match = re.search(r'(\d+)\s*(?:тис|тыс)\.?\s*км', odometer_text, re.IGNORECASE)
            if match:
                return int(match.group(1)) * 1000
        
        # Try detail page format (base-information)
        odometer_element = car_soup.select_one('.base-information .size18')
        if odometer_element:
            # Extract the number and check if it's in thousands
            odometer_text = odometer_element.text.strip()
            odometer_container = odometer_element.parent.text.strip()
            
            # Get the digits from the element
            odometer_value = int(re.sub(r'[^\d]', '', odometer_text))
            
            # Check if it's in thousands by looking for "тис. км" in the container text
            if 'тис' in odometer_container.lower():
                return odometer_value * 1000
            return odometer_value
        
        # Last resort - look for any number followed by km
        km_texts = car_soup.find_all(string=re.compile(r'\d+\s*(?:тис|тыс)\.?\s*км', re.IGNORECASE))
        if km_texts:
            for text in km_texts:
                match = re.search(r'(\d+)\s*(?:тис|тыс)\.?\s*км', text, re.IGNORECASE)
                if match:
                    return int(match.group(1)) * 1000
    except Exception as e:
        logger.error(f"Error extracting odometer: {e}")
    return None


def extract_images_info(car_soup: BeautifulSoup) -> Tuple[Optional[str], int]:
    """Extract main image URL and count of images"""
    try:
        # Try to get the main image URL
        image_url = None
        
        # First check for images in listing page format (ticket-photo)
        ticket_photo = car_soup.select_one('.ticket-photo')
        if ticket_photo:
            # Try to get source srcset first (webp format) since it's usually higher quality
            source_element = ticket_photo.select_one('source[srcset]')
            if source_element and source_element.get('srcset'):
                image_url = source_element.get('srcset')
            # Fallback to img src if source not found
            if not image_url:
                img_element = ticket_photo.select_one('img[src]')
                if img_element and img_element.get('src'):
                    image_url = img_element.get('src')
        
        # If not found in ticket-photo, check gallery-order carousel (detail page)
        if not image_url:
            carousel = car_soup.select_one('.gallery-order.carousel')
            if carousel:
                # Find the first image in the carousel
                first_img = carousel.select_one('.photo-620x465 img')
                if first_img and first_img.get('src'):
                    image_url = first_img.get('src')
                # If src not found, try to get from image in LD+JSON
                elif not image_url:
                    json_ld = carousel.select_one('script[type="application/ld+json"]')
                    if json_ld:
                        try:
                            import json
                            data = json.loads(json_ld.string)
                            if data.get('image') and isinstance(data['image'], list) and len(data['image']) > 0:
                                first_image = data['image'][0]
                                if isinstance(first_image, dict) and first_image.get('contentUrl'):
                                    image_url = first_image.get('contentUrl')
                        except:
                            pass
        
        # If not found in carousel or ticket-photo, try other sources
        if not image_url:
            # Try picture source element first (modern pages)
            source_element = car_soup.select_one('picture source[srcset]')
            if source_element:
                image_url = source_element.get('srcset')
            
            # If not found, try regular img elements
            if not image_url:
                img_element = car_soup.select_one('.photo-620x465 img[src], .carousel img[src], .gallery-order img[src], .ticket-photo img[src]')
                if img_element:
                    image_url = img_element.get('src')
        
        # Count images
        images_count = 0
        
        # Try to find the count in "show all X photos" text
        show_all_element = car_soup.select_one('.show-all')
        if show_all_element:
            # Look for pattern "Дивитися всі XX фотографій"
            count_match = re.search(r'всі\s+(\d+)\s+фотографій', show_all_element.text, re.IGNORECASE)
            if count_match:
                images_count = int(count_match.group(1))
        
        # If no count found, try to count the thumbnail elements
        if images_count == 0:
            thumbnail_elements = car_soup.select('.carousel-photo, .photo-620x465, .thumbnail')
            images_count = len(thumbnail_elements)
            
            # If still no count, look for photo count in data attributes
            if images_count == 0:
                photo_data = car_soup.select_one('[data-photo-count]')
                if photo_data:
                    try:
                        images_count = int(photo_data.get('data-photo-count', '0'))
                    except:
                        pass
                
                # Try to get count from count-photo span
                if images_count == 0:
                    count_element = car_soup.select_one('.count-photo .count .mhide, .count-photo .count .dhide')
                    if count_element:
                        count_match = re.search(r'з\s+(\d+)', count_element.text)
                        if count_match:
                            images_count = int(count_match.group(1))
        
        # Make sure URL is absolute
        if image_url and not image_url.startswith('http'):
            image_url = urljoin("https://auto.ria.com", image_url)
            
        return image_url, images_count
    except Exception as e:
        logger.error(f"Error extracting images: {e}")
        return None, 0


def extract_username(car_soup: BeautifulSoup) -> Optional[str]:
    """Extract seller username"""
    try:
        # Look for seller_info_name element (most common)
        username_element = car_soup.select_one('.seller_info_name')
        if username_element:
            return username_element.text.strip()
            
        # Try alternative selectors
        username_element = car_soup.select_one('.seller-info .name')
        if username_element:
            return username_element.text.strip()
            
        # Try phone unmask data
        phone_element = car_soup.select_one('[data-phone-unmask]')
        if phone_element:
            unmask_data = phone_element.get('data-phone-unmask', '')
            if unmask_data:
                try:
                    import json
                    data = json.loads(unmask_data)
                    if 'name' in data and data['name']:
                        return data['name']
                except:
                    pass
    except Exception as e:
        logger.error(f"Error extracting username: {e}")
    return None


def extract_phone_number(car_soup: BeautifulSoup) -> Optional[str]:
    """Extract phone number"""
    try:
        # Try data-phone-number attribute first
        phone_element = car_soup.select_one('.phone[data-phone-number]')
        if phone_element:
            phone = phone_element.get('data-phone-number', '')
            if phone:
                return format_phone_number(phone)
        
        # Try data-value attribute (shown after clicking "показати")
        phone_element = car_soup.select_one('[data-value]')
        if phone_element:
            phone = phone_element.get('data-value', '')
            if phone:
                return format_phone_number(phone)
                
        # Try to find phone in data-phone-number or directly in text
        phone_element = car_soup.select_one('span.phone[data-phone-unmask]')
        if phone_element:
            # Try to get from data-phone-number attribute
            phone = phone_element.get('data-phone-number', '')
            if not phone:
                # Try to get from visible text
                phone = phone_element.text.strip()
            
            if phone:
                return format_phone_number(phone)
    except Exception as e:
        logger.error(f"Error extracting phone number: {e}")
    return None


def format_phone_number(phone_text: str) -> str:
    """Format phone number to consistent format"""
    # Remove non-digit and + characters
    phone_text = re.sub(r'[^\d+]', '', phone_text)
    
    # Format with +38 prefix if needed
    if phone_text and not phone_text.startswith('+'):
        phone_text = '+' + phone_text
    if phone_text and not phone_text.startswith('+38'):
        phone_text = '+38' + phone_text.lstrip('+')
        
    return phone_text


def extract_car_number(car_soup: BeautifulSoup) -> Optional[str]:
    """Extract car license plate number"""
    try:
        # Try to find the state-num element
        car_number_element = car_soup.select_one('.state-num')
        if car_number_element:
            # Extract text without tooltip
            tooltip = car_number_element.select_one('.popup')
            if tooltip:
                tooltip.decompose()
            
            car_number = car_number_element.text.strip()
            return car_number
    except Exception as e:
        logger.error(f"Error extracting car number: {e}")
    return None


def extract_car_vin(car_soup: BeautifulSoup) -> Optional[str]:
    """Extract car VIN"""
    try:
        # Try to find the label-vin element
        vin_element = car_soup.select_one('.label-vin')
        if vin_element:
            # Remove SVG element if exists
            svg = vin_element.find('svg')
            if svg:
                svg.decompose()
                
            # Remove popup element if exists
            popup = vin_element.select_one('.popup')
            if popup:
                popup.decompose()
            
            # Extract VIN text
            vin_text = vin_element.text.strip()
            
            # Use regex to extract 17-char VIN
            vin_match = re.search(r'[A-HJ-NPR-Z0-9]{17}', vin_text, re.IGNORECASE)
            if vin_match:
                return vin_match.group(0)
                
            return vin_text
    except Exception as e:
        logger.error(f"Error extracting car VIN: {e}")
    return None


def extract_car_title(car_soup: BeautifulSoup) -> str:
    """Extract car title/name"""
    try:
        # Try to extract from ticket-title first (listing page)
        title_element = car_soup.select_one('.ticket-title')
        if title_element:
            brand_element = title_element.select_one('.blue.bold')
            year_element = title_element.text
            
            if brand_element:
                brand = brand_element.text.strip()
                # Extract year as the last 4-digit number in the text
                year_match = re.search(r'(\d{4})', year_element)
                year = year_match.group(1) if year_match else ""
                
                return f"{brand} {year}".strip()
        
        # Try to find title in the head element (detail page)
        title_element = car_soup.select_one('h1.head, h1.auto-head')
        if title_element:
            return title_element.text.strip()
            
        # Try to extract from meta tags
        meta_title = car_soup.select_one('meta[property="og:title"]')
        if meta_title:
            return meta_title.get('content', 'Unknown')
    except Exception as e:
        logger.error(f"Error extracting title: {e}")
    return "Unknown"


def parse_car_detail_page(html: str, url: str) -> Dict[str, Any]:
    """
    Parse a car detail page and extract relevant information.
    Also works with listing pages to extract available info.
    """
    soup = BeautifulSoup(html, "lxml")
    
    # Check if this is a listing page or detail page
    is_listing_page = bool(soup.select_one('.ticket-item, .content-bar, .content-ticket'))
    logger.info(f"Processing {'listing' if is_listing_page else 'detail'} page: {url}")
    
    # Extract all fields that work for both listing and detail pages
    title = extract_car_title(soup)
    price_usd = extract_price_usd(soup)
    image_url, images_count = extract_images_info(soup)
    
    # For listing pages, try to extract limited information
    if is_listing_page:
        # Try to extract odometer from listing page
        odometer_element = soup.select_one('li.item-char.js-race, .characteristic-oil')
        odometer = None
        if odometer_element:
            odometer_text = odometer_element.text.strip()
            match = re.search(r'(\d+)\s*(?:тис|тыс)\.?\s*км', odometer_text, re.IGNORECASE)
            if match:
                odometer = int(match.group(1)) * 1000
        
        # Try to extract username from listing page
        username_element = soup.select_one('.seller_info_name, .user-name, .seller-info .name')
        username = username_element.text.strip() if username_element else None
        
        # Try to extract car location from listing page
        location_element = soup.select_one('.item-city, .title-location, .breadcrumbs span[itemprop="itemListElement"]:last-child')
        car_location = location_element.text.strip() if location_element else None
        
        # These are typically not available on listing pages
        phone_number = None
        car_number = None
        car_vin = None
    else:
        # Extract all detailed info for detail pages
        odometer = extract_odometer(soup)
        username = extract_username(soup)
        phone_number = extract_phone_number(soup)
        car_number = extract_car_number(soup)
        car_vin = extract_car_vin(soup)
        
        # Try to extract car location from detail page
        location_element = soup.select_one('.breadcrumbs span[itemprop="itemListElement"]:last-child, .item_inner span.city')
        car_location = location_element.text.strip() if location_element else None
    
    # Create car data dictionary with all available fields except location
    car_data = {
        "url": url,
        "title": title,
        "price_usd": price_usd,
        "odometer": odometer,
        "username": username,
        "phone_number": phone_number,
        "image_url": image_url,
        "images_count": images_count,
        "car_number": car_number,
        "car_vin": car_vin,
    }
    
    # Add location separately (we'll handle this in the scraper function)
    if car_location:
        car_data["location"] = car_location
    
    logger.info(f"Extracted car data: title={title}, price_usd={price_usd}, odometer={odometer}, vin={car_vin if not is_listing_page else 'NA'}")
    return car_data


async def get_next_page_url(html: str, current_url: str) -> Optional[str]:
    """
    Extract the URL for the next page if it exists
    """
    soup = BeautifulSoup(html, "lxml")
    
    # Try different selectors for next page link
    selectors = [
        ".pagination .next a[href]",
        ".pager a.next[href]",
        ".pagination a.arrow-right[href]",
        ".search-result-pager a.page-link[rel='next'][href]",
        ".pager a.js-next[href]",
        "a[rel='next'][href]"
    ]
    
    for selector in selectors:
        next_link = soup.select_one(selector)
        if next_link and next_link.get("href"):
            next_page_url = next_link["href"]
            if not next_page_url.startswith('http'):
                next_page_url = urljoin(current_url, next_page_url)
            return next_page_url
    
    return None 