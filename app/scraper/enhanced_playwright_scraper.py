import asyncio
import os
import re
import json
import time
import random
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from datetime import datetime

from app.config import settings, logger
from app.scraper.parser import parse_car_detail_page, parse_car_listing_page
from app.db.models import Car


async def setup_browser(proxy: Optional[str] = None) -> Tuple[Any, Browser, BrowserContext, Page]:
    """
    Setup Playwright browser with advanced stealth settings to avoid detection
    
    Args:
        proxy: Optional proxy server in format 'http://user:pass@host:port' or 'socks5://host:port'
    
    Returns:
        Tuple containing playwright instance, browser, context and page
    """
    logger.info("Initializing Playwright browser with enhanced stealth settings")
    playwright = await async_playwright().start()
    
    browser_args = [
        '--disable-blink-features=AutomationControlled',
        '--disable-features=IsolateOrigins,site-per-process',
        '--disable-site-isolation-trials',
        '--disable-web-security',
        '--disable-setuid-sandbox',
        '--no-sandbox',
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        '--disable-extensions',
        '--disable-dev-shm-usage',
        '--disable-accelerated-2d-canvas',
        '--no-first-run',
        '--no-zygote',
        '--lang=uk-UA,uk',
        '--window-size=1920,1080',
        '--use-gl=angle',
        '--enable-webgl',
        '--use-angle=default',
        '--disable-notifications',
        '--mute-audio'
    ]
    
    # Use chromium browser with enhanced stealth mode
    browser = await playwright.chromium.launch(
        headless=True,
        args=browser_args
    )
    
    # Context options
    context_options = {
        'viewport': {'width': 1920, 'height': 1080},
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'locale': 'uk-UA',
        'timezone_id': 'Europe/Kiev',
        'bypass_csp': True,
        'ignore_https_errors': True,
        'java_script_enabled': True,
        'has_touch': False,
        'is_mobile': False,
        'device_scale_factor': 1,
        'color_scheme': 'light',
        'reduced_motion': 'no-preference',
        'forced_colors': 'none',
        'accept_downloads': False
    }
    
    # Add proxy configuration if provided
    if proxy and settings.USE_PROXIES:
        logger.info(f"Using proxy: {proxy.split('@')[-1] if '@' in proxy else proxy}")
        proxy_config = {"server": proxy}
        
        # Add authentication if required
        if settings.PROXY_USERNAME and settings.PROXY_PASSWORD:
            proxy_config["username"] = settings.PROXY_USERNAME
            proxy_config["password"] = settings.PROXY_PASSWORD
            
        context_options["proxy"] = proxy_config
    
    # Create context and page
    context = await browser.new_context(**context_options)
    
    # Add extra headers
    await context.set_extra_http_headers({
        'Accept-Language': 'uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Cache-Control': 'max-age=0',
        'sec-ch-ua': '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'none',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1'
    })
    
    # Create a new page
    page = await context.new_page()
    
    # Apply enhanced stealth scripts
    await apply_stealth_settings(page)
    
    return playwright, browser, context, page


async def apply_stealth_settings(page: Page) -> None:
    """Apply comprehensive anti-detection settings to the page"""
    
    # Apply basic stealth settings
    await page.evaluate("""() => {
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
    }""")
    
    # Spoof languages
    await page.evaluate("""() => {
        Object.defineProperty(navigator, 'languages', {
            get: () => ['uk-UA', 'uk', 'en-US', 'en'],
        });
    }""")
    
    # Add sophisticated WebGL fingerprinting protection
    await page.evaluate("""() => {
        // WebGL vendor and renderer spoofing
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            // UNMASKED_RENDERER_WEBGL
            if (parameter === 37446) {
                return 'Intel(R) HD Graphics 630';
            }
            // UNMASKED_VENDOR_WEBGL
            if (parameter === 37445) {
                return 'Intel Inc.';
            }
            
            // Add noise to some parameters
            if (parameter === 3415) return 0;
            if (parameter === 3414) return 24;
            if (parameter === 35661) return 32;
            if (parameter === 34047) return 16;
            if (parameter === 34930) return 16;
            if (parameter === 3379) return 16384;
            if (parameter === 36349) return 1024;
            if (parameter === 34076) return 16384;
            if (parameter === 36348) return 30;
            if (parameter === 34024) return 16384;
            if (parameter === 3386) return 16384;
            if (parameter === 3413) return 16;
            if (parameter === 3412) return 16;
            if (parameter === 3410) return 8;
            if (parameter === 3411) return 8;
            if (parameter === 34852) return 8;
            if (parameter === 34068) return 32;
            
            return getParameter.apply(this, arguments);
        };
    }""")
    
    # Plugin spoofing with realistic data
    await page.evaluate("""() => {
        // Add plugins to spoof plugin count
        const mockPlugins = [
            {
                name: 'Chrome PDF Plugin',
                description: 'Portable Document Format',
                filename: 'internal-pdf-viewer',
                mimeTypes: [
                    { type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format' }
                ]
            },
            {
                name: 'Chrome PDF Viewer',
                description: 'Portable Document Format',
                filename: 'internal-pdf-viewer',
                mimeTypes: [
                    { type: 'application/pdf', suffices: 'pdf', description: 'Portable Document Format' }
                ]
            },
            {
                name: 'Native Client',
                description: '',
                filename: 'internal-nacl-plugin',
                mimeTypes: [
                    { type: 'application/x-nacl', suffices: '', description: 'Native Client Executable' },
                    { type: 'application/x-pnacl', suffices: '', description: 'Portable Native Client Executable' }
                ]
            }
        ];
        
        // Define navigator.plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                // Create plugin array with correct prototype
                const pluginArray = Object.create(PluginArray.prototype);
                
                // Add length property
                Object.defineProperty(pluginArray, 'length', {
                    get: () => mockPlugins.length,
                });
                
                // Add each plugin
                mockPlugins.forEach((plugin, i) => {
                    // Create the plugin
                    const pluginObj = Object.create(Plugin.prototype);
                    
                    // Define plugin properties
                    Object.defineProperty(pluginObj, 'name', { get: () => plugin.name });
                    Object.defineProperty(pluginObj, 'description', { get: () => plugin.description });
                    Object.defineProperty(pluginObj, 'filename', { get: () => plugin.filename });
                    
                    // Create mimeTypes collection
                    const mimeTypes = Object.create(MimeTypeArray.prototype);
                    Object.defineProperty(mimeTypes, 'length', { get: () => plugin.mimeTypes.length });
                    
                    // Add each mime type
                    plugin.mimeTypes.forEach((mimeType, j) => {
                        // Create the mimeType
                        const mimeTypeObj = Object.create(MimeType.prototype);
                        
                        // Define mimeType properties
                        Object.defineProperty(mimeTypeObj, 'type', { get: () => mimeType.type });
                        Object.defineProperty(mimeTypeObj, 'suffices', { get: () => mimeType.suffices });
                        Object.defineProperty(mimeTypeObj, 'description', { get: () => mimeType.description });
                        Object.defineProperty(mimeTypeObj, 'enabledPlugin', { get: () => pluginObj });
                        
                        // Add the mimeType to mimeTypes
                        Object.defineProperty(mimeTypes, j, { get: () => mimeTypeObj });
                        Object.defineProperty(mimeTypes, mimeType.type, { get: () => mimeTypeObj });
                    });
                    
                    // Add mimeTypes to plugin
                    Object.defineProperty(pluginObj, 'length', { get: () => plugin.mimeTypes.length });
                    plugin.mimeTypes.forEach((mimeType, j) => {
                        Object.defineProperty(pluginObj, j, { get: () => mimeTypes[j] });
                    });
                    
                    // Add the plugin to pluginArray
                    Object.defineProperty(pluginArray, i, { get: () => pluginObj });
                    Object.defineProperty(pluginArray, plugin.name, { get: () => pluginObj });
                });
                
                // Add item method
                pluginArray.item = function(index) {
                    return this[index];
                };
                
                // Add namedItem method
                pluginArray.namedItem = function(name) {
                    return this[name];
                };
                
                // Add refresh method
                pluginArray.refresh = function() {};
                
                return pluginArray;
            }
        });
    }""")
    
    # Permissions API spoofing
    await page.evaluate("""() => {
        // Permissions spoofing
        if (navigator.permissions) {
            const originalQuery = navigator.permissions.query;
            navigator.permissions.query = function(parameters) {
                if (parameters.name === 'notifications') {
                    return Promise.resolve({ state: Notification.permission, onchange: null });
                }
                return originalQuery.call(this, parameters);
            };
        }
        
        // Add userActivation (Chrome-specific)
        Object.defineProperty(navigator, 'userActivation', {
            get: () => {
                return {
                    hasBeenActive: true,
                    isActive: true
                };
            }
        });
    }""")
    
    # Handle window.open to prevent popup usage for detection
    await page.evaluate("""() => {
        window.open = function(url, target, features) {
            console.log('Window open called: ', url, target, features);
            return null;
        };
    }""")
    
    logger.info("Applied enhanced stealth settings to page")


async def simulate_human_behavior(page: Page) -> None:
    """
    Simulate human-like behavior on the page to avoid detection
    """
    logger.info("Simulating human-like behavior on page")
    
    # Random scroll with variable speed and pauses
    scroll_height = await page.evaluate("document.body.scrollHeight")
    viewport_height = await page.evaluate("window.innerHeight")
    
    if scroll_height > viewport_height:
        # Number of scroll steps (variable)
        num_steps = random.randint(5, 10)
        
        for i in range(1, num_steps + 1):
            # Calculate scroll position with some randomness
            target_position = (i / num_steps) * scroll_height
            jitter = random.uniform(-100, 100)
            target_position = max(0, min(scroll_height - viewport_height, target_position + jitter))
            
            # Scroll to position
            await page.evaluate(f"window.scrollTo(0, {target_position})")
            
            # Random pause between scrolls (300-700ms)
            await asyncio.sleep(random.uniform(0.3, 0.7))
    
    # Random mouse movements (only a few to avoid excessive resource usage)
    for _ in range(random.randint(3, 6)):
        x = random.randint(200, 800)
        y = random.randint(200, 600)
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.1, 0.3))
    
    # Possibly click on a random non-link element
    if random.random() < 0.3:  # 30% chance
        await page.evaluate("""() => {
            const elements = Array.from(document.querySelectorAll('div, span, p')).filter(el => {
                const rect = el.getBoundingClientRect();
                return rect.width > 10 && rect.height > 10 && 
                       rect.top > 0 && rect.left > 0 &&
                       !el.querySelector('a') && !el.closest('a');
            });
            if (elements.length > 0) {
                const randomElement = elements[Math.floor(Math.random() * elements.length)];
                const rect = randomElement.getBoundingClientRect();
                return {x: rect.left + rect.width/2, y: rect.top + rect.height/2};
            }
            return null;
        }""")
        
    # Final pause to simulate reading
    await asyncio.sleep(random.uniform(1.0, 2.0))
    
    logger.info("Completed human behavior simulation")


async def fetch_with_playwright(url: str, page: Page) -> str:
    """
    Fetch a page with Playwright with enhanced reliability and anti-detection
    
    Args:
        url: URL to fetch
        page: Playwright page object
        
    Returns:
        HTML content of the page
    """
    logger.info(f"Fetching page with Playwright: {url}")
    
    try:
        # Navigate to the page with a more reliable timeout (30s) and wait for DOM content
        # Using domcontentloaded instead of networkidle which can be unreliable
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        # Add a small wait for dynamic content
        await asyncio.sleep(random.uniform(1.5, 2.5))
        
        # Check if page loaded successfully
        current_url = page.url
        if "captcha" in current_url.lower() or "security" in current_url.lower() or "check" in current_url.lower():
            logger.warning(f"Detected potential security/captcha page: {current_url}")
            
            # Take a screenshot for debugging
            debug_dir = "debug"
            os.makedirs(debug_dir, exist_ok=True)
            screenshot_path = os.path.join(debug_dir, f"security_page_{int(time.time())}.png")
            await page.screenshot(path=screenshot_path)
            logger.warning(f"Saved security page screenshot to {screenshot_path}")
            
            # Try to save HTML for debugging
            try:
                html = await page.content()
                html_path = os.path.join(debug_dir, f"security_page_{int(time.time())}.html")
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html)
                logger.warning(f"Saved security page HTML to {html_path}")
            except Exception as e:
                logger.error(f"Failed to save security page HTML: {e}")
                
            return ""
        
        # Simulate human-like behavior
        await simulate_human_behavior(page)
        
        # Get the page content after interaction
        html = await page.content()
        
        # Basic content validation
        if len(html) < 1000 or "not found" in html.lower() or "error" in html.lower():
            logger.warning(f"Page content appears invalid. Length: {len(html)}")
            
            # Save suspicious page for inspection
            debug_dir = "debug"
            os.makedirs(debug_dir, exist_ok=True)
            file_path = os.path.join(debug_dir, f"invalid_page_{int(time.time())}.html")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.warning(f"Saved invalid page to {file_path}")
            
            screenshot_path = os.path.join(debug_dir, f"invalid_page_{int(time.time())}.png")
            await page.screenshot(path=screenshot_path)
            logger.warning(f"Saved screenshot to {screenshot_path}")
        
        logger.info(f"Successfully fetched page: {url}, content length: {len(html)}")
        return html
        
    except Exception as e:
        logger.error(f"Error fetching page {url} with Playwright: {e}")
        
        # Try to capture error state
        try:
            debug_dir = "debug"
            os.makedirs(debug_dir, exist_ok=True)
            screenshot_path = os.path.join(debug_dir, f"error_page_{int(time.time())}.png")
            await page.screenshot(path=screenshot_path)
            logger.error(f"Saved error screenshot to {screenshot_path}")
        except Exception as screenshot_error:
            logger.error(f"Could not capture error screenshot: {screenshot_error}")
            
        return ""


async def parse_car_listing_page(html: str) -> List[str]:
    """
    Parse a listing page and extract all car detail URLs
    
    Args:
        html: HTML content of the listing page
        
    Returns:
        List of car detail URLs
    """
    if not html:
        logger.error("Empty HTML, cannot parse car listings")
        return []
        
    logger.info(f"Parsing car listing page, HTML length: {len(html)}")
    
    # Save HTML for debugging
    debug_dir = "debug"
    os.makedirs(debug_dir, exist_ok=True)
    with open(os.path.join(debug_dir, f"listing_page_{int(time.time())}.html"), "w", encoding="utf-8") as f:
        f.write(html)
        
    soup = BeautifulSoup(html, "lxml")
    car_links = []
    
    # Check if the page might be a CAPTCHA challenge or anti-bot page
    if "captcha" in html.lower() or "robot" in html.lower() or "detection" in html.lower():
        logger.warning("Possible anti-bot protection detected on the page")
        with open(os.path.join(debug_dir, f"antibot_page_{int(time.time())}.html"), "w", encoding="utf-8") as f:
            f.write(html)
        return []
    
    # Try multiple selectors to find car elements
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
                except Exception as e:
                    logger.error(f"Error processing car element: {e}")
    
    # If no car links found yet, try regex pattern matching
    if not car_links:
        logger.info("No car links found with selectors, trying regex pattern matching")
        auto_links = re.findall(r'(?:href|link|url)=[\"\']?([^\"\'\s>]+auto_[^\"\']+\.html)', html)
        for link in auto_links:
            if not link.startswith('http'):
                link = urljoin("https://auto.ria.com", link)
            if link not in car_links:
                car_links.append(link)
    
    # Filter out duplicate links
    car_links = list(set(car_links))
    
    logger.info(f"Successfully extracted {len(car_links)} car links from page")
    if car_links:
        for i, link in enumerate(car_links[:3]):
            logger.info(f"Link {i+1}: {link}")
    
    return car_links 


async def extract_phone_number(page: Page, car_url: str, ad_id: str) -> Optional[str]:
    """
    Extract phone number from car detail page
    
    Args:
        page: Playwright page object
        car_url: URL of the car detail page
        ad_id: Ad ID extracted from the URL
        
    Returns:
        Phone number or None if not found
    """
    logger.info(f"Attempting to extract phone number for ad ID: {ad_id}")
    
    try:
        # Check if there's a button to show phone
        show_phone_button = page.locator("span.showCenterNumber.bold, a.phone_show_link, a[data-click-call-now]").first
        
        # If button exists, click it to reveal the phone number
        if await show_phone_button.count() > 0:
            logger.info("Found show phone button, clicking it...")
            await show_phone_button.click()
            
            # Wait briefly for number to appear
            await asyncio.sleep(1.5)
            
            # Try several approaches to get the phone number
            
            # 1. Check for phone_show_link parent with data-phone-number
            phone_data = await page.evaluate("""() => {
                const phoneEl = document.querySelector('.phone_show_link[data-phone-number]');
                if (phoneEl) return phoneEl.getAttribute('data-phone-number');
                return null;
            }""")
            
            if phone_data:
                logger.info(f"Found phone number via data attribute: {phone_data}")
                return phone_data
                
            # 2. Check for revealed phone element
            phone_text = await page.evaluate("""() => {
                const phoneEl = document.querySelector('.show-phone-data, .phone_show_link span, .phone, [data-call-phone]');
                if (phoneEl) return phoneEl.textContent.trim();
                return null;
            }""")
            
            if phone_text:
                # Clean up the phone number (remove non-numeric except +)
                phone_clean = re.sub(r'[^\d+]', '', phone_text)
                if phone_clean:
                    logger.info(f"Found phone number via element text: {phone_clean}")
                    return phone_clean
            
            # 3. Try to extract from API call using the ad ID
            # This is a fallback method if the other approaches fail
            try:
                phone_api_url = f"https://auto.ria.com/users/phones/{ad_id}?hash=hash_{ad_id}"
                
                # Navigate to API endpoint in a new tab
                phone_page = await page.context.new_page()
                await phone_page.goto(phone_api_url, timeout=10000)
                
                # Get the response text
                phone_json = await phone_page.content()
                await phone_page.close()
                
                # Extract phone from JSON
                match = re.search(r'"phone":\s*"([^"]+)"', phone_json)
                if match:
                    phone = match.group(1)
                    logger.info(f"Found phone number via API: {phone}")
                    return phone
            except Exception as api_err:
                logger.error(f"Failed to get phone from API: {api_err}")
        
        # 4. Check if phone is directly visible without clicking (sometimes the case)
        visible_phone = await page.evaluate("""() => {
            const phoneElements = document.querySelectorAll('.phone, .phone-block .phones .item span, .phone-list span');
            for (const el of phoneElements) {
                const text = el.textContent.trim();
                if (text.match(/^\\+?\\d{7,15}$/)) return text;
            }
            return null;
        }""")
        
        if visible_phone:
            logger.info(f"Found visible phone number: {visible_phone}")
            return visible_phone
            
        logger.warning(f"Could not extract phone number for ad ID: {ad_id}")
        return None
        
    except Exception as e:
        logger.error(f"Error extracting phone number: {e}")
        return None


async def process_car_page(car_url: str, page: Page, session: AsyncSession) -> None:
    """
    Process a single car detail page
    
    Args:
        car_url: URL of the car detail page
        page: Playwright page object
        session: Database session
    """
    logger.info(f"Processing car page: {car_url}")
    
    try:
        # Extract car ID from URL
        car_id_match = re.search(r'auto_([^.]+)\.html', car_url)
        if not car_id_match:
            logger.warning(f"Could not extract car ID from URL: {car_url}")
            return
            
        ad_id = car_id_match.group(1)
        
        # Check if this car already exists in the database
        existing_car = await session.execute(
            select(Car).where(Car.url == car_url)
        )
        if existing_car.scalar_one_or_none():
            logger.info(f"Car already exists in database: {car_url}")
            return
            
        # Fetch the car detail page
        html = await fetch_with_playwright(car_url, page)
        if not html:
            logger.error(f"Failed to fetch car detail page: {car_url}")
            return
            
        # Extract phone number
        phone_number = await extract_phone_number(page, car_url, ad_id)
        
        # Parse the car details
        car_data = parse_car_detail_page(html, car_url)
        if not car_data:
            logger.error(f"Failed to parse car details: {car_url}")
            return
            
        # Add the phone number to the car data
        car_data['phone_number'] = phone_number
        
        # Save the car to the database
        new_car = Car(**car_data)
        session.add(new_car)
        await session.commit()
        
        logger.info(f"Successfully processed and saved car: {car_url}")
        
    except Exception as e:
        logger.error(f"Error processing car page {car_url}: {e}")
        await session.rollback()


async def get_next_page_url(page: Page, current_url: str) -> Optional[str]:
    """
    Get URL of the next page in search results
    
    Args:
        page: Playwright page object
        current_url: Current page URL
        
    Returns:
        URL of the next page or None if not found
    """
    logger.info("Looking for next page link")
    
    try:
        # Check for pagination elements
        next_page = await page.evaluate("""() => {
            // Try different selectors for the next page button
            const selectors = [
                '.pagination .page-item:not(.disabled) a[rel="next"]',
                '.pagination a.arrow.next:not(.disabled)',
                'span.pagenl > a.page-link.js-next',
                '.pager a.js-next',
                '.pagination a.js-next',
                '.pagination a:has(span.page-link.next:not(.disabled))',
                '.pagination li.next:not(.disabled) a'
            ];
            
            for (const selector of selectors) {
                const el = document.querySelector(selector);
                if (el && el.href) return el.href;
            }
            
            // Fallback method: look for the current page number and construct next page URL
            const currentPageEl = document.querySelector('.pagination .active');
            if (currentPageEl) {
                const currentPage = parseInt(currentPageEl.textContent.trim());
                const nextPage = currentPage + 1;
                
                // Check if next page exists
                const pages = Array.from(document.querySelectorAll('.pagination .page-item a'))
                    .map(el => parseInt(el.textContent.trim()))
                    .filter(num => !isNaN(num));
                    
                if (pages.includes(nextPage)) {
                    // Try to construct the next page URL
                    const currentUrl = window.location.href;
                    if (currentUrl.includes('page=')) {
                        return currentUrl.replace(/page=\\d+/, `page=${nextPage}`);
                    } else {
                        const separator = currentUrl.includes('?') ? '&' : '?';
                        return `${currentUrl}${separator}page=${nextPage}`;
                    }
                }
            }
            
            return null;
        }""")
        
        if next_page:
            logger.info(f"Found next page URL: {next_page}")
            return next_page
        
        # If JavaScript method failed, try parsing the HTML
        html = await page.content()
        soup = BeautifulSoup(html, "lxml")
        
        # Try different next page link selectors
        next_link = soup.select_one('.pagination .page-item:not(.disabled) a[rel="next"], .pagination a.arrow.next:not(.disabled), span.page-link.js-next')
        
        if next_link and next_link.get('href'):
            next_url = next_link.get('href')
            if not next_url.startswith('http'):
                next_url = urljoin(current_url, next_url)
            logger.info(f"Found next page URL via HTML parsing: {next_url}")
            return next_url
            
        logger.info("No next page found, this appears to be the last page")
        return None
        
    except Exception as e:
        logger.error(f"Error getting next page URL: {e}")
        return None


async def get_random_proxy() -> Optional[str]:
    """Get a random proxy from the configured proxy list if proxy use is enabled"""
    if not settings.USE_PROXIES or not settings.PROXY_LIST:
        return None
        
    return random.choice(settings.PROXY_LIST)


async def run_enhanced_playwright_scraper(db_session: AsyncSession) -> None:
    """
    Run the enhanced Playwright-based scraper to extract car listings and details
    
    Args:
        db_session: SQLAlchemy database session
    """
    start_time = time.time()
    logger.info(f"Starting enhanced Playwright scraper at {datetime.now().isoformat()}")
    
    # Tracking variables
    processed_tickets = 0
    processed_pages = 0
    current_url = settings.AUTO_RIA_START_URL
    
    # Get proxy if enabled
    proxy = await get_random_proxy()
    if settings.USE_PROXIES:
        logger.info(f"Proxy usage is enabled. Using proxy: {proxy if proxy else 'None available'}")
    
    # Initialize empty instances
    playwright = None
    browser = None
    
    try:
        # Setup browser with enhanced stealth settings
        playwright, browser, context, page = await setup_browser(proxy)
        logger.info(f"Browser setup complete, navigating to start URL: {current_url}")
        
        # Process pages until we reach the limit or run out of pages
        while processed_pages < settings.MAX_PAGES and processed_tickets < settings.MAX_TICKETS_PER_RUN:
            logger.info(f"Processing page {processed_pages + 1}: {current_url}")
            
            # Fetch the page with anti-bot protection
            html = await fetch_with_playwright(current_url, page)
            
            if not html:
                logger.error(f"Failed to fetch page: {current_url}")
                break
                
            # Parse the page to extract car links
            car_links = await parse_car_listing_page(html)
            logger.info(f"Found {len(car_links)} car links on page {processed_pages + 1}")
            
            if not car_links:
                logger.warning(f"No car links found on page {current_url}")
                break
                
            # Process each car link up to the ticket limit
            for car_link in car_links:
                if processed_tickets >= settings.MAX_TICKETS_PER_RUN:
                    logger.info(f"Reached maximum tickets per run ({settings.MAX_TICKETS_PER_RUN})")
                    break
                    
                try:
                    # Process individual car page
                    await process_car_page(car_link, page, db_session)
                    processed_tickets += 1
                    
                    # Add random delay to avoid detection
                    delay = settings.REQUEST_DELAY * (1 + random.random() * 0.5)
                    logger.info(f"Processed ticket {processed_tickets}/{settings.MAX_TICKETS_PER_RUN}. Waiting {delay:.2f}s before next request")
                    await asyncio.sleep(delay)
                    
                except Exception as e:
                    logger.error(f"Error processing car page {car_link}: {e}")
                    continue
            
            processed_pages += 1
            
            # Get next page URL
            next_page_url = await get_next_page_url(page, current_url)
            
            if not next_page_url:
                logger.info("No more pages available")
                break
                
            current_url = next_page_url
            
            # Add random delay between pages
            page_delay = settings.REQUEST_DELAY * 2 * (1 + random.random() * 0.5)
            logger.info(f"Moving to next page. Waiting {page_delay:.2f}s")
            await asyncio.sleep(page_delay)
            
        # Log scraping results
        duration = time.time() - start_time
        logger.info(f"Scraping completed: Processed {processed_tickets} tickets across {processed_pages} pages in {duration:.2f} seconds")
        
    except Exception as e:
        logger.error(f"Error in enhanced Playwright scraper: {e}")
    finally:
        # Clean up resources
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()


async def process_mock_data(listing_file_path: str, detail_file_path: str = None, db_session: AsyncSession = None) -> Dict[str, Any]:
    """
    Process mock HTML data from files instead of fetching from the real site
    
    Args:
        listing_file_path: Path to the file containing HTML for the listings page
        detail_file_path: Optional path to the file containing HTML for the car detail page
        db_session: Optional database session for saving extracted data
        
    Returns:
        Dictionary with processing results
    """
    logger.info(f"Processing mock data from listing file: {listing_file_path}")
    start_time = time.time()
    
    try:
        # Normalize file paths (convert Windows paths if needed)
        listing_file_path = os.path.normpath(listing_file_path)
        if detail_file_path:
            detail_file_path = os.path.normpath(detail_file_path)
        
        # Check for Windows-style absolute paths and convert if needed
        if re.match(r'^[A-Za-z]:\\', listing_file_path):
            listing_file_path = listing_file_path.replace('\\', '/')
            logger.info(f"Converted Windows path to: {listing_file_path}")
            
        if detail_file_path and re.match(r'^[A-Za-z]:\\', detail_file_path):
            detail_file_path = detail_file_path.replace('\\', '/')
            logger.info(f"Converted Windows path to: {detail_file_path}")
            
        # Try different path variations to handle both relative and absolute paths
        base_paths = [
            "",  # Original path as provided
            os.path.join(os.getcwd(), ""),  # Absolute from current working directory 
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),  # From module location
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # App dir with abs path
            re.sub(r'^/[a-zA-Z]/', '/', listing_file_path) if listing_file_path.startswith('/') else listing_file_path,  # Remove drive letter if present
        ]
        
        # Additional paths to try for Windows
        if os.name == 'nt':
            drive = os.getcwd()[0].lower()
            base_paths.extend([
                f"{drive}:",  # Drive letter only
                f"{drive}:/PROJECTS/DataoxTest/",  # Common project path
                f"/",  # Root in Docker
                f"/app/",  # Docker app directory
            ])
        
        # Log the current working directory and base paths to try
        logger.info(f"Current working directory: {os.getcwd()}")
        logger.info(f"Base paths to try: {base_paths}")
        
        # Find listing file
        listing_file_found = False
        for base_path in base_paths:
            # Try multiple path combinations
            paths_to_try = [
                os.path.join(base_path, listing_file_path),
                listing_file_path,
                # Check if the path is already an absolute path
                listing_file_path if os.path.isabs(listing_file_path) else os.path.join(base_path, listing_file_path),
                # Try with only the filename
                os.path.join(base_path, os.path.basename(listing_file_path)),
                # Try with mock_data prefix if not already there (now at root level)
                listing_file_path if listing_file_path.endswith('mock_data/' + os.path.basename(listing_file_path)) 
                else os.path.join(base_path, "mock_data", os.path.basename(listing_file_path)),
                # Try with app/mock_data for backward compatibility
                os.path.join(base_path, "app", "mock_data", os.path.basename(listing_file_path))
            ]
            
            for path in paths_to_try:
                logger.info(f"Trying listing file path: {path}")
                if os.path.exists(path):
                    listing_file_path = path
                    listing_file_found = True
                    logger.info(f"Found listing file at: {listing_file_path}")
                    break
                    
            if listing_file_found:
                break
                
        if not listing_file_found:
            # Try a direct check as last resort
            direct_paths = [
                "mock_data/listing_page.html",  # New location
                "app/mock_data/listing_page.html"  # Old location for backward compatibility
            ]
            for direct_path in direct_paths:
                if os.path.exists(direct_path):
                    listing_file_path = direct_path
                    listing_file_found = True
                    logger.info(f"Found listing file with direct path: {listing_file_path}")
                    break
            
            if not listing_file_found:
                logger.error(f"Listing file not found: {listing_file_path}")
                return {
                    "success": False,
                    "error": f"Listing file not found: {listing_file_path}",
                    "tried_paths": [p for base in base_paths for p in [
                        os.path.join(base, listing_file_path),
                        os.path.join(base, "mock_data", os.path.basename(listing_file_path)),
                        os.path.join(base, "app", "mock_data", os.path.basename(listing_file_path))
                    ]],
                    "cwd": os.getcwd(),
                    "file_exists_check": [
                        {"path": p, "exists": os.path.exists(p)} 
                        for p in ["mock_data/listing_page.html", "app/mock_data/listing_page.html"]
                    ]
                }
        
        # Find detail file if provided
        detail_file_found = False
        if detail_file_path:
            for base_path in base_paths:
                # Try multiple path combinations
                paths_to_try = [
                    os.path.join(base_path, detail_file_path),
                    detail_file_path,
                    # Check if the path is already an absolute path
                    detail_file_path if os.path.isabs(detail_file_path) else os.path.join(base_path, detail_file_path),
                    # Try with only the filename
                    os.path.join(base_path, os.path.basename(detail_file_path)),
                    # Try with mock_data prefix if not already there (now at root level)
                    detail_file_path if detail_file_path.endswith('mock_data/' + os.path.basename(detail_file_path)) 
                    else os.path.join(base_path, "mock_data", os.path.basename(detail_file_path)),
                    # Try with app/mock_data for backward compatibility
                    os.path.join(base_path, "app", "mock_data", os.path.basename(detail_file_path))
                ]
                
                for path in paths_to_try:
                    logger.info(f"Trying detail file path: {path}")
                    if os.path.exists(path):
                        detail_file_path = path
                        detail_file_found = True
                        logger.info(f"Found detail file at: {detail_file_path}")
                        break
                        
                if detail_file_found:
                    break
                    
            if not detail_file_found and detail_file_path:
                # Try a direct check as last resort
                direct_paths = [
                    "mock_data/car_page.html",  # New location
                    "app/mock_data/car_page.html"  # Old location for backward compatibility
                ]
                for direct_path in direct_paths:
                    if os.path.exists(direct_path):
                        detail_file_path = direct_path
                        detail_file_found = True
                        logger.info(f"Found detail file with direct path: {detail_file_path}")
                        break
                        
                if not detail_file_found:
                    logger.warning(f"Detail file not found: {detail_file_path}, will still process listing page data")
        
        # Read the listings HTML file
        logger.info(f"Reading listing file: {listing_file_path}")
        with open(listing_file_path, 'r', encoding='utf-8') as f:
            listing_html = f.read()
            
        # Parse the listings page to extract car links
        car_links = await parse_car_listing_page(listing_html)
        logger.info(f"Found {len(car_links)} car links in mock listing file")
        
        extracted_cars = []
        detail_car_data = None
        
        # Process the detail file if provided and found
        if detail_file_path and detail_file_found:
            try:
                logger.info(f"Reading detail file: {detail_file_path}")
                with open(detail_file_path, 'r', encoding='utf-8') as f:
                    detail_html = f.read()
                
                # Get a URL for the detail page
                detail_url = "https://auto.ria.com/uk/auto_mock_detail_123.html"
                
                # Process the car detail page
                detail_car_data = parse_car_detail_page(detail_html, detail_url)
                
                # Fill in MOCK data for fields that might not be present in the sample
                if not detail_car_data.get('car_number'):
                    detail_car_data['car_number'] = "AA0000AA"
                
                if not detail_car_data.get('car_vin'):
                    detail_car_data['car_vin'] = "WBAAA1111AAA00000"
                    
                if not detail_car_data.get('username'):
                    detail_car_data['username'] = "Автосалон Тест"
                    
                if not detail_car_data.get('phone_number'):
                    detail_car_data['phone_number'] = "+380987654321"
                
                # Store location but don't include it when saving to database
                detail_car_location = detail_car_data.get('location')
                if 'location' in detail_car_data:
                    del detail_car_data['location']
                
                logger.info(f"Extracted data from detail page: {detail_car_data['title']}")
                
                # Save just this one detailed car to the database if a session is provided
                if db_session:
                    try:
                        # Check if this car already exists
                        existing_car = await db_session.execute(
                            select(Car).where(Car.url == detail_car_data['url'])
                        )
                        car_exists = existing_car.scalar_one_or_none() is not None
                        
                        if not car_exists:
                            # Make a copy to keep the location in our response data
                            db_car_data = {k: v for k, v in detail_car_data.items() if k != 'location'}
                            new_car = Car(**db_car_data)
                            db_session.add(new_car)
                            await db_session.commit()
                            logger.info(f"Added detail car to database: {detail_car_data['url']}")
                        else:
                            logger.info(f"Detail car already exists in database: {detail_car_data['url']}")
                    except Exception as e:
                        logger.error(f"Error saving detail car to database: {e}")
                        await db_session.rollback()
                
                # Add the location back for display purposes
                if detail_car_location:
                    detail_car_data['location'] = detail_car_location
                
                # Add to extracted cars
                if detail_car_data:
                    extracted_cars.append(detail_car_data)
            except Exception as e:
                logger.error(f"Error processing detail file: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
        
        # Process the listing page to extract data from all ticket items
        logger.info("Extracting data from all listing page ticket items")
        soup = BeautifulSoup(listing_html, "lxml")
        
        # Find all ticket items
        car_items = soup.select('.ticket-item, .content-bar, .content-ticket')
        logger.info(f"Found {len(car_items)} car items on the listing page")
        
        # Generate a timestamp to add uniqueness to the mock URLs
        timestamp = int(time.time())
        
        # Process each car item from the listing page
        for idx, item in enumerate(car_items):
            try:
                # Create a new soup object with just this item
                item_html = str(item)
                
                # Get the URL for this car with timestamp to ensure uniqueness
                car_url = None
                url_element = item.select_one('a[href*="auto_"]')
                if url_element and url_element.get('href'):
                    car_url = url_element.get('href')
                    if not car_url.startswith('http'):
                        car_url = urljoin("https://auto.ria.com", car_url)
                else:
                    # If no URL found, create a unique URL with timestamp and index
                    car_url = f"https://auto.ria.com/uk/auto_mock_{timestamp}_{idx}.html"
                
                # Process this listing item
                car_data = parse_car_detail_page(item_html, car_url)
                
                # Add mock data for listing items
                if not car_data.get('phone_number'):
                    car_data['phone_number'] = f"+3809999{idx:05d}" 
                
                # Add default values for fields not available in listings
                if not car_data.get('car_number'):
                    car_data['car_number'] = f"AA{idx:04d}AA"  
                
                if not car_data.get('car_vin'):
                    car_data['car_vin'] = f"WBAAA{idx:05d}XXX00000"
                    
                if not car_data.get('username'):
                    car_data['username'] = f"Seller{idx}"
                
                # Store location separately and remove from database fields
                car_location = car_data.get('location', f"City{idx}")
                if 'location' in car_data:
                    del car_data['location']
                
                # Add the item to our extracted cars list (with location for display)
                display_data = dict(car_data)
                display_data['location'] = car_location
                extracted_cars.append(display_data)
                
                logger.info(f"Extracted data from listing item {idx+1}: {car_data['title']}")
            except Exception as e:
                logger.error(f"Error processing listing item {idx+1}: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
        
        # Save cars to the database if a session is provided
        saved_cars = 0
        if db_session:
            # Save each car individually instead of using a nested transaction
            for car_data in extracted_cars:
                # Skip the detail car that was already processed
                if car_data == detail_car_data and detail_car_data is not None:
                    continue
                    
                try:
                    if not car_data.get('url'):
                        logger.warning("Skipping car with no URL")
                        continue
                    
                    # Create a copy of car_data without the location field for DB
                    db_car_data = {k: v for k, v in car_data.items() if k != 'location'}
                        
                    # Check if this car already exists in the database
                    existing_car = await db_session.execute(
                        select(Car).where(Car.url == db_car_data['url'])
                    )
                    car_exists = existing_car.scalar_one_or_none() is not None
                    
                    if not car_exists:
                        new_car = Car(**db_car_data)
                        db_session.add(new_car)
                        await db_session.commit()  # Commit each car individually
                        saved_cars += 1
                        if saved_cars % 5 == 0:  # Log every 5th car
                            logger.info(f"Added car #{saved_cars} to database: {db_car_data['url']}")
                    else:
                        logger.info(f"Car already exists in database: {db_car_data['url']}")
                except Exception as e:
                    logger.error(f"Error saving car to database: {e}")
                    await db_session.rollback()
                    # Continue with other cars even if one fails
            
            logger.info(f"Successfully saved {saved_cars} cars to database")
        
        execution_time = time.time() - start_time
        logger.info(f"Mock data processing completed in {execution_time:.2f} seconds")
        
        # Make sure the sample data includes both detail page and listings
        sample_data = []
        if detail_car_data:
            sample_data.append({k: v for k, v in detail_car_data.items() if k != 'datetime_found'})
        
        # Add some listing data samples too
        for car_data in extracted_cars[:2]:
            if car_data != detail_car_data:  # Avoid duplicate of detail car
                sample_data.append({k: v for k, v in car_data.items() if k != 'datetime_found'})
                if len(sample_data) >= 2:  # Limit to at most 2 samples
                    break
        
        return {
            "success": True,
            "car_links_found": len(car_links),
            "car_items_processed": len(car_items),
            "total_cars_extracted": len(extracted_cars),
            "detail_page_processed": bool(detail_car_data),
            "cars_saved_to_database": saved_cars + (1 if detail_car_data and db_session else 0),
            "sample_data": sample_data,
            "processing_time": f"{execution_time:.2f} seconds",
            "file_paths": {
                "listing": listing_file_path,
                "detail": detail_file_path if detail_file_found else None
            }
        }
        
    except Exception as e:
        logger.error(f"Error processing mock data: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        } 