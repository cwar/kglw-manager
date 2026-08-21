"""Tour data scraping from kglw.net for accurate tour assignments."""

import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import json
import logging
from .utils import setup_logging

logger = setup_logging()


class TourScraper:
    """Scrapes and manages tour data from kglw.net."""
    
    def __init__(self, cache_dir: Path = None):
        if cache_dir is None:
            cache_dir = Path.home() / '.kglw_manager' / 'cache'
        
        self.cache_dir = cache_dir
        self.cache_file = cache_dir / 'tour_data.json'
        self.tours = {}
        self.last_updated = None
        
        # Create cache directory
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Load cached data
        self._load_cache()
    
    def _load_cache(self):
        """Load cached tour data."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    self.tours = data.get('tours', {})
                    self.last_updated = data.get('last_updated')
                logger.debug(f"Loaded {len(self.tours)} tours from cache")
            except Exception as e:
                logger.warning(f"Failed to load tour cache: {e}")
                self.tours = {}
    
    def _save_cache(self):
        """Save tour data to cache."""
        try:
            data = {
                'tours': self.tours,
                'last_updated': self.last_updated
            }
            with open(self.cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug("Saved tour data to cache")
        except Exception as e:
            logger.warning(f"Failed to save tour cache: {e}")
    
    def scrape_tours(self) -> Dict[str, Dict[str, Any]]:
        """Scrape tour data from kglw.net."""
        url = 'https://kglw.net/tour/'
        
        try:
            logger.info("Fetching tour data from kglw.net...")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            tables = soup.find_all('table')
            
            if not tables:
                logger.error("No tables found on tour page")
                return {}
            
            table = tables[0]  # First table contains tour data
            rows = table.find_all('tr')
            
            tours = {}
            
            for row in rows[1:]:  # Skip header row
                cells = [cell.get_text(strip=True) for cell in row.find_all(['td', 'th'])]
                
                if len(cells) >= 5:
                    tour_name = cells[0]
                    artist = cells[1]
                    num_shows = cells[2]
                    start_date = cells[3]
                    end_date = cells[4]
                    
                    # Only include King Gizzard tours
                    if 'King Gizzard' in artist:
                        tours[tour_name] = {
                            'name': tour_name,
                            'artist': artist,
                            'num_shows': int(num_shows) if num_shows.isdigit() else 0,
                            'start_date': start_date,
                            'end_date': end_date
                        }
            
            logger.info(f"Scraped {len(tours)} King Gizzard tours")
            
            # Update cache
            self.tours = tours
            self.last_updated = datetime.now().isoformat()
            self._save_cache()
            
            return tours
            
        except Exception as e:
            logger.error(f"Failed to scrape tour data: {e}")
            return {}
    
    def get_tour_for_date(self, date_str: str) -> Optional[str]:
        """Get the tour name for a specific date."""
        if not self.tours:
            # Try to scrape if no data
            self.scrape_tours()
        
        if not self.tours:
            logger.warning("No tour data available")
            return None
        
        try:
            show_date = datetime.strptime(date_str, '%Y-%m-%d')
            
            # First, try to find a specific named tour (skip the catch-all "Not Part of a Tour")
            for tour_name, tour_info in self.tours.items():
                # Skip the catch-all entry - we'll use it as fallback
                if tour_name == "Not Part of a Tour":
                    continue
                    
                start_date = datetime.strptime(tour_info['start_date'], '%Y-%m-%d')
                end_date = datetime.strptime(tour_info['end_date'], '%Y-%m-%d')
                
                if start_date <= show_date <= end_date:
                    logger.debug(f"Found tour for {date_str}: {tour_name}")
                    return tour_name
            
            # If no specific tour found, check if it's in the catch-all category
            if "Not Part of a Tour" in self.tours:
                catch_all = self.tours["Not Part of a Tour"]
                start_date = datetime.strptime(catch_all['start_date'], '%Y-%m-%d')
                end_date = datetime.strptime(catch_all['end_date'], '%Y-%m-%d')
                
                if start_date <= show_date <= end_date:
                    logger.debug(f"No specific tour for {date_str}, using catch-all")
                    return "Not Part of a Tour"
            
            # Fallback
            logger.debug(f"No tour found for {date_str}")
            return "Not Part of a Tour"
            
        except ValueError as e:
            logger.error(f"Invalid date format {date_str}: {e}")
            return None
    
    def get_all_tours(self) -> Dict[str, Dict[str, Any]]:
        """Get all available tours."""
        if not self.tours:
            self.scrape_tours()
        return self.tours
    
    def refresh_cache(self) -> bool:
        """Force refresh of tour data from web."""
        logger.info("Force refreshing tour data...")
        result = self.scrape_tours()
        return bool(result)
    
    def get_cache_age_days(self) -> Optional[int]:
        """Get cache age in days."""
        if not self.last_updated:
            return None
        
        try:
            updated_time = datetime.fromisoformat(self.last_updated)
            age = datetime.now() - updated_time
            return age.days
        except Exception:
            return None
    
    def is_cache_stale(self, max_age_days: int = 7) -> bool:
        """Check if cache is older than max_age_days."""
        age = self.get_cache_age_days()
        if age is None:
            return True  # No cache, consider stale
        return age > max_age_days


# Global instance
tour_scraper = TourScraper()