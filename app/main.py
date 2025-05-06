import asyncio
import uvicorn
import threading
import os
import sys
import platform
from pathlib import Path
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.config import settings, logger
from app.db.database import init_db, check_db_connection
from app.scheduler import start_scheduler
from app.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown events handler
    """
    # Startup
    logger.info("Application startup")
    
    # Log system information
    logger.info(f"Platform: {platform.platform()}")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"Path separator: {os.path.sep}")
    
    # Log important configuration settings
    logger.info(f"AutoRia Starting URL: {settings.AUTO_RIA_START_URL}")
    logger.info(f"Max Tickets Per Run: {settings.MAX_TICKETS_PER_RUN}")
    logger.info(f"Request Delay: {settings.REQUEST_DELAY} seconds")
    logger.info(f"Max Pages: {settings.MAX_PAGES}")
    logger.info(f"Auto Start Scraping: {settings.AUTO_START_SCRAPING}")
    logger.info(f"Create Dirs Automatically: {settings.CREATE_DIRS_AUTOMATICALLY}")
    
    # Initialize database
    db_connected = await check_db_connection()
    if db_connected:
        await init_db()
    else:
        logger.error("Failed to connect to database, check your settings")
    
    # Start scheduler in a separate thread
    scheduler_thread = threading.Thread(target=start_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    logger.info("Scheduler started in background thread")
    
    yield
    
    # Shutdown
    logger.info("Application shutdown")


# Create FastAPI application
app = FastAPI(
    title="AutoRia Scraper API",
    description="API for scraping and accessing AutoRia used car data",
    version="1.0.0",
    lifespan=lifespan
)

# Include API routes
app.include_router(router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint - health check"""
    return {
        "status": "ok", 
        "message": "AutoRia Scraper API is running",
        "cwd": os.getcwd(),
        "platform": platform.platform(),
        "auto_start_scraping": settings.AUTO_START_SCRAPING,
        "create_dirs_automatically": settings.CREATE_DIRS_AUTOMATICALLY
    }


# Run the application directly when script is executed
if __name__ == "__main__":
    try:
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=8000,
            reload=False
        )
    except Exception as e:
        logger.error(f"Error starting the application: {e}")
        raise 