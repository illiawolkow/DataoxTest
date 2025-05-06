# AutoRia Scraper API

A FastAPI application for scraping and accessing used car listings from AutoRia.

## Features

- Scraping car listings from AutoRia using Playwright with advanced anti-detection features
- Storing scraped data in a PostgreSQL database
- REST API for accessing car data
- Scheduled scraping and database dumps
- Mock data processing for testing without accessing the real site
- Docker support for easy deployment

## Prerequisites

- Python 3.11+
- PostgreSQL 12+
- Playwright browser automation
- Docker and Docker Compose (recommended)

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/autoria-scraper.git
cd autoria-scraper
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up Playwright

```bash
python setup_playwright.py
```

### 5. Create a PostgreSQL database

```bash
createdb autoria
```

### 6. Create .env file

Create a `.env` file in the root directory with the following content:

```
# Database settings
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/autoria
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=autoria

# Application settings
AUTO_RIA_START_URL=https://auto.ria.com/uk/car/used/
SCRAPE_TIME=30 0 * * *  # Cron format: 00:30 every day
DUMP_TIME=0 1 * * *     # Cron format: 01:00 every day

# Scraping settings
REQUEST_DELAY=2.0
MAX_CONCURRENT_REQUESTS=2
MAX_PAGES=10
MAX_TICKETS_PER_RUN=50

# Control flags
AUTO_START_SCRAPING=false
CREATE_DIRS_AUTOMATICALLY=true
```

Adjust the settings according to your environment.

### 7. Create required directories

Create a `dumps` directory in the root of the project:

```bash
mkdir -p dumps
```

## Running the Application

### Using Python directly

```bash
python run.py
```

### Using Uvicorn

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Using Docker (Recommended)

```bash
docker-compose up -d
```

## Environment Variables

| Variable | Description | Format | Default |
|----------|-------------|--------|---------|
| DATABASE_URL | PostgreSQL connection string | - | - |
| POSTGRES_USER | PostgreSQL username | - | - |
| POSTGRES_PASSWORD | PostgreSQL password | - | - |
| POSTGRES_DB | PostgreSQL database name | - | - |
| AUTO_RIA_START_URL | Starting URL for scraping | - | - |
| SCRAPE_TIME | Time to run daily scraping | Cron format (e.g., `30 0 * * *`) | - |
| DUMP_TIME | Time to run daily database dump | Cron format (e.g., `0 1 * * *`) | - |
| REQUEST_DELAY | Delay between requests in seconds | Float | - |
| MAX_CONCURRENT_REQUESTS | Maximum number of concurrent requests | Integer | - |
| MAX_PAGES | Maximum number of pages to scrape | Integer | 10 |
| MAX_TICKETS_PER_RUN | Maximum number of listings to process per run | Integer | 50 |
| AUTO_START_SCRAPING | Whether to start scraping automatically on startup | Boolean | false |
| CREATE_DIRS_AUTOMATICALLY | Whether to create directories automatically | Boolean | true |
| USE_PROXIES | Whether to use proxies for scraping (not used in Docker) | Boolean | false |

## API Endpoints

### Car Listings

- `GET /api/cars` - Get paginated car listings
  - Query parameters: `page` (default: 1), `limit` (default: 10, max: 100)

### Scraping

- `POST /api/scrape/start-playwright` - Start a scraping job
- `POST /api/scrape/process-mock-data` - Process mock HTML data for testing without accessing the real site

### Database

- `POST /api/database/dump` - Create a database dump
- `GET /api/dumps` - List available database dumps

### Configuration

- `GET /api/config` - Get current scraper configuration
- `POST /api/config/max-tickets` - Update maximum tickets per run
- `POST /api/scrape/config/proxies` - Update proxy settings (only relevant when not using Docker)

## License

MIT 