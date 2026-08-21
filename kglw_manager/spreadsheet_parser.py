"""Parser for the gizzard_shows.html spreadsheet to extract video links."""

import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup
from .utils import setup_logging
from .config import config

logger = setup_logging()


class SpreadsheetParser:
    """Parser for the gizzard_shows.html spreadsheet."""
    
    def __init__(self, spreadsheet_path: Optional[str] = None):
        # Use configured path or fallback to old default
        if spreadsheet_path is None:
            spreadsheet_path = config.get_spreadsheet_path()
        
        self.spreadsheet_path = Path(spreadsheet_path)
        self.shows_data = {}
        self.last_parsed = None
        
    def parse_spreadsheet(self) -> Dict[str, Dict[str, Any]]:
        """Parse the HTML spreadsheet and extract show data with video links."""
        if not self.spreadsheet_path.exists():
            logger.warning(f"Spreadsheet not found: {self.spreadsheet_path}")
            return {}
        
        logger.info(f"Parsing spreadsheet: {self.spreadsheet_path}")
        
        try:
            with open(self.spreadsheet_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Find all table rows
            rows = soup.find_all('tr')
            shows_data = {}
            
            for row in rows:
                show_data = self._parse_row(row)
                if show_data:
                    date_key = show_data['date']
                    shows_data[date_key] = show_data
            
            self.shows_data = shows_data
            self.last_parsed = datetime.now()
            
            logger.info(f"Parsed {len(shows_data)} shows from spreadsheet")
            return shows_data
            
        except Exception as e:
            logger.error(f"Error parsing spreadsheet: {e}")
            return {}
    
    def _parse_row(self, row) -> Optional[Dict[str, Any]]:
        """Parse a single table row to extract show information."""
        cells = row.find_all(['td', 'th'])
        if len(cells) < 6:  # Need at least date, location, country, venue columns
            return None
        
        try:
            # Extract date (first cell, format: DD-MMM-YYYY)
            date_text = cells[0].get_text(strip=True)
            if not date_text or not self._is_valid_date(date_text):
                return None
                
            # Convert date format from DD-MMM-YYYY to YYYY-MM-DD
            parsed_date = self._convert_date_format(date_text)
            if not parsed_date:
                return None
            
            # Extract location and venue info
            location = cells[2].get_text(strip=True) if len(cells) > 2 else ""
            country = cells[3].get_text(strip=True) if len(cells) > 3 else ""
            venue = cells[4].get_text(strip=True) if len(cells) > 4 else ""
            if len(cells) > 5:
                venue2 = cells[5].get_text(strip=True)
                if venue2 and venue2 not in venue:
                    venue = f"{venue} {venue2}".strip()
            
            # Extract YouTube links from remaining cells
            youtube_links = []
            for cell in cells[6:]:  # Skip date, location, country, venue columns
                links = cell.find_all('a', href=True)
                for link in links:
                    href = link['href']
                    if 'youtube.com' in href or 'youtu.be' in href:
                        youtube_links.append({
                            'url': href,
                            'text': link.get_text(strip=True)
                        })
            
            if not youtube_links:
                return None  # No YouTube links found
            
            # Clean up location data
            clean_location = self._clean_location(location, country)
            
            return {
                'date': parsed_date,
                'original_date': date_text,
                'location': clean_location,
                'venue': venue,
                'country': country,
                'youtube_links': youtube_links,
                'source': 'spreadsheet'
            }
            
        except Exception as e:
            logger.debug(f"Error parsing row: {e}")
            return None
    
    def _is_valid_date(self, date_text: str) -> bool:
        """Check if text looks like a date."""
        # Match formats like "19-Nov-2024" or "1-Jan-2025"
        date_pattern = r'^\d{1,2}-[A-Za-z]{3}-\d{4}$'
        return bool(re.match(date_pattern, date_text))
    
    def _convert_date_format(self, date_text: str) -> Optional[str]:
        """Convert DD-MMM-YYYY to YYYY-MM-DD format."""
        try:
            # Parse the date
            parsed = datetime.strptime(date_text, '%d-%b-%Y')
            return parsed.strftime('%Y-%m-%d')
        except ValueError:
            logger.debug(f"Could not parse date: {date_text}")
            return None
    
    def _clean_location(self, location: str, country: str) -> str:
        """Clean up location string for better matching."""
        if not location:
            return ""
        
        # Remove country suffix if already included
        if country.lower() in location.lower():
            return location
        
        # Add country suffix for US shows for consistency
        if country.upper() == "USA" and "USA" not in location:
            # Extract state if present (e.g., "Atlanta, GA" -> "Atlanta GA")
            location_clean = location.replace(',', '')
            return f"{location_clean} (USA)"
        
        return location
    
    def get_show_by_date(self, date: str) -> Optional[Dict[str, Any]]:
        """Get show data for a specific date."""
        if not self.shows_data:
            self.parse_spreadsheet()
        
        return self.shows_data.get(date)
    
    def search_shows_by_location(self, location: str) -> List[Dict[str, Any]]:
        """Search for shows by location."""
        if not self.shows_data:
            self.parse_spreadsheet()
        
        matches = []
        location_lower = location.lower()
        
        for show_data in self.shows_data.values():
            show_location = show_data['location'].lower()
            if location_lower in show_location or show_location in location_lower:
                matches.append(show_data)
        
        return matches
    
    def get_all_shows(self) -> Dict[str, Dict[str, Any]]:
        """Get all parsed show data."""
        if not self.shows_data:
            self.parse_spreadsheet()
        
        return self.shows_data
    
    def get_youtube_links_for_date(self, date: str) -> List[Dict[str, Any]]:
        """Get YouTube links for a specific date."""
        show = self.get_show_by_date(date)
        if show:
            return show.get('youtube_links', [])
        return []
    
    def get_stats(self) -> Dict[str, int]:
        """Get statistics about the parsed data."""
        if not self.shows_data:
            self.parse_spreadsheet()
        
        total_shows = len(self.shows_data)
        total_links = sum(len(show.get('youtube_links', [])) for show in self.shows_data.values())
        
        # Count shows by year
        years = {}
        for show in self.shows_data.values():
            year = show['date'][:4]
            years[year] = years.get(year, 0) + 1
        
        return {
            'total_shows': total_shows,
            'total_youtube_links': total_links,
            'years': years,
            'latest_show': max(self.shows_data.keys()) if self.shows_data else None
        }