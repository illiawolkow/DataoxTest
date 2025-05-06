from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import text, MetaData, Table
import os
import asyncio
import subprocess
import platform
import json
import csv
from datetime import datetime
import sys
import socket
from pathlib import Path

from app.config import settings, logger
from app.db.models import Base

# Determine if we need to modify the database connection based on environment
def get_connection_url() -> str:
    """
    Get the appropriate database connection URL based on environment
    
    Returns:
        Modified DATABASE_URL if needed
    """
    db_url = settings.DATABASE_URL
    
    # Extract host from connection URL
    try:
        db_url_parts = db_url.split('@')
        if len(db_url_parts) > 1:
            auth_part = db_url_parts[0]
            conn_part = db_url_parts[1]
            
            # Extract hostname
            host_part = conn_part.split(':')[0]
            
            # Check if the hostname is 'db' (Docker service name)
            if host_part == 'db':
                # Try to check if 'db' is resolvable
                try:
                    socket.gethostbyname('db')
                    logger.info("Successfully resolved hostname 'db'")
                except socket.gaierror:
                    # If 'db' is not resolvable, replace with localhost
                    logger.warning("Could not resolve hostname 'db', falling back to 'localhost'")
                    db_url = db_url.replace('@db:', '@localhost:')
    except Exception as e:
        logger.warning(f"Error parsing DATABASE_URL: {e}, using original URL")
    
    return db_url

# Get the appropriate database URL
db_url = get_connection_url()
logger.info(f"Using database connection URL (host part): {db_url.split('@')[1] if '@' in db_url else db_url}")

# Create async engine
engine = create_async_engine(
    db_url,
    echo=False,
    poolclass=NullPool,
)

# Create async session factory
async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    """Dependency for getting async DB session"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized")


async def check_db_connection():
    """Check database connection"""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        
        # Try to give a more helpful error message based on the error
        error_str = str(e).lower()
        if "could not translate host name" in error_str or "could not connect to server" in error_str:
            if "db:" in settings.DATABASE_URL:
                logger.error("The hostname 'db' could not be resolved. If you're not using Docker, "
                             "try changing the host in DATABASE_URL to 'localhost'")
        
        return False


def ensure_dumps_directory_exists() -> str:
    """
    Ensure the dumps directory exists
    
    Returns:
        Path to the dumps directory
    
    Raises:
        OSError: If CREATE_DIRS_AUTOMATICALLY is False and dumps directory does not exist
    """
    # Define the dumps directory path
    dumps_dir = "dumps"
    
    # Check if dumps directory exists
    if not os.path.exists(dumps_dir):
        if settings.CREATE_DIRS_AUTOMATICALLY:
            try:
                os.makedirs(dumps_dir)
                logger.info(f"Created dumps directory: {dumps_dir}")
            except Exception as e:
                logger.error(f"Failed to create dumps directory: {e}")
                raise
        else:
            logger.error(f"Dumps directory '{dumps_dir}' does not exist and CREATE_DIRS_AUTOMATICALLY is set to False")
            raise OSError(f"Directory '{dumps_dir}' does not exist and automatic directory creation is disabled")
    
    return dumps_dir


def create_db_dump():
    """Create a database dump"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    try:
        # Ensure the dumps directory exists
        dumps_dir = ensure_dumps_directory_exists()
        
        # Determine the system and choose the appropriate dump method
        is_windows = platform.system() == "Windows"
        
        # For Windows, use a simple CSV export instead of pg_dump
        if is_windows:
            try:
                return create_csv_dump(timestamp)
            except Exception as e:
                logger.error(f"Failed to create CSV dump: {e}")
                return False
        else:
            # For Linux/Mac, try pg_dump first
            try:
                return create_pg_dump(timestamp)
            except Exception as e:
                logger.warning(f"pg_dump failed: {e}, falling back to CSV dump")
                try:
                    return create_csv_dump(timestamp)
                except Exception as csv_error:
                    logger.error(f"Failed to create CSV dump: {csv_error}")
                    return False
    except OSError as e:
        logger.error(f"Error accessing dumps directory: {e}")
        return False


def create_pg_dump(timestamp):
    """Create a PostgreSQL dump using pg_dump"""
    dump_file = f"dumps/autoria_dump_{timestamp}.sql"
    
    try:
        # Parse the database URL to extract host, user, and database
        db_url = settings.DATABASE_URL
        
        # Extract host from DATABASE_URL
        try:
            if '@' in db_url:
                host_part = db_url.split('@')[1].split(':')[0]
            else:
                host_part = "localhost"
        except Exception:
            logger.warning("Could not extract host from DATABASE_URL, using 'localhost'")
            host_part = "localhost"
            
        # Create the dump using pg_dump
        subprocess.run([
            "pg_dump",
            "-h", host_part,
            "-U", settings.POSTGRES_USER,
            "-d", settings.POSTGRES_DB,
            "-f", dump_file
        ], env={**os.environ, "PGPASSWORD": settings.POSTGRES_PASSWORD}, check=True)
        
        logger.info(f"Database dump created: {dump_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to create PostgreSQL dump: {e}")
        raise


async def create_csv_dump(timestamp):
    """Create a simple CSV dump of the database tables"""
    try:
        # Ensure dumps root directory exists
        dumps_dir = ensure_dumps_directory_exists()
        
        # Create directory for this specific dump
        dump_dir = f"{dumps_dir}/dump_{timestamp}"
        
        if settings.CREATE_DIRS_AUTOMATICALLY:
            os.makedirs(dump_dir, exist_ok=True)
        elif not os.path.exists(dump_dir):
            try:
                os.makedirs(dump_dir)
            except Exception as e:
                logger.error(f"Failed to create dump directory '{dump_dir}': {e}")
                return False
        
        # Create info file with timestamp and metadata
        info_file = os.path.join(dump_dir, "info.json")
        with open(info_file, 'w') as f:
            json.dump({
                "timestamp": timestamp,
                "database": settings.POSTGRES_DB,
                "created_at": datetime.now().isoformat(),
                "platform": platform.platform(),
                "python_version": sys.version
            }, f, indent=2)
        
        # Dump each table to CSV
        async with engine.begin() as conn:
            # First, get a list of all tables
            result = await conn.execute(text("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public'
            """))
            tables = [row[0] for row in result.fetchall()]
            
            for table_name in tables:
                # Get all data from the table
                result = await conn.execute(text(f"SELECT * FROM {table_name}"))
                rows = result.fetchall()
                
                if not rows:
                    logger.info(f"Table {table_name} is empty, skipping")
                    continue
                
                # Get column names
                columns = result.keys()
                
                # Write to CSV
                csv_file = os.path.join(dump_dir, f"{table_name}.csv")
                with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(columns)  # Write header
                    for row in rows:
                        writer.writerow(row)
                
                logger.info(f"Exported {len(rows)} rows from table {table_name} to {csv_file}")
        
        # Create a zip file of the dump
        zip_file = f"{dumps_dir}/autoria_dump_{timestamp}.zip"
        import shutil
        shutil.make_archive(zip_file.replace('.zip', ''), 'zip', dump_dir)
        
        logger.info(f"Database dump created as CSV files in {zip_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to create CSV dump: {e}")
        raise 