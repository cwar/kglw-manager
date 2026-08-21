"""YouTube search and quality analysis for upgrades."""

import re
import subprocess
import time
import yt_dlp
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from .utils import setup_logging
from .official_video_database import official_db
from .google_sheets_parser import GoogleSheetsParser
from .link_failure_tracker import LinkFailureTracker, FailureReason

logger = setup_logging()

class YouTubeSearcher:
    """Handle YouTube searching and quality analysis for upgrades."""
    
    # Official and trusted channels (in priority order)
    OFFICIAL_CHANNEL_ID = "UC4BR8d-GI5MQy8JMhKPdq8w"  # King Gizzard & The Lizard Wizard
    OFFICIAL_HANDLES = ("@kinggizzard", "@kinggizzardandthelizardwizard")
    PRIORITY_CHANNELS = [
        OFFICIAL_CHANNEL_ID,
        "@Dempsee",  # Dempsee - known for high quality livestream captures
    ]

    def _is_official_kglw(self, video: Dict) -> bool:
        """True if the video is from the official KGLW channel.

        Modern yt-dlp puts the @handle in uploader_id and the UC… id in
        channel_id, so both fields must be checked.
        """
        channel_id = video.get('channel_id') or ''
        uploader_id = video.get('uploader_id') or ''
        return (channel_id == self.OFFICIAL_CHANNEL_ID
                or uploader_id == self.OFFICIAL_CHANNEL_ID
                or uploader_id.lower() in self.OFFICIAL_HANDLES)

    def _is_dempsee(self, video: Dict) -> bool:
        """True if the video is from the trusted Dempsee channel."""
        uploader_id = (video.get('uploader_id') or '').lower()
        channel = (video.get('channel') or '').lower()
        uploader = (video.get('uploader') or '').lower()
        return uploader_id == '@dempsee' or 'dempsee' in channel or 'dempsee' in uploader
    
    # Minimum quality thresholds
    MIN_HEIGHT = 720   # Minimum 720p
    PREFER_HEIGHT = 1080  # Prefer 1080p+
    
    # Concert length expectations (in minutes)
    MIN_CONCERT_LENGTH = 45   # 45 minutes minimum
    MAX_CONCERT_LENGTH = 240  # 4 hours maximum
    IDEAL_MIN_LENGTH = 60     # 1 hour ideal minimum
    IDEAL_MAX_LENGTH = 180    # 3 hours ideal maximum
    
    def __init__(self):
        self.session_cache = {}  # Cache search results during session
        self._yt_dlp_available = None  # Cache yt-dlp availability check
        self._last_search_time = 0  # Track timing for rate limiting
        self.failure_tracker = LinkFailureTracker()
        self._consecutive_timeouts = 0  # Track consecutive timeouts
        
        # Initialize spreadsheet parser for curated links
        from .config import config
        spreadsheet_path = config.get_spreadsheet_path()
        self.spreadsheet_parser = GoogleSheetsParser(spreadsheet_path) if spreadsheet_path else None
        
        # Load dead link registry to avoid retrying known bad URLs
        self._dead_link_registry = self._load_dead_link_registry()
    
    def check_yt_dlp_availability(self) -> bool:
        """Check if yt-dlp is available and working."""
        if self._yt_dlp_available is not None:
            return self._yt_dlp_available
        
        try:
            # Find yt-dlp in current environment
            import shutil
            yt_dlp_path = shutil.which('yt-dlp')
            if not yt_dlp_path:
                logger.warning("yt-dlp not found in PATH")
                self._yt_dlp_available = False
                return False
            
            cmd = [yt_dlp_path, '--version']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            self._yt_dlp_available = result.returncode == 0
            if self._yt_dlp_available:
                logger.debug(f"yt-dlp version: {result.stdout.strip()}")
            else:
                logger.warning("yt-dlp not working properly")
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
            logger.warning(f"yt-dlp not available: {e}")
            self._yt_dlp_available = False
        
        return self._yt_dlp_available
    
    def search_for_upgrades_with_fallback(self, show: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Enhanced search with comprehensive fallback logic and failure tracking.

        Returns ALL candidates from ALL sources (spreadsheet + database + YouTube),
        prioritized by source reliability. This allows the download logic to try
        each candidate until one succeeds, rather than giving up after one source fails.
        """
        show_date = show['date']
        location = show.get('location', '')

        logger.info(f"🔄 Enhanced search for upgrades: {show_date} - {location}")

        all_candidates = []

        # Step 1: Try ALL spreadsheet links with failure tracking (highest priority)
        logger.info("📊 Phase 1: Collecting spreadsheet links...")
        spreadsheet_candidates = self._get_all_spreadsheet_candidates_with_tracking(show_date, location)

        if spreadsheet_candidates:
            logger.info(f"📊 Found {len(spreadsheet_candidates)} working spreadsheet links")
            all_candidates.extend(spreadsheet_candidates)
        else:
            logger.info("📊 No working spreadsheet links found")

        # Step 2: Check official video database (medium priority)
        logger.info("🎯 Phase 2: Checking official video database...")
        official_video = official_db.get_priority_video(show_date, location)
        if official_video:
            logger.info(f"🎯 Found in database: {official_video.get('title', 'Unknown')}")
            all_candidates.append(official_video)
        else:
            logger.info("🎯 No official database entry found")

        # Step 3: Add YouTube search results (lowest priority)
        logger.info("📡 Phase 3: Adding YouTube search results...")
        youtube_candidates = self._search_youtube_with_tracking(show)
        if youtube_candidates:
            logger.info(f"📡 Found {len(youtube_candidates)} YouTube search results")
            all_candidates.extend(youtube_candidates)
        else:
            logger.info("📡 No YouTube search results found")

        logger.info(f"🎯 Total candidates from all sources: {len(all_candidates)}")
        return all_candidates
    
    def _get_all_spreadsheet_candidates_with_tracking(self, show_date: str, location: str) -> List[Dict[str, Any]]:
        """Try all spreadsheet links with failure tracking and intelligent retry."""
        if not self.spreadsheet_parser or not self.spreadsheet_parser.ensure_loaded():
            return []
        
        # Get all YouTube links for this show
        youtube_links = self._get_spreadsheet_videos_raw(show_date, location)
        if not youtube_links:
            return []
        
        logger.info(f"🔗 Found {len(youtube_links)} spreadsheet links to test")
        
        working_candidates = []
        failed_urls = []
        
        for i, link_data in enumerate(youtube_links, 1):
            url = link_data['url']
            column_source = link_data.get('column', 'Link')
            
            # Check if we know this link has failed recently
            if self.failure_tracker.is_known_failed(url):
                logger.debug(f"⏭️  Skipping known failed link {i}/{len(youtube_links)}: {url[:50]}...")
                continue
            
            logger.info(f"🧪 Testing spreadsheet link {i}/{len(youtube_links)}: {url[:50]}...")
            
            # Test the link
            result = self._test_single_link_with_tracking(
                url, show_date, location, column_source
            )
            
            if result['success']:
                working_candidates.append(result['candidate'])
                logger.info(f"✅ Link {i} works: {result['candidate'].get('title', 'Unknown')}")
            else:
                failed_urls.append(url)
                logger.warning(f"❌ Link {i} failed: {result['error']}")
        
        if failed_urls:
            logger.info(f"📝 Tracked {len(failed_urls)} failed links for reporting")
        
        # Sort working candidates by quality
        working_candidates.sort(key=lambda x: x.get('quality_score', 0), reverse=True)
        
        return working_candidates
    
    def _test_single_link_with_tracking(self, url: str, show_date: str, location: str, column_source: str) -> Dict[str, Any]:
        """Test a single link and track failures with detailed error categorization."""
        try:
            # Get video info to test if link works
            quality_info = self.get_video_quality_info(url)
            
            if not quality_info:
                # Link failed - try to determine why
                error_msg = "Unable to extract video information"
                failure_reason = FailureReason.UNKNOWN_ERROR
                
                # Try to get more specific error by running yt-dlp directly
                try:
                    import subprocess
                    result = subprocess.run([
                        'yt-dlp', '--remote-components', 'ejs:github',
                        '--dump-json', '--no-download', url
                    ], capture_output=True, text=True, timeout=30)
                    
                    if result.returncode != 0:
                        error_msg = result.stderr
                        failure_reason = self.failure_tracker.classify_error(error_msg, url)
                        
                except Exception as e:
                    error_msg = f"Error testing link: {str(e)}"
                
                # Record the failure
                self.failure_tracker.record_failure(
                    url=url,
                    show_date=show_date,
                    show_location=location,
                    failure_reason=failure_reason,
                    error_message=error_msg,
                    column_source=column_source
                )
                
                return {
                    'success': False,
                    'error': error_msg,
                    'failure_reason': failure_reason.value
                }
            
            # Link works - create candidate data
            video_data = {
                'title': f"Spreadsheet: {url}",
                'url': url,
                'webpage_url': url,
                'source': 'spreadsheet',
                'priority_score': 3000,  # High priority for curated content
                'uploader': 'Spreadsheet Database',
                'description': f"Curated link from {column_source} column for {show_date}",
                'column_source': column_source
            }
            
            # Add quality information
            video_data.update(quality_info)
            
            # Calculate quality score
            height = quality_info.get('height') or 0
            duration = quality_info.get('duration') or 0
            
            if height >= 1080:
                video_data['quality_score'] = 100
            elif height >= 720:
                video_data['quality_score'] = 80
            elif height >= 480:
                video_data['quality_score'] = 60
            else:
                video_data['quality_score'] = 40
            
            # Boost score for good duration (1-3 hours)
            if 60 <= duration/60 <= 180:
                video_data['quality_score'] += 20
            
            return {
                'success': True,
                'candidate': video_data
            }
            
        except Exception as e:
            error_msg = f"Exception testing link: {str(e)}"
            failure_reason = self.failure_tracker.classify_error(error_msg, url)
            
            self.failure_tracker.record_failure(
                url=url,
                show_date=show_date,
                show_location=location,
                failure_reason=failure_reason,
                error_message=error_msg,
                column_source=column_source
            )
            
            return {
                'success': False,
                'error': error_msg,
                'failure_reason': failure_reason.value
            }
    
    def _get_spreadsheet_videos_raw(self, show_date: str, location: str) -> List[Dict[str, Any]]:
        """Get raw YouTube links from spreadsheet without quality testing."""
        if not self.spreadsheet_parser:
            return []

        self.spreadsheet_parser.ensure_loaded()

        try:
            # Try exact date match first
            youtube_links = self.spreadsheet_parser.get_youtube_links_for_show(date=show_date, location=location)
            
            if not youtube_links:
                # Try alternative date formats or location matching
                if location:
                    show_matches = self.spreadsheet_parser.search_shows_by_location(location)
                    
                    # Find closest date match within 1 day
                    closest_show = None
                    closest_diff = float('inf')
                    
                    for show in show_matches:
                        date_diff = abs(self._date_difference_days(show['date'], show_date))
                        if date_diff <= 1 and date_diff < closest_diff:
                            closest_diff = date_diff
                            closest_show = show
                    
                    if closest_show:
                        youtube_links = closest_show.get('youtube_links', [])
            
            return youtube_links or []
            
        except Exception as e:
            logger.error(f"Error getting spreadsheet videos: {e}")
            return []
    
    def _search_youtube_with_tracking(self, show: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search YouTube with failure tracking for any issues found."""
        show_date = show['date']
        location = show.get('location', '')
        
        # Check if yt-dlp is available
        if not self.check_yt_dlp_availability():
            error_msg = "yt-dlp is not available for YouTube search"
            logger.error(error_msg)
            return []
        
        try:
            # Use the existing YouTube search logic
            queries = self._generate_search_queries(show)
            logger.info(f"🔍 Running {len(queries)} YouTube search queries...")
            
            all_candidates = []
            found_official_source = False

            for i, query in enumerate(queries):
                logger.info(f"🔎 Query {i+1}/{len(queries)}: {query[:60]}...")
                candidates = self._search_youtube(query, show_date)
                all_candidates.extend(candidates)

                if any(self._is_official_kglw(c) or self._is_dempsee(c) for c in candidates):
                    found_official_source = True

                # Stop if we have enough results
                if len(all_candidates) >= 10:
                    break

            # Same pipeline as search_for_upgrades: dedupe, drop non-concerts,
            # rank best-first so download logic tries candidates in order
            unique = self._deduplicate_videos(all_candidates)
            filtered = self._filter_concert_candidates(unique, found_official_source)
            sorted_candidates = self._sort_by_upgrade_quality(filtered, show)

            if not sorted_candidates:
                # Don't record a failure-tracker entry here: these entries are
                # keyed by URL and a "youtube_search:<date>" sentinel would show
                # up in failure reports as if it were a real spreadsheet link.
                logger.info(f"📡 No YouTube results for {show_date}")

            return sorted_candidates

        except Exception as e:
            logger.error(f"YouTube search failed: {e}")
            return []
    
    def search_for_upgrades(self, show: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search for potential upgrades - checks spreadsheet first, then official database, then YouTube."""
        show_date = show['date']
        location = show.get('location', '')
        
        logger.info(f"Searching for upgrades for {show_date} - {location}")
        
        # First priority: Check spreadsheet for curated links
        logger.info("📊 Checking spreadsheet for curated links...")
        if self.spreadsheet_parser:
            if self.spreadsheet_parser.shows_data:
                logger.info(f"📊 Spreadsheet database loaded ({len(self.spreadsheet_parser.shows_data)} shows)")
            else:
                logger.info("📊 Spreadsheet parser exists but no data loaded")
        else:
            logger.info("📊 No spreadsheet parser configured")
        
        spreadsheet_videos = self._get_spreadsheet_videos(show_date, location)
        if spreadsheet_videos:
            logger.info(f"📊 Found {len(spreadsheet_videos)} curated link(s) in spreadsheet")
            return spreadsheet_videos
        else:
            logger.info("📊 No curated links found in spreadsheet")
        
        # Second priority: check official video database (learned + static)
        official_video = official_db.get_priority_video(show_date, location)
        if official_video:
            logger.info(f"🎯 Found in database: {official_video.get('title', 'Unknown')} ({official_video.get('quality_label', 'Unknown')})")
            # Return immediately - no need to search YouTube!
            return [official_video]
        
        # No cached video found, search YouTube and learn from results
        logger.info("📡 No cached video found, searching YouTube...")
        
        # Check if yt-dlp is available first
        if not self.check_yt_dlp_availability():
            logger.error("yt-dlp is not available, cannot search for upgrades")
            return []
        
        # Generate search queries
        queries = self._generate_search_queries(show)
        logger.info(f"🔍 Running {len(queries)} YouTube search queries...")
        
        all_candidates = []
        found_official_source = False
        
        for i, query in enumerate(queries):
            logger.info(f"🔎 Query {i+1}/{len(queries)}: {query[:60]}...")
            candidates = self._search_youtube(query, show_date)
            all_candidates.extend(candidates)
            
            # Check if we found any official/trusted sources in this batch
            for candidate in candidates:
                if self._is_official_kglw(candidate) or self._is_dempsee(candidate):
                    found_official_source = True
                    logger.info(f"🥇 Found official/trusted source: {candidate.get('title', 'Unknown')}")
                    break
            
            # Early exit conditions
            if found_official_source:
                if show.get('quick_search', True):  # Default to quick search
                    logger.info("🛑 Stopping search early - found official/trusted source (quick search mode)")
                    break
                elif len(all_candidates) >= 3:
                    logger.info("🛑 Stopping search early - found official/trusted source with sufficient results")
                    break
            elif len(all_candidates) >= 20:
                logger.debug("Found sufficient candidates, stopping search")
                break
        
        # Remove duplicates and filter out obvious non-concerts
        unique_candidates = self._deduplicate_videos(all_candidates)
        filtered_candidates = self._filter_concert_candidates(unique_candidates, found_official_source)
        sorted_candidates = self._sort_by_upgrade_quality(filtered_candidates, show)
        
        # Learn from official/trusted results for future searches
        if sorted_candidates:
            for candidate in sorted_candidates[:3]:  # Learn from top 3 results
                if self._is_official_kglw(candidate) or self._is_dempsee(candidate):
                    # Learn this video for future instant lookups
                    official_db.learn_from_search_result(show, candidate)
                    break  # Only learn from the first official source found
        
        logger.info(f"Found {len(sorted_candidates)} upgrade candidates")
        return sorted_candidates[:10]  # Return top 10 candidates
    
    def _generate_search_queries(self, show: Dict[str, Any]) -> List[str]:
        """Generate search queries for a show."""
        date = show['date']
        location = show.get('location', '')
        venue = show.get('venue', '')
        
        # Parse date for search variations
        year_full = None
        year_short = None
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            year_short = date_obj.strftime('%y')  # '24 for 2024
            year_full = date_obj.strftime('%Y')   # '2024'
            month_num = date_obj.strftime('%m')   # '11'
            month_name = date_obj.strftime('%B')  # 'November'
            month_abbr = date_obj.strftime('%b')  # 'Nov'
            
            date_variants = [
                date_obj.strftime('%Y-%m-%d'),   # 2024-11-15
                date_obj.strftime('%m/%d/%Y'),   # 11/15/2024
                date_obj.strftime('%B %d %Y'),   # November 15 2024
                date_obj.strftime('%b %d %Y'),   # Nov 15 2024
                f"'{year_short}",                 # '24 (KGLW official format)
                year_full,                       # 2024
                month_name,                      # November
                month_abbr                       # Nov
            ]
        except ValueError:
            date_variants = [date] if date else [""]
            # Extract year from any string that might contain a year
            year_match = re.search(r'20\d{2}', str(date) + str(location))
            if year_match:
                year_full = year_match.group()
                year_short = year_full[2:]
        
        # Clean location for search
        clean_location = re.sub(r'[()]', '', location).strip()
        location_parts = clean_location.split(',')
        main_location = location_parts[0].strip() if location_parts else clean_location
        
        # Check if current files are single songs (short duration) to prioritize full show searches
        # (interactive.py passes 'current_files'; collection scans pass 'files')
        current_files = show.get('current_files') or show.get('files') or []
        has_short_content = any(f.get('duration', 0) > 0 and f.get('duration', 0) < 900 for f in current_files)
        
        # Generate queries
        queries = []
        base_terms = ["King Gizzard", "KGLW", "King Gizzard & The Lizard Wizard"]
        
        # Priority queries for official channel format: "Live in [Location] '[year_short]"
        # Add the exact official video title format first
        queries.append(f'"King Gizzard & The Lizard Wizard" "Live in {main_location}"')
        queries.append(f'"King Gizzard" "Live in {main_location}"')
        if year_short:
            # These should match "King Gizzard & The Lizard Wizard - Live in Austin '24"
            queries.append(f'"King Gizzard & The Lizard Wizard" "Live in {main_location} \'{year_short}\'"')
            queries.append(f'"King Gizzard" "Live in {main_location} \'{year_short}\'"')
        
        for base_term in base_terms:
            # Location + year variants (official format)
            if year_full:
                queries.append(f'"{base_term}" "{main_location}" "{year_full}"')
            if year_short:
                queries.append(f'"{base_term}" "{main_location}" "\'{year_short}\'"')
            
            # Traditional date searches (for fan uploads)
            for date_variant in date_variants[:4]:  # Limit date variants
                queries.append(f'"{base_term}" "{date_variant}" "{main_location}"')
                
            # If we have short content, prioritize full show searches  
            if has_short_content:
                queries.insert(-len(queries)+2, f'"{base_term}" "{main_location}" {year_full} "full show"')
                queries.insert(-len(queries)+2, f'"{base_term}" "{main_location}" {year_full} "complete concert"')
                queries.insert(-len(queries)+2, f'"{base_term}" "{main_location}" "full setlist"')
            
            # Livestream specific
            queries.append(f'"{base_term}" "{main_location}" live')
            queries.append(f'"{base_term}" "{main_location}" livestream')
        
        return queries[:15]  # Increased for single-song upgrade searches
    
    def _search_youtube(self, query: str, show_date: str) -> List[Dict[str, Any]]:
        """Search YouTube using yt-dlp library with rate limiting protection."""
        logger.info(f"⏳ Searching YouTube (may take 30-60 seconds)...")
        
        # Implement rate limiting protection
        current_time = time.time()
        time_since_last = current_time - self._last_search_time
        
        # If we've had consecutive timeouts, implement exponential backoff
        if self._consecutive_timeouts > 0:
            backoff_delay = min(60, 2 ** self._consecutive_timeouts)  # Max 60 seconds
            logger.info(f"Rate limiting protection: waiting {backoff_delay}s after {self._consecutive_timeouts} timeouts")
            time.sleep(backoff_delay)
        elif time_since_last < 1.0:  # Minimum 1 second between searches
            time.sleep(1.0 - time_since_last)
        
        self._last_search_time = time.time()
        
        try:
            # Use yt-dlp library directly for better consistency
            # yt_dlp imported at module level
            
            ydl_opts = {
                'remote_components': ['ejs:github'],  # solve YouTube's JS challenge
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,  # Get full info
                'playlistend': 10,  # Limit to first 10 results
                'noplaylist': True,  # Don't follow playlists
                'nocheckcertificate': True,  # Bypass SSL issues
                'socket_timeout': 30,  # Socket timeout
                'retries': 1,  # Limit retries to avoid hanging
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            search_query = f"ytsearch10:{query}"
            logger.debug(f"🔍 Running YouTube search: {search_query}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Search YouTube and get video info
                search_results = ydl.extract_info(search_query, download=False)
                
                if not search_results or 'entries' not in search_results:
                    logger.debug("No search results found")
                    return []
                
                entries = search_results['entries']
                logger.info(f"📊 Processing {len(entries)} search results...")
                
                videos = []
                found_official_source = False
                
                for entry in entries:
                    if not entry:  # Skip None entries
                        continue
                        
                    # Sanitize the entry for consistency
                    video_info = ydl.sanitize_info(entry)
                    
                    # Check for audio-only content and mark it
                    is_audio_only = self._detect_audio_only(video_info, video_info.get('title', ''))
                    video_info['is_audio_only'] = is_audio_only
                    if is_audio_only:
                        video_info['audio_only_detected'] = True
                        # Reduce effective height for audio-only content
                        if video_info.get('height', 0) > 0:
                            video_info['original_height'] = video_info['height']
                            video_info['height'] = 0  # Treat as lowest quality
                    
                    # Check if this is from a priority channel
                    is_official = self._is_official_kglw(video_info) or self._is_dempsee(video_info)
                    
                    if is_official:
                        found_official_source = True
                        logger.info(f"🥇 Found official/trusted source: {video_info.get('title', 'Unknown')}")
                    
                    videos.append(video_info)
                    
                    # Early stop if we found official source and have enough results
                    if found_official_source and len(videos) >= 3:
                        logger.info("🛑 Stopping search early - found official/trusted source")
                        break
                
                # Filter for relevance and return
                relevant_videos = []
                for video_info in videos:
                    is_relevant = self._is_relevant_video(video_info, show_date)
                    if is_relevant:
                        relevant_videos.append(video_info)
                        logger.debug(f"✅ Added relevant video: {video_info.get('title', 'Unknown')}")
                    else:
                        logger.debug(f"❌ Rejected video: {video_info.get('title', 'Unknown')}")
                
                logger.info(f"✅ Found {len(relevant_videos)} relevant videos from search")
                self._consecutive_timeouts = 0  # Successful search resets backoff
                return relevant_videos
                
        except yt_dlp.utils.DownloadError as e:
            logger.warning(f"YouTube search failed for query: {query} - {e}")
            if 'too many requests' in str(e).lower() or '429' in str(e):
                logger.warning("Detected rate limiting from YouTube")
                self._consecutive_timeouts += 1
            return []
        except Exception as e:
            logger.error(f"Unexpected error in YouTube search for query: {query} - {e}")
            return []
    
    def _is_relevant_video(self, video_info: Dict, show_date: str) -> bool:
        """Check if video is relevant for the show date."""
        title = (video_info.get('title') or '').lower()
        description = (video_info.get('description') or '').lower()
        channel = (video_info.get('channel') or '').lower()
        uploader_id = video_info.get('uploader_id') or ''
        
        logger.debug(f"🔍 Relevance check for: '{title[:50]}...'")
        logger.debug(f"    Channel: {channel}")
        logger.debug(f"    Uploader ID: {uploader_id}")
        
        # Must contain King Gizzard references
        gizzard_terms = ['king gizzard', 'kglw', 'gizz']
        has_gizzard = any(term in title or term in description or term in channel
                         for term in gizzard_terms)
        
        logger.debug(f"    Has Gizzard terms: {has_gizzard}")
        if not has_gizzard:
            logger.debug(f"    ❌ No King Gizzard terms found")
            return False
        
        # Exclude other bands that might appear in searches
        exclude_bands = [
            'king stingray', 'stingray', 'king crimson', 'king diamond'
        ]
        
        has_excluded_band = any(band in title or band in description or band in channel
                               for band in exclude_bands)
        
        logger.debug(f"    Has excluded bands: {has_excluded_band}")
        if has_excluded_band:
            logger.debug(f"    ❌ Excluding video for other band: {title[:50]}...")
            return False
        
        # Check date proximity - be more lenient for official channels
        upload_date = video_info.get('upload_date')
        is_official_channel = (
            self._is_official_kglw(video_info) or
            self._is_dempsee(video_info) or
            'king gizzard' in channel or
            'kglw' in channel
        )
        
        logger.debug(f"    Upload date: {upload_date}")
        logger.debug(f"    Is official channel: {is_official_channel}")
        logger.debug(f"    Show date: {show_date}")
        
        if upload_date:
            try:
                upload_datetime = datetime.strptime(upload_date, '%Y%m%d')
                show_datetime = datetime.strptime(show_date, '%Y-%m-%d')
                
                days_diff = abs((upload_datetime - show_datetime).days)
                
                # More lenient for official channels (6 months vs 30 days)
                max_days = 180 if is_official_channel else 30
                
                logger.debug(f"    Days difference: {days_diff} (max allowed: {max_days})")
                
                if days_diff > max_days:
                    logger.debug(f"    ❌ Video too far from show date: {days_diff} days (max {max_days})")
                    return False
                else:
                    logger.debug(f"    ✅ Date check passed")
                    
            except ValueError as e:
                logger.debug(f"    ⚠️ Date parsing error: {e}")
        else:
            logger.debug(f"    ⚠️ No upload date available")
        
        # Filter out obvious non-concerts
        exclude_terms = [
            'interview', 'backstage', 'soundcheck', 'snippet', 'clip',
            'reaction', 'review', 'analysis', 'trailer', 'teaser',
            'behind the scenes', 'studio', 'acoustic'
        ]
        
        has_exclude_terms = any(term in title for term in exclude_terms)
        logger.debug(f"    Has exclude terms: {has_exclude_terms}")
        
        if has_exclude_terms:
            matching_terms = [term for term in exclude_terms if term in title]
            logger.debug(f"    ❌ Excluding video with terms: {matching_terms} in '{title[:50]}...'")
            return False
        
        logger.debug(f"    ✅ Video passed all relevance checks")
        return True
    
    def _deduplicate_videos(self, videos: List[Dict]) -> List[Dict]:
        """Remove duplicate videos based on video ID."""
        seen_ids = set()
        unique_videos = []
        
        for video in videos:
            # Extract video ID from URL or use the 'id' field
            video_id = video.get('id')
            if not video_id:
                # Extract ID from URL like https://www.youtube.com/watch?v=VIDEO_ID
                url = video.get('webpage_url') or video.get('url', '')
                if 'watch?v=' in url:
                    video_id = url.split('watch?v=')[1].split('&')[0]
                elif 'youtu.be/' in url:
                    video_id = url.split('youtu.be/')[1].split('?')[0]
            
            if video_id and video_id not in seen_ids:
                seen_ids.add(video_id)
                unique_videos.append(video)
            elif not video_id:
                # Fallback to URL-based dedup for videos without IDs
                url = video.get('webpage_url') or video.get('url')
                if url and url not in seen_ids:
                    seen_ids.add(url)
                    unique_videos.append(video)
        
        return unique_videos
    
    def _filter_concert_candidates(self, videos: List[Dict], found_official_source: bool) -> List[Dict]:
        """Filter out obvious non-concert videos, especially when official sources are found."""
        filtered_videos = []
        
        for video in videos:
            duration = video.get('duration') or 0
            title = (video.get('title') or '').lower()
            
            # Hard filters for obvious non-concerts
            if duration > 0:
                duration_minutes = duration / 60
                
                # If we found official sources, be more strict about duration
                min_duration = self.MIN_CONCERT_LENGTH if not found_official_source else 30
                
                if duration_minutes < min_duration:
                    logger.debug(f"Filtered out short video: {video.get('title', 'Unknown')} ({duration_minutes:.1f} min)")
                    continue
                    
                if duration_minutes > self.MAX_CONCERT_LENGTH:
                    logger.debug(f"Filtered out overly long video: {video.get('title', 'Unknown')} ({duration_minutes:.1f} min)")
                    continue
            
            # Filter out obvious single-song videos when we have official sources
            if found_official_source:
                single_song_indicators = [
                    'single', 'track', 'studio version', 'music video', 
                    'official video', 'acoustic version', 'solo'
                ]
                if any(indicator in title for indicator in single_song_indicators):
                    # Unless it's a really long "single" (probably mislabeled)
                    if duration > 0 and duration / 60 < 15:
                        logger.debug(f"Filtered out single song: {video.get('title', 'Unknown')}")
                        continue
            
            
            filtered_videos.append(video)
        
        return filtered_videos
    
    def _sort_by_upgrade_quality(self, videos: List[Dict], show: Dict[str, Any]) -> List[Dict]:
        """Sort videos by upgrade quality score."""
        scored_videos = []
        
        for video in videos:
            score = self._calculate_upgrade_score(video, show)
            scored_videos.append((score, video))
        
        # Sort by score (higher is better)
        scored_videos.sort(key=lambda x: x[0], reverse=True)
        
        return [video for score, video in scored_videos]
    
    def _calculate_upgrade_score(self, video: Dict, show: Dict[str, Any]) -> float:
        """Calculate upgrade quality score for a video."""
        score = 0.0
        
        # Channel priority (most important)
        channel = (video.get('channel') or '').lower()

        if self._is_official_kglw(video):
            score += 2000  # Highest priority for official channel
        elif self._is_dempsee(video):
            score += 1500  # High priority for Dempsee
        elif 'king gizzard' in channel or 'kglw' in channel:
            score += 1000  # Other official-seeming channels

        # Video quality
        height = video.get('height') or 0
        if height >= self.PREFER_HEIGHT:
            score += 200  # 1080p+
        elif height >= self.MIN_HEIGHT:
            score += 100  # 720p
        elif height > 0:
            score += 50   # Any known quality
        
        # Video length (concert length preference)
        duration = video.get('duration') or 0
        if duration > 0:
            duration_minutes = duration / 60
            
            if self.IDEAL_MIN_LENGTH <= duration_minutes <= self.IDEAL_MAX_LENGTH:
                score += 150  # Ideal concert length
            elif self.MIN_CONCERT_LENGTH <= duration_minutes <= self.MAX_CONCERT_LENGTH:
                score += 75   # Acceptable concert length
            elif duration_minutes < 10:
                score -= 100  # Probably just a clip
        
        # Date matching in title
        show_date = show.get('date') or ''
        title = (video.get('title') or '').lower()

        if show_date:
            # Check for date in various formats
            date_patterns = [
                show_date,  # 2024-09-09
                show_date.replace('-', '/'),  # 2024/09/09
                show_date.replace('-', '.'),  # 2024.09.09
            ]

            if any(date_pattern in title for date_pattern in date_patterns):
                score += 100
        
        # Location matching
        location = (show.get('location') or '').lower()
        if location:
            location_words = re.findall(r'\w+', location)
            title_words = re.findall(r'\w+', title)
            
            # Bonus for location matches
            matches = sum(1 for word in location_words if word in title_words and len(word) > 3)
            score += matches * 25
        
        # View count (popularity indicator)
        view_count = video.get('view_count') or 0
        if view_count > 1000:
            score += min(50, view_count / 10000)  # Cap at 50 points
        
        # Upload recency (prefer newer uploads for same show)
        upload_date = video.get('upload_date')
        if upload_date:
            try:
                upload_datetime = datetime.strptime(upload_date, '%Y%m%d')
                days_old = (datetime.now() - upload_datetime).days
                score += max(0, 30 - (days_old * 0.5))  # Newer is better, but cap effect
            except ValueError:
                pass
        
        logger.debug(f"Score {score:.1f} for: {video.get('title', 'Unknown')} | {channel}")
        return score
    
    def get_video_quality_info(self, url: str) -> Dict[str, Any]:
        """Get detailed quality information for a video."""
        logger.info(f"⏳ Getting video quality info (max 20s timeout)...")
        
        try:
            cmd = [
                'yt-dlp',
                '--remote-components', 'ejs:github',  # solve YouTube's JS challenge
                '--dump-json',
                '--no-download',
                '--no-check-certificate',
                '--socket-timeout', '15',  # Reduced from 20s  
                '--retries', '0',  # No retries for speed
                '--quiet',
                url
            ]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            try:
                stdout, stderr = process.communicate(timeout=20)  # Reduced from 30s
                
                if process.returncode == 0 and stdout:
                    import json
                    try:
                        # Handle single JSON object
                        quality_info = json.loads(stdout)
                        logger.debug(f"Got quality info: {quality_info.get('height', 'unknown')}p, {quality_info.get('duration', 0)}s")
                        return quality_info
                    except json.JSONDecodeError:
                        # Handle multiple JSON objects (playlists) - take the first video
                        try:
                            lines = stdout.strip().split('\n')
                            for line in lines:
                                if line.strip():
                                    quality_info = json.loads(line)
                                    logger.debug(f"Got playlist quality info: {quality_info.get('height', 'unknown')}p, {quality_info.get('duration', 0)}s")
                                    return quality_info
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse JSON for {url}: {e}")
                            # Try to extract just the video ID and retry with single video URL
                            if 'playlist?list=' in url:
                                logger.debug(f"Playlist detected, skipping quality info for: {url}")
                                return {'title': 'Playlist (quality unknown)', 'height': 720, 'duration': 3600}
                            return {}
                else:
                    logger.warning(f"Failed to get quality info for {url}")
                    if stderr:
                        logger.debug(f"Error: {stderr[:300]}")
                    return {}
                    
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout getting quality info for {url}")
                process.kill()
                try:
                    process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    process.terminate()
                return {}
                
        except Exception as e:
            logger.error(f"Error getting quality info for {url}: {e}")
            return {}
    
    def _get_playlist_quality_info(self, playlist_url: str) -> Dict[str, Any]:
        """Get quality info from the first video in a playlist."""
        logger.info(f"⏳ Getting playlist quality info (max 30s timeout)...")
        
        try:
            cmd = [
                'yt-dlp',
                '--remote-components', 'ejs:github',  # solve YouTube's JS challenge
                '--dump-json',
                '--no-download',
                '--no-check-certificate',
                '--socket-timeout', '10',  # Reduced from 20s
                '--quiet',
                '--playlist-items', '1',  # Only get first video
                '--retries', '0',  # No retries
                playlist_url
            ]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            try:
                stdout, stderr = process.communicate(timeout=30)  # Hard 30 second limit
                
                if process.returncode == 0 and stdout:
                    import json
                    # For playlists with --playlist-items 1, we should get a single JSON object
                    lines = stdout.strip().split('\n')
                    for line in lines:
                        if line.strip():
                            try:
                                quality_info = json.loads(line)
                                # Mark as playlist and add playlist URL
                                quality_info['is_playlist'] = True
                                quality_info['playlist_url'] = playlist_url
                                quality_info['title'] = f"Playlist: {quality_info.get('title', 'Unknown')}"
                                logger.info(f"✅ Got playlist quality: {quality_info.get('height', 'unknown')}p, {quality_info.get('duration', 0)}s")
                                return quality_info
                            except json.JSONDecodeError:
                                continue
                
                # Fallback if we can't get quality info
                logger.warning(f"⚠️  Could not get quality info for playlist (using defaults): {playlist_url}")
                return {
                    'title': 'Playlist (quality unknown)',
                    'height': 720,  # Conservative assumption
                    'duration': 3600,  # Assume 1 hour
                    'is_playlist': True,
                    'playlist_url': playlist_url
                }
                    
            except subprocess.TimeoutExpired:
                logger.warning(f"⏰ Playlist quality check timed out after 30s: {playlist_url}")
                process.kill()
                try:
                    process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    process.terminate()
                return {
                    'title': 'Playlist (timeout)',
                    'height': 720,
                    'duration': 3600,
                    'is_playlist': True,
                    'playlist_url': playlist_url
                }
                
        except Exception as e:
            logger.error(f"Error getting playlist quality info for {playlist_url}: {e}")
            return {
                'title': 'Playlist (error)',
                'height': 720,
                'duration': 3600,
                'is_playlist': True,
                'playlist_url': playlist_url
            }
    
    def _detect_audio_only(self, quality_info: Dict[str, Any], title_text: str = "") -> bool:
        """Detect if a video is audio-only content."""
        
        # Check title for audio-only indicators
        title_lower = title_text.lower()
        audio_only_keywords = [
            'audio only', 'audio-only', 'sound only', 'music only',
            'no video', 'pure audio', 'just audio', 'soundtrack only'
        ]
        
        if any(keyword in title_lower for keyword in audio_only_keywords):
            return True
        
        # A real video track in the formats list settles it, even when the
        # top-level height/width/vcodec fields are absent.
        formats = quality_info.get('formats') or []
        if any((fmt.get('vcodec') or 'none') != 'none'
               for fmt in formats if isinstance(fmt, dict)):
            return False

        # Check video metadata
        height = quality_info.get('height') or 0
        width = quality_info.get('width') or 0

        # If no video dimensions, likely audio-only
        if height == 0 and width == 0:
            return True
        
        # Check for very low resolution that suggests audio-only with static image
        if height > 0 and height <= 144 and width <= 256:
            # Could be audio-only with static image/slideshow
            return True
        
        # Check if video codec is missing but audio codec exists
        vcodec = quality_info.get('vcodec') or ''
        acodec = quality_info.get('acodec') or ''

        if (vcodec == 'none' or not vcodec) and acodec:
            return True

        # Check format note for audio-only indicators
        format_note = (quality_info.get('format_note') or '').lower()
        if 'audio only' in format_note:
            return True
        
        return False
    
    def validate_youtube_url(self, url: str) -> tuple[bool, str]:
        """Quick validation to check if YouTube URL is accessible before download attempt."""
        # First check if URL is in our dead link registry
        if self.is_dead_link(url):
            return False, "Previously confirmed unavailable (cached)"
        
        try:
            # yt_dlp imported at module level
            
            # Use minimal yt-dlp check with very short timeout
            ydl_opts = {
                'remote_components': ['ejs:github'],  # solve YouTube's JS challenge
                'quiet': True,
                'no_warnings': True, 
                'extract_flat': True,  # Don't get full info, just check availability
                'socket_timeout': 10,  # Quick timeout
                'retries': 0  # No retries for validation
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if info is None:
                    return False, "Video information unavailable"
                
                # Special handling for playlists - use deeper check with timeout
                if 'playlist' in url.lower() or info.get('_type') == 'playlist':
                    entries = info.get('entries', [])
                    if not entries:
                        self.add_dead_link(url, "Empty playlist")
                        return False, "Playlist is empty"
                    
                    # For playlists, do a quick check of the first video with full extraction
                    # to see if videos are actually available (not just metadata)
                    try:
                        first_entry = entries[0]
                        if first_entry:
                            first_video_url = first_entry.get('url') or f"https://youtube.com/watch?v={first_entry.get('id')}"
                            # Quick check with very short timeout
                            test_ydl_opts = {
                                'remote_components': ['ejs:github'],
                                'quiet': True,
                                'no_warnings': True,
                                'socket_timeout': 5,  # Very short timeout for test
                                'retries': 0
                            }
                            
                            with yt_dlp.YoutubeDL(test_ydl_opts) as test_ydl:
                                test_info = test_ydl.extract_info(first_video_url, download=False)
                                if test_info is None:
                                    self.add_dead_link(url, "First playlist video unavailable")
                                    return False, "First playlist video unavailable"
                    
                    except Exception as e:
                        # If we can't check the first video, the playlist is likely problematic
                        error_msg = str(e).lower()
                        if any(keyword in error_msg for keyword in 
                              ['unavailable', 'terminated', 'private', 'removed']):
                            self.add_dead_link(url, f"Playlist validation failed: {str(e)}")
                            return False, f"Playlist videos unavailable: {str(e)}"
                
                # Check for common unavailability indicators
                title = info.get('title', '')
                if 'unavailable' in title.lower() or 'private' in title.lower():
                    return False, f"Video unavailable: {title}"
                
                return True, "Available"
                
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in 
                  ['unavailable', 'private', 'terminated', 'removed', 'copyright']):
                # Add to dead link registry to avoid future attempts
                self.add_dead_link(url, f"DownloadError: {str(e)}")
                return False, f"Video unavailable: {str(e)}"
            return False, f"Access error: {str(e)}"
            
        except Exception as e:
            logger.debug(f"URL validation error for {url}: {e}")
            return False, f"Validation error: {str(e)}"
    
    def _load_dead_link_registry(self) -> set:
        """Load the dead link registry from cache directory."""
        try:
            from pathlib import Path
            import json
            
            cache_dir = Path.home() / '.kglw_manager' / 'cache'
            registry_file = cache_dir / 'dead_links.json'
            
            if registry_file.exists():
                with open(registry_file, 'r') as f:
                    data = json.load(f)
                    # Convert list back to set and filter out old entries (older than 30 days)
                    import time
                    current_time = time.time()
                    valid_entries = set()
                    for entry in data.get('urls', []):
                        if isinstance(entry, dict):
                            if current_time - entry.get('timestamp', 0) < 30 * 24 * 3600:  # 30 days
                                valid_entries.add(entry['url'])
                        else:
                            # Legacy format - just URL strings
                            valid_entries.add(entry)
                    
                    logger.debug(f"Loaded {len(valid_entries)} dead links from registry")
                    return valid_entries
        except Exception as e:
            logger.debug(f"Could not load dead link registry: {e}")
        
        return set()
    
    def _save_dead_link_registry(self):
        """Save the dead link registry to cache."""
        try:
            from pathlib import Path
            import json
            import time
            
            cache_dir = Path.home() / '.kglw_manager' / 'cache'
            cache_dir.mkdir(parents=True, exist_ok=True)
            registry_file = cache_dir / 'dead_links.json'
            
            # Save with timestamps for future cleanup
            current_time = time.time()
            data = {
                'urls': [{'url': url, 'timestamp': current_time} for url in self._dead_link_registry],
                'last_updated': current_time
            }
            
            with open(registry_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"Saved {len(self._dead_link_registry)} dead links to registry")
        except Exception as e:
            logger.warning(f"Could not save dead link registry: {e}")
    
    def add_dead_link(self, url: str, reason: str = "unavailable"):
        """Add a URL to the dead link registry."""
        self._dead_link_registry.add(url)
        self._save_dead_link_registry()
        logger.info(f"Added dead link to registry: {url} ({reason})")
    
    def is_dead_link(self, url: str) -> bool:
        """Check if URL is in the dead link registry."""
        return url in self._dead_link_registry
    
    def _get_spreadsheet_videos(self, show_date: str, location: str) -> List[Dict[str, Any]]:
        """Get video links from the spreadsheet for a specific show."""
        try:
            # Check if spreadsheet parser is available
            if not self.spreadsheet_parser:
                logger.debug(f"No spreadsheet parser available for {show_date}")
                return []
            
            # Ensure data is loaded
            if not self.spreadsheet_parser.shows_data:
                self.spreadsheet_parser.parse_html_export()
            
            logger.debug(f"Looking for spreadsheet match: date='{show_date}', location='{location}'")
            
            # Debug: show some sample keys and search for exact match
            if self.spreadsheet_parser.shows_data:
                sample_keys = list(self.spreadsheet_parser.shows_data.keys())[:3]
                logger.debug(f"Sample spreadsheet date keys: {sample_keys}")
                
                # Check if exact date exists
                if show_date in self.spreadsheet_parser.shows_data:
                    show_data = self.spreadsheet_parser.shows_data[show_date]
                    links_count = len(show_data.get('youtube_links', []))
                    logger.debug(f"Found exact date match with {links_count} YouTube links")
                    # Debug: Show what links we found
                    for i, link in enumerate(show_data.get('youtube_links', [])[:2], 1):
                        logger.debug(f"  Link {i}: {link.get('url', 'No URL')} - {link.get('text', 'No text')}")
                else:
                    logger.debug(f"No exact date match for '{show_date}' in {len(self.spreadsheet_parser.shows_data)} loaded shows")
                    # Debug: Check for similar dates
                    similar_dates = [key for key in self.spreadsheet_parser.shows_data.keys() if '2025-05-31' in key or '31-May-2025' in key or 'vilnius' in key.lower()]
                    if similar_dates:
                        logger.debug(f"Similar dates found: {similar_dates}")
            
            # Get links for exact date match
            youtube_links = self.spreadsheet_parser.get_youtube_links_for_show(date=show_date, location=location)
            
            if not youtube_links:
                logger.debug(f"No direct date match, trying alternative approaches")
                
                # Try alternative date formats - convert YYYY-MM-DD to DD-MMM-YYYY format
                try:
                    from datetime import datetime
                    parsed_date = datetime.strptime(show_date, '%Y-%m-%d')
                    alt_format = parsed_date.strftime('%d-%b-%Y')  # "31-May-2025"
                    logger.debug(f"Trying alternative date format: '{alt_format}'")
                    if alt_format in self.spreadsheet_parser.shows_data:
                        youtube_links = self.spreadsheet_parser.shows_data[alt_format].get('youtube_links', [])
                        logger.debug(f"Found match with alternative date format, {len(youtube_links)} links")
                        # Debug: Show what we found for this specific case
                        if show_date == "2025-05-31":
                            show_data = self.spreadsheet_parser.shows_data[alt_format]
                            logger.debug(f"DEBUG: 2025-05-31 case - show data: location='{show_data.get('location')}', venue='{show_data.get('venue')}'")
                            for i, link in enumerate(show_data.get('youtube_links', []), 1):
                                logger.debug(f"  Link {i}: {link.get('url', 'NO_URL')}")
                except Exception as e:
                    logger.debug(f"Date format conversion failed: {e}")
                
                if not youtube_links:
                    logger.debug(f"No alternative date match, trying location-based search for '{location}'")
                    # Try searching by location if no exact date match
                    show_matches = self.spreadsheet_parser.search_shows_by_location(location)
                    logger.debug(f"Location search returned {len(show_matches)} matches")
                    
                    # CRITICAL: Only use location matches if date is very close (same day or within 1 day)
                    closest_show = None
                    closest_diff = float('inf')
                    
                    for show in show_matches:
                        # Find closest date match
                        date_diff = abs(self._date_difference_days(show['date'], show_date))
                        logger.debug(f"Checking show {show['date']} vs {show_date}, diff: {date_diff} days")
                        
                        if date_diff <= 1 and date_diff < closest_diff:
                            closest_diff = date_diff
                            closest_show = show
                    
                    if closest_show:
                        youtube_links = closest_show.get('youtube_links', [])
                        logger.debug(f"Found close date match: {closest_show['date']}, {len(youtube_links)} links (diff: {closest_diff} days)")
                    else:
                        logger.debug(f"No location matches within 1 day of target date {show_date}")
                        
                        # Safety check: Log all location matches to detect wrong matches
                        if show_matches:
                            logger.warning(f"⚠️  Location search for '{location}' found {len(show_matches)} shows but none within 1 day:")
                            for show in show_matches[:5]:  # Log first 5 matches
                                days_diff = abs(self._date_difference_days(show['date'], show_date))
                                logger.warning(f"   - {show['date']} ({show.get('location', 'Unknown')}) - {days_diff} days away")
                            if len(show_matches) > 5:
                                logger.warning(f"   ... and {len(show_matches) - 5} more matches")
            
            if not youtube_links:
                return []
            
            # Convert spreadsheet links to our format and get quality info
            video_candidates = []
            logger.info(f"🔍 Found {len(youtube_links)} spreadsheet links - analyzing quality info...")
            
            # Debug: Show what links we're actually processing
            logger.debug(f"DEBUG: Processing {len(youtube_links)} links for {show_date}:")
            for i, link_data in enumerate(youtube_links, 1):
                logger.debug(f"  Link {i}: URL='{link_data.get('url', 'NO_URL')}', Text='{link_data.get('text', 'NO_TEXT')}', Column='{link_data.get('column', 'NO_COLUMN')}'")
            
            for i, link_data in enumerate(youtube_links, 1):
                url = link_data['url']
                
                # Show progress for slow operations
                logger.info(f"⏳ Analyzing spreadsheet link {i}/{len(youtube_links)}: {url[:50]}...")
                
                # Handle playlists differently - get info for first video
                if 'playlist?list=' in url or ('list=' in url and 'watch?v=' not in url):
                    logger.debug(f"Getting first video info from playlist: {url}")
                    quality_info = self._get_playlist_quality_info(url)
                else:
                    # Get quality information for individual videos
                    quality_info = self.get_video_quality_info(url)
                
                video_data = {
                    'title': f"Spreadsheet: {link_data.get('text', 'Link')}",
                    'url': url,
                    'webpage_url': url,
                    'source': 'spreadsheet',
                    'priority_score': 3000,  # Higher than official channels for curated content
                    'uploader': 'Spreadsheet Database',
                    'description': f"Curated link from gizzard_shows.html for {show_date}",
                }
                
                # Add quality information if available
                if quality_info:
                    # Check for audio-only content
                    is_audio_only = self._detect_audio_only(quality_info, link_data.get('text') or '')

                    video_data.update(quality_info)
                    video_data['is_audio_only'] = is_audio_only

                    # Add quality scoring
                    height = quality_info.get('height') or 0
                    duration = quality_info.get('duration') or 0
                    
                    # Penalize audio-only content heavily in scoring
                    if is_audio_only:
                        height = 0  # Treat as lowest video quality
                        video_data['audio_only_detected'] = True
                    
                    if height >= 1080:
                        video_data['quality_score'] = 100
                    elif height >= 720:
                        video_data['quality_score'] = 80
                    elif height >= 480:
                        video_data['quality_score'] = 60
                    else:
                        video_data['quality_score'] = 40
                    
                    # Boost score for good duration (concerts should be 60-180 minutes)
                    if 60 <= duration/60 <= 180:
                        video_data['quality_score'] += 20
                else:
                    # Default values if quality info unavailable
                    video_data.update({
                        'height': 720,  # Assume decent quality
                        'duration': 7200,  # Assume 2 hours
                        'quality_score': 90,  # High score for curated content
                        'quality_label': 'Unknown (Spreadsheet)'
                    })
                
                video_candidates.append(video_data)
            
            # Sort by quality score (highest first)
            video_candidates.sort(key=lambda x: x.get('quality_score', 0), reverse=True)
            
            logger.info(f"📊 Found {len(video_candidates)} spreadsheet videos for {show_date}")
            return video_candidates
            
        except Exception as e:
            logger.error(f"Error getting spreadsheet videos: {e}")
            return []
    
    def _date_difference_days(self, date1: str, date2: str) -> int:
        """Calculate difference between two dates in days."""
        try:
            from datetime import datetime
            d1 = datetime.strptime(date1, '%Y-%m-%d')
            d2 = datetime.strptime(date2, '%Y-%m-%d')
            return abs((d1 - d2).days)
        except ValueError:
            return 999  # Large number if dates can't be parsed