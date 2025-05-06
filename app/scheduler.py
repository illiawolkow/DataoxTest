import asyncio
import schedule
import time
import threading
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings, logger
from app.db.database import async_session, create_db_dump
from app.scraper.enhanced_playwright_scraper import run_enhanced_playwright_scraper

# Make sure we're importing the correct schedule module 
try:
    schedule.every  # Test if schedule.every exists
except AttributeError:
    # If it doesn't exist, reimport as a different name to avoid conflicts
    import schedule as schedule_lib
    schedule = schedule_lib

def run_threaded(job_func, *args, **kwargs):
    """Run a function in a separate thread"""
    job_thread = threading.Thread(target=job_func, args=args, kwargs=kwargs)
    job_thread.start()


def run_async_job(coro_func, *args, **kwargs):
    """Run an async function in a new event loop"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def run_job():
        try:
            # Create a new session for this job
            async with async_session() as session:
                await coro_func(session, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error running scheduled job {coro_func.__name__}: {e}")
        finally:
            loop.stop()
    
    loop.create_task(run_job())
    loop.run_forever()
    loop.close()


def run_scraper_job():
    """Run the enhanced Playwright scraper job - called by the scheduler"""
    logger.info(f"Starting scheduled scrape job at {datetime.now()}")
    # Use the enhanced Playwright scraper
    run_threaded(run_async_job, run_enhanced_playwright_scraper)


def run_db_dump_job():
    """Run the database dump job - called by the scheduler"""
    logger.info(f"Starting scheduled database dump job at {datetime.now()}")
    success = create_db_dump()
    if success:
        logger.info("Database dump completed successfully")
    else:
        logger.error("Database dump failed")


def start_scheduler():
    """Initialize and start the scheduler"""
    logger.info(f"Starting scheduler with AUTO_START_SCRAPING={settings.AUTO_START_SCRAPING}")
    
    try:
        # Schedule the scraper job
        schedule.every().day.at(settings.SCRAPE_TIME).do(run_scraper_job)
        logger.info(f"Scheduled scraper job to run daily at {settings.SCRAPE_TIME}")
        
        # Schedule the database dump job
        schedule.every().day.at(settings.DUMP_TIME).do(run_db_dump_job)
        logger.info(f"Scheduled database dump job to run daily at {settings.DUMP_TIME}")
        
        # Check if we should run the scraper immediately
        if settings.AUTO_START_SCRAPING:
            logger.info("AUTO_START_SCRAPING is enabled, running scraper immediately")
            run_scraper_job()
        else:
            logger.info("AUTO_START_SCRAPING is disabled, scraper will only run as scheduled")
        
        # Run the scheduler in a loop
        while True:
            schedule.run_pending()
            time.sleep(1)
    except Exception as e:
        logger.error(f"Error in scheduler: {e}")
        # Do not run the scraper as fallback, respect the AUTO_START_SCRAPING setting
        logger.info("Scheduler encountered an error, will not run scraper as fallback") 