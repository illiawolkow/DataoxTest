#!/usr/bin/env python
"""
Entry point for running the AutoRia Scraper application directly
"""
import uvicorn
import os
from pathlib import Path
import sys

# Make sure we're in the right directory
APP_DIR = Path(__file__).parent
os.chdir(APP_DIR)

# Add the current directory to path to ensure imports work
sys.path.insert(0, str(APP_DIR))

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=True
    ) 