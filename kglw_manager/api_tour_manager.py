"""API-based tour management using KGLW.net API for accurate tour assignment."""

import requests
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import json

logger = logging.getLogger(__name__)

class APITourManager:
    """Manages tour assignment using KGLW.net API for accurate tour names."""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize API tour manager with optional caching."""
        self.cache_dir = cache_dir or (Path.home() / '.kglw_manager' / 'cache')
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / 'api_tours_cache.json'
        
        # In-memory cache
        self._tours_cache = None
        self._cache_timestamp = None
        
        # Cache duration: 1 hour
        self.cache_duration = 3600
    
    def _fetch_api_tours(self) -> Optional[Dict[int, Dict[str, Any]]]:
        """Fetch tour data from KGLW.net API and create comprehensive show mapping."""
        try:
            logger.debug("Fetching show data from KGLW.net API...")
            response = requests.get('https://kglw.net/api/v2/shows.json', timeout=30)
            response.raise_for_status()
            api_response = response.json()
            
            if api_response.get('error') is False and 'data' in api_response:
                shows_data = api_response['data']
                logger.debug(f"Fetched {len(shows_data)} total shows from API")
                
                # Filter for King Gizzard shows only (artist_id: 1)
                kglw_shows = [show for show in shows_data if show.get('artist_id') == 1]
                logger.debug(f"Filtered to {len(kglw_shows)} King Gizzard shows")
                
                # Get show IDs for setlist filtering
                show_ids = [show.get('show_id') for show in kglw_shows if show.get('show_id')]
                logger.debug(f"Getting setlist data for {len(show_ids)} shows...")
                
                # Get setlist data to filter out radio sessions
                valid_show_ids = self._filter_shows_by_setlist_type(show_ids)
                logger.debug(f"Filtered to {len(valid_show_ids)} concert shows (excluding radio sessions)")
                
                # Create comprehensive show_id to show info mapping
                show_id_to_show = {}
                for show in kglw_shows:
                    show_id = show.get('show_id')
                    show_date = show.get('showdate')
                    
                    # Skip shows not in our valid list (radio sessions, etc.)
                    if show_id not in valid_show_ids:
                        continue
                    
                    if show_date:
                        try:
                            # Validate date format
                            datetime.strptime(show_date, '%Y-%m-%d')
                            
                            # Store comprehensive show information with show_id as key
                            show_id_to_show[show_id] = {
                                'show_id': show.get('show_id'),
                                'show_date': show_date,
                                'tour_name': show.get('tourname'),
                                'tour_id': show.get('tour_id'),
                                'venue_name': show.get('venuename'),
                                'location': show.get('location'),
                                'city': show.get('city'),
                                'state': show.get('state'),
                                'country': show.get('country'),
                                'artist': show.get('artist'),
                                'show_title': show.get('showtitle'),
                                'permalink': show.get('permalink'),
                                'updated_at': show.get('updated_at')
                            }
                        except ValueError:
                            logger.debug(f"Invalid date format: {show_date}")
                            continue
                
                logger.info(f"Created mapping for {len(show_id_to_show)} King Gizzard concert shows")
                return show_id_to_show
            else:
                logger.error(f"API returned error: {api_response.get('error_message', 'Unknown error')}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"Failed to fetch API data: {e}")
            return None
        except Exception as e:
            logger.error(f"Error processing API data: {e}")
            return None
    
    def _filter_shows_by_setlist_type(self, show_ids: List[int]) -> set:
        """Filter shows by setlist type, excluding radio sessions."""
        # For now, let's use a simpler approach - get all setlists and filter
        # This is more efficient than individual API calls per show
        
        valid_show_ids = set()
        excluded_show_ids = set()
        
        try:
            logger.debug("Fetching all setlists to filter show types...")
            response = requests.get('https://kglw.net/api/v2/setlists.json', timeout=60)
            response.raise_for_status()
            
            setlist_response = response.json()
            if setlist_response.get('error') is False and 'data' in setlist_response:
                setlists_data = setlist_response['data']
                logger.debug(f"Fetched {len(setlists_data)} setlist entries")
                
                # Group setlists by show_id
                show_setlists = {}
                for setlist in setlists_data:
                    show_id = setlist.get('show_id')
                    if show_id:
                        if show_id not in show_setlists:
                            show_setlists[show_id] = []
                        show_setlists[show_id].append(setlist)
                
                # Filter shows based on setlist types
                for show_id in show_ids:
                    if show_id in show_setlists:
                        # Check if show has any valid set types
                        has_valid_set = False
                        set_types = []
                        
                        for setlist in show_setlists[show_id]:
                            settype = setlist.get('settype', '')
                            set_types.append(settype)
                            
                            # Include "Set" and "DJ Set" but exclude "Radio Session"
                            if settype in ['Set', 'DJ Set']:
                                has_valid_set = True
                        
                        if has_valid_set:
                            valid_show_ids.add(show_id)
                        else:
                            excluded_show_ids.add(show_id)
                            logger.debug(f"Excluded show {show_id}: set types {set_types}")
                    else:
                        # No setlist data - assume it's a concert
                        valid_show_ids.add(show_id)
                
                logger.debug(f"Setlist filtering: {len(valid_show_ids)} included, {len(excluded_show_ids)} excluded")
                
            else:
                # If setlists API fails, include all shows
                logger.warning("Failed to get setlists data - including all shows")
                valid_show_ids = set(show_ids)
        
        except Exception as e:
            # If setlists API fails completely, include all shows
            logger.warning(f"Setlist filtering failed: {e} - including all shows")
            valid_show_ids = set(show_ids)
        
        return valid_show_ids
    
    def _load_cached_tours(self) -> Optional[Dict[int, Dict[str, Any]]]:
        """Load tour data from cache file."""
        try:
            if not self.cache_file.exists():
                return None
            
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            # Check cache age
            cache_time = cache_data.get('timestamp', 0)
            current_time = datetime.now().timestamp()
            
            if current_time - cache_time > self.cache_duration:
                logger.debug("Cache expired")
                return None
            
            # Convert string keys to int keys (JSON serialization converts int keys to strings)
            shows_data = cache_data.get('shows', {})
            if shows_data:
                # Convert string show_id keys back to integers
                return {int(k): v for k, v in shows_data.items() if k.isdigit()}
            return {}
            
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"Failed to load cache: {e}")
            return None
    
    def _save_cached_tours(self, shows: Dict[int, Dict[str, Any]]):
        """Save show data to cache file."""
        try:
            cache_data = {
                'timestamp': datetime.now().timestamp(),
                'shows': shows
            }
            
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            logger.debug(f"Saved {len(shows)} shows to cache")
            
        except OSError as e:
            logger.warning(f"Failed to save cache: {e}")
    
    def _get_tours_data(self) -> Dict[int, Dict[str, Any]]:
        """Get show data with caching (show_id-based mapping)."""
        current_time = datetime.now().timestamp()
        
        # Check in-memory cache first
        if (self._tours_cache and self._cache_timestamp and 
            current_time - self._cache_timestamp < self.cache_duration):
            return self._tours_cache
        
        # Try loading from file cache
        shows = self._load_cached_tours()
        
        # If cache miss or expired, fetch from API
        if shows is None:
            shows = self._fetch_api_tours()
            if shows:
                self._save_cached_tours(shows)
            else:
                # If API fails, return empty dict (will fall back to default behavior)
                shows = {}
        
        # Update in-memory cache
        self._tours_cache = shows
        self._cache_timestamp = current_time
        
        return shows
    
    def get_tour_for_date(self, date_str: str) -> Optional[str]:
        """Get official tour name for a specific date (returns first show if multiple)."""
        shows_for_date = self.get_shows_for_date(date_str)
        return shows_for_date[0].get('tour_name') if shows_for_date else None
    
    def get_show_info_for_date(self, date_str: str) -> Optional[Dict[str, Any]]:
        """Get complete show information for a specific date (returns first show if multiple)."""
        shows_for_date = self.get_shows_for_date(date_str)
        return shows_for_date[0] if shows_for_date else None
    
    def get_shows_for_date(self, date_str: str) -> List[Dict[str, Any]]:
        """Get all shows for a specific date (can be multiple shows per date)."""
        shows = self._get_tours_data()
        shows_for_date = []
        for show_id, show_info in shows.items():
            if show_info.get('show_date') == date_str:
                shows_for_date.append(show_info)
        return shows_for_date
    
    def get_show_by_id(self, show_id: int) -> Optional[Dict[str, Any]]:
        """Get show information by show_id."""
        shows = self._get_tours_data()
        return shows.get(show_id)
    
    def get_all_shows(self) -> Dict[int, Dict[str, Any]]:
        """Get all shows mapped by show_id."""
        return self._get_tours_data()
    
    def assign_tour_from_api(self, show_info: Dict[str, Any]) -> Optional[str]:
        """Assign tour based on KGLW.net API data."""
        date = show_info.get('date', '')
        if not date:
            return None
        
        # Normalize date format
        try:
            show_date = datetime.strptime(date, '%Y-%m-%d')
            date_str = show_date.strftime('%Y-%m-%d')
        except ValueError:
            logger.debug(f"Invalid date format: {date}")
            return None
        
        return self.get_tour_for_date(date_str)
    
    def normalize_tour_name_for_filesystem(self, tour_name: str) -> str:
        """Normalize API tour name for filesystem usage."""
        if not tour_name:
            return tour_name
        
        # Handle common API tour name formats
        normalized = tour_name
        
        # Replace forward slashes with dashes (common in API: "Europe/UK" → "Europe-UK")
        normalized = normalized.replace('/', '-')
        
        # Replace colons with dashes (API format: "2012: 12 Bar Bruise" → "2012- 12 Bar Bruise")
        normalized = normalized.replace(': ', '- ')
        normalized = normalized.replace(':', '-')
        
        # Remove other problematic characters
        normalized = normalized.replace('\\', '-')
        normalized = normalized.replace('|', '-')
        normalized = normalized.replace('?', '')
        normalized = normalized.replace('*', '')
        normalized = normalized.replace('<', '')
        normalized = normalized.replace('>', '')
        normalized = normalized.replace('"', "'")
        
        # Clean up multiple consecutive dashes
        while '--' in normalized:
            normalized = normalized.replace('--', '-')
        
        # Remove leading/trailing dashes and whitespace
        normalized = normalized.strip(' -')
        
        return normalized
    
    def get_all_tours(self) -> List[Tuple[str, str]]:
        """Get all tours as (original_name, normalized_name) tuples."""
        shows_data = self._get_tours_data()
        unique_tours = set()
        
        for show_info in shows_data.values():
            tour_name = show_info.get('tour_name')
            if tour_name:
                unique_tours.add(tour_name)
        
        return [(tour, self.normalize_tour_name_for_filesystem(tour)) 
                for tour in sorted(unique_tours)]
    
    def clear_cache(self):
        """Clear both in-memory and file cache."""
        self._tours_cache = None
        self._cache_timestamp = None
        
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
                logger.info("Cleared API tours cache")
        except OSError as e:
            logger.warning(f"Failed to clear cache file: {e}")
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get information about the current cache."""
        try:
            if not self.cache_file.exists():
                return {"cached": False, "age": 0, "tours_count": 0}
            
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            cache_time = cache_data.get('timestamp', 0)
            current_time = datetime.now().timestamp()
            age_seconds = current_time - cache_time
            shows_count = len(cache_data.get('shows', {}))
            
            return {
                "cached": True,
                "age_seconds": age_seconds,
                "age_minutes": age_seconds / 60,
                "tours_count": shows_count,
                "expired": age_seconds > self.cache_duration
            }
            
        except (json.JSONDecodeError, OSError):
            return {"cached": False, "age": 0, "tours_count": 0}


# Enhanced TourManager that uses API when available
class EnhancedTourManager:
    """Tour manager that prioritizes API data but falls back to hardcoded definitions."""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize enhanced tour manager."""
        from .tours import TourManager  # Import the existing TourManager
        
        self.api_manager = APITourManager(cache_dir)
        self.fallback_manager = TourManager()
    
    def assign_tour(self, show_info: Dict[str, Any]) -> str:
        """Assign tour using API data first, fallback to hardcoded definitions."""
        date = show_info.get('date', '')
        if not date:
            return f"{datetime.now().year} Not Part of a Tour"
        
        try:
            show_date = datetime.strptime(date, '%Y-%m-%d')
            year = show_date.year
        except ValueError:
            return f"{datetime.now().year} Not Part of a Tour"
        
        # Try API first
        api_tour = self.api_manager.assign_tour_from_api(show_info)
        if api_tour:
            logger.debug(f"API assigned tour for {date}: {api_tour}")
            return api_tour
        
        # Fall back to hardcoded definitions
        fallback_tour = self.fallback_manager.assign_tour(show_info)
        logger.debug(f"Fallback assigned tour for {date}: {fallback_tour}")
        return fallback_tour
    
    def normalize_tour_name_for_filesystem(self, tour_name: str) -> str:
        """Normalize tour name for filesystem usage."""
        return self.api_manager.normalize_tour_name_for_filesystem(tour_name)
    
    def get_tour_for_date(self, date_str: str) -> Optional[str]:
        """Get tour name for specific date (API only)."""
        return self.api_manager.get_tour_for_date(date_str)
    
    def get_show_info_for_date(self, date_str: str) -> Optional[Dict[str, Any]]:
        """Get complete show information for specific date (API only)."""
        return self.api_manager.get_show_info_for_date(date_str)
    
    def clear_api_cache(self):
        """Clear API cache."""
        self.api_manager.clear_cache()
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get API cache information."""
        return self.api_manager.get_cache_info()


# Factory function to get the enhanced tour manager
def get_tour_manager(cache_dir: Optional[Path] = None) -> EnhancedTourManager:
    """Factory function to get an enhanced tour manager instance."""
    return EnhancedTourManager(cache_dir)