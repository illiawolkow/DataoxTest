"""
Setup script for Playwright browsers
Run this after installing the package to download and install browsers
"""
import subprocess
import sys
import os

def install_playwright_browsers():
    """Install Playwright browsers"""
    print("Installing Playwright browsers (Chromium)...")
    try:
        # Run the Playwright install command
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        print("Playwright browsers installed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error installing Playwright browsers: {e}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False

if __name__ == "__main__":
    # Ensure the debug directory exists
    debug_dir = "debug"
    os.makedirs(debug_dir, exist_ok=True)
    
    # Install Playwright browsers
    success = install_playwright_browsers()
    
    if success:
        print("\nSetup completed successfully!")
        print("\nYou can now run the scraper with:")
        print("  - Run the API server: python run.py")
        print("  - Test the scraper with the /api/scrape/test-playwright endpoint")
        print("  - Start a full scrape with the /api/scrape/start-playwright endpoint")
    else:
        print("\nSetup failed. Please check the error messages above and try again.") 