"""Enhanced parser for King Gizzard live show spreadsheet with YouTube links."""

import csv
import re
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from bs4 import BeautifulSoup
from .utils import setup_logging

logger = setup_logging()


class GoogleSheetsParser:
    """Parser for the King Gizzard live show Google Sheets with YouTube links."""
    
    # Google Sheets URL for the live show database
    SPREADSHEET_ID = "1D5YoZkFG29Ldbi8M2XvfXY3ipmb6ydnAyeQoMK0wIZQ"
    GID = "0"
    
    def __init__(self, local_file_path: Optional[str] = None):
        self.local_file_path = Path(local_file_path) if local_file_path else None
        self.shows_data = {}
        self.last_parsed = None

    def ensure_loaded(self) -> Dict[str, Dict[str, Any]]:
        """Parse the configured export on first use.

        Constructing the parser does not read anything, so consumers that only
        looked at `shows_data` saw an empty dict and silently skipped every
        curated link.
        """
        if not self.shows_data and self.local_file_path and not self.last_parsed:
            try:
                self.parse_html_export()
            except Exception as e:
                logger.warning(f"Could not load spreadsheet: {e}")
                self.last_parsed = datetime.now()  # don't retry every call
        return self.shows_data

    def _get_csv_url(self) -> str:
        """Get the CSV export URL for the Google Sheet."""
        return f"https://docs.google.com/spreadsheets/d/{self.SPREADSHEET_ID}/export?format=csv&gid={self.GID}"
    
    def _get_html_url(self) -> str:
        """Get the HTML export URL for the Google Sheet (contains YouTube links)."""
        # Try different HTML export formats
        return f"https://docs.google.com/spreadsheets/d/{self.SPREADSHEET_ID}/gviz/tq?tqx=out:html&gid={self.GID}"
    
    def download_spreadsheet(self, format_type: str = "html", output_path: Optional[str] = None) -> bool:
        """Download the spreadsheet in specified format."""
        try:
            if format_type == "html":
                url = self._get_html_url()
                extension = ".html"
            else:
                url = self._get_csv_url()
                extension = ".csv"
            
            if not output_path:
                output_path = f"kglw_live_shows{extension}"
            
            logger.info(f"Downloading spreadsheet as {format_type} from Google Sheets...")
            
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(response.text)
            
            logger.info(f"Spreadsheet downloaded to: {output_path}")
            
            if format_type == "html":
                self.local_file_path = Path(output_path)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to download spreadsheet: {e}")
            return False
    
    def parse_html_export(self, html_path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Parse HTML export of the spreadsheet to extract YouTube links."""
        if html_path:
            file_path = Path(html_path)
        elif self.local_file_path:
            file_path = self.local_file_path
        else:
            logger.error("No HTML file path provided")
            return {}
        
        if not file_path.exists():
            logger.error(f"HTML file not found: {file_path}")
            return {}
        
        logger.info(f"Parsing HTML spreadsheet: {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Try traditional table parsing first (more accurate location data)
            shows_data = self._parse_traditional_table_format(html_content)
            
            if not shows_data:
                # Fall back to compressed format (less accurate but more coverage)
                shows_data = self._parse_google_sheets_format(html_content)
            
            self.shows_data = shows_data
            self.last_parsed = datetime.now()
            
            logger.info(f"Parsed {len(shows_data)} shows with YouTube links from HTML export")
            return shows_data
            
        except Exception as e:
            logger.error(f"Error parsing HTML spreadsheet: {e}")
            return {}
    
    def _parse_traditional_table_format(self, html_content: str) -> Dict[str, Dict[str, Any]]:
        """Parse traditional HTML table format."""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find the table
        table = soup.find('table')
        if not table:
            return {}
        
        # Find all table rows, skip header
        rows = table.find_all('tr')[1:]  # Skip header row
        shows_data = {}
        
        for row in rows:
            show_data = self._parse_html_row(row)
            if show_data and show_data.get('youtube_links'):
                date_key = show_data['date']
                existing = shows_data.get(date_key)
                if existing:
                    # Doubleheaders share a date - merge their links rather than
                    # letting the later row silently replace the earlier one.
                    known = {l['url'] for l in existing['youtube_links']}
                    existing['youtube_links'].extend(
                        l for l in show_data['youtube_links'] if l['url'] not in known
                    )
                else:
                    shows_data[date_key] = show_data

        return shows_data
    
    def _parse_google_sheets_format(self, html_content: str) -> Dict[str, Dict[str, Any]]:
        """Parse the compressed Google Sheets HTML format."""
        import re
        
        # Extract all YouTube URLs from the content
        youtube_pattern = r'https://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/playlist\?list=)[\w\-]+'
        youtube_urls = re.findall(youtube_pattern, html_content)
        
        if not youtube_urls:
            logger.warning("No YouTube URLs found in Google Sheets format")
            return {}
        
        # Extract table cell data - looking for patterns like >29-Oct-2010< or >Date<
        # This is a more complex parsing task since the HTML is compressed
        
        # Try to find date patterns in the HTML
        date_pattern = r'>(\d{1,2}-[A-Za-z]{3}-\d{4})<'
        dates = re.findall(date_pattern, html_content)
        
        # Try to find location patterns - look for location data after dates
        # Pattern to match: >date< followed by >1< then >location< 
        # Example: >31-May-2025</td><td>1</td><td>Vilnius</td>
        location_pattern = r'>\d{1,2}-[A-Za-z]{3}-\d{4}</td><td[^>]*>1</td><td[^>]*>([^<]+)<'
        locations = re.findall(location_pattern, html_content)
        
        # Fallback pattern: just look for city-like words after date cells
        if not locations:
            simple_location_pattern = r'>([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)<'
            potential_locations = re.findall(simple_location_pattern, html_content)
            # Filter out obvious non-locations
            locations = [loc for loc in potential_locations if len(loc) > 2 and loc not in ['Date', 'Sets', 'Link', 'Archive', 'Length', 'Sources', 'Notes']]
        
        logger.info(f"Found {len(youtube_urls)} YouTube URLs and {len(dates)} dates in compressed format")
        logger.debug(f"Found {len(locations)} locations: {locations[:10]}")  # Show first 10 locations found
        
        # For now, create a simplified mapping
        # This is a basic implementation - we could enhance it further
        shows_data = {}
        
        if dates and youtube_urls:
            # Try to correlate dates with YouTube URLs
            # This is approximate since the exact mapping is complex in the compressed format
            for i, date_text in enumerate(dates):
                try:
                    parsed_date = self._convert_date_format(date_text)
                    if not parsed_date:
                        continue
                    
                    # Estimate location (this is very approximate)
                    location = locations[i] if i < len(locations) else f"Location {i+1}"
                    
                    # Assign YouTube links (this is a simplified approach)
                    # In reality, we'd need more sophisticated parsing to match links to specific shows
                    links_per_show = 2  # Estimate
                    start_idx = i * links_per_show
                    end_idx = min(start_idx + links_per_show, len(youtube_urls))
                    
                    show_links = []
                    for j, url in enumerate(youtube_urls[start_idx:end_idx]):
                        show_links.append({
                            'url': url,
                            'text': f"Show {parsed_date}",
                            'column': f"Link {j+1}" if j > 0 else "Link"
                        })
                    
                    if show_links:  # Only add shows with links
                        shows_data[parsed_date] = {
                            'date': parsed_date,
                            'original_date': date_text,
                            'location': location,
                            'venue': '',
                            'country': '',
                            'youtube_links': show_links,
                            'source': 'google_sheets_compressed'
                        }
                        
                        # Continue processing all shows
                        # Removed artificial 50-show limit to process all available data
                    
                except Exception as e:
                    logger.debug(f"Error processing date {date_text}: {e}")
                    continue
        
        return shows_data
    
    def _parse_html_row(self, row) -> Optional[Dict[str, Any]]:
        """Parse a single HTML table row to extract show information with YouTube links.

        Column positions are NOT fixed: Google Sheets exports include a
        row-number column, may insert blank spacer columns, and the number of
        populated "Link" columns varies per row. So rather than hardcoding
        indices, locate the date cell by parsing, take the descriptive fields
        from offsets relative to it, and harvest YouTube links from every
        remaining cell (numbering them by the order they appear).
        """
        cells = row.find_all(['td', 'th'])
        if len(cells) < 3:
            return None

        try:
            # Locate the date cell by trying to parse each one
            date_idx = None
            date_text = ""
            parsed_date = None
            for idx, cell in enumerate(cells[:6]):
                link = cell.find('a')
                text = (link.get_text(strip=True) if link else cell.get_text(strip=True))
                if text and self._is_valid_date(text):
                    candidate = self._convert_date_format(text)
                    if candidate:
                        date_idx, date_text, parsed_date = idx, text, candidate
                        break

            if parsed_date is None:
                return None

            def cell_text(offset: int) -> str:
                i = date_idx + offset
                return cells[i].get_text(strip=True) if 0 <= i < len(cells) else ""

            # Layout after the date: [spacer] Sets | Location | Country | Venue
            sets = cell_text(2)
            location = cell_text(3)
            country = cell_text(4)
            venue = cell_text(5)

            # Harvest YouTube links from every cell beyond the venue column
            youtube_links = []
            seen_urls = set()
            link_number = 0
            for cell in cells[date_idx + 6:]:
                cell_links = []
                for link in cell.find_all('a', href=True):
                    if self._is_youtube_url(link['href']):
                        cell_links.append((link['href'], link.get_text(strip=True)))

                # Bare (non-hyperlinked) URLs sitting in the cell text
                raw = cell.get_text(strip=True)
                if not cell_links and raw and self._is_youtube_url(raw):
                    cell_links.append((raw, ""))

                if not cell_links:
                    continue

                link_number += 1
                for href, text in cell_links:
                    if href in seen_urls:
                        continue
                    seen_urls.add(href)
                    youtube_links.append({
                        'url': href,
                        'text': text or f"Show {parsed_date}",
                        'column': "Link" if link_number == 1 else f"Link {link_number}",
                    })

            if not youtube_links:
                return None  # Skip rows without YouTube links

            clean_location = self._clean_location(location, country)

            length = cell_text(10)
            sources = cell_text(11)
            notes = cell_text(12)

            return {
                'date': parsed_date,
                'original_date': date_text,
                'sets': sets,
                'location': clean_location,
                'venue': venue,
                'country': country,
                'youtube_links': youtube_links,
                'length': length,
                'sources': sources,
                'notes': notes,
                'source': 'google_sheets_html'
            }
            
        except Exception as e:
            logger.debug(f"Error parsing HTML row: {e}")
            return None
    
    def _is_youtube_url(self, url: str) -> bool:
        """Check if a URL is a YouTube URL."""
        if not url:
            return False
        return ('youtube.com' in url.lower() or 
                'youtu.be' in url.lower() or
                'www.youtube.com' in url.lower())
    
    def _is_valid_date(self, date_text: str) -> bool:
        """Check if text looks like a date in DD-MMM-YYYY format."""
        if not date_text:
            return False
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
        if country and country.lower() in location.lower():
            return location
        
        # Add country suffix for better matching
        if country and country.upper() == "USA" and "USA" not in location and "US" not in location:
            # Clean up state abbreviations
            location_clean = location.replace(',', '')
            return f"{location_clean}"
        
        return location
    
    def get_show_by_date(self, date: str) -> Optional[Dict[str, Any]]:
        """Get show data for a specific date."""
        if not self.shows_data:
            logger.warning("No data loaded. Call parse_html_export() first.")
            return None
        
        return self.shows_data.get(date)
    
    def search_shows_by_location(self, location: str) -> List[Dict[str, Any]]:
        """Search for shows by location."""
        if not self.shows_data:
            logger.warning("No data loaded. Call parse_html_export() first.")
            return []
        
        matches = []
        location_lower = location.lower()
        
        # Don't do broad searches for generic/weird location names
        if len(location.split()) > 5 or 'chunky' in location_lower or 'forum' in location_lower:
            logger.debug(f"Skipping broad location search for unusual location: {location}")
            return []
        
        for show_data in self.shows_data.values():
            show_location = show_data['location'].lower()
            show_venue = show_data.get('venue', '').lower()
            
            # Much more restrictive matching - require substantial overlap
            location_words = set(location_lower.split())
            show_location_words = set(show_location.split())
            venue_words = set(show_venue.split())
            
            # Require at least 2 word overlap or exact city match
            location_overlap = len(location_words & show_location_words)
            venue_overlap = len(location_words & venue_words)
            
            if location_overlap >= 2 or venue_overlap >= 2:
                matches.append(show_data)
            elif len(location_words) == 1 and (location_lower in show_location or location_lower in show_venue):
                # Single word exact match (like "Chicago")
                matches.append(show_data)
        
        logger.debug(f"Location search for '{location}' returned {len(matches)} matches")
        return matches
    
    def get_youtube_links_for_show(self, date: str = None, location: str = None) -> List[Dict[str, Any]]:
        """Get YouTube links for a specific show by date or location."""
        if date:
            show = self.get_show_by_date(date)
            if show:
                return show.get('youtube_links', [])
        
        if location:
            shows = self.search_shows_by_location(location)
            all_links = []
            for show in shows:
                all_links.extend(show.get('youtube_links', []))
            return all_links
        
        return []
    
    def get_all_shows(self) -> Dict[str, Dict[str, Any]]:
        """Get all parsed show data."""
        return self.shows_data
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the parsed data."""
        if not self.shows_data:
            return {
                'total_shows': 0,
                'total_youtube_links': 0,
                'years': {},
                'latest_show': None
            }
        
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
            'latest_show': max(self.shows_data.keys()) if self.shows_data else None,
            'countries': self._get_country_stats(),
            'venues_with_links': self._get_venues_with_links()
        }
    
    def _get_country_stats(self) -> Dict[str, int]:
        """Get show count by country."""
        countries = {}
        for show in self.shows_data.values():
            country = show.get('country', 'Unknown')
            countries[country] = countries.get(country, 0) + 1
        return countries
    
    def _get_venues_with_links(self) -> int:
        """Get count of unique venues with YouTube links."""
        venues = set()
        for show in self.shows_data.values():
            if show.get('youtube_links'):
                venue_key = f"{show.get('venue', '')} - {show.get('location', '')}"
                venues.add(venue_key)
        return len(venues)