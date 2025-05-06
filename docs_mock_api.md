# Mock Data API Documentation

This document describes the API endpoints for working with mock data in the AutoRia scraper project.

## Overview

The mock data API allows you to process mock HTML files to extract car information.

**Important Note**: The mock data directory (`mock_data/`) at the project root must be created manually before using these endpoints. You'll also need to place your HTML files manually in this directory.

## Endpoints

### Process Mock Data

**Endpoint:** `POST /api/scrape/process-mock-data`

**Description:** Process HTML files to extract car information and save to database.

**Prerequisites:**
- The mock HTML files should already exist in the `mock_data/` directory
- The directory must be created manually before using this endpoint
- You must manually place the HTML files in the directory

**Request:**
- Content-Type: `application/json`
- Body (all parameters optional):
```json
{
  "listing_file_path": "mock_data/listing_page.html",
  "detail_file_path": "mock_data/car_page.html"
}
```

**Response:**
```json
{
  "success": true,
  "car_links_found": 20,
  "car_items_processed": 40,
  "total_cars_extracted": 41,
  "detail_page_processed": true,
  "cars_saved_to_database": 41,
  "sample_data": [
    {
      "url": "https://auto.ria.com/uk/auto_example_123.html",
      "title": "Example Car 2022",
      "price_usd": 15999.0,
      "odometer": 50000,
      "username": "Seller Name",
      "phone_number": "+380999900000",
      "image_url": "https://example.com/image.jpg",
      "images_count": 25,
      "car_number": "AA0000AA",
      "car_vin": "WBAAA1111AAA00000",
      "location": "Kyiv"
    }
  ],
  "processing_time": "0.65 seconds",
  "file_paths": {
    "listing": "mock_data/listing_page.html",
    "detail": "mock_data/car_page.html"
  }
}
```

## Using with cURL

### Process Mock Data
```bash
curl -X POST "http://localhost:8000/api/scrape/process-mock-data" \
  -H "Content-Type: application/json" \
  -d '{
  "listing_file_path": "mock_data/listing_page.html",
  "detail_file_path": "mock_data/car_page.html"
}'
```

## Directory Setup

Before using the mock data API, you need to manually create the `mock_data` directory at the root of your project and place your HTML files inside:

```bash
# On Linux/Mac
mkdir -p mock_data
cp /path/to/your/listing_page.html mock_data/
cp /path/to/your/car_page.html mock_data/

# On Windows
mkdir mock_data
copy path\to\your\listing_page.html mock_data\
copy path\to\your\car_page.html mock_data\
```

## Use Cases

These endpoints are useful for:
- Testing the scraper with predefined HTML
- Debugging parser issues
- Developing new parser features without hitting the real AutoRia site
- Running tests without external dependencies

## HTML File Format Requirements

### Listing File
The listing HTML file should contain the car listings page from AutoRia with multiple car elements.
Each car element should have a link that points to a detail page.

### Detail File
The detail HTML file should contain the detailed information for a single car.
This should include elements for car title, price, odometer, seller information, etc.

## Sample HTML Files

You can obtain sample HTML files by:
1. Running the test endpoint: `GET /api/scrape/test-playwright`
2. Check the debug directory for saved HTML files
3. Modify these files for testing different scenarios

## Errors and Troubleshooting

If the endpoint returns an error, check:
1. File paths are correct and accessible by the server
2. The `mock_data` directory exists at the project root
3. HTML files contain valid HTML from AutoRia pages
4. The detail page contains all required car information
5. Files use UTF-8 encoding 