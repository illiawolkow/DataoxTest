import asyncio
import os
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time
import random
import json
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from app.config import settings, logger
from app.scraper.parser import parse_car_detail_page
from app.db.models import Car


async def setup_browser():
    """
    Setup Playwright browser with advanced stealth settings to avoid detection
    """
    playwright = await async_playwright().start()
    
    # Use chromium browser with enhanced stealth mode
    browser = await playwright.chromium.launch(
        headless=True,  # True for production, False for debugging
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-site-isolation-trials',
            '--disable-web-security',
            '--disable-setuid-sandbox',
            '--no-sandbox',
            '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            '--disable-extensions',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote',
            '--disable-gpu',
            '--lang=uk-UA,uk',
            '--window-size=1920,1080'
        ]
    )
    
    # Create a context with realistic viewport and user agent
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        locale='uk-UA',
        timezone_id='Europe/Kiev',
        bypass_csp=True,
        ignore_https_errors=True,  # Try to ignore HTTPS errors
        java_script_enabled=True,
        has_touch=False,
        is_mobile=False,
        device_scale_factor=1
    )
    
    # Add extra headers but keep simple to avoid fingerprinting
    await context.set_extra_http_headers({
        'Accept-Language': 'uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Cache-Control': 'max-age=0'
    })
    
    # Emulate non-automation behavior by injecting enhanced stealth script
    await context.add_init_script("""
        // Overwrite the 'navigator.webdriver' property
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        
        // Add chrome object
        window.chrome = {
            app: {
                isInstalled: false,
            },
            webstore: {
                onInstallStageChanged: {},
                onDownloadProgress: {},
            },
            runtime: {
                PlatformOs: {
                    MAC: 'mac',
                    WIN: 'win',
                    ANDROID: 'android',
                    CROS: 'cros',
                    LINUX: 'linux',
                    OPENBSD: 'openbsd',
                },
                PlatformArch: {
                    ARM: 'arm',
                    X86_32: 'x86-32',
                    X86_64: 'x86-64',
                },
                PlatformNaclArch: {
                    ARM: 'arm',
                    X86_32: 'x86-32',
                    X86_64: 'x86-64',
                },
                RequestUpdateCheckStatus: {
                    THROTTLED: 'throttled',
                    NO_UPDATE: 'no_update',
                    UPDATE_AVAILABLE: 'update_available',
                },
                OnInstalledReason: {
                    INSTALL: 'install',
                    UPDATE: 'update',
                    CHROME_UPDATE: 'chrome_update',
                    SHARED_MODULE_UPDATE: 'shared_module_update',
                },
                OnRestartRequiredReason: {
                    APP_UPDATE: 'app_update',
                    OS_UPDATE: 'os_update',
                    PERIODIC: 'periodic',
                }
            }
        };
        
        // Add language plugins
        Object.defineProperty(navigator, 'languages', {
            get: () => ['uk-UA', 'uk', 'en-US', 'en'],
        });
        
        // Add plugins to spoof plugin count
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const plugins = [
                    {
                        0: {type: 'application/pdf'},
                        name: 'PDF Viewer',
                        description: 'Portable Document Format',
                        filename: 'internal-pdf-viewer'
                    },
                    {
                        0: {type: 'application/pdf'},
                        name: 'Chrome PDF Viewer',
                        description: 'Portable Document Format',
                        filename: 'internal-pdf-viewer'
                    },
                    {
                        0: {type: 'application/x-google-chrome-pdf'},
                        name: 'Chrome PDF Plugin',
                        description: 'Portable Document Format',
                        filename: 'internal-pdf-viewer'
                    }
                ];
                plugins.forEach((plugin) => {
                    plugin.__proto__ = Plugin.prototype;
                });
                return plugins;
            },
        });
        
        // Add permissions - notifications
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
        );
        
        // Add userActivation
        Object.defineProperty(navigator, 'userActivation', {
            get: () => {
                return {
                    hasBeenActive: true,
                    isActive: true
                };
            }
        });
        
        // Spoof webGL renderer
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            // UNMASKED_RENDERER_WEBGL
            if (parameter === 37446) {
                return 'Intel Open Source Technology Center';
            }
            // UNMASKED_VENDOR_WEBGL
            if (parameter === 37445) {
                return 'Intel Inc.';
            }
            return getParameter.apply(this, arguments);
        };
    """)
    
    # Create a new page
    page = await context.new_page()
    
    # Add custom script to handle window.open
    await page.evaluate("""
        window.open = function(url, target, features) {
            // Just log and do nothing to prevent popups
            console.log('Window open called: ', url, target, features);
            return null;
        };
    """)
    
    # Set default navigation timeout
    page.set_default_timeout(30000)  # 30 seconds
    
    return playwright, browser, context, page


async def fetch_with_playwright(url: str, page: Page) -> str:
    """
    Fetch a page using Playwright with human-like behavior
    """
    try:
        # Add a small random delay to simulate human behavior
        await asyncio.sleep(random.uniform(1.0, 3.0))
        
        logger.info(f"Navigating to {url} with Playwright")
        
        # Use a less strict wait condition - just wait for the document instead of networkidle
        response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        # Check if the navigation was successful
        if not response:
            logger.error(f"Failed to navigate to {url}: No response")
            return ""
            
        if not response.ok and response.status != 200:
            logger.error(f"Failed to navigate to {url}: Status {response.status}")
            return ""
        
        # Wait a moment for any dynamic content to load
        await asyncio.sleep(random.uniform(2.0, 5.0))
        
        # Wait for body to be present
        try:
            await page.wait_for_selector("body", timeout=5000)
        except Exception as e:
            logger.warning(f"Could not find body element: {e}")
        
        # Perform random scrolling to simulate human behavior
        await simulate_human_behavior(page)
        
        # Additional wait time after scrolling to let any lazy-loaded content appear
        await asyncio.sleep(random.uniform(1.0, 3.0))
        
        # Get page content
        content = await page.content()
        
        # Check if content is empty
        if not content or len(content.strip()) < 100:
            logger.error(f"Response from {url} was empty or too short: {len(content) if content else 0} bytes")
            return ""
        
        # Log success
        logger.info(f"Successfully fetched {url} with Playwright: {len(content)} bytes")
        
        # Save for debugging
        debug_dir = "debug"
        os.makedirs(debug_dir, exist_ok=True)
        filename = f"playwright_response_{int(time.time())}.html"
        with open(os.path.join(debug_dir, filename), "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Saved response to {os.path.join(debug_dir, filename)}")
        
        # Also save a screenshot for debugging
        screenshot_path = os.path.join(debug_dir, f"playwright_screenshot_{int(time.time())}.png")
        await page.screenshot(path=screenshot_path, full_page=True)
        logger.info(f"Saved screenshot to {screenshot_path}")
        
        return content
    except Exception as e:
        logger.error(f"Error fetching with Playwright: {str(e)}")
        # Log more details about the exception
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return ""


async def simulate_human_behavior(page: Page):
    """
    Simulate human-like behavior on the page
    """
    # Get page height
    page_height = await page.evaluate('document.body.scrollHeight')
    viewport_height = await page.evaluate('window.innerHeight')
    
    # Perform random scrolling
    scroll_positions = list(range(0, page_height, viewport_height))
    random.shuffle(scroll_positions)  # Randomize scroll positions
    
    # Scroll to a few random positions
    for i, pos in enumerate(scroll_positions[:min(3, len(scroll_positions))]):
        await page.evaluate(f'window.scrollTo(0, {pos})')
        # Random pause between scrolls
        await asyncio.sleep(random.uniform(0.5, 2.0))
    
    # Random mouse movements (optional)
    if random.random() > 0.5:
        for _ in range(2):
            x = random.randint(100, 1000)
            y = random.randint(100, 500)
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.2, 0.7))


async def parse_car_listing_page(html: str) -> List[str]:
    """
    Parse a listing page and extract all car detail URLs
    """
    soup = BeautifulSoup(html, "lxml")
    car_links = []
    
    # Save HTML for debugging
    debug_dir = "debug"
    os.makedirs(debug_dir, exist_ok=True)
    with open(os.path.join(debug_dir, "listing_page_playwright.html"), "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"Saved listing page HTML to {os.path.join(debug_dir, 'listing_page_playwright.html')}")
    
    # Log page title for debugging
    page_title = soup.title.text if soup.title else "No title"
    logger.info(f"Page title: {page_title}")
    
    # Approach 1: Try all possible selectors for car listings
    selectors_to_try = [
        "section.ticket-item",                 # Classic format
        "div.ticket-item",                     # Alternative format
        "div.content-ticket",                  # Alternative format
        "div.content-bar",                     # Container format
        ".search-result .ticket-item",         # Nested format
        "div.app-catalog .app-catalog-item",   # Modern app format
        ".content-bar",                        # Container only
        ".app-catalog a[href*='auto_']",       # Direct links in modern format
        "a.address[href*='auto_']",            # Direct address links
        "a[href*='auto_'][href$='.html']"      # Any auto link
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


async def extract_phone_number(page: Page, car_url: str, ad_id: str) -> Optional[str]:
    """
    Extract phone number by emulating "show phone" button click
    """
    try:
        # Try to find and click the "show phone" button
        phone_button_selectors = [
            ".phone-btn",
            ".phones-item .phone",
            ".show-phone-btn",
            "button.phone",
            "a.show-phone",
            "[data-phone-button]"
        ]
        
        # First try API method
        phone_api_url = f"https://auto.ria.com/users/phones/{ad_id}"
        
        logger.info(f"Navigating to phone API: {phone_api_url}")
        
        # Add necessary headers
        await page.set_extra_http_headers({
            "Referer": car_url,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json"
        })
        
        # Navigate to the API URL
        response = await page.goto(phone_api_url, wait_until="networkidle")
        
        if response and response.ok:
            # Get the response body
            content = await response.text()
            
            try:
                # Parse JSON response
                phone_data = json.loads(content)
                
                # Extract phone number
                if "formattedPhoneNumber" in phone_data:
                    return phone_data["formattedPhoneNumber"]
                elif "phones" in phone_data and phone_data["phones"]:
                    return phone_data["phones"][0]
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON response from phone API: {content[:100]}")
        
        # If API method fails, try UI method
        # Go back to the car page
        await page.goto(car_url, wait_until="networkidle")
        
        # Try to find and click each possible phone button
        for selector in phone_button_selectors:
            if await page.query_selector(selector):
                logger.info(f"Found phone button with selector: {selector}")
                await page.click(selector)
                # Wait for the phone to appear
                await asyncio.sleep(2)
                
                # Look for phone numbers on the page after clicking
                content = await page.content()
                soup = BeautifulSoup(content, "lxml")
                
                # Try different ways to extract phone number
                phone_selectors = [
                    ".phones .phone", 
                    ".phone-number", 
                    "[data-phone-number]",
                    ".show-phone span"
                ]
                
                for phone_selector in phone_selectors:
                    phone_elements = soup.select(phone_selector)
                    if phone_elements:
                        # Get the first phone number found
                        phone_text = phone_elements[0].text.strip()
                        # Clean up the phone number
                        phone = re.sub(r'\D', '', phone_text)
                        if phone and len(phone) >= 10:
                            return phone
                
                # Also try regex to find any phone number pattern in the page content
                phone_matches = re.findall(r'(?<!\d)(?:\+38)?[(\s-]*(?:0\d{2}|\(\d{3}\))[\s-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)', content)
                if phone_matches:
                    # Clean up the phone number
                    phone = re.sub(r'\D', '', phone_matches[0])
                    if phone and len(phone) >= 10:
                        return phone
    
    except Exception as e:
        logger.error(f"Error extracting phone number: {e}")
    
    return None


async def process_car_page(car_url: str, page: Page, session: AsyncSession) -> None:
    """
    Process a single car detail page
    """
    try:
        # Extract advertisement ID from URL
        ad_id = None
        url_match = re.search(r'auto_[^_]+_(\d+)\.html', car_url)
        if url_match:
            ad_id = url_match.group(1)
        
        # Fetch car detail page
        car_html = await fetch_with_playwright(car_url, page)
        if not car_html:
            logger.error(f"Failed to fetch car page: {car_url}")
            return
        
        # Parse car data
        car_data = await parse_car_detail_page(car_html, car_url)
        
        # If ad_id was found and no phone number in parsed data, try to get it via API
        if ad_id and not car_data.get('phone_number'):
            logger.info(f"Trying to get phone number for car {ad_id}")
            phone_number = await extract_phone_number(page, car_url, ad_id)
            if phone_number:
                car_data['phone_number'] = phone_number
        
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
        logger.error(f"Error processing car page {car_url}: {e}")


async def get_next_page_url(page: Page, current_url: str) -> Optional[str]:
    """
    Extract the URL for the next page if it exists
    """
    try:
        # Try to find next page elements
        next_page_selectors = [
            ".pagination .next a",
            ".pager a.next",
            ".pagination a.arrow-right",
            ".search-result-pager a.page-link[rel='next']",
            ".pager a.js-next",
            "a[rel='next']"
        ]
        
        for selector in next_page_selectors:
            next_link = await page.query_selector(selector)
            if next_link:
                # Get the href attribute
                href = await next_link.get_attribute('href')
                if href:
                    # Build the full URL if it's a relative link
                    if not href.startswith('http'):
                        next_page_url = urljoin(current_url, href)
                    else:
                        next_page_url = href
                    
                    logger.info(f"Found next page URL: {next_page_url}")
                    return next_page_url
        
        # If no next page link is found via selectors, try a fallback approach
        # Check if there's a current page indicator and try to find the next page
        content = await page.content()
        soup = BeautifulSoup(content, "lxml")
        
        # Look for pagination elements with active/current class
        current_page_elements = soup.select(".pagination .active, .pager .active, .page-item.active")
        if current_page_elements:
            for current_elem in current_page_elements:
                # Try to find the next sibling that's a link
                next_sibling = current_elem.find_next_sibling()
                if next_sibling and next_sibling.name == 'a' or next_sibling.find('a'):
                    link_elem = next_sibling if next_sibling.name == 'a' else next_sibling.find('a')
                    if link_elem and link_elem.get('href'):
                        href = link_elem.get('href')
                        if not href.startswith('http'):
                            next_page_url = urljoin(current_url, href)
                        else:
                            next_page_url = href
                        
                        logger.info(f"Found next page URL via pagination: {next_page_url}")
                        return next_page_url
        
        logger.info("No next page URL found")
        return None
        
    except Exception as e:
        logger.error(f"Error getting next page URL: {e}")
        return None


async def run_playwright_scraper(db_session: AsyncSession) -> None:
    """
    Main scraper function using Playwright for browser automation
    """
    start_time = time.time()
    logger.info("Starting AutoRia scraper with Playwright browser automation...")
    
    # Initialize Playwright
    playwright, browser, context, page = await setup_browser()
    
    try:
        # Start with the initial URL
        current_page_url = settings.AUTO_RIA_START_URL
        page_count = 0
        
        # Process pages until there are no more pages or limit is reached
        max_pages = 1 if settings.TEST_MODE else settings.MAX_PAGES
        
        logger.info(f"Starting scraping with max pages: {max_pages}")
        
        while current_page_url and page_count < max_pages:
            logger.info(f"Processing page {page_count + 1}: {current_page_url}")
            
            # Fetch the page
            html = await fetch_with_playwright(current_page_url, page)
            if not html:
                logger.error(f"Failed to fetch page {current_page_url}")
                break
            
            # Parse the page to extract car URLs
            car_urls = await parse_car_listing_page(html)
            
            if not car_urls:
                logger.warning(f"No car URLs found on page {current_page_url}")
                
                # Check if there's a next page even if no cars found
                next_page_url = await get_next_page_url(page, current_page_url)
                if next_page_url:
                    logger.info(f"No cars found but next page exists: {next_page_url}")
                    current_page_url = next_page_url
                    page_count += 1
                    continue
                else:
                    logger.info("No more pages to process")
                    break
            
            logger.info(f"Found {len(car_urls)} car URLs on page {current_page_url}")
            
            # Process car URLs sequentially
            # In test mode, only process the first few links
            if settings.TEST_MODE:
                test_limit = 3  # For testing
                logger.info(f"TEST MODE: Processing only {test_limit} cars")
                car_urls = car_urls[:test_limit]
            
            # Process each car URL
            for car_url in car_urls:
                await process_car_page(car_url, page, db_session)
                # Add a small delay between requests to avoid rate limiting
                await asyncio.sleep(random.uniform(2.0, 4.0))
            
            # Get the URL for the next page
            next_page_url = await get_next_page_url(page, current_page_url)
            if not next_page_url or next_page_url == current_page_url:
                logger.info("No more pages to process")
                break
            
            current_page_url = next_page_url
            page_count += 1
            
            # Add a delay between pages to avoid rate limiting
            await asyncio.sleep(random.uniform(3.0, 5.0))
        
        elapsed_time = time.time() - start_time
        logger.info(f"Scraping completed. Processed {page_count} pages in {elapsed_time:.2f} seconds")
        
    except Exception as e:
        logger.error(f"Error in Playwright scraper: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
    
    finally:
        # Clean up resources
        if 'page' in locals():
            await page.close()
        if 'context' in locals():
            await context.close()
        if 'browser' in locals():
            await browser.close()
        if 'playwright' in locals():
            await playwright.stop()


async def test_playwright_scraper() -> Dict[str, Any]:
    """
    Test the Playwright scraper on a single page
    """
    logger.info("Testing Playwright scraper...")
    
    try:
        # Initialize Playwright
        playwright, browser, context, page = await setup_browser()
        
        try:
            # Fetch the listing page
            url = settings.AUTO_RIA_START_URL
            logger.info(f"Starting fetch from URL: {url}")
            
            # Navigate to the URL
            html = await fetch_with_playwright(url, page)
            
            if not html:
                return {
                    "success": False,
                    "error": "Failed to fetch page content"
                }
            
            # Check if content seems to be HTML
            is_html = "<html" in html.lower() and "</html>" in html.lower()
            logger.info(f"Content appears to be HTML: {is_html}")
            
            # Check for captcha or bot detection
            is_blocked = any(block_text in html.lower() for block_text in [
                "captcha", "bot detected", "blocked", "access denied", "verify you are human"
            ])
            if is_blocked:
                logger.warning("Possible bot detection in the response")
            
            # Parse the page to extract car URLs
            car_urls = await parse_car_listing_page(html)
            
            # Take a screenshot for visual inspection
            debug_dir = "debug"
            os.makedirs(debug_dir, exist_ok=True)
            screenshot_path = os.path.join(debug_dir, f"playwright_test_screenshot_{int(time.time())}.png")
            await page.screenshot(path=screenshot_path, full_page=True)
            logger.info(f"Saved test screenshot to {screenshot_path}")
            
            return {
                "success": True,
                "url": url,
                "content_length": len(html),
                "is_valid_html": is_html,
                "possibly_blocked": is_blocked,
                "car_links_found": len(car_urls),
                "sample_links": car_urls[:5] if car_urls else [],
                "screenshot_path": screenshot_path
            }
            
        except Exception as e:
            logger.error(f"Error during test: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                "success": False,
                "error": str(e)
            }
        
        finally:
            # Clean up resources
            await page.close()
            await context.close()
            await browser.close()
            await playwright.stop()
            
    except Exception as e:
        logger.error(f"Error initializing Playwright: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            "success": False,
            "error": f"Failed to initialize Playwright: {str(e)}"
        } 