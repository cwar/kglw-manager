"""Download and extract Google Sheets HTML export with preserved hyperlinks."""

import requests
import zipfile
import io
import json
import re
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from .utils import setup_logging

logger = setup_logging()


class SpreadsheetDownloader:
    """Handle downloading and extracting Google Sheets HTML exports with preserved links."""
    
    # Google Sheets URL and identifiers
    SPREADSHEET_ID = "1D5YoZkFG29Ldbi8M2XvfXY3ipmb6ydnAyeQoMK0wIZQ"
    SHEET_NAME = "King Gizzard Live Shows"
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize downloader with cache directory."""
        self.cache_dir = cache_dir or (Path.home() / '.kglw_manager' / 'spreadsheet_cache')
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
    def download_html_export(self, output_dir: Optional[Path] = None) -> Optional[Path]:
        """
        Download Google Sheets HTML export with preserved hyperlinks.
        
        Approach 1: Direct HTML Export URL (might require authentication)
        """
        try:
            # This URL format exports as HTML zip
            export_url = f"https://docs.google.com/spreadsheets/d/{self.SPREADSHEET_ID}/export?format=zip"
            
            logger.info("Attempting to download HTML export from Google Sheets...")
            
            # Try with standard headers to appear like a browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            response = requests.get(export_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                # Save and extract the zip file
                output_dir = output_dir or self.cache_dir
                output_dir.mkdir(parents=True, exist_ok=True)
                
                # Save the zip temporarily
                zip_path = output_dir / 'spreadsheet_export.zip'
                with open(zip_path, 'wb') as f:
                    f.write(response.content)
                
                # Extract the HTML file
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    # List contents
                    file_list = zip_ref.namelist()
                    logger.info(f"Zip contains: {file_list}")
                    
                    # Extract all files
                    zip_ref.extractall(output_dir)
                    
                    # Find the main HTML file (usually Sheet1.html or similar)
                    html_files = [f for f in file_list if f.endswith('.html')]
                    if html_files:
                        html_path = output_dir / html_files[0]
                        logger.info(f"Successfully downloaded and extracted: {html_path}")
                        
                        # Clean up the zip file
                        zip_path.unlink()
                        
                        return html_path
                    else:
                        logger.error("No HTML file found in the export")
                        return None
                        
            else:
                logger.error(f"Failed to download (status {response.status_code})")
                # If direct download fails, try alternative methods
                return self._try_alternative_download_method(output_dir)
                
        except Exception as e:
            logger.error(f"Error downloading HTML export: {e}")
            return self._try_alternative_download_method(output_dir)
    
    def _try_alternative_download_method(self, output_dir: Optional[Path] = None) -> Optional[Path]:
        """
        Alternative method: Try published web view URL.
        This won't give us a zip but might give us parseable HTML.
        """
        try:
            logger.info("Trying alternative download method (published view)...")
            
            # Try the published web view URL
            published_url = f"https://docs.google.com/spreadsheets/d/{self.SPREADSHEET_ID}/pubhtml"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(published_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                output_dir = output_dir or self.cache_dir
                output_dir.mkdir(parents=True, exist_ok=True)
                
                html_path = output_dir / 'Sheet1.html'
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(response.text)
                
                logger.info(f"Downloaded published HTML to: {html_path}")
                return html_path
            else:
                logger.error(f"Alternative method failed (status {response.status_code})")
                return None
                
        except Exception as e:
            logger.error(f"Alternative download method failed: {e}")
            return None
    
    def download_with_selenium(self, output_dir: Optional[Path] = None) -> Optional[Path]:
        """
        Approach 3: Use Selenium to automate the browser download.
        This requires selenium and a browser driver to be installed.
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.chrome.options import Options
            
            logger.info("Attempting download using Selenium automation...")
            
            # Setup Chrome options
            chrome_options = Options()
            chrome_options.add_argument("--headless")  # Run in headless mode
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            
            # Set download directory
            output_dir = output_dir or self.cache_dir
            output_dir.mkdir(parents=True, exist_ok=True)
            
            prefs = {
                "download.default_directory": str(output_dir),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True
            }
            chrome_options.add_experimental_option("prefs", prefs)
            
            # Initialize driver
            driver = webdriver.Chrome(options=chrome_options)
            
            try:
                # Navigate to the spreadsheet
                spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{self.SPREADSHEET_ID}"
                driver.get(spreadsheet_url)
                
                # Wait for the spreadsheet to load
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "docs-sheet-tab"))
                )
                
                # Use keyboard shortcut to open File menu (Ctrl+Alt+Shift+F)
                # Then navigate to Download -> Web page (.html)
                # This is complex and might not work in headless mode
                
                logger.warning("Selenium automation requires manual interaction or advanced scripting")
                return None
                
            finally:
                driver.quit()
                
        except ImportError:
            logger.error("Selenium not installed. Install with: pip install selenium")
            return None
        except Exception as e:
            logger.error(f"Selenium automation failed: {e}")
            return None
    
    def manual_download_instructions(self) -> str:
        """
        Provide instructions for manual download as a fallback.
        """
        instructions = f"""
Manual Download Instructions for Google Sheets HTML Export:

1. Open the spreadsheet in your browser:
   https://docs.google.com/spreadsheets/d/{self.SPREADSHEET_ID}

2. Click File → Download → Web page (.html, zipped)

3. Save the downloaded ZIP file

4. Extract the ZIP file to get Sheet1.html

5. Use the following command to load it:
   ./kglw-manager.py spreadsheet load-file --file /path/to/Sheet1.html

The HTML file will preserve all YouTube hyperlinks that are lost in CSV exports.
        """
        return instructions
    
    def create_download_script(self, output_path: Optional[Path] = None) -> Path:
        """
        Create a shell script that can help automate the download process.
        """
        script_content = f'''#!/bin/bash
# Script to download King Gizzard Live Shows spreadsheet as HTML

SPREADSHEET_ID="{self.SPREADSHEET_ID}"
OUTPUT_DIR="${{1:-.}}"

echo "Downloading King Gizzard Live Shows spreadsheet..."

# Method 1: Try direct export (may fail due to auth)
echo "Trying direct download..."
curl -L -o "$OUTPUT_DIR/spreadsheet_export.zip" \\
  -H "User-Agent: Mozilla/5.0" \\
  "https://docs.google.com/spreadsheets/d/$SPREADSHEET_ID/export?format=zip"

if [ -f "$OUTPUT_DIR/spreadsheet_export.zip" ]; then
    echo "Download successful! Extracting..."
    unzip -o "$OUTPUT_DIR/spreadsheet_export.zip" -d "$OUTPUT_DIR"
    rm "$OUTPUT_DIR/spreadsheet_export.zip"
    echo "Extracted to $OUTPUT_DIR"
else
    echo "Direct download failed."
    echo ""
    echo "Please download manually:"
    echo "1. Open: https://docs.google.com/spreadsheets/d/$SPREADSHEET_ID"
    echo "2. Click File → Download → Web page (.html, zipped)"
    echo "3. Extract the ZIP to get Sheet1.html"
    echo "4. Run: ./kglw-manager.py spreadsheet load-file --file Sheet1.html"
fi
'''
        
        output_path = output_path or (self.cache_dir / 'download_spreadsheet.sh')
        output_path.write_text(script_content)
        output_path.chmod(0o755)  # Make executable
        
        logger.info(f"Created download script: {output_path}")
        return output_path
    
    def check_for_updates(self, current_html_path: Path) -> bool:
        """
        Check if the online spreadsheet has been updated since the local HTML was downloaded.
        """
        try:
            # Get the last modified time of local file
            local_modified = datetime.fromtimestamp(current_html_path.stat().st_mtime)
            
            # Try to get the last modified time from Google Sheets API or headers
            # This is approximate as Google Sheets doesn't always expose modification time
            url = f"https://docs.google.com/spreadsheets/d/{self.SPREADSHEET_ID}/pubhtml"
            response = requests.head(url, timeout=10)
            
            if 'last-modified' in response.headers:
                remote_modified = datetime.strptime(
                    response.headers['last-modified'],
                    '%a, %d %b %Y %H:%M:%S %Z'
                )
                
                if remote_modified > local_modified:
                    logger.info("Spreadsheet has been updated since last download")
                    return True
                else:
                    logger.info("Local HTML is up to date")
                    return False
            else:
                # Can't determine update status
                logger.debug("Cannot determine if spreadsheet was updated")
                return False
                
        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            return False