"""
KGLW.net API integration for song and show data.

Provides functionality to:
- Get song lists and identify songs from titles
- Get show data and setlists by date/location
- Cache API responses for performance
"""

import logging
import re
import requests
import time
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import json
from datetime import datetime, timedelta
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# kglw.net artist id for King Gizzard & the Lizard Wizard
KGLW_ARTIST_ID = 1

class KGLWApi:
    def __init__(self, cache_dir: Path):
        self.base_url = "https://kglw.net/api/v2"
        self.cache_dir = cache_dir / "kglw_api"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = 30

        # Read version for User-Agent
        try:
            version_file = Path(__file__).parent.parent / "VERSION"
            if version_file.exists():
                self.version = version_file.read_text().strip()
            else:
                self.version = "unknown"
        except:
            self.version = "unknown"

        # User-Agent header to identify the application
        self.user_agent = f"KGLW-Manager/{self.version} (https://github.com/yourusername/kglw-manager)"

        # Cache for songs list (updated weekly)
        self._songs_cache = None
        self._songs_cache_time = None

        # Cache for show data (per date)
        self._show_cache = {}
        self._show_cache_times = {}

    def _make_request(self, endpoint: str, max_retries: int = 3) -> Optional[Dict]:
        """Make a request to the KGLW.net API with retry logic and error handling.

        Implements exponential backoff for 403 errors (Cloudflare protection).
        """
        url = f"{self.base_url}/{endpoint}"
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'application/json'
        }

        for attempt in range(max_retries):
            try:
                logger.debug(f"Making API request to: {url} (attempt {attempt + 1}/{max_retries})")
                response = requests.get(url, headers=headers, timeout=self.timeout)

                # Handle 403 with exponential backoff
                if response.status_code == 403:
                    if attempt < max_retries - 1:
                        # Exponential backoff: 2, 4, 8 seconds
                        wait_time = 2 ** (attempt + 1)
                        logger.warning(f"API returned 403 (Cloudflare protection), retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"API request failed after {max_retries} attempts: 403 Forbidden")
                        return None

                response.raise_for_status()
                return response.json()

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403 and attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 1)
                    logger.warning(f"API returned 403, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                logger.warning(f"API request failed for {url}: {e}")
                return None
            except requests.exceptions.RequestException as e:
                logger.warning(f"API request failed for {url}: {e}")
                return None
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON response from {url}: {e}")
                return None

        return None
    
    def _is_cache_expired(self, cache_time: Optional[datetime], max_age_hours: int = 168) -> bool:
        """Check if cache is expired.

        Default: 168 hours (7 days) - extended to reduce API load during Cloudflare protection.
        """
        if not cache_time:
            return True
        return datetime.now() - cache_time > timedelta(hours=max_age_hours)
    
    def get_songs(self, force_refresh: bool = False) -> List[Dict]:
        """Get list of all songs from KGLW.net API."""
        # Check cache first
        if not force_refresh and self._songs_cache and not self._is_cache_expired(self._songs_cache_time):
            return self._songs_cache
        
        # Try to load from disk cache
        cache_file = self.cache_dir / "songs.json"
        if not force_refresh and cache_file.exists():
            try:
                cache_stat = cache_file.stat()
                cache_time = datetime.fromtimestamp(cache_stat.st_mtime)
                if not self._is_cache_expired(cache_time):
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        self._songs_cache = json.load(f)
                        self._songs_cache_time = cache_time
                        logger.debug(f"Loaded {len(self._songs_cache)} songs from disk cache")
                        return self._songs_cache
            except Exception as e:
                logger.warning(f"Failed to load songs from cache: {e}")
        
        # Fetch from API
        api_response = self._make_request("songs.json")
        if not api_response:
            # FALLBACK: Try expired disk cache if API fails
            if cache_file.exists():
                try:
                    logger.warning("API unavailable, using expired cache for songs list")
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        self._songs_cache = json.load(f)
                        return self._songs_cache
                except Exception as e:
                    logger.warning(f"Failed to load expired songs cache: {e}")
            # Final fallback: return memory cache or empty list
            return self._songs_cache or []

        # Extract data from API response structure
        songs_data = api_response.get('data', [])
        if not songs_data:
            logger.warning(f"API response has no 'data' field or it's empty: {api_response}")
            # FALLBACK: Try expired disk cache
            if cache_file.exists():
                try:
                    logger.warning("API returned empty data, using expired cache for songs list")
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        self._songs_cache = json.load(f)
                        return self._songs_cache
                except Exception as e:
                    logger.warning(f"Failed to load expired songs cache: {e}")
            return self._songs_cache or []
        
        # Cache in memory and disk
        self._songs_cache = songs_data
        self._songs_cache_time = datetime.now()
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(songs_data, f, indent=2)
            logger.debug(f"Cached {len(songs_data)} songs to disk")
        except Exception as e:
            logger.warning(f"Failed to write songs cache to disk: {e}")
        
        return songs_data
    
    def get_poster_url_for_date(self, date: str, force_refresh: bool = False) -> Optional[str]:
        """Get poster URL for a specific date from the uploads endpoint.

        Args:
            date: Show date in YYYY-MM-DD format
            force_refresh: Force refresh from API (bypass cache)

        Returns:
            URL to poster image, or None if not found
        """
        cache_file = self.cache_dir / f"poster_{date}.json"

        # Check disk cache first
        if not force_refresh and cache_file.exists():
            try:
                cache_stat = cache_file.stat()
                cache_time = datetime.fromtimestamp(cache_stat.st_mtime)
                if not self._is_cache_expired(cache_time, max_age_hours=336):  # Cache posters for 14 days
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cached_url = json.load(f).get('url')
                        logger.debug(f"Loaded poster URL for {date} from cache: {cached_url}")
                        return cached_url
            except Exception as e:
                logger.warning(f"Failed to load poster cache for {date}: {e}")

        # Fetch from uploads API
        api_response = self._make_request("uploads.json?limit=2000")
        if not api_response:
            # FALLBACK: Try to use expired cache if API is unavailable
            if cache_file.exists():
                try:
                    logger.warning(f"API unavailable, using expired cache for poster {date}")
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        return json.load(f).get('url')
                except Exception as e:
                    logger.debug(f"Failed to load expired poster cache for {date}: {e}")
            return None

        uploads_data = api_response.get('data', [])
        if not uploads_data:
            logger.warning("Uploads API response has no 'data' field or it's empty")
            # FALLBACK: Try expired cache
            if cache_file.exists():
                try:
                    logger.warning(f"API returned empty data, using expired cache for poster {date}")
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        return json.load(f).get('url')
                except Exception as e:
                    logger.debug(f"Failed to load expired poster cache for {date}: {e}")
            return None

        # Find poster for this date
        poster_url = None
        for upload in uploads_data:
            if upload.get('showdate') == date and upload.get('upload_type') == 'poster-art':
                poster_url = upload.get('URL')
                break

        # Cache the result (even if None, to avoid repeated API calls)
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({'url': poster_url, 'date': date}, f)
            logger.debug(f"Cached poster URL for {date}: {poster_url}")
        except Exception as e:
            logger.warning(f"Failed to cache poster URL for {date}: {e}")

        return poster_url

    def get_show_by_date(self, date: str, force_refresh: bool = False) -> Optional[Dict]:
        """Get show data for a specific date (YYYY-MM-DD format)."""
        # Check memory cache first
        if not force_refresh and date in self._show_cache:
            cache_time = self._show_cache_times.get(date)
            if not self._is_cache_expired(cache_time, max_age_hours=336):  # Cache shows for 14 days
                cached_data = self._show_cache[date]
                # Ensure cached data has the expected format
                if 'shownotes' in cached_data and 'setlist_notes' not in cached_data:
                    cached_data['setlist_notes'] = cached_data.get('shownotes', '')
                return cached_data

        # Try to load from disk cache
        cache_file = self.cache_dir / f"show_{date}.json"
        if not force_refresh and cache_file.exists():
            try:
                cache_stat = cache_file.stat()
                cache_time = datetime.fromtimestamp(cache_stat.st_mtime)
                if not self._is_cache_expired(cache_time, max_age_hours=336):  # Cache shows for 14 days
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        show_data = json.load(f)
                        # Ensure disk cached data has the expected format
                        if 'shownotes' in show_data and 'setlist_notes' not in show_data:
                            show_data['setlist_notes'] = show_data.get('shownotes', '')
                        self._show_cache[date] = show_data
                        self._show_cache_times[date] = cache_time
                        logger.debug(f"Loaded show {date} from disk cache")
                        return show_data
            except Exception as e:
                logger.warning(f"Failed to load show {date} from cache: {e}")
        
        # Extract year for API call
        try:
            year = date.split('-')[0]
        except (ValueError, IndexError):
            logger.error(f"Invalid date format: {date}")
            return None
        
        # Fetch from API
        api_response = self._make_request(f"setlists/showyear/{year}.json")
        if not api_response:
            # FALLBACK: Try to use expired cache if API is unavailable
            if cache_file.exists():
                try:
                    logger.warning(f"API unavailable, using expired cache for show {date}")
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        show_data = json.load(f)
                        if 'shownotes' in show_data and 'setlist_notes' not in show_data:
                            show_data['setlist_notes'] = show_data.get('shownotes', '')
                        return show_data
                except Exception as e:
                    logger.warning(f"Failed to load expired cache for {date}: {e}")
            return None

        # Extract data from API response structure
        shows_data = api_response.get('data', [])
        if not shows_data:
            logger.warning(f"Shows API response has no 'data' field or it's empty for year {year}")
            # FALLBACK: Try expired cache
            if cache_file.exists():
                try:
                    logger.warning(f"API returned empty data, using expired cache for show {date}")
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        show_data = json.load(f)
                        if 'shownotes' in show_data and 'setlist_notes' not in show_data:
                            show_data['setlist_notes'] = show_data.get('shownotes', '')
                        return show_data
                except Exception as e:
                    logger.warning(f"Failed to load expired cache for {date}: {e}")
            return None
        
        # The setlists endpoint returns one row per song. A single date can
        # cover several distinct shows - support acts and side events play the
        # same festival day (e.g. 2026-08-16 carries both King Gizzard and
        # Bullant) - so group by show_id and keep only this artist's set.
        date_rows = [show for show in shows_data if show.get('showdate') == date]
        if not date_rows:
            logger.debug(f"No show found for date {date}")
            return None

        shows_by_id: Dict[Any, List[Dict]] = {}
        for row in date_rows:
            shows_by_id.setdefault(row.get('show_id'), []).append(row)

        # Prefer King Gizzard (artist_id 1); fall back to the largest set.
        def _is_kglw(rows: List[Dict]) -> bool:
            first = rows[0]
            return (first.get('artist_id') == KGLW_ARTIST_ID
                    or 'king gizzard' in (first.get('artist') or '').lower())

        kglw_groups = [rows for rows in shows_by_id.values() if _is_kglw(rows)]
        candidate_groups = kglw_groups or list(shows_by_id.values())
        # Earliest showorder first, then the most complete set
        song_rows = min(
            candidate_groups,
            key=lambda rows: (rows[0].get('showorder') or 0, -len(rows)),
        )

        if len(shows_by_id) > 1:
            logger.debug(
                f"{len(shows_by_id)} shows listed on {date}; using "
                f"{song_rows[0].get('artist')} ({len(song_rows)} songs)"
            )

        show_data = dict(song_rows[0])
        # Only synthesize the setlist when the rows don't already carry one
        # (some responses embed a nested setlist on the show record itself).
        if not show_data.get('setlist'):
            show_data['setlist'] = song_rows
        
        # Transform API response to expected format
        # Map 'shownotes' field to 'setlist_notes' for consistent interface
        if 'shownotes' in show_data and 'setlist_notes' not in show_data:
            show_data['setlist_notes'] = show_data.get('shownotes', '')
        
        # Cache in memory and disk
        self._show_cache[date] = show_data
        self._show_cache_times[date] = datetime.now()
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(show_data, f, indent=2)
            logger.debug(f"Cached show {date} to disk")
        except Exception as e:
            logger.warning(f"Failed to write show {date} cache to disk: {e}")
        
        return show_data
    
    def identify_song_from_title(self, title: str, threshold: float = 0.6) -> Optional[Dict]:
        """
        Identify a song from a video title using fuzzy matching.
        
        Args:
            title: Video title to analyze
            threshold: Similarity threshold (0.0 to 1.0)
        
        Returns:
            Dictionary with song info if match found, None otherwise
        """
        songs = self.get_songs()
        if not songs:
            return None
        
        # Clean title for better matching
        clean_title = self._clean_title_for_matching(title)
        original_title = title.lower()
        
        best_match = None
        best_similarity = 0.0
        
        for song in songs:
            song_name = song.get('name', '').lower()
            if not song_name:
                continue
            
            # Calculate similarity with cleaned title
            similarity = SequenceMatcher(None, clean_title, song_name).ratio()
            
            # Also check similarity with original title (sometimes cleaning removes important parts)
            original_similarity = SequenceMatcher(None, original_title, song_name).ratio()
            similarity = max(similarity, original_similarity)
            
            # Boost score for exact substring matches (in either direction)
            if song_name in clean_title or song_name in original_title:
                similarity += 0.3  # Strong boost for exact song name match
            elif clean_title in song_name:  # Song name contains the cleaned title
                similarity += 0.25
            else:
                # Check for partial word matches (boost for each significant word match)
                song_words = [word for word in song_name.split() if len(word) > 3]
                title_words = [word for word in clean_title.split() if len(word) > 3]
                
                matching_words = 0
                for song_word in song_words:
                    for title_word in title_words:
                        if song_word == title_word or song_word in title_word or title_word in song_word:
                            matching_words += 1
                            break
                
                if song_words:  # Avoid division by zero
                    word_match_ratio = matching_words / len(song_words)
                    similarity += word_match_ratio * 0.2
            
            if similarity > best_similarity and similarity >= threshold:
                best_similarity = similarity
                best_match = song
        
        if best_match:
            logger.debug(f"Identified song '{best_match['name']}' from title '{title}' (similarity: {best_similarity:.2f})")
            return {
                'song': best_match,
                'similarity': best_similarity
            }
        
        return None
    
    def _clean_title_for_matching(self, title: str) -> str:
        """Clean video title for better song matching."""
        clean = title.lower()
        
        # Remove common video metadata
        patterns_to_remove = [
            r'\b\d{4}-\d{2}-\d{2}\b',  # Dates
            r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',  # Alternative date formats
            r'\bking gizzard.*?lizard wizard\b',  # Band name variations
            r'\bkglw\b',  # Abbreviation
            r'\blive\b',  # Live indicators
            r'\bconcert\b',
            r'\bshow\b',
            r'\bperformance\b',
            r'\b\d{3,4}p\b',  # Resolution indicators
            r'\bhd\b',
            r'\bfull\b',
            r'\bcomplete\b',
            r'\baudio\b',
            r'\bvideo\b',
            r'\brecording\b',
            r'\bofficial\b',
            r'\bunofficial\b',
            r'\bbootleg\b',
        ]
        
        for pattern in patterns_to_remove:
            clean = re.sub(pattern, ' ', clean)
        
        # Remove venue/location info (usually in parentheses or after dashes)
        clean = re.sub(r'\([^)]*\)', ' ', clean)
        clean = re.sub(r' - .*$', '', clean)
        clean = re.sub(r' @ .*$', '', clean)
        
        # Clean up whitespace
        clean = re.sub(r'\s+', ' ', clean).strip()
        
        return clean
    
    def get_setlist_for_show(self, date: str) -> List[str]:
        """Get setlist (list of song names) for a specific show date."""
        show_data = self.get_show_by_date(date)
        if show_data is not None and 'setlist' not in show_data:
            # Cached records written before setlist aggregation lack the key
            show_data = self.get_show_by_date(date, force_refresh=True)
        if not show_data:
            return []
        
        setlist = show_data.get('setlist', [])
        if not setlist:
            return []
        
        # Extract song names from setlist
        song_names = []
        for song_entry in setlist:
            if isinstance(song_entry, dict) and 'songname' in song_entry:
                song_names.append(song_entry['songname'])
        
        return song_names
    
    def is_same_song(self, title1: str, title2: str, threshold: float = 0.8) -> Tuple[bool, Optional[str]]:
        """
        Determine if two video titles represent the same song.
        
        Returns:
            (is_same_song, song_name_if_identified)
        """
        # Try to identify both titles
        song1 = self.identify_song_from_title(title1)
        song2 = self.identify_song_from_title(title2)
        
        # If both are identified and match the same song
        if song1 and song2:
            if song1['song']['id'] == song2['song']['id']:
                return True, song1['song']['name']
            else:
                return False, None
        
        # If only one is identified, they're likely different
        if song1 or song2:
            identified_song = song1 or song2
            return False, identified_song['song']['name']
        
        # If neither is identified, use direct similarity
        clean1 = self._clean_title_for_matching(title1)
        clean2 = self._clean_title_for_matching(title2)
        
        similarity = SequenceMatcher(None, clean1, clean2).ratio()
        return similarity >= threshold, None

    def download_poster_from_api(self, show_path: Path) -> Optional[Path]:
        """Download poster from KGLW.net API if available."""
        try:
            # Extract date from show path
            show_name = show_path.name
            date_part = show_name.split(" - ")[0] if " - " in show_name else show_name

            if len(date_part) < 10:
                logger.debug(f"Could not extract show date from '{show_name}'")
                return None

            show_date = date_part[:10]  # YYYY-MM-DD format

            # Prefer a poster URL carried on the show record; otherwise fall
            # back to the uploads API, which is where poster art normally lives.
            poster_url = None
            show_info = self.get_show_by_date(show_date)
            if show_info:
                poster_url = show_info.get('poster_image')
            if not poster_url:
                poster_url = self.get_poster_url_for_date(show_date)

            if not poster_url:
                logger.debug(f"No poster URL found in API data for {show_date}")
                return None

            if not poster_url.startswith(("http://", "https://")):
                logger.debug(f"Poster URL is not a direct link: {poster_url}")
                return None

            logger.info(f"📥 Downloading poster from API: {poster_url}")
            response = requests.get(poster_url, timeout=30)

            if response.status_code != 200:
                logger.warning(f"Failed to download poster: HTTP {response.status_code}")
                return None

            # Determine file extension from URL or content type
            url_lower = poster_url.lower()
            if url_lower.endswith((".jpg", ".jpeg")):
                ext = ".jpg"
            elif url_lower.endswith(".png"):
                ext = ".png"
            elif url_lower.endswith(".webp"):
                ext = ".webp"
            else:
                content_type = response.headers.get("content-type", "")
                if "jpeg" in content_type or "jpg" in content_type:
                    ext = ".jpg"
                elif "png" in content_type:
                    ext = ".png"
                elif "webp" in content_type:
                    ext = ".webp"
                else:
                    ext = ".jpg"  # Default

            poster_path = show_path / f"poster{ext}"
            with open(poster_path, "wb") as f:
                f.write(response.content)

            logger.info(f"✅ Downloaded poster: {poster_path}")
            return poster_path

        except Exception as e:
            logger.error(f"❌ Error downloading poster from API: {e}")

        return None
