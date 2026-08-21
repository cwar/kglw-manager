"""Data sources for KGLW concert information."""

import requests
from typing import Dict, List, Any, Optional
from .utils import setup_logging

logger = setup_logging()

# Updated API base URL
KGLW_API_BASE = "https://kglw.net/api/v2"


class KGLWNetSource:
    """Interface to KGLW.net API for official concert data."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'KGLW-Manager/1.0.0'
        })
    
    def get_shows_for_year(self, year: int) -> List[Dict[str, Any]]:
        """Get all shows for a specific year."""
        try:
            url = f"{KGLW_API_BASE}/setlists/showyear/{year}.json"
            logger.debug(f"Fetching shows for {year} from: {url}")
            
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            # API returns {"error": false, "error_message": "", "data": [...]}
            if isinstance(data, dict) and 'data' in data:
                shows = data['data']
            else:
                shows = data.get('shows', []) if isinstance(data, dict) else data
            
            logger.debug(f"Retrieved {len(shows)} shows for {year}")
            return shows
            
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch shows for {year}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error parsing shows for {year}: {e}")
            return []
    
    def get_all_tours(self) -> List[Dict[str, Any]]:
        """Get all tour information.

        There is no tours endpoint on kglw.net, so tours are derived from the
        tour_id/tourname carried on every show row.
        """
        try:
            url = f"{KGLW_API_BASE}/shows.json"
            logger.debug(f"Fetching shows (for tour derivation) from: {url}")

            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            payload = response.json()
            shows = payload.get('data', []) if isinstance(payload, dict) else (payload or [])

            tours: Dict[Any, Dict[str, Any]] = {}
            for show in shows:
                tour_name = show.get('tourname')
                if not tour_name:
                    continue
                tour_id = show.get('tour_id')
                key = tour_id if tour_id is not None else tour_name
                tour = tours.setdefault(key, {
                    'tour_id': tour_id,
                    'tourname': tour_name,
                    'show_count': 0,
                })
                tour['show_count'] += 1

            tour_list = list(tours.values())
            logger.debug(f"Derived {len(tour_list)} tours from shows data")
            return tour_list

        except requests.RequestException as e:
            logger.warning(f"Failed to fetch tours: {e}")
            return []
        except Exception as e:
            logger.error(f"Error parsing tours: {e}")
            return []
    
    def search_show_by_date_location(self, date: str, location: str) -> Optional[Dict[str, Any]]:
        """Search for a specific show by date and location."""
        try:
            # Extract year from date
            year = int(date.split('-')[0])
            shows = self.get_shows_for_year(year)
            
            # Search for matching show. API rows use showdate/city/venuename.
            for show in shows:
                show_date = show.get('showdate') or show.get('date', '')
                show_location = ' '.join(filter(None, [
                    show.get('location'), show.get('city'), show.get('venuename')
                ])).lower()

                if show_date == date and location.lower() in show_location:
                    logger.debug(f"Found matching show: {show_date} - {show_location}")
                    return show
            
            logger.debug(f"No matching show found for {date} - {location}")
            return None
            
        except Exception as e:
            logger.error(f"Error searching for show {date} - {location}: {e}")
            return None
    
    def get_show_details(self, show_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information for a specific show."""
        try:
            url = f"{KGLW_API_BASE}/setlists/show/{show_id}.json"
            logger.debug(f"Fetching show details for {show_id}")
            
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            return response.json()
            
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch show details for {show_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing show details for {show_id}: {e}")
            return None
    
    def get_show_poster(self, show_date: str) -> Optional[str]:
        """Get poster image URL for a specific show."""
        try:
            # First, try to get poster from the individual show page (for external links)
            poster_url = self._get_poster_from_show_page(show_date)
            if poster_url:
                return poster_url
            
            # Fallback to uploads API for uploaded posters
            return self._get_poster_from_uploads_api(show_date)
            
        except Exception as e:
            logger.error(f"Error fetching poster for {show_date}: {e}")
            return None
    
    def _get_poster_from_show_page(self, show_date: str) -> Optional[str]:
        """Extract poster image from individual show page."""
        try:
            # Find the show to get its permalink
            show_info = self._find_show_by_date(show_date)
            if not show_info:
                logger.debug(f"No show found for {show_date}")
                return None
            
            permalink = show_info.get('permalink', '')
            if not permalink:
                logger.debug(f"No permalink found for show {show_date}")
                return None
            
            # Construct the full URL to the show page
            show_page_url = f"https://kglw.net/setlists/{permalink}.html"
            logger.debug(f"Fetching poster from show page: {show_page_url}")
            
            # Fetch the HTML page
            response = self.session.get(show_page_url, timeout=30)
            response.raise_for_status()
            
            # Parse the HTML to find poster image
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for poster images - try multiple selectors
            poster_selectors = [
                'img[src*="poster"]',
                'img[src*="lolla"]', 
                'img[src*="festival"]',
                '.poster img',
                '.show-poster img',
                'img[alt*="poster"]',
                'img[alt*="Poster"]'
            ]
            
            for selector in poster_selectors:
                img_tag = soup.select_one(selector)
                if img_tag and img_tag.get('src'):
                    poster_url = img_tag['src']
                    # Ensure absolute URL
                    if poster_url.startswith('//'):
                        poster_url = 'https:' + poster_url
                    elif poster_url.startswith('/'):
                        poster_url = 'https://kglw.net' + poster_url
                    elif not poster_url.startswith('http'):
                        continue  # Skip relative URLs we can't resolve
                        
                    logger.info(f"Found poster on show page for {show_date}: {poster_url}")
                    return poster_url
            
            # If no specific poster selectors work, look for any large images
            large_images = soup.select('img[src]')
            for img in large_images:
                src = img.get('src', '')
                alt = img.get('alt', '').lower()
                
                # Skip small images and icons
                if any(skip in src.lower() for skip in ['icon', 'logo', 'thumb', 'small']):
                    continue
                    
                # Look for poster-like images
                if any(keyword in src.lower() or keyword in alt for keyword in [
                    'poster', 'festival', 'lolla', 'event', 'show'
                ]):
                    poster_url = src
                    if poster_url.startswith('//'):
                        poster_url = 'https:' + poster_url
                    elif poster_url.startswith('/'):
                        poster_url = 'https://kglw.net' + poster_url
                    elif poster_url.startswith('http'):
                        logger.info(f"Found poster image for {show_date}: {poster_url}")
                        return poster_url
            
            logger.debug(f"No poster image found on show page for {show_date}")
            return None
            
        except Exception as e:
            logger.debug(f"Error scraping poster from show page for {show_date}: {e}")
            return None
    
    def _get_poster_from_uploads_api(self, show_date: str) -> Optional[str]:
        """Get poster from uploads API with date range search."""
        try:
            # Without an explicit limit the API returns only the first page,
            # so recent poster uploads would be missing.
            url = f"{KGLW_API_BASE}/uploads.json?limit=2000"
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            uploads = data.get('data', []) if isinstance(data, dict) else data
            
            # First, try exact date match
            for upload in uploads:
                if upload.get('showdate') == show_date and upload.get('upload_type') == 'poster-art':
                    poster_url = upload.get('URL', '').replace('\\/', '/')  # Fix escaped slashes
                    logger.debug(f"Found exact poster match in uploads for {show_date}: {poster_url}")
                    return poster_url
            
            # If no exact match, try nearby dates with location matching
            from datetime import datetime, timedelta
            try:
                target_date = datetime.strptime(show_date, '%Y-%m-%d')
                show_info = self._find_show_by_date(show_date)
                show_location = show_info.get('city', '') if show_info else ''
                
                # Search ±2 days for uploaded posters
                for days_offset in [-2, -1, 1, 2]:
                    check_date = (target_date + timedelta(days=days_offset)).strftime('%Y-%m-%d')
                    
                    for upload in uploads:
                        if (upload.get('showdate') == check_date and 
                            upload.get('upload_type') == 'poster-art'):
                            
                            # Check if location matches if we have location info
                            if show_location:
                                img_name = upload.get('img_name', '').lower()
                                if show_location.lower() in img_name:
                                    poster_url = upload.get('URL', '').replace('\\/', '/')
                                    logger.info(f"Found poster in uploads for {show_date} via location match on {check_date}: {poster_url}")
                                    return poster_url
                            else:
                                # No location info, take any poster from nearby date
                                poster_url = upload.get('URL', '').replace('\\/', '/')
                                logger.info(f"Found poster in uploads for {show_date} via date proximity on {check_date}: {poster_url}")
                                return poster_url
                                
            except ValueError:
                logger.warning(f"Invalid date format for poster search: {show_date}")
            
            logger.debug(f"No poster found in uploads for show {show_date}")
            return None
            
        except Exception as e:
            logger.debug(f"Error fetching poster from uploads API for {show_date}: {e}")
            return None
    
    def _find_show_by_date(self, show_date: str) -> Optional[Dict[str, Any]]:
        """Find show information by date."""
        try:
            year = int(show_date.split('-')[0])
            shows = self.get_shows_for_year(year)
            
            for show in shows:
                if show.get('showdate') == show_date:
                    return show
                    
            return None
        except Exception as e:
            logger.debug(f"Error finding show by date {show_date}: {e}")
            return None
    
    def get_show_setlist_summary(self, show_date: str) -> Optional[Dict[str, Any]]:
        """Get setlist summary for a specific show."""
        try:
            # Extract year from date
            year = int(show_date.split('-')[0])
            shows = self.get_shows_for_year(year)
            
            # Find shows for this date and aggregate setlist
            show_songs = []
            show_notes = ""
            venue_name = ""
            city = ""
            tour_name = ""
            permalink = ""
            
            for show in shows:
                if show.get('showdate') == show_date:
                    show_songs.append({
                        'name': show.get('songname', ''),
                        'position': show.get('position', 0),
                        'set': show.get('setnumber', 1),
                        'tracktime': show.get('tracktime', ''),
                        'footnote': show.get('footnote', ''),
                        'transition': show.get('transition', '')
                    })
                    
                    # Get show metadata from first song entry
                    if not show_notes:
                        show_notes = show.get('shownotes', '')
                        venue_name = show.get('venuename', '')
                        city = show.get('city', '')
                        tour_name = show.get('tourname', '')
                        permalink = show.get('permalink', '')
            
            if not show_songs:
                logger.debug(f"No setlist found for {show_date}")
                return None
            
            # Sort songs by set and position
            show_songs.sort(key=lambda x: (x['set'], x['position']))
            
            # Group by sets
            sets = {}
            for song in show_songs:
                set_num = song['set']
                if set_num not in sets:
                    sets[set_num] = []
                sets[set_num].append(song)
            
            setlist_summary = {
                'date': show_date,
                'venue': venue_name,
                'city': city,
                'tour': tour_name,
                'notes': show_notes,
                'sets': sets,
                'total_songs': len(show_songs),
                'permalink': permalink
            }
            
            logger.debug(f"Found setlist for {show_date}: {len(show_songs)} songs in {len(sets)} sets")
            return setlist_summary
            
        except Exception as e:
            logger.error(f"Error fetching setlist for {show_date}: {e}")
            return None


class LocalSpreadsheetSource:
    """Interface to local spreadsheet data."""
    
    def __init__(self, csv_path: str = "gizzard_shows.csv"):
        self.csv_path = csv_path
    
    def get_all_shows(self) -> List[Dict[str, Any]]:
        """Get all shows from local CSV."""
        try:
            import csv
            from pathlib import Path
            
            csv_file = Path(self.csv_path)
            if not csv_file.exists():
                logger.warning(f"CSV file not found: {self.csv_path}")
                return []
            
            shows = []
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    shows.append(dict(row))
            
            logger.debug(f"Loaded {len(shows)} shows from CSV")
            return shows
            
        except Exception as e:
            logger.error(f"Error loading CSV data: {e}")
            return []
    
    def get_shows_for_year(self, year: int) -> List[Dict[str, Any]]:
        """Get shows for a specific year from CSV."""
        all_shows = self.get_all_shows()
        
        year_shows = []
        for show in all_shows:
            show_date = show.get('date', '')
            if show_date.startswith(str(year)):
                year_shows.append(show)
        
        return year_shows


class DataSourceManager:
    """Manages multiple data sources for KGLW concert information."""
    
    def __init__(self, prefer_api: bool = True):
        self.kglw_source = KGLWNetSource()
        self.csv_source = LocalSpreadsheetSource()
        self.prefer_api = prefer_api
    
    def get_shows_for_year(self, year: int) -> List[Dict[str, Any]]:
        """Get shows for a year from preferred source."""
        if self.prefer_api:
            # Try API first
            shows = self.kglw_source.get_shows_for_year(year)
            if shows:
                return shows
            
            # Fallback to CSV
            logger.info(f"API failed for {year}, falling back to CSV")
            return self.csv_source.get_shows_for_year(year)
        else:
            # Use CSV first
            shows = self.csv_source.get_shows_for_year(year)
            if not shows:
                # Fallback to API
                logger.info(f"CSV has no data for {year}, trying API")
                return self.kglw_source.get_shows_for_year(year)
            return shows
    
    def search_show(self, date: str, location: str) -> Optional[Dict[str, Any]]:
        """Search for a show across all sources."""
        # Try API first
        show = self.kglw_source.search_show_by_date_location(date, location)
        if show:
            return show
        
        # Try CSV
        csv_shows = self.csv_source.get_all_shows()
        for show in csv_shows:
            show_date = show.get('date', '')
            show_location = show.get('location', '').lower()
            
            if show_date == date and location.lower() in show_location:
                return show
        
        return None
    
    def get_all_tours(self) -> List[Dict[str, Any]]:
        """Get tour information."""
        return self.kglw_source.get_all_tours()
    
    def get_show_poster(self, show_date: str) -> Optional[str]:
        """Get poster URL for a show by date."""
        return self.kglw_source.get_show_poster(show_date)
    
    def get_show_setlist_summary(self, show_date: str) -> Optional[Dict[str, Any]]:
        """Get setlist summary for a show by date."""
        return self.kglw_source.get_show_setlist_summary(show_date)