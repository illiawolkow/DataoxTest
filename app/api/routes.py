from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional, Dict, Any
import os
import platform
from datetime import datetime
from pydantic import BaseModel

from app.db.database import get_db, create_db_dump, ensure_dumps_directory_exists
from app.db.models import Car
from app.scraper.enhanced_playwright_scraper import run_enhanced_playwright_scraper, process_mock_data
from app.config import logger, settings


class ProxySettings(BaseModel):
    use_proxies: bool = False
    proxy_list: List[str] = []
    proxy_username: Optional[str] = None
    proxy_password: Optional[str] = None


class ScraperSettings(BaseModel):
    max_tickets: int = 50


class MockDataPaths(BaseModel):
    listing_file_path: str
    detail_file_path: str


router = APIRouter()


@router.get("/cars", response_model=List[dict])
async def get_cars(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Get paginated car listings"""
    offset = (page - 1) * limit
    
    # Get the total count
    count_query = select(func.count()).select_from(Car)
    count_result = await db.execute(count_query)
    total_count = count_result.scalar()
    
    # Get the cars for the current page
    cars_query = select(Car).order_by(Car.datetime_found.desc()).offset(offset).limit(limit)
    cars_result = await db.execute(cars_query)
    cars = [
        {
            "id": car.id,
            "url": car.url,
            "title": car.title,
            "price_usd": car.price_usd,
            "odometer": car.odometer,
            "username": car.username,
            "phone_number": car.phone_number,
            "image_url": car.image_url,
            "images_count": car.images_count,
            "car_number": car.car_number,
            "car_vin": car.car_vin,
            "datetime_found": car.datetime_found
        }
        for car in cars_result.scalars().all()
    ]
    
    return cars


@router.post("/scrape/start-playwright")
async def start_enhanced_playwright_scraper_endpoint(
    background_tasks: BackgroundTasks,
    settings_update: Optional[ScraperSettings] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Manually start a scraping job using enhanced Playwright browser automation
    
    Optionally update max tickets to scrape per run
    """
    try:
        # Update settings if provided
        if settings_update:
            settings.MAX_TICKETS_PER_RUN = settings_update.max_tickets
            logger.info(f"Updated max tickets per run to: {settings.MAX_TICKETS_PER_RUN}")
        
        # Run the enhanced Playwright scraper in the background
        background_tasks.add_task(run_enhanced_playwright_scraper, db)
        return {
            "status": "Scraping started in the background using enhanced Playwright scraper",
            "max_tickets": settings.MAX_TICKETS_PER_RUN
        }
    except Exception as e:
        logger.error(f"Error starting enhanced Playwright scraper: {e}")
        raise HTTPException(status_code=500, detail="Could not start enhanced Playwright scraper")


@router.post("/scrape/config/proxies")
async def update_proxy_settings(proxy_settings: ProxySettings):
    """
    Update proxy settings for the scraper
    
    Note: This is only effective when not running in Docker
    
    Args:
        proxy_settings: New proxy configuration
    """
    try:
        settings.USE_PROXIES = proxy_settings.use_proxies
        settings.PROXY_LIST = proxy_settings.proxy_list
        settings.PROXY_USERNAME = proxy_settings.proxy_username
        settings.PROXY_PASSWORD = proxy_settings.proxy_password
        
        # Log a warning if we're likely in Docker
        if os.environ.get("PYTHONPATH") == "/app":
            logger.warning("Updating proxy settings in Docker environment may not be effective")
        
        return {
            "success": True,
            "message": "Proxy settings updated successfully (Note: not effective in Docker)",
            "settings": {
                "use_proxies": settings.USE_PROXIES,
                "proxy_count": len(settings.PROXY_LIST),
                "has_credentials": bool(settings.PROXY_USERNAME and settings.PROXY_PASSWORD),
                "in_docker": os.environ.get("PYTHONPATH") == "/app"
            }
        }
    except Exception as e:
        logger.error(f"Error updating proxy settings: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update proxy settings: {str(e)}")


@router.post("/database/dump")
async def create_dump():
    """Manually create a database dump"""
    try:
        # Ensure dumps directory exists
        try:
            ensure_dumps_directory_exists()
        except OSError as e:
            logger.error(f"Failed to ensure dumps directory: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        
        # Check if running on Windows
        is_windows = platform.system() == "Windows"
        if is_windows:
            # On Windows, use the async CSV dump method
            from app.db.database import create_csv_dump
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            success = await create_csv_dump(timestamp)
        else:
            # On Linux/Mac, use the regular pg_dump method
            success = create_db_dump()
            
        if success:
            return {"status": "Database dump created successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to create database dump")
    except Exception as e:
        logger.error(f"Error in create_dump endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create database dump: {str(e)}")


@router.get("/dumps")
def list_dumps():
    """List all available database dumps"""
    try:
        dumps_dir = "dumps"
        
        # Check if dumps directory exists
        if not os.path.exists(dumps_dir):
            return []
            
        dump_files = []
        for file in os.listdir(dumps_dir):
            if file.endswith(".sql") or file.endswith(".zip"):
                file_path = os.path.join(dumps_dir, file)
                file_stats = os.stat(file_path)
                dump_files.append({
                    "filename": file,
                    "size_bytes": file_stats.st_size,
                    "created_at": datetime.fromtimestamp(file_stats.st_ctime).isoformat()
                })
                
        return sorted(dump_files, key=lambda x: x["created_at"], reverse=True)
    except Exception as e:
        logger.error(f"Error listing dumps: {e}")
        raise HTTPException(status_code=500, detail="Could not list database dumps")


@router.get("/config")
async def get_scraper_config() -> Dict[str, Any]:
    """Get current scraper configuration"""
    return {
        "max_tickets_per_run": settings.MAX_TICKETS_PER_RUN,
        "use_proxies": settings.USE_PROXIES,
        "proxy_list_count": len(settings.PROXY_LIST),
        "has_proxy_credentials": bool(settings.PROXY_USERNAME and settings.PROXY_PASSWORD),
        "max_pages": settings.MAX_PAGES,
        "request_delay": settings.REQUEST_DELAY,
        "auto_start_scraping": settings.AUTO_START_SCRAPING,
        "create_dirs_automatically": settings.CREATE_DIRS_AUTOMATICALLY
    }


@router.post("/config/max-tickets")
async def update_max_tickets(max_tickets: int = Query(..., ge=1, le=500)):
    """Update the maximum number of tickets to process per scraping run"""
    try:
        settings.MAX_TICKETS_PER_RUN = max_tickets
        return {
            "success": True,
            "message": f"Maximum tickets per run updated to {max_tickets}"
        }
    except Exception as e:
        logger.error(f"Error updating max tickets: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update max tickets: {str(e)}")


@router.post("/scrape/process-mock-data")
async def process_mock_data_endpoint(
    listing_file_path: Optional[str] = "mock_data/listing_page.html",
    detail_file_path: Optional[str] = "mock_data/car_page.html",
    db: AsyncSession = Depends(get_db)
):
    """Process mock HTML data for testing"""
    try:
        # Check if mock files exist
        if not os.path.exists(listing_file_path):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": f"Listing file '{listing_file_path}' not found"
                }
            )
            
        if detail_file_path and not os.path.exists(detail_file_path):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": f"Detail file '{detail_file_path}' not found"
                }
            )
        
        # Run the mock data processing function
        result = await process_mock_data(
            listing_file_path=listing_file_path,
            detail_file_path=detail_file_path,
            db_session=db
        )
        
        if not result.get("success", False):
            return JSONResponse(
                status_code=400,
                content=result
            )
        
        return result
    except Exception as e:
        logger.error(f"Error processing mock data: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing mock data: {str(e)}") 