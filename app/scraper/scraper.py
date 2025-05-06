import httpx
import asyncio
import time
import random
import os
import re
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from app.config import settings, logger
from app.scraper.parser import (
    parse_car_listing_page,
    parse_car_detail_page,
    get_next_page_url,
    format_phone_number
)
from app.db.models import Car


async def fetch_page(url: str, client: httpx.AsyncClient) -> str:
    """
    Fetch a page with retry logic
    """
    max_retries = 3
    retry_delay = 2
    
    # Add a small random delay to avoid being blocked
    await asyncio.sleep(random.uniform(0.5, 2.0) * settings.REQUEST_DELAY)
    
    for attempt in range(max_retries):
        try:
            logger.debug(f"Fetching URL: {url}")
            
            # Use a random User-Agent for each request
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
                "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:88.0) Gecko/20100101 Firefox/88.0",
                "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
            ]
            
            headers = client.headers.copy()
            headers["User-Agent"] = random.choice(user_agents)
            # Add accept-language for Ukrainian content
            headers["Accept-Language"] = "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7"
            
            response = await client.get(url, headers=headers, follow_redirects=True)
            logger.info(f"HTTP Request: {response.request.method} {url} \"{response.http_version} {response.status_code} {response.reason_phrase}\"")
            
            # Check for redirects to homepage (sign of being blocked)
            if response.url != url and "auto_" not in str(response.url) and "/car/used/" not in str(response.url):
                logger.warning(f"Possible redirect to homepage detected: {url} -> {response.url}")
                raise httpx.HTTPStatusError("Possible blocking detected", request=response.request, response=response)
            
            if response.status_code == 403:
                logger.error(f"Access forbidden (403) for URL: {url}. Possible anti-scraping measures detected.")
                raise httpx.HTTPStatusError("Access forbidden", request=response.request, response=response)
                
            response.raise_for_status()
            
            # Check if the response is likely to be a CAPTCHA or blocked page
            content = response.text
            if "captcha" in content.lower() or "robot" in content.lower() or "blocked" in content.lower():
                logger.error(f"Possible CAPTCHA or blocking detected on URL: {url}")
                
                # Save the page for debugging
                debug_dir = "debug"
                os.makedirs(debug_dir, exist_ok=True)
                captcha_file = os.path.join(debug_dir, f"captcha_{int(time.time())}.html")
                with open(captcha_file, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.error(f"Saved CAPTCHA page to {captcha_file}")
                
                if attempt < max_retries - 1:
                    # Longer delay for CAPTCHA/blocking
                    backoff_time = retry_delay * (4 ** attempt)
                    logger.info(f"Waiting {backoff_time} seconds before retry due to possible CAPTCHA...")
                    await asyncio.sleep(backoff_time)
                continue
                
            return content
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching {url}: {e}")
            if attempt < max_retries - 1:
                # Exponential backoff
                backoff_time = retry_delay * (2 ** attempt)
                logger.info(f"Retrying in {backoff_time} seconds...")
                await asyncio.sleep(backoff_time)
            else:
                logger.error(f"Failed to fetch {url} after {max_retries} attempts")
                raise
        except Exception as e:
            logger.error(f"Unexpected error fetching {url}: {e}")
            raise


async def save_car_data(car_data: Dict[str, Any], session: AsyncSession) -> None:
    """
    Save car data to database, avoiding duplicates
    """
    try:
        # Check if car with this URL already exists
        stmt = select(Car).where(Car.url == car_data["url"])
        result = await session.execute(stmt)
        existing_car = result.scalar_one_or_none()
        
        if existing_car:
            logger.info(f"Car with URL {car_data['url']} already exists, skipping")
            return
        
        # Create new car record
        car = Car(**car_data)
        session.add(car)
        await session.commit()
        logger.info(f"Saved car: {car_data['title']} with VIN {car_data.get('car_vin', 'unknown')}")
    except Exception as e:
        await session.rollback()
        logger.error(f"Error saving car data: {e}")


async def process_car_page(car_url: str, client: httpx.AsyncClient, session: AsyncSession) -> None:
    """
    Process a single car detail page
    """
    try:
        # Fetch car detail page
        car_html = await fetch_page(car_url, client)
        
        # Parse car data
        car_data = await parse_car_detail_page(car_html, car_url)
        
        # If no phone number was found, we need to emulate clicking "show phone" button
        if not car_data.get('phone_number'):
            logger.info(f"Phone number not found on initial load, trying to get phone via API for {car_url}")
            
            try:
                # Extract advertisement ID from URL or page
                ad_id = None
                # Try to get from URL first
                url_match = re.search(r'auto_[^_]+_(\d+)\.html', car_url)
                if url_match:
                    ad_id = url_match.group(1)
                
                # If not found in URL, look in the HTML for data-advertisement-id
                if not ad_id:
                    soup = BeautifulSoup(car_html, "lxml")
                    ad_element = soup.select_one('[data-advertisement-id]')
                    if ad_element:
                        ad_id = ad_element.get('data-advertisement-id')
                
                if ad_id:
                    # Construct API URL to get phone number
                    phone_api_url = f"https://auto.ria.com/users/phones/{ad_id}"
                    
                    # Add referer header to mimic clicking from the page
                    headers = client.headers.copy()
                    headers["Referer"] = car_url
                    headers["X-Requested-With"] = "XMLHttpRequest"
                    
                    # Make API request
                    response = await client.get(phone_api_url, headers=headers)
                    if response.status_code == 200:
                        try:
                            # Parse response JSON
                            phone_data = response.json()
                            
                            # Extract phone number from response
                            if "formattedPhoneNumber" in phone_data:
                                car_data["phone_number"] = format_phone_number(phone_data["formattedPhoneNumber"])
                                logger.info(f"Successfully retrieved phone number via API: {car_data['phone_number']}")
                            elif "phones" in phone_data and phone_data["phones"]:
                                car_data["phone_number"] = format_phone_number(phone_data["phones"][0])
                                logger.info(f"Successfully retrieved phone number via API: {car_data['phone_number']}")
                        except Exception as e:
                            logger.error(f"Error parsing phone API response: {e}")
                else:
                    logger.warning(f"Could not extract advertisement ID for {car_url}")
            except Exception as e:
                logger.error(f"Error fetching phone number via API: {e}")
        
        # Save car data to database
        await save_car_data(car_data, session)
        
    except Exception as e:
        logger.error(f"Error processing car page {car_url}: {e}")


async def process_listing_page(page_url: str, client: httpx.AsyncClient, session: AsyncSession) -> str:
    """
    Process a listing page and get the next page URL
    """
    try:
        # Fetch the listing page
        html = await fetch_page(page_url, client)
        
        # Parse listing page and get all car URLs
        car_urls = await parse_car_listing_page(html)
        
        if not car_urls:
            logger.warning(f"No car URLs found on page {page_url}")
            
            # Check if there's a next page even if no cars found (might be temporary error)
            next_page_url = await get_next_page_url(html, page_url)
            if next_page_url:
                logger.info(f"No cars found but next page exists: {next_page_url}")
                return next_page_url
                
            return None
            
        logger.info(f"Found {len(car_urls)} car URLs on page {page_url}")
        
        # Process each car URL with a limited number of concurrent tasks
        semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_REQUESTS)
        
        async def process_with_semaphore(url):
            async with semaphore:
                await process_car_page(url, client, session)
        
        # Process only a limited number of links in test mode
        if settings.TEST_MODE:
            test_limit = 3  # For testing
            logger.info(f"TEST MODE: Processing only {test_limit} cars")
            car_urls = car_urls[:test_limit]
        
        # Create tasks for each car URL
        tasks = [process_with_semaphore(url) for url in car_urls]
        await asyncio.gather(*tasks)
        
        # Get the URL for the next page
        next_page_url = await get_next_page_url(html, page_url)
        if next_page_url:
            logger.info(f"Next page URL: {next_page_url}")
        else:
            logger.info("No next page found")
        
        return next_page_url
    except Exception as e:
        logger.error(f"Error processing listing page {page_url}: {e}")
        return None


async def run_scraper(db_session: AsyncSession) -> None:
    """
    Main scraper function
    """
    start_time = time.time()
    logger.info("Starting AutoRia scraper...")
    
    if settings.TEST_MODE:
        logger.info("Running in TEST MODE - limited scraping will be performed")
    
    # Initialize HTTP client with proper headers
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Cache-Control": "max-age=0",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "sec-ch-ua": '"Google Chrome";v="91", "Chromium";v="91", ";Not A Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "Referer": "https://auto.ria.com/uk/"
    }
    
    limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
    
    # Create debug directory
    debug_dir = "debug"
    os.makedirs(debug_dir, exist_ok=True)
    
    # Create client with limits and timeout
    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(
        headers=headers, 
        follow_redirects=True, 
        timeout=timeout,
        limits=limits
    ) as client:
        # Start with the initial URL
        current_page_url = settings.AUTO_RIA_START_URL
        page_count = 0
        
        # Process pages until there are no more pages or a limit is reached
        max_pages = 1 if settings.TEST_MODE else settings.MAX_PAGES
        
        logger.info(f"Starting scraping with max pages: {max_pages}")
        
        while current_page_url and page_count < max_pages:
            logger.info(f"Processing page {page_count + 1}: {current_page_url}")
            
            # Process the current page and get the next page URL
            next_page_url = await process_listing_page(current_page_url, client, db_session)
            
            if not next_page_url or next_page_url == current_page_url:
                logger.info("No more pages to process")
                break
            
            current_page_url = next_page_url
            page_count += 1
            
            # Small delay between pages to avoid rate limiting
            await asyncio.sleep(settings.REQUEST_DELAY * 2)
    
    elapsed_time = time.time() - start_time
    logger.info(f"Scraping completed. Processed {page_count} pages in {elapsed_time:.2f} seconds") 