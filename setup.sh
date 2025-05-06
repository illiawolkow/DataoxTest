#!/bin/bash

# Create necessary directories
mkdir -p dumps debug tests/scraper tests/api

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    cat > .env << EOF
# Database settings
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/autoria
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=autoria

# Application settings
AUTO_RIA_START_URL=https://auto.ria.com/uk/car/used/
SCRAPE_TIME=12:00
DUMP_TIME=12:30

# Scraping settings
REQUEST_DELAY=1.5
MAX_CONCURRENT_REQUESTS=5
MAX_PAGES=100
TEST_MODE=False

# Ticket limits
MAX_TICKETS_PER_RUN=50

# Proxy settings
USE_PROXIES=False
# Format: ["http://proxy1.example.com:8080", "http://proxy2.example.com:8080"]
PROXY_LIST=[]
PROXY_USERNAME=
PROXY_PASSWORD=
EOF
    echo ".env file created"
else
    echo ".env file already exists"
fi

# Make script executable
chmod +x setup.sh

echo "Setup completed!" 