"""
Test module for the enhanced Playwright scraper.
This can be run directly to test the scraper functionality.
"""
import asyncio
import os
import sys
import time
import logging
from pathlib import Path

# Add the project root to Python path for imports to work correctly
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.config import logger, settings
from app.scraper.enhanced_playwright_scraper import setup_browser, fetch_with_playwright, parse_car_listing_page


async def test_playwright_scraper():
    """
    Test the Playwright scraper's ability to parse a listing page
    
    Returns:
        Dictionary with test results
    """
    logger.info("Testing Playwright scraper")
    
    playwright = None
    browser = None
    
    try:
        # Set up browser with enhanced stealth
        playwright, browser, context, page = await setup_browser()
        
        # Fetch the listing page
        url = settings.AUTO_RIA_START_URL
        html = await fetch_with_playwright(url, page)
        
        if not html:
            logger.error("Failed to fetch page")
            return {
                "success": False,
                "error": "Failed to fetch page"
            }
            
        # Check for anti-bot patterns in the page
        is_bot_detected = "captcha" in html.lower() or "robot" in html.lower() or "detection" in html.lower()
        
        # Take a screenshot for debugging
        debug_dir = "debug"
        os.makedirs(debug_dir, exist_ok=True)
        screenshot_path = os.path.join(debug_dir, f"test_screenshot_{int(time.time())}.png")
        await page.screenshot(path=screenshot_path)
        
        # Parse the page to extract car links
        car_links = await parse_car_listing_page(html)
        
        # Detailed page info for debugging
        page_info = {
            "title": await page.title(),
            "url": page.url,
            "html_length": len(html),
            "anti_bot_detected": is_bot_detected,
            "screenshot": screenshot_path
        }
        
        # Store HTML for debugging
        html_path = os.path.join(debug_dir, f"test_page_{int(time.time())}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        
        # Return the result
        return {
            "success": len(car_links) > 0,
            "url": url,
            "car_links_found": len(car_links),
            "sample_links": car_links[:5] if car_links else [],
            "page_info": page_info,
            "html_saved_to": html_path
        }
        
    except Exception as e:
        logger.error(f"Error in test Playwright scraper: {e}")
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        # Clean up resources
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()


async def main():
    """Test the enhanced Playwright scraper"""
    # Configure logging for standalone testing
    if not logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler()]
        )
    
    # Create debug directory
    os.makedirs("debug", exist_ok=True)
    
    logger.info("Testing Playwright Scraper for AutoRia")
    
    # Run the test
    result = await test_playwright_scraper()
    
    # Display results
    if result["success"]:
        logger.info("✅ Test Successful!")
        logger.info(f"Found {result['car_links_found']} car links")
        
        if result["sample_links"]:
            logger.info("Sample car links:")
            for i, link in enumerate(result["sample_links"]):
                logger.info(f"  {i+1}. {link}")
                
        logger.info(f"Page info: {result['page_info']}")
        logger.info(f"HTML saved to: {result['html_saved_to']}")
        logger.info(f"Screenshot saved to: {result['page_info']['screenshot']}")
    else:
        logger.error("❌ Test Failed!")
        logger.error(f"Error: {result.get('error', 'Unknown error')}")
        if "page_info" in result:
            logger.info(f"Page info: {result['page_info']}")


if __name__ == "__main__":
    asyncio.run(main()) 