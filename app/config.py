from pydantic_settings import BaseSettings, SettingsConfigDict
import logging
import os
from typing import Optional, List
from pathlib import Path
from dotenv import load_dotenv, find_dotenv


# Configure logging first to capture startup information
LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = Path("app.log")

logging.basicConfig(
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ]
)

logger = logging.getLogger("autoria-scraper")

# Load the .env file explicitly
dotenv_path = find_dotenv()
if dotenv_path:
    logger.info(f"Found .env file at {dotenv_path}")
    load_dotenv(dotenv_path)
    logger.info("Successfully loaded environment variables from .env file")
else:
    logger.warning("No .env file found, will use environment variables if available")


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file"""
    
    # Database settings
    DATABASE_URL: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    
    # Application settings
    AUTO_RIA_START_URL: str
    SCRAPE_TIME: str
    DUMP_TIME: str
    
    # Scraping settings
    REQUEST_DELAY: float
    MAX_CONCURRENT_REQUESTS: int
    MAX_PAGES: int  # Safety limit for number of pages to scrape
    TEST_MODE: bool = False  # Set to True for testing with limited scraping
    
    # Control flags
    AUTO_START_SCRAPING: bool = False  # Set to False to prevent automatic scraping on startup
    CREATE_DIRS_AUTOMATICALLY: bool = False  # Whether to automatically create missing directories
    
    # Proxy settings
    USE_PROXIES: bool = False
    PROXY_LIST: List[str] = []
    PROXY_USERNAME: Optional[str] = None
    PROXY_PASSWORD: Optional[str] = None
    
    # Ticket limits
    MAX_TICKETS_PER_RUN: int  # Maximum number of tickets to process per scraping run
    
    # Configure settings behavior
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Initialize settings
try:
    settings = Settings()
    
    # Log database settings (with masked password)
    db_url = settings.DATABASE_URL
    masked_url = db_url
    if "@" in db_url:
        # Safely mask the password in the URL for logging
        parts = db_url.split("@")
        if ":" in parts[0]:
            # Format is typically protocol://user:password@host:port/db
            protocol_user_pass = parts[0].split(":")
            if len(protocol_user_pass) >= 3:
                # Handle protocol://user:password format
                password_part = protocol_user_pass[-1]
                masked_part = protocol_user_pass[:-1]
                masked_part.append("*" * len(password_part))
                masked_url = ":".join(masked_part) + "@" + parts[1]
    
    logger.info(f"Database URL: {masked_url}")
    logger.info(f"Database User: {settings.POSTGRES_USER}")
    logger.info(f"Database Name: {settings.POSTGRES_DB}")
    
    # Log other important settings
    logger.info(f"Starting URL: {settings.AUTO_RIA_START_URL}")
    logger.info(f"Scrape Schedule: {settings.SCRAPE_TIME}")
    logger.info(f"Dump Schedule: {settings.DUMP_TIME}")
    logger.info(f"Request Delay: {settings.REQUEST_DELAY}")
    logger.info(f"Max Concurrent Requests: {settings.MAX_CONCURRENT_REQUESTS}")
    logger.info(f"Max Pages: {settings.MAX_PAGES}")
    logger.info(f"Max Tickets Per Run: {settings.MAX_TICKETS_PER_RUN}")
    logger.info(f"Auto Start Scraping: {settings.AUTO_START_SCRAPING}")
    logger.info(f"Create Dirs Automatically: {settings.CREATE_DIRS_AUTOMATICALLY}")
except Exception as e:
    logger.error(f"Error loading settings: {e}")
    raise 