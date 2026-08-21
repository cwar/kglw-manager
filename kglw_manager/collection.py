"""Main collection management functionality."""

import subprocess
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from .utils import setup_logging, is_video_file, parse_date_from_filename, format_duration
from .naming import NamingManager  
from .api_tour_manager import get_tour_manager
from .youtube_search import YouTubeSearcher
from .video_cache import VideoMetadataCache
from .download import DownloadManager
from .diskcache_collection import DiskcacheCollectionCache
# Backward compatibility alias
CollectionCache = DiskcacheCollectionCache
from .discord_notifications import DiscordNotifier
from .google_sheets_parser import GoogleSheetsParser
from .kglw_api import KGLWApi
from .config import config

# Rich console for upgrade output formatting
from rich.console import Console

# Import plex manager with conditional handling
try:
    from .plex_manager import PlexManager
    PLEX_AVAILABLE = True
except ImportError:
    PLEX_AVAILABLE = False
    PlexManager = None

logger = setup_logging()

# Export all imports for test mocking
__all__ = [
    'CollectionManager', 'CollectionCache', 'DiskcacheCollectionCache',
    'NamingManager', 'YouTubeSearcher', 'VideoMetadataCache',
    'DownloadManager', 'DiscordNotifier', 'GoogleSheetsParser',
    'KGLWApi', 'PlexManager', 'get_tour_manager'
]


class CollectionManager:
    """Main manager for KGLW concert collection."""
    
    def __init__(self, collection_path: str, mode: str = "movie", discord_webhook_url: Optional[str] = None):
        self.collection_path = Path(collection_path)
        self.mode = mode  # "movie" or "tv"
        
        # Initialize managers
        self.naming_manager = NamingManager()
        self.tour_manager = get_tour_manager()
        self.youtube_searcher = YouTubeSearcher()
        self.video_cache = VideoMetadataCache()
        self.download_manager = DownloadManager()
        self.collection_cache = CollectionCache()
        
        # Initialize Discord notifications (config > parameter > env)
        webhook_url = discord_webhook_url or config.get_discord_webhook_url()
        self.discord_notifier = DiscordNotifier(webhook_url)
        
        # Initialize spreadsheet parser with configured path
        spreadsheet_path = config.get_spreadsheet_path()
        self.sheets_parser = GoogleSheetsParser(spreadsheet_path)
        
        # Initialize KGLW.net API integration
        cache_dir = Path.home() / '.kglw_manager' / 'cache'
        self.kglw_api = KGLWApi(cache_dir)
        
        # Auto-load spreadsheet if configured
        if config.get('auto_load_spreadsheet') and spreadsheet_path:
            try:
                self.load_spreadsheet_data(spreadsheet_path)
                logger.info("📊 Auto-loaded spreadsheet data")
            except Exception as e:
                logger.warning(f"Failed to auto-load spreadsheet: {e}")
        
        # Initialize upgrade tracking
        self.upgrade_tracker = self._init_upgrade_tracker()
        
        # Initialize console for upgrade output
        self.console = Console()
        
        # Initialize Plex manager if available
        self.plex_manager = None
        if PLEX_AVAILABLE and config.get('enable_plex_integration', True):
            try:
                self.plex_manager = PlexManager()
                logger.info("📺 Plex integration initialized")
            except Exception as e:
                logger.warning(f"⚠️  Plex integration failed: {e}")
        
        logger.info(f"Collection manager initialized for: {collection_path}")
        logger.info(f"Mode: {mode.title()}")
    
    def scan_collection(self, force_rescan: bool = False) -> Dict[str, Any]:
        """Scan the collection and return structure."""
        logger.info("Scanning collection...")
        
        # Check if cache was recently cleared (treat as rescan to avoid notification spam)
        # Only check cache if not forcing rescan
        if force_rescan:
            cache_is_empty = True  # Treat force rescan as cache empty for notification logic
            is_rescan_operation = True
        else:
            cache_is_empty = not self.collection_cache.get_cached_collection(self.collection_path)
            is_rescan_operation = cache_is_empty
        
        # Check what has changed since last scan (unless forcing full rescan)
        if force_rescan:
            # Force rescan: scan all tour directories
            changed_tours = None
            print("🔄 Force rescan requested - scanning all tours")
        else:
            changed_tours = self.collection_cache.get_changed_tours(self.collection_path)
            # If no changes detected, try to use cached collection data
            if not changed_tours:
                cached_data = self.collection_cache.get_cached_collection(self.collection_path)
                if cached_data:
                    print("⚡ Using cached collection data (use --force to rescan)")
                    return cached_data

        tours = {}
        total_shows = 0
        total_videos = 0

        # Scan tour directories
        if self.collection_path.exists():
            tour_dirs = [d for d in self.collection_path.iterdir() if d.is_dir()]
            total_tours = len(tour_dirs)

            # This check was moved up before we reach this point

            # Handle force rescan vs incremental scan
            if force_rescan:
                # Force rescan: scan all tours
                changed_tours = {d.name for d in tour_dirs}
                print(f"🔄 Force rescanning all {len(changed_tours)} tours")
                tours = {}  # Don't use cached data
            else:
                print(f"🔍 Found {len(changed_tours)} changed tours out of {total_tours} total")
                # Get cached data for unchanged tours
                cached_data = self.collection_cache.get_cached_collection(self.collection_path)
                if cached_data:
                    tours = cached_data.get('tours', {}).copy()
                else:
                    # No usable cache to supply the unchanged tours. Scanning only
                    # the changed ones would cache a collection missing every other
                    # tour (and, if nothing looks changed, an empty one that then
                    # gets served as valid). Promote to a full rescan instead.
                    logger.info("Collection cache unavailable - promoting to full rescan")
                    print("🔄 Collection cache unavailable - scanning all tours")
                    changed_tours = {d.name for d in tour_dirs}

            # Scan changed tours
            changed_tours_list = list(changed_tours)
            new_shows = []  # Track new shows for Discord notifications

            for i, tour_dir in enumerate(tour_dirs):
                if tour_dir.name in changed_tours:
                    # Calculate progress based on changed tours index
                    changed_index = changed_tours_list.index(tour_dir.name)
                    progress = int((changed_index / len(changed_tours)) * 100) if changed_tours else 0

                    print(f"📁 Scanning {tour_dir.name} ({progress}%)", end='\r')
                    
                    # Get previous shows for this tour to detect new ones
                    old_tour_info = tours.get(tour_dir.name, {})
                    old_shows = set(old_tour_info.get('shows', {}).keys())
                    
                    tour_info = self._scan_tour_directory(tour_dir, force_rescan=force_rescan)
                    new_tour_shows = set(tour_info.get('shows', {}).keys())
                    
                    # Detect new shows
                    newly_added_shows = new_tour_shows - old_shows
                    for show_name in newly_added_shows:
                        show_info = tour_info['shows'][show_name]
                        show_info['tour'] = self.tour_manager.assign_tour(show_info)
                        new_shows.append(show_info)
                    
                    tours[tour_dir.name] = tour_info
                    
                    # Update cache for this tour
                    self.collection_cache.update_tour_cache(self.collection_path, tour_dir.name, tour_info)
            
            # Calculate totals
            total_shows = sum(len(tour_info.get('shows', {})) for tour_info in tours.values())
            total_videos = sum(
                sum(len(show.get('files', [])) for show in tour_info.get('shows', {}).values())
                for tour_info in tours.values()
            )
            
            # Show completion
            changed_count = len(changed_tours)
            # Show completion
            # Clear progress line and show completion
            print("\r" + " " * 80 + "\r", end="")  # Clear any progress line
            print(f"✅ Scanned {changed_count} changed tours, found {total_shows} shows, {total_videos} videos")
            
            # Send Discord notifications for new shows (only if not rescanning/cache was empty)
            if new_shows and not is_rescan_operation:
                print(f"📢 Notifying Discord about {len(new_shows)} new show(s)")
                for show_info in new_shows:
                    try:
                        # Add proper tour assignment for Discord notification
                        from .tours import TourManager
                        tour_manager = TourManager()
                        show_info_with_tour = show_info.copy()
                        show_info_with_tour['tour'] = tour_manager.assign_tour(show_info)
                        
                        self.discord_notifier.notify_new_show_added(show_info_with_tour)
                    except Exception as e:
                        logger.warning(f"Failed to send Discord notification for new show: {e}")
            elif new_shows and is_rescan_operation:
                print(f"🔄 Found {len(new_shows)} shows during rescan (notifications skipped)")
        else:
            print(f"❌ Collection path does not exist: {self.collection_path}")
        
        # Cache the complete collection
        collection_data = {
            'tours': tours,
            'total_tours': len(tours),
            'total_shows': total_shows,
            'total_videos': total_videos
        }
        
        self.collection_cache.cache_collection(self.collection_path, collection_data)
        
        logger.info(f"Collection scan complete: {len(tours)} tours, {total_shows} shows, {total_videos} videos")
        
        return {
            'tours': tours,
            'total_tours': len(tours),
            'total_shows': total_shows,
            'total_videos': total_videos
        }
    
    def _scan_tour_directory(self, tour_dir: Path, force_rescan: bool = False) -> Dict[str, Any]:
        """Scan a single tour directory using show-level caching.

        `force_rescan` bypasses the per-show cache. Without it, a forced rescan
        still served cached show entries whose files were recorded by a fast
        scan (quality 'unknown'), so callers that force a rescan specifically to
        get accurate quality - like find_upgrade_candidates - never saw any.
        """
        shows = {}

        show_dirs = [d for d in tour_dir.iterdir() if d.is_dir()]

        # Check if cache is empty to optimize bulk operations
        cache_is_empty = self.collection_cache.is_empty()

        for i, show_dir in enumerate(show_dirs):
            # Show progress for shows within tour (simplified)
            if len(show_dirs) > 10:  # Only show progress if there are many shows
                if i % 5 == 0:  # Only print every 5th show to reduce spam
                    progress = int((i / len(show_dirs)) * 100) if show_dirs else 0
                    print(f"  📅 Processing shows... ({progress}%)".ljust(50), end='\r')

            # Try to get cached show data first (skip expensive signature checks if cache is empty)
            cached_show = None
            if not force_rescan:
                cached_show = self.collection_cache.get_cached_show(
                    show_dir, skip_signature_check=cache_is_empty)
            if cached_show:
                # Use cached data
                if cached_show.get('files'):  # Only include shows with video files
                    shows[show_dir.name] = cached_show
            else:
                # Scan and cache new show data
                show_info = self._scan_show_directory(show_dir)
                if show_info['files']:  # Only include shows with video files
                    shows[show_dir.name] = show_info
                    # Cache the show data
                    self.collection_cache.cache_show(show_dir, show_info)

        # Clear any remaining progress line
        if len(show_dirs) > 10:
            print("\r" + " " * 50 + "\r", end="")

        return {
            'path': str(tour_dir),  # Convert Path to string for JSON serialization
            'shows': shows,
            'show_count': len(shows)
        }
    
    def _scan_show_directory(self, show_dir: Path) -> Dict[str, Any]:
        """Scan a single show directory."""
        files = []
        
        # Find video files (use fast scan for initial collection scanning)
        for file_path in show_dir.iterdir():
            if file_path.is_file() and is_video_file(file_path):
                file_info = self._analyze_video_file(file_path, fast_scan=True)
                files.append(file_info)
        
        # Extract show information from directory name
        show_info = self._parse_show_info_from_directory(show_dir)
        
        # Skip expensive setlist sorting during initial scan (can be done later if needed)
        # Sort files alphabetically for now
        files = sorted(files, key=lambda f: f.get('name', '').lower())
        
        return {
            'path': str(show_dir),  # Convert Path to string for JSON serialization
            'files': files,
            'date': show_info.get('date', ''),
            'location': show_info.get('location', ''),
            'venue': show_info.get('venue', '')
        }
    
    def _parse_show_info_from_directory(self, show_dir: Path) -> Dict[str, Any]:
        """Parse show information from directory name."""
        # Try to parse directory name: "YYYY-MM-DD - Location (Venue)"
        import re
        
        show_info = {'date': '', 'location': '', 'venue': ''}
        
        # Extract date
        date = parse_date_from_filename(show_dir.name)
        if date:
            show_info['date'] = date
        
        # Extract location and venue
        # Pattern: "YYYY-MM-DD - Location" or "YYYY-MM-DD - Location (Venue)"
        pattern = r'\d{4}-\d{2}-\d{2}\s*-\s*(.+?)(?:\s*\(([^)]+)\))?$'
        match = re.search(pattern, show_dir.name)
        
        if match:
            show_info['location'] = match.group(1).strip()
            if match.group(2):
                show_info['venue'] = match.group(2).strip()
        else:
            # Fallback: use directory name as location
            clean_name = re.sub(r'^\d{4}-\d{2}-\d{2}\s*-?\s*', '', show_dir.name)
            show_info['location'] = clean_name.strip()
        
        return show_info
    
    def _sort_files_by_setlist(self, files: List[Dict[str, Any]], show_date: str) -> List[Dict[str, Any]]:
        """Sort video files by setlist order if setlist data is available."""
        try:
            from .sources import DataSourceManager
            data_source = DataSourceManager()
            
            # Get setlist data for this show
            setlist_data = data_source.get_show_setlist_summary(show_date)
            if not setlist_data or 'sets' not in setlist_data:
                # No setlist data available, return files sorted alphabetically
                return sorted(files, key=lambda f: f.get('name', '').lower())
            
            # Create a mapping of song names to their setlist positions
            song_positions = {}
            for set_num, songs in setlist_data['sets'].items():
                if isinstance(songs, list):
                    for song_info in songs:
                        song_name = song_info.get('name', '').lower()
                        position = song_info.get('position', 999)
                        song_positions[song_name] = position
            
            # Sort files by matching them to setlist positions
            def get_sort_key(file_info):
                filename = file_info.get('name', '').lower()
                
                # First check for exact song matches in filename
                best_position = 999  # Default for unmatched files
                
                for song_name, position in song_positions.items():
                    # Clean song name for matching (remove punctuation and spaces)
                    clean_song = song_name.replace("'", "").replace("-", "").replace(" ", "").replace(".", "").lower()
                    clean_filename = filename.replace("'", "").replace("-", "").replace(" ", "").replace(".", "").lower()
                    
                    # Check if song name appears in filename
                    if clean_song in clean_filename:
                        best_position = min(best_position, position)
                
                # Full concerts get position 0 (first)
                if any(keyword in filename for keyword in ['concert', 'full', 'complete', 'entire']):
                    return (0, filename)
                
                # Setlist matches get their position + 1 (after full concert)
                if best_position < 999:
                    return (best_position + 1, filename)
                
                # Unknown files go at the end, sorted alphabetically
                return (999, filename)
            
            sorted_files = sorted(files, key=get_sort_key)
            
            # Add setlist completeness info
            matched_songs = set()
            total_songs = len(song_positions)
            
            for file_info in sorted_files:
                filename = file_info.get('name', '').lower()
                for song_name in song_positions.keys():
                    clean_song = song_name.replace("'", "").replace("-", "").replace(" ", "").replace(".", "").lower()
                    clean_filename = filename.replace("'", "").replace("-", "").replace(" ", "").replace(".", "").lower()
                    if clean_song in clean_filename:
                        matched_songs.add(song_name)
                        # Don't break - one file might contain multiple songs
            
            # Add metadata about setlist completeness to the first file
            if sorted_files:
                sorted_files[0]['setlist_completeness'] = {
                    'matched_songs': len(matched_songs),
                    'total_songs': total_songs,
                    'is_complete': len(matched_songs) == total_songs,
                    'missing_songs': list(set(song_positions.keys()) - matched_songs)
                }
            
            return sorted_files
            
        except Exception as e:
            logger.debug(f"Error sorting files by setlist for {show_date}: {e}")
            # Fallback to alphabetical sorting
            return sorted(files, key=lambda f: f.get('name', '').lower())
    
    def _analyze_video_file(self, file_path: Path, fast_scan: bool = False) -> Dict[str, Any]:
        """Analyze a video file."""
        # Basic file info (always fast). Built first so identity keys (path,
        # name, size) are always present even when the cache holds a partial
        # entry - callers do Path(file_info['path']) and would KeyError.
        file_info = {
            'path': str(file_path),  # Convert Path to string for JSON serialization
            'name': file_path.name,
            'size': file_path.stat().st_size,
            'is_plex_named': self.naming_manager.is_plex_named(file_path.name),
            'quality': 'unknown',
            'duration': 0,
            'resolution': 'unknown',
            'codec': 'unknown'
        }

        # Check cache for previously computed quality metadata
        cached_metadata = self.video_cache.get_metadata(file_path)
        if cached_metadata:
            logger.debug(f"Using cached metadata for {file_path.name}")
            file_info.update(cached_metadata)
            # Identity keys always reflect the file on disk
            file_info['path'] = str(file_path)
            file_info['name'] = file_path.name
            return file_info

        # Skip expensive ffprobe analysis during fast scanning
        if not fast_scan:
            # Get detailed quality info using ffprobe
            quality_info = self._analyze_video_quality(file_path)
            file_info.update(quality_info)

        # Cache the results (even if incomplete from fast scan)
        if not fast_scan:  # Only cache complete metadata
            self.video_cache.set_metadata(file_path, file_info)

        return file_info
    
    def _analyze_video_quality(self, video_file: Path) -> Dict[str, Any]:
        """Analyze video file quality using ffprobe (with caching)."""
        # Check cache first
        cached_metadata = self.video_cache.get_metadata(video_file)
        if cached_metadata:
            logger.debug(f"Using cached metadata for {video_file.name}")
            return cached_metadata
        
        quality_info = {
            'quality': 'unknown',
            'duration': 0,
            'resolution': 'unknown',
            'codec': 'unknown',
            'bitrate': 0,
            'fps': 0
        }
        
        try:
            # Use ffprobe to get video information
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', str(video_file)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                
                # Extract format information
                format_info = data.get('format', {})
                duration = float(format_info.get('duration', 0))
                bitrate = int(format_info.get('bit_rate', 0))
                
                # Find video stream
                video_streams = [s for s in data.get('streams', []) 
                               if s.get('codec_type') == 'video']
                
                if video_streams:
                    video_stream = video_streams[0]
                    width = int(video_stream.get('width', 0))
                    height = int(video_stream.get('height', 0))
                    codec = video_stream.get('codec_name', 'unknown')
                    # Parse the "num/den" frame rate without eval(): the value
                    # comes from file metadata, and "0/0" (common) would raise
                    # ZeroDivisionError and discard everything parsed above.
                    fps = self._parse_frame_rate(video_stream.get('r_frame_rate', '0/1'))


                    quality_info.update({
                        'duration': int(duration),
                        'resolution': f"{width}x{height}",
                        'quality': f"{height}p",
                        'codec': codec,
                        'bitrate': bitrate,
                        'fps': round(fps, 2) if fps else 0
                    })
                
                logger.debug(f"Analyzed {video_file.name}: {quality_info['quality']}, "
                           f"{quality_info['duration']}s")
            
        except subprocess.TimeoutExpired:
            logger.warning(f"ffprobe timeout for {video_file.name}")
        except Exception as e:
            logger.warning(f"Failed to analyze {video_file.name}: {e}")
        
        # Use fallback quality detection
        if quality_info['quality'] == 'unknown':
            quality_info.update(self._detect_quality_from_filename(video_file))
        
        return quality_info
    
    @staticmethod
    def _parse_frame_rate(rate: Any) -> float:
        """Parse an ffprobe 'num/den' frame rate into a float (0.0 if unusable)."""
        if not rate:
            return 0.0
        try:
            text = str(rate)
            if '/' in text:
                num, _, den = text.partition('/')
                den_value = float(den)
                return float(num) / den_value if den_value else 0.0
            return float(text)
        except (TypeError, ValueError):
            return 0.0

    def _detect_quality_from_filename(self, file_path: Path) -> Dict[str, Any]:
        """Detect quality from filename patterns."""
        filename = file_path.name.lower()
        # Size-based heuristics only apply to real files; filename-based
        # detection must work for paths that don't exist on disk.
        try:
            size_mb = file_path.stat().st_size / (1024 * 1024)
        except OSError:
            size_mb = None

        quality_info = {
            'quality': 'unknown',
            'resolution': 'unknown'
        }
        
        # Check for quality indicators in filename
        if any(term in filename for term in ['4k', '2160p', '2160']):
            quality_info.update({'quality': '2160p', 'resolution': '3840x2160'})
        elif any(term in filename for term in ['1080p', '1080', 'hd']):
            quality_info.update({'quality': '1080p', 'resolution': '1920x1080'})
        elif any(term in filename for term in ['720p', '720']):
            quality_info.update({'quality': '720p', 'resolution': '1280x720'})
        elif any(term in filename for term in ['480p', '480']):
            quality_info.update({'quality': '480p', 'resolution': '854x480'})
        elif any(term in filename for term in ['360p', '360']):
            quality_info.update({'quality': '360p', 'resolution': '640x360'})
        elif size_mb is not None and size_mb > 2000:  # Large file, probably high quality
            quality_info.update({'quality': '1080p+', 'resolution': 'unknown'})
        elif size_mb is not None and size_mb < 500:   # Small file, probably low quality
            quality_info.update({'quality': '480p-', 'resolution': 'unknown'})
        
        return quality_info
    
    def find_upgrade_candidates(self, filters: Dict[str, Any] = None, force: bool = False) -> List[Dict[str, Any]]:
        """Find shows that could benefit from upgrades."""
        logger.info("Finding upgrade candidates...")
        
        # Force a full rescan to get accurate upgrade candidate data
        collection = self.scan_collection(force_rescan=True)
        candidates = []
        
        for tour_name, tour_info in collection['tours'].items():
            for show_name, show_info in tour_info['shows'].items():
                # Get detailed upgrade analysis
                upgrade_analysis = self._analyze_upgrade_need(show_info, filters, force=force)

                # force bypasses upgrade tracking, but never a user's filters
                if (upgrade_analysis['needs_upgrade'] or force) and not upgrade_analysis.get('filtered_out'):
                    candidate = {
                        'tour': tour_name,
                        'show': show_name,
                        'date': show_info['date'],
                        'location': show_info['location'],
                        'venue': show_info['venue'],
                        'current_files': show_info['files'],
                        'path': show_info['path'],
                        'upgrade_reasons': upgrade_analysis.get('reasons', []),
                        'current_quality': upgrade_analysis.get('current_quality', 'Unknown')
                    }
                    candidates.append(candidate)
        
        # Sort candidates by date (newest first)
        def parse_date(candidate):
            date_str = candidate.get('date', '')
            try:
                # Handle various date formats
                if len(date_str) == 10 and date_str.count('-') == 2:  # YYYY-MM-DD
                    return date_str
                elif len(date_str) == 8 and date_str.isdigit():  # YYYYMMDD
                    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                else:
                    return '0000-00-00'  # Put unparseable dates at the end
            except:
                return '0000-00-00'
        
        candidates.sort(key=parse_date, reverse=True)  # Newest first
        
        logger.info(f"Found {len(candidates)} upgrade candidates (sorted by date)")
        return candidates
    
    def _needs_upgrade(self, show_info: Dict[str, Any], filters: Dict[str, Any] = None, force: bool = False) -> bool:
        """Check if a show needs upgrading."""
        files = show_info.get('files', [])
        if not files:
            return False
        
        # Check upgrade tracking to avoid re-processing (unless forced)
        show_date = show_info.get('date', '')
        if not force and show_date and self._should_skip_upgrade_check(show_date):
            return False
        
        # Check quality thresholds
        max_quality = 0
        min_duration = float('inf')
        has_phone_recording = False
        
        for file_info in files:
            # Extract quality number
            quality_str = file_info.get('quality', '0p')
            try:
                quality_num = int(quality_str.replace('p', '').replace('+', '').replace('-', ''))
                max_quality = max(max_quality, quality_num)
            except ValueError:
                pass
            
            # Check duration
            duration = file_info.get('duration', 0)
            if duration > 0:
                min_duration = min(min_duration, duration)
            
            # Check for phone recording indicators
            filename = file_info.get('name', '').lower()
            if any(term in filename for term in ['phone', 'mobile', 'amateur', 'audience']):
                has_phone_recording = True
        
        # Apply upgrade criteria
        needs_upgrade = False
        
        # Quality too low (less than 720p)
        if max_quality < 720:
            needs_upgrade = True
        
        # Duration too short for a full show (less than 1 hour) 
        # But only flag if it's a single song, not partial shows that might be complete setlist segments
        if min_duration < 3600:  # 1 hour
            # Only flag single songs (<=15min) and very short partials (<=30min) for upgrade
            # Don't flag longer partials (30-60min) as they might be intentional multi-song segments
            if min_duration <= 1800:  # 30 minutes or less - likely needs upgrading
                needs_upgrade = True
            # For 30-60 minute content, only flag if quality is also poor
            elif max_quality < 480:  # Poor quality AND medium duration = upgrade candidate
                needs_upgrade = True
        
        # Has phone recording (check for better sources)
        if has_phone_recording:
            needs_upgrade = True
        
        # Apply filters if provided
        if filters:
            year_filter = filters.get('year')
            if year_filter:
                show_date = show_info.get('date', '')
                if not show_date.startswith(str(year_filter)):
                    needs_upgrade = False
        
        return needs_upgrade
    
    def _analyze_upgrade_need(self, show_info: Dict[str, Any], filters: Dict[str, Any] = None,
                              force: bool = False) -> Dict[str, Any]:
        """Analyze if a show needs upgrading and return detailed reasons.

        `force` bypasses the upgrade-tracking skip only; it never overrides
        user-supplied filters such as --year.
        """
        files = show_info.get('files', [])
        if not files:
            return {'needs_upgrade': False, 'reasons': [], 'current_quality': 'No files'}

        # Check upgrade tracking to avoid re-processing
        show_date = show_info.get('date', '')
        if show_date and not force and self._should_skip_upgrade_check(show_date):
            return {
                'needs_upgrade': False, 
                'reasons': ['Recently checked or upgraded'],
                'current_quality': 'Skipped (tracking)'
            }
        
        # Analyze quality and duration
        max_quality = 0
        min_duration = float('inf')
        has_phone_recording = False
        quality_issues = []

        quality_measured = False
        for file_info in files:
            # Extract quality number
            quality_str = file_info.get('quality', '0p')
            try:
                quality_num = int(quality_str.replace('p', '').replace('+', '').replace('-', ''))
                max_quality = max(max_quality, quality_num)
                quality_measured = True
            except ValueError:
                # 'unknown' - the file hasn't been ffprobed yet
                pass

            # Check duration
            duration = file_info.get('duration', 0)
            if duration > 0:
                min_duration = min(min_duration, duration)

            # Check for phone recording indicators
            filename = file_info.get('name', '').lower()
            if any(term in filename for term in ['phone', 'mobile', 'amateur', 'audience']):
                has_phone_recording = True

        # Build reasons list
        reasons = []
        needs_upgrade = False

        # Quality too low (less than 720p). Only claim this when the resolution
        # was actually measured - collection scans are fast scans that leave
        # quality 'unknown', and reporting that as "0p < 720p" previously
        # flagged every unanalysed show as an upgrade candidate.
        if not quality_measured:
            reasons.append("Quality not analyzed yet (run 'analyze-quality')")
        elif max_quality < 720:
            reasons.append(f"Low resolution ({max_quality}p < 720p)")
            needs_upgrade = True
        
        # Duration too short (less than 1 hour, likely incomplete)
        if min_duration < 3600:  # 1 hour
            duration_min = min_duration / 60 if min_duration != float('inf') else 0
            reasons.append(f"Short duration ({duration_min:.0f}min < 60min - likely incomplete)")
            needs_upgrade = True
        
        # Has phone recording (check for better sources)
        if has_phone_recording:
            reasons.append("Contains phone/amateur recording")
            needs_upgrade = True
        
        # Apply filters if provided
        filtered_out = False
        if filters:
            year_filter = filters.get('year')
            if year_filter:
                show_date = show_info.get('date', '')
                if not show_date.startswith(str(year_filter)):
                    needs_upgrade = False
                    filtered_out = True
                    reasons = ['Filtered out by year']
        
        # Build current quality summary
        if min_duration == float('inf'):
            duration_str = "Unknown duration"
        else:
            # Use consistent duration formatting
            duration_str = format_duration(int(min_duration))
        
        quality_str_display = f"{max_quality}p" if quality_measured else "Unknown quality"
        current_quality = f"{quality_str_display}, {duration_str}"
        if has_phone_recording:
            current_quality += ", amateur source"
        
        return {
            'needs_upgrade': needs_upgrade,
            'filtered_out': filtered_out,
            'reasons': reasons if reasons else ['Good quality and duration'],
            'current_quality': current_quality,
            'max_quality': max_quality,
            'min_duration': min_duration,
            'has_phone_recording': has_phone_recording
        }
    
    def perform_upgrade(self, show_path, candidate_video: Dict[str, Any], format_id: str = 'best') -> bool:
        """Perform an upgrade for a show."""
        logger.info(f"Performing upgrade for show in {show_path}")
        
        # Ensure show_path is a Path object
        if isinstance(show_path, str):
            show_path = Path(show_path)
        
        # Parse show info from path including files
        show_info = self._scan_show_directory(show_path)
        
        # Analyze and display upgrade reasoning
        analysis = self._analyze_upgrade_need(show_info)
        show_date = show_info.get('date', 'Unknown Date')
        show_location = show_info.get('location', 'Unknown Location')
        
        # Log current show characteristics
        current_files = show_info.get('files', [])
        if current_files:
            current_qualities = [f.get('quality', 'Unknown') for f in current_files]
            current_durations = [format_duration(f.get('duration', 0)) for f in current_files]
            self.console.print(f"\n📊 [cyan]Current show characteristics:[/cyan]")
            self.console.print(f"    Quality: {', '.join(current_qualities)} (best: {analysis.get('current_quality', 'Unknown')})")
            self.console.print(f"    Duration: {', '.join(current_durations)} (min: {format_duration(analysis.get('min_duration', 0))})")
        
        # Log candidate characteristics
        candidate_quality_str = f"{candidate_video.get('height', 0)}p" if candidate_video.get('height') else "Unknown"
        candidate_duration_str = format_duration(candidate_video.get('duration', 0))
        candidate_title = candidate_video.get('title', 'Unknown')[:80] + "..." if len(candidate_video.get('title', '')) > 80 else candidate_video.get('title', 'Unknown')
        
        self.console.print(f"\n🎯 [green]Candidate video:[/green]")
        self.console.print(f"    Title: {candidate_title}")
        self.console.print(f"    Quality: {candidate_quality_str}")
        self.console.print(f"    Duration: {candidate_duration_str}")
        self.console.print(f"    Source: {candidate_video.get('source', 'YouTube')}")
        
        # CRITICAL SAFETY CHECK: Prevent downloading wrong show
        if self._is_wrong_show_match(show_date, show_location, candidate_video):
            self.console.print(f"\n🚨 [red]SAFETY ABORT: Candidate appears to be for wrong show![/red]")
            self.console.print(f"📊 Expected: {show_date} - {show_location}")
            self.console.print(f"📊 Candidate: {candidate_title}")
            self.console.print(f"📊 This would be dangerous - skipping to prevent wrong download")
            return False
        
        # Validate that the candidate is actually an improvement
        upgrade_result, rejection_reason = self._is_meaningful_upgrade(show_info, candidate_video, analysis)
        if not upgrade_result:
            self.console.print(f"\n⚠️  [yellow]Skipping upgrade for {show_date} - {show_location}[/yellow]")
            self.console.print(f"📊 Reason: {rejection_reason}")
            return False
        
        self.console.print(f"\n🔄 [bold cyan]Upgrading {show_date} - {show_location}[/bold cyan]")
        self.console.print(f"📊 [yellow]Current Quality:[/yellow] {analysis['current_quality']}")
        
        if analysis['reasons']:
            self.console.print(f"📝 [yellow]Upgrade Reasons:[/yellow]")
            for reason in analysis['reasons']:
                self.console.print(f"   • {reason}")
        
        # Show candidate info
        candidate_title = candidate_video.get('title', 'Unknown Video')
        candidate_quality = candidate_video.get('height') or 0
        candidate_duration = candidate_video.get('duration') or 0
        candidate_uploader = candidate_video.get('uploader', 'Unknown')
        
        # Format duration
        if candidate_duration > 0:
            duration_hours = candidate_duration // 3600
            duration_minutes = (candidate_duration % 3600) // 60
            if duration_hours > 0:
                duration_str = f"{duration_hours}h {duration_minutes}min"
            else:
                duration_str = f"{duration_minutes}min"
        else:
            duration_str = "Unknown length"
        
        self.console.print(f"📹 [green]New Source:[/green] {candidate_title}")
        
        # Get quality profile to show effective download quality
        from .quality_config import QualityManager
        quality_manager = QualityManager()
        active_profile = quality_manager.get_active_profile()
        
        # Show effective quality (what will actually be downloaded)
        if candidate_quality > 0:
            effective_quality = min(candidate_quality, active_profile.max_resolution)
            quality_display = f"{candidate_quality}p"
            if candidate_quality > active_profile.max_resolution:
                quality_display = f"{candidate_quality}p → {effective_quality}p"
        else:
            quality_display = "Unknown"
        
        # Check for audio-only content and display warning
        if candidate_video.get('is_audio_only', False) or candidate_video.get('audio_only_detected', False):
            self.console.print(f"   🎬 Quality: [bold yellow]{quality_display}[/bold yellow] [red]⚠️  AUDIO ONLY[/red]")
        else:
            self.console.print(f"   🎬 Quality: [bold]{quality_display}[/bold]")
            
        self.console.print(f"   ⏱️  Length: {duration_str}")
        self.console.print(f"   👤 Uploader: {candidate_uploader}")
        
        # Validate URL before attempting download
        candidate_url = candidate_video.get('webpage_url', candidate_video.get('url', ''))
        if candidate_url:
            self.console.print("🔍 [yellow]Validating video availability...[/yellow]", end=" ")
            is_valid, validation_msg = self.youtube_searcher.validate_youtube_url(candidate_url)
            
            if not is_valid:
                self.console.print(f"❌ [red]Link unavailable: {validation_msg}[/red]")
                self.console.print("⏭️  [yellow]Skipping this upgrade candidate[/yellow]")
                return False
            else:
                self.console.print("✅ [green]Available[/green]")
        
        self.console.print()
        
        # Determine if we should backup existing files
        # For different single songs, we want to ADD to the collection, not replace
        backup_existing = True
        
        # Get current file info for analysis
        current_min_duration = analysis.get('min_duration', 0)
        
        # Check if this is adding a different single song (should not backup/replace)
        if candidate_duration > 0 and current_min_duration > 0:
            SINGLE_SONG_MAX = 900  # 15 minutes
            if (candidate_duration <= SINGLE_SONG_MAX and 
                current_min_duration <= SINGLE_SONG_MAX and 
                current_files):
                
                # Check if they're different songs
                current_title = current_files[0].get('title', '')
                candidate_title = candidate_video.get('title', '')
                is_same_song, identified_song = self.kglw_api.is_same_song(current_title, candidate_title)
                
                if not is_same_song:
                    backup_existing = False  # Don't backup - we're collecting different songs
                    song_info = f" (adding: {identified_song})" if identified_song else ""
                    self.console.print(f"🎵 [green]Adding different single song to collection{song_info}[/green]")
        
        # Use download manager to download directly to existing show directory
        downloaded_file = self.download_manager.download_upgrade_to_existing_dir(
            candidate_video, 
            show_path,  # Use the existing show path directly
            show_info,
            backup_existing=backup_existing,
            format_id=format_id,
            quiet_mode=False  # Show progress bars for downloads
        )
        
        # Track the upgrade attempt
        show_date = show_info.get('date', '')
        
        if downloaded_file:
            logger.info(f"Upgrade successful: {downloaded_file}")
            if show_date:
                self._mark_upgrade_attempt(show_date, success=True)
            
            # Send Discord notification for successful upgrade
            try:
                # Determine if this is a new show or an upgrade
                current_files = show_info.get('files', [])
                is_new_show = len(current_files) == 0
                
                # Calculate effective download quality
                from .quality_config import QualityManager
                quality_manager = QualityManager()
                active_profile = quality_manager.get_active_profile()
                candidate_quality = candidate_video.get('height') or 0
                effective_quality = min(candidate_quality, active_profile.max_resolution) if candidate_quality > 0 else candidate_quality
                
                # Add effective quality to candidate info
                enhanced_candidate_info = candidate_video.copy()
                enhanced_candidate_info['effective_quality'] = effective_quality
                
                # Ensure tour assignment for Discord notification
                show_info_with_tour = show_info.copy()
                if 'tour' not in show_info_with_tour or not show_info_with_tour.get('tour'):
                    from .tours import TourManager
                    tour_manager = TourManager()
                    show_info_with_tour['tour'] = tour_manager.assign_tour(show_info)
                
                if is_new_show:
                    self.discord_notifier.notify_new_show_added(
                        show_info=show_info_with_tour,
                        candidate_info=enhanced_candidate_info
                    )
                else:
                    self.discord_notifier.notify_show_upgraded(
                        show_info=show_info_with_tour,
                        upgrade_reasons=analysis.get('reasons', []),
                        candidate_info=enhanced_candidate_info
                    )
            except Exception as e:
                logger.warning(f"Failed to send Discord notification for upgrade: {e}")
            
            return True
        else:
            logger.error("Upgrade failed")
            if show_date:
                self._mark_upgrade_attempt(show_date, success=False)
            return False
    
    def cleanup_stale_cache(self):
        """Clean up stale cache entries."""
        self.video_cache.cleanup_stale_entries()

    def import_video_file(self, file_path: Path, show_info: Dict[str, Any],
                         youtube_url: Optional[str] = None,
                         move_file: bool = True) -> Optional[Path]:
        """Import an existing video file into the collection.

        Args:
            file_path: Path to the video file to import
            show_info: Dictionary with keys: date, location, venue
            youtube_url: Optional YouTube URL for reference metadata
            move_file: If True, move the file; if False, copy it

        Returns:
            Path to the imported file in the collection, or None if failed
        """
        from shutil import move, copy2

        logger.info(f"Importing video file: {file_path}")

        # Validate file exists and is a video
        if not file_path.exists():
            logger.error(f"File does not exist: {file_path}")
            return None

        if not is_video_file(file_path):
            logger.error(f"File is not a video: {file_path}")
            return None

        # Validate required show info
        if not show_info.get('date'):
            logger.error("Show date is required for import")
            return None
        if not show_info.get('location'):
            logger.error("Show location is required for import")
            return None

        # Analyze video file to get metadata
        logger.info("Analyzing video file metadata...")
        video_metadata = self._analyze_video_file(file_path, fast_scan=False)

        # Assign tour using API data
        tour_name = self.tour_manager.assign_tour(show_info)
        normalized_tour_name = self.tour_manager.normalize_tour_name_for_filesystem(tour_name)
        tour_dir = self.collection_path / normalized_tour_name

        # Log tour assignment
        api_tour = self.tour_manager.get_tour_for_date(show_info.get('date', ''))
        if api_tour:
            logger.info(f"🎯 API assigned tour: {api_tour} → {normalized_tour_name}")
        else:
            logger.debug(f"No API data for {show_info.get('date', '')}, using fallback: {tour_name}")

        # Create show directory
        show_dir_name = self.naming_manager.generate_directory_name(show_info)
        show_dir = tour_dir / show_dir_name
        show_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Importing to: {show_dir}")

        # Generate proper Plex filename
        file_extension = file_path.suffix
        plex_filename = self.naming_manager.generate_plex_filename(
            show_info, file_extension
        )
        plex_path = show_dir / plex_filename

        # Check if file already exists
        if plex_path.exists():
            logger.warning(f"File already exists at destination: {plex_path}")
            # Generate unique filename
            base = plex_path.stem
            counter = 1
            while plex_path.exists():
                plex_path = show_dir / f"{base} ({counter}){file_extension}"
                counter += 1
            logger.info(f"Using unique filename: {plex_path.name}")

        # Move or copy the file
        try:
            if move_file:
                logger.info(f"Moving file to: {plex_path}")
                move(str(file_path), str(plex_path))
            else:
                logger.info(f"Copying file to: {plex_path}")
                copy2(str(file_path), str(plex_path))

            logger.info(f"✅ File imported successfully: {plex_path.name}")
        except Exception as e:
            logger.error(f"Failed to import file: {e}")
            return None

        # Create download metadata file if YouTube URL provided
        if youtube_url:
            try:
                from .download_metadata import DownloadMetadataDetector
                metadata_detector = DownloadMetadataDetector()

                # Create a minimal candidate info for metadata
                candidate_info = {
                    'url': youtube_url,
                    'webpage_url': youtube_url,
                    'title': f"Imported: {show_info.get('location', 'Unknown')}",
                    'source': 'manual_import'
                }

                metadata_path = metadata_detector.create_metadata_file(
                    download_path=plex_path,
                    candidate=candidate_info,
                    chosen_filename=plex_path.name,
                    show_info=show_info
                )

                if metadata_path:
                    logger.info(f"📝 Created download metadata: {metadata_path.name}")

            except Exception as e:
                logger.warning(f"Failed to create download metadata: {e}")

        # Process with Plex integration
        if self.plex_manager:
            try:
                logger.info("📺 Processing with Plex integration...")

                # Get tour name from directory structure
                tour_name = show_dir.parent.name

                # Process the new show with full Plex workflow
                results = self.process_new_show(show_dir, tour_name)

                if results['success']:
                    logger.info("✅ Plex integration completed successfully")
                    logger.info(f"   Videos processed: {results['videos_processed']}")
                    logger.info(f"   Collections updated: {'Yes' if results['collection_updated'] else 'No'}")
                    logger.info(f"   Metadata updated: {'Yes' if results['metadata_updated'] else 'No'}")
                else:
                    logger.warning("⚠️  Plex integration had issues:")
                    for error in results.get('errors', []):
                        logger.warning(f"   • {error}")
            except Exception as e:
                logger.warning(f"Plex integration failed: {e}")

        # Send Discord notification for imported show
        try:
            show_info_with_tour = show_info.copy()
            show_info_with_tour['tour'] = tour_name
            show_info_with_tour['files'] = [{'path': str(plex_path), **video_metadata}]

            self.discord_notifier.notify_new_show_added(show_info_with_tour)
        except Exception as e:
            logger.warning(f"Failed to send Discord notification: {e}")

        return plex_path

    def get_collection_stats(self) -> Dict[str, Any]:
        """Get detailed collection statistics."""
        collection = self.scan_collection()
        
        stats = {
            'total_tours': collection['total_tours'],
            'total_shows': collection['total_shows'], 
            'total_videos': collection['total_videos'],
            'cache_stats': self.video_cache.get_stats(),
            'tours_by_year': {},
            'quality_distribution': {},
            'plex_naming_compliance': {'compliant': 0, 'non_compliant': 0}
        }
        
        # Analyze by year and quality
        for tour_info in collection['tours'].values():
            for show_info in tour_info['shows'].values():
                # Year analysis
                date = show_info.get('date', '')
                if date:
                    year = date[:4]
                    stats['tours_by_year'][year] = stats['tours_by_year'].get(year, 0) + 1
                
                # Quality and naming analysis
                for file_info in show_info.get('files', []):
                    quality = file_info.get('quality', 'unknown')
                    stats['quality_distribution'][quality] = stats['quality_distribution'].get(quality, 0) + 1
                    
                    if file_info.get('is_plex_named', False):
                        stats['plex_naming_compliance']['compliant'] += 1
                    else:
                        stats['plex_naming_compliance']['non_compliant'] += 1
        
        return stats
    
    def _init_upgrade_tracker(self) -> Dict[str, Any]:
        """Initialize upgrade tracking data."""
        cache_dir = Path.home() / '.kglw_manager' / 'cache'
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.upgrade_tracker_file = cache_dir / 'upgrade_tracker.json'
        
        if self.upgrade_tracker_file.exists():
            try:
                with open(self.upgrade_tracker_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                logger.warning("Could not load upgrade tracker, starting fresh")
        
        return {
            'last_checked': {},  # show_date -> timestamp
            'last_upgrade_attempt': {},  # show_date -> timestamp  
            'successful_upgrades': {},  # show_date -> timestamp
            'failed_attempts': {},  # show_date -> count
        }
    
    def _save_upgrade_tracker(self):
        """Save upgrade tracking data to cache."""
        try:
            with open(self.upgrade_tracker_file, 'w') as f:
                json.dump(self.upgrade_tracker, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save upgrade tracker: {e}")
    
    def _should_skip_upgrade_check(self, show_date: str) -> bool:
        """Check if we should skip upgrade check for this show."""
        now = datetime.now()
        
        # Skip if checked recently (within last 7 days)
        last_checked = self.upgrade_tracker['last_checked'].get(show_date)
        if last_checked:
            last_check_time = datetime.fromisoformat(last_checked)
            if now - last_check_time < timedelta(days=7):
                return True
        
        # Skip if successfully upgraded recently (within last 30 days)
        last_upgrade = self.upgrade_tracker['successful_upgrades'].get(show_date)
        if last_upgrade:
            upgrade_time = datetime.fromisoformat(last_upgrade)
            if now - upgrade_time < timedelta(days=30):
                return True
        
        # Skip if too many recent failures (5+ in last 7 days)
        failed_count = self.upgrade_tracker['failed_attempts'].get(show_date, 0)
        if failed_count >= 5:
            last_attempt = self.upgrade_tracker['last_upgrade_attempt'].get(show_date)
            if last_attempt:
                attempt_time = datetime.fromisoformat(last_attempt)
                if now - attempt_time < timedelta(days=7):
                    return True
        
        return False
    
    def _mark_upgrade_checked(self, show_date: str):
        """Mark that we checked this show for upgrades."""
        self.upgrade_tracker['last_checked'][show_date] = datetime.now().isoformat()
        self._save_upgrade_tracker()
    
    def _mark_upgrade_attempt(self, show_date: str, success: bool):
        """Mark an upgrade attempt for this show."""
        now = datetime.now().isoformat()
        self.upgrade_tracker['last_upgrade_attempt'][show_date] = now
        
        if success:
            self.upgrade_tracker['successful_upgrades'][show_date] = now
            # Reset failed attempts on success
            if show_date in self.upgrade_tracker['failed_attempts']:
                del self.upgrade_tracker['failed_attempts'][show_date]
        else:
            # Increment failed attempts
            current_failures = self.upgrade_tracker['failed_attempts'].get(show_date, 0)
            self.upgrade_tracker['failed_attempts'][show_date] = current_failures + 1
        
        self._save_upgrade_tracker()

    def record_upgrade_attempt(self, show_date: str, success: bool, error: Optional[str] = None):
        """Record the outcome of an upgrade attempt for a show.

        Public wrapper around the internal tracker; `error` is logged for
        diagnostics but is not persisted in the tracker.
        """
        if error and not success:
            logger.warning(f"Upgrade attempt failed for {show_date}: {error}")
        self._mark_upgrade_attempt(show_date, success)

    def clear_failed_upgrade_attempts(self, show_date: Optional[str] = None) -> int:
        """Clear failed upgrade attempts for a specific show or all shows.
        
        Args:
            show_date: Specific show date to clear, or None to clear all
            
        Returns:
            Number of shows cleared
        """
        if show_date:
            # Clear specific show
            cleared = 0
            if show_date in self.upgrade_tracker['failed_attempts']:
                del self.upgrade_tracker['failed_attempts'][show_date]
                cleared += 1
            if show_date in self.upgrade_tracker['last_upgrade_attempt']:
                del self.upgrade_tracker['last_upgrade_attempt'][show_date]
                cleared += 1
            if show_date in self.upgrade_tracker['last_checked']:
                del self.upgrade_tracker['last_checked'][show_date]
                cleared += 1
                
            if cleared > 0:
                self._save_upgrade_tracker()
                logger.info(f"Cleared upgrade tracking for {show_date}")
            return 1 if cleared > 0 else 0
        else:
            # Clear all failed attempts
            failed_count = len(self.upgrade_tracker['failed_attempts'])
            self.upgrade_tracker['failed_attempts'] = {}
            self.upgrade_tracker['last_upgrade_attempt'] = {}
            self.upgrade_tracker['last_checked'] = {}
            
            if failed_count > 0:
                self._save_upgrade_tracker()
                logger.info(f"Cleared upgrade tracking for {failed_count} shows")
            return failed_count
    
    def get_upgrade_tracking_stats(self) -> Dict[str, Any]:
        """Get statistics about upgrade tracking."""
        failed_shows = len(self.upgrade_tracker['failed_attempts'])
        successful_shows = len(self.upgrade_tracker['successful_upgrades'])
        recently_checked = len(self.upgrade_tracker['last_checked'])
        
        # Count shows with 5+ failures (blocked from retrying)
        blocked_shows = sum(1 for count in self.upgrade_tracker['failed_attempts'].values() if count >= 5)
        
        return {
            'failed_shows': failed_shows,
            'successful_shows': successful_shows,
            'recently_checked': recently_checked,
            'blocked_shows': blocked_shows,
            'total_attempts': sum(self.upgrade_tracker['failed_attempts'].values())
        }
    
    def _is_wrong_show_match(self, expected_date: str, expected_location: str, candidate_video: Dict[str, Any]) -> bool:
        """Check if candidate video is clearly for a different show (safety check)."""
        candidate_title = candidate_video.get('title', '').lower()
        
        # Extract year from expected date (YYYY-MM-DD format)
        try:
            expected_year = expected_date.split('-')[0]
        except:
            expected_year = None
        
        # Check for obvious year mismatches in title
        if expected_year:
            # Look for year patterns in title like '22, '24, 2022, 2024, etc.
            import re
            year_patterns = re.findall(r"['']\d{2}|20\d{2}", candidate_title)
            for year_pattern in year_patterns:
                # Convert '22 to 2022, '24 to 2024, etc.
                if year_pattern.startswith("'") or year_pattern.startswith("'"):
                    year = "20" + year_pattern[1:]
                else:
                    year = year_pattern
                
                # If we find a year that's different from expected, it's likely wrong
                if year != expected_year:
                    logger.warning(f"🚨 SAFETY: Title contains year {year} but expected {expected_year}")
                    return True
        
        # Check for obvious location mismatches
        expected_location_words = set(expected_location.lower().split())
        
        # Common location patterns that would indicate wrong show
        wrong_location_indicators = [
            'oklahoma', 'city', 'austin', 'chicago', 'boston', 'detroit', 
            'seattle', 'portland', 'denver', 'phoenix', 'vegas', 'francisco',
            'angeles', 'diego', 'atlanta', 'miami', 'york', 'philadelphia'
        ]
        
        for indicator in wrong_location_indicators:
            if indicator in candidate_title and indicator not in expected_location.lower():
                # Found a city/location in title that's not in expected location
                logger.warning(f"🚨 SAFETY: Title contains '{indicator}' but expected location is '{expected_location}'")
                return True
        
        return False
    
    def _is_meaningful_upgrade(self, current_show_info: Dict[str, Any], candidate_video: Dict[str, Any], analysis: Dict[str, Any]) -> tuple[bool, str]:
        """Check if candidate video is a meaningful upgrade over current files.
        
        Returns:
            tuple: (is_upgrade, rejection_reason) where rejection_reason is only set if is_upgrade is False
        """
        
        current_files = current_show_info.get('files', [])
        if not current_files:
            # If no current files, any candidate is an upgrade
            return True, ""
        
        # Get candidate properties
        candidate_title = candidate_video.get('title', '').lower()
        candidate_quality = candidate_video.get('height') or 0
        candidate_duration = candidate_video.get('duration', 0)
        
        # Get current best properties
        current_max_quality = analysis.get('max_quality', 0)
        current_min_duration = analysis.get('min_duration', 0)
        current_has_phone = analysis.get('has_phone_recording', False)
        
        # Fix min_duration if it's infinity
        if current_min_duration == float('inf'):
            current_min_duration = 0
        
        # Check for obvious incomplete/partial indicators in candidate title
        incomplete_keywords = [
            'last 30 minutes', 'last 20 minutes', 'last 10 minutes',
            'first 30 minutes', 'first 20 minutes', 'first 10 minutes', 
            'partial', 'incomplete', 'fragment', 'excerpt',
            'outro only', 'intro only', 'ending only',
            'cut short', 'interrupted'
        ]
        
        candidate_is_incomplete = any(keyword in candidate_title for keyword in incomplete_keywords)
        
        # Check for audio-only content
        audio_only_keywords = [
            'audio only', 'audio-only', 'audio stream', 'audio recording',
            'just audio', 'sound only', 'no video', 'audio version'
        ]
        candidate_is_audio_only = any(keyword in candidate_title for keyword in audio_only_keywords)
        
        # Check if current collection has audio-only content that could be upgraded
        current_has_audio_only = False
        for file_info in current_files:
            current_title = file_info.get('title', '').lower()
            if any(keyword in current_title for keyword in audio_only_keywords):
                current_has_audio_only = True
                break
        
        # Audio-only upgrade logic: prioritize video content over audio-only
        if candidate_is_audio_only and not current_has_audio_only:
            # Don't downgrade from video to audio-only unless it's a massive improvement
            quality_improvement = candidate_quality - current_max_quality
            duration_improvement = candidate_duration - current_min_duration
            
            # Require very significant improvement to justify audio-only
            if quality_improvement < 720 and duration_improvement < 3600:  # < 720p improvement and < 1 hour duration improvement
                return False, f"Candidate is audio-only but current has video content. Would need massive improvement (720p+ or 1hr+ longer) but only offers {quality_improvement}p quality and {format_duration(duration_improvement)} duration improvement"
        
        elif current_has_audio_only and not candidate_is_audio_only:
            # Always prioritize video content over audio-only content
            logger.info(f"Prioritizing video content over audio-only: current has audio-only, candidate has video")
            return True, ""  # Any video content is better than audio-only
        
        # EARLY CHECK: Single song -> Single song logic (override general rules for collecting different songs)
        if candidate_duration > 0 and current_min_duration > 0:
            SINGLE_SONG_MAX = 900  # 15 minutes - single songs/partial clips
            current_is_single = current_min_duration <= SINGLE_SONG_MAX
            candidate_is_single = candidate_duration <= SINGLE_SONG_MAX
            
            if current_is_single and candidate_is_single:
                # Check if they're the same song using KGLW API
                current_title = current_files[0].get('title', '') if current_files else ''
                is_same_song, identified_song = self.kglw_api.is_same_song(current_title, candidate_title)
                
                if is_same_song:
                    # Same song: only upgrade for significant quality improvement
                    quality_improvement = candidate_quality - current_max_quality
                    duration_improvement = candidate_duration - current_min_duration
                    
                    # Be more strict for same song upgrades
                    if quality_improvement < 240 and duration_improvement < 300:  # < 240p and < 5min improvement
                        song_label = f" ({identified_song})" if identified_song else ""
                        return False, f"Same song{song_label} replacement needs significant improvement (quality: {quality_improvement}p gain, duration: {format_duration(duration_improvement)} gain, need 240p+ or 5min+)"
                    
                    # Allow upgrade if quality or duration is significantly better
                    if quality_improvement >= 240 or duration_improvement >= 300:
                        song_label = f" ({identified_song})" if identified_song else ""
                        logger.info(f"Upgrading same song{song_label}: {quality_improvement}p quality gain, {format_duration(duration_improvement)} duration gain")
                        return True, ""
                else:
                    # Different songs: allow the upgrade (collecting different songs is good)
                    song_info = f" (adding: {identified_song})" if identified_song else ""
                    logger.info(f"Adding different single song{song_info}")
                    return True, ""
        
        # If candidate appears incomplete, be more strict
        if candidate_is_incomplete:
            # Only upgrade if current is significantly worse
            quality_improvement = candidate_quality - current_max_quality
            duration_improvement = candidate_duration - current_min_duration
            
            # Require significant quality jump for incomplete candidates
            if quality_improvement < 240:  # Less than 240p improvement (e.g., 480p->720p)
                return False, f"Candidate appears incomplete and quality improvement insufficient ({quality_improvement}p gain, need 240p+ for incomplete content)"
                
            # Or require significant duration improvement
            if duration_improvement < 1800:  # Less than 30 minutes improvement
                return False, f"Candidate appears incomplete and duration improvement insufficient ({format_duration(duration_improvement)} gain, need 30min+ for incomplete content)"
        
        # Standard upgrade validation
        
        # 1. Quality improvement check
        if candidate_quality > 0 and current_max_quality > 0:
            # For same/similar quality, require other improvements
            if candidate_quality <= current_max_quality:
                # If quality is same or worse, require duration improvement
                if candidate_duration <= current_min_duration:
                    # If both quality and duration are same/worse, only upgrade if removing phone recording
                    if not current_has_phone:
                        return False, f"Quality and duration are both same or worse (quality: {candidate_quality}p vs {current_max_quality}p, duration: {format_duration(candidate_duration)} vs {format_duration(current_min_duration)}) and no phone recording to remove"
        
        # 2. Duration improvement check with significant threshold logic
        if candidate_duration > 0 and current_min_duration > 0:
            
            # Define duration categories for better decision making
            SINGLE_SONG_MAX = 900      # 15 minutes - single songs/partial clips
            PARTIAL_SHOW_MAX = 2700    # 45 minutes - partial shows/multiple songs  
            FULL_SHOW_MIN = 3600       # 60 minutes - likely full shows
            SIGNIFICANT_UPGRADE = 2700 # 45 minutes - must be this much longer to be meaningful
            
            # Categorize current and candidate content
            current_is_single = current_min_duration <= SINGLE_SONG_MAX
            current_is_partial = SINGLE_SONG_MAX < current_min_duration <= PARTIAL_SHOW_MAX
            current_is_full = current_min_duration >= FULL_SHOW_MIN
            
            candidate_is_single = candidate_duration <= SINGLE_SONG_MAX
            candidate_is_partial = SINGLE_SONG_MAX < candidate_duration <= PARTIAL_SHOW_MAX
            candidate_is_full = candidate_duration >= FULL_SHOW_MIN
            
            # Logic for meaningful duration upgrades:
            
            # 1. Single song -> Full show: Always upgrade
            if current_is_single and candidate_is_full:
                return True, ""
            
            # 2. Full show -> Single song: Never downgrade
            if current_is_full and candidate_is_single:
                return False, f"Would downgrade from full show ({format_duration(current_min_duration)}) to single song ({format_duration(candidate_duration)})"
                
            # 3. Single song -> Partial show: Only if significantly longer (45+ min improvement)
            if current_is_single and candidate_is_partial:
                duration_improvement = candidate_duration - current_min_duration
                if duration_improvement < SIGNIFICANT_UPGRADE:
                    return False, f"Single song to partial show needs 45min+ improvement (current: {format_duration(current_min_duration)}, candidate: {format_duration(candidate_duration)}, gain: {format_duration(duration_improvement)})"
            
            # 4. Partial show -> Single song: Never downgrade
            if current_is_partial and candidate_is_single:
                return False, f"Would downgrade from partial show ({format_duration(current_min_duration)}) to single song ({format_duration(candidate_duration)})"
            
            # 5. Partial show -> Partial show: Only if significantly longer
            if current_is_partial and candidate_is_partial:
                duration_improvement = candidate_duration - current_min_duration
                if duration_improvement < SIGNIFICANT_UPGRADE:
                    return False, f"Partial show to partial show needs 45min+ improvement (current: {format_duration(current_min_duration)}, candidate: {format_duration(candidate_duration)}, gain: {format_duration(duration_improvement)})"
                    
            # 6. Full show -> Partial show: Only if quality is massively better
            if current_is_full and candidate_is_partial:
                quality_improvement = candidate_quality - current_max_quality
                if quality_improvement < 480:  # Less than 480p improvement (e.g., 480p->960p)
                    return False, f"Would downgrade from full show ({format_duration(current_min_duration)}) to partial show ({format_duration(candidate_duration)}) without massive quality gain ({quality_improvement}p gain, need 480p+)"
            
            # 7. General rule: Don't allow significant duration loss without massive quality gain
            duration_loss = current_min_duration - candidate_duration
            if duration_loss > SIGNIFICANT_UPGRADE:  # More than 45 minutes shorter
                quality_improvement = candidate_quality - current_max_quality
                if quality_improvement < 720:  # Less than 720p improvement
                    return False, f"Significant duration loss ({format_duration(duration_loss)}) without massive quality gain ({quality_improvement}p gain, need 720p+)"
        
        # 3. Check for lateral moves (same quality, same duration) - tightened thresholds
        if (candidate_quality > 0 and current_max_quality > 0 and 
            abs(candidate_quality - current_max_quality) < 120):  # Within 120p
            
            if (candidate_duration > 0 and current_min_duration > 0 and
                abs(candidate_duration - current_min_duration) < 900):  # Within 15 minutes (tightened from 30)
                
                # This is essentially the same quality and duration
                # Only upgrade if current has phone recording and candidate doesn't
                if not current_has_phone:
                    return False, f"Lateral move - similar quality ({candidate_quality}p vs {current_max_quality}p) and duration ({format_duration(candidate_duration)} vs {format_duration(current_min_duration)}) with no phone recording improvement"
        
        # If we get here, it's a meaningful upgrade
        return True, ""
    
    def load_spreadsheet_data(self, html_file_path: Optional[str] = None) -> bool:
        """Load YouTube links from the live show spreadsheet HTML export."""
        try:
            if html_file_path:
                success = self.sheets_parser.parse_html_export(html_file_path)
            else:
                # Try to download the latest version
                if self.sheets_parser.download_spreadsheet("html", "kglw_live_shows.html"):
                    success = self.sheets_parser.parse_html_export("kglw_live_shows.html")
                else:
                    logger.error("Failed to download spreadsheet")
                    return False
            
            if success:
                stats = self.sheets_parser.get_stats()
                logger.info(f"Loaded {stats['total_shows']} shows with {stats['total_youtube_links']} YouTube links from spreadsheet")
                return True
            else:
                logger.error("Failed to parse spreadsheet data")
                return False
                
        except Exception as e:
            logger.error(f"Error loading spreadsheet data: {e}")
            return False
    
    def identify_and_label_song(self, video_info: Dict, duration_threshold: int = 900) -> Optional[Dict]:
        """
        Identify if a video is a single song and return song information.
        
        Args:
            video_info: Video metadata dictionary
            duration_threshold: Maximum duration in seconds to consider a single song (default: 15 minutes)
        
        Returns:
            Dictionary with song info if identified as single song, None otherwise
        """
        title = video_info.get('title', '')
        duration = video_info.get('duration', 0)
        
        # Only process videos that are likely single songs based on duration
        if duration <= 0 or duration > duration_threshold:
            return None
        
        # Try to identify the song using KGLW API
        song_match = self.kglw_api.identify_song_from_title(title)
        if song_match:
            return {
                'title': title,
                'duration': duration,
                'song_name': song_match['song']['name'],
                'song_id': song_match['song']['id'],
                'similarity': song_match['similarity'],
                'is_original': bool(song_match['song'].get('isoriginal', 1)),
                'original_artist': song_match['song'].get('original_artist', 'King Gizzard & the Lizard Wizard')
            }
        
        return None
    
    def get_song_label_for_video(self, video_info: Dict) -> str:
        """
        Get a formatted song label for a video if it's identified as a single song.
        
        Returns:
            String label like " (Rattlesnake)" or " (Highway Star - Deep Purple cover)" or empty string
        """
        song_info = self.identify_and_label_song(video_info)
        if not song_info:
            return ""
        
        song_name = song_info['song_name']
        
        # Add cover information if it's not an original King Gizzard song
        if not song_info['is_original']:
            original_artist = song_info['original_artist']
            if original_artist and original_artist != 'King Gizzard & the Lizard Wizard':
                return f" ({song_name} - {original_artist} cover)"
        
        return f" ({song_name})"
    
    def find_youtube_links_for_show(self, show_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find YouTube links for a specific show from the spreadsheet."""
        if not self.sheets_parser.shows_data:
            logger.warning("Spreadsheet data not loaded. Call load_spreadsheet_data() first.")
            return []
        
        show_date = show_info.get('date', '')
        show_location = show_info.get('location', '')
        
        # Try exact date match first
        if show_date:
            links = self.sheets_parser.get_youtube_links_for_show(date=show_date)
            if links:
                return links
        
        # Try location-based search
        if show_location:
            location_matches = self.sheets_parser.search_shows_by_location(show_location)
            
            # If we have a date, try to find the closest match by date
            if show_date and location_matches:
                from datetime import datetime
                show_date_obj = None
                try:
                    show_date_obj = datetime.strptime(show_date, '%Y-%m-%d')
                except ValueError:
                    pass
                
                if show_date_obj:
                    closest_match = None
                    min_diff = float('inf')
                    
                    for match in location_matches:
                        try:
                            match_date_obj = datetime.strptime(match['date'], '%Y-%m-%d')
                            diff = abs((show_date_obj - match_date_obj).days)
                            if diff < min_diff:
                                min_diff = diff
                                closest_match = match
                        except ValueError:
                            continue
                    
                    if closest_match and min_diff <= 7:  # Within a week
                        return closest_match.get('youtube_links', [])
            
            # Return all matches if no date filtering
            all_links = []
            for match in location_matches:
                all_links.extend(match.get('youtube_links', []))
            return all_links
        
        return []
    
    def get_spreadsheet_stats(self) -> Dict[str, Any]:
        """Get statistics about the loaded spreadsheet data.

        Always returns the (possibly zeroed) stats dict; when no data is
        loaded an 'error' key is added so callers can surface a message.
        """
        stats = self.sheets_parser.get_stats()
        if not self.sheets_parser.shows_data:
            stats['error'] = 'No spreadsheet data loaded'
        return stats
    
    def find_missing_shows_in_collection(self) -> List[Dict[str, Any]]:
        """Find shows that exist in spreadsheet but not in local collection."""
        if not self.sheets_parser.shows_data:
            logger.warning("Spreadsheet data not loaded. Call load_spreadsheet_data() first.")
            return []
        
        # Get all shows from collection
        collection = self.scan_collection()
        collection_dates = set()
        
        for tour_info in collection['tours'].values():
            for show_info in tour_info['shows'].values():
                show_date = show_info.get('date', '')
                if show_date:
                    collection_dates.add(show_date)
        
        # Find shows in spreadsheet that aren't in collection
        missing_shows = []
        for show_data in self.sheets_parser.shows_data.values():
            if show_data['date'] not in collection_dates:
                missing_shows.append(show_data)
        
        return missing_shows
    
    def suggest_upgrades_from_spreadsheet(self, show_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Suggest potential upgrades for a show using spreadsheet YouTube links."""
        youtube_links = self.find_youtube_links_for_show(show_info)
        
        if not youtube_links:
            return []
        
        # Convert YouTube links to candidate format for upgrade suggestions
        candidates = []
        for link_info in youtube_links:
            url = link_info['url']
            title = link_info.get('text', f"Show {show_info.get('date', '')}")
            column = link_info.get('column', 'Link')
            
            candidates.append({
                'url': url,
                'title': title,
                'source': f'spreadsheet_{column.lower()}',
                'description': f'From spreadsheet {column} column',
                'webpage_url': url
            })
        
        return candidates
    
    def find_missing_shows(self, source_priority: str = "both", max_results: int = 50, year_filter: Optional[int] = None) -> List[Dict[str, Any]]:
        """Find shows from API data that have no local video files and search for download candidates.
        
        Args:
            source_priority: "spreadsheet", "youtube", or "both" (default)
            max_results: Maximum number of candidates to return
            year_filter: Only search for shows from specific year
            
        Returns:
            List of shows with candidate videos found
        """
        logger.info(f"Searching for missing shows (source: {source_priority}, max: {max_results})")
        
        # Get all shows from local collection
        collection_data = self.scan_collection(force_rescan=False)
        local_shows_by_date = {}
        
        # Build index of local shows by date
        for tour_name, tour_info in collection_data.get('tours', {}).items():
            for show_path, show in tour_info.get('shows', {}).items():
                show_date = show.get('date', '')
                if show_date:
                    local_shows_by_date[show_date] = {
                        'show_info': show,
                        'tour': tour_name,
                        'has_files': len(show.get('files', [])) > 0
                    }
        
        # Get API shows to compare against local collection
        from .sources import DataSourceManager
        data_source = DataSourceManager()
        
        # Determine years to check
        if year_filter:
            years_to_check = [year_filter]
        else:
            # Get years from local collection + recent years
            years = set()
            for tour_name in collection_data.get('tours', {}).keys():
                year_match = tour_name.split()[0]
                if year_match.isdigit():
                    years.add(int(year_match))
            
            # Add recent years that might not have tours yet, but not future years
            import datetime
            current_year = datetime.datetime.now().year
            for year in range(current_year - 2, current_year + 1):  # Only up to current year
                years.add(year)
            
            years_to_check = list(years)
        
        missing_shows = []
        processed_show_dates = set()  # Track show dates to avoid duplicates
        
        # Check each year for API shows not in local collection
        for year in years_to_check:
            if year_filter and year != year_filter:
                continue
                
            api_shows = data_source.get_shows_for_year(year)
            
            for api_show in api_shows:
                show_date = api_show.get('showdate', '')
                if not show_date:
                    continue
                
                # Skip if we've already processed this show date
                if show_date in processed_show_dates:
                    continue
                
                # Check if this show is missing or has no files locally
                local_show = local_shows_by_date.get(show_date)
                
                if not local_show or not local_show['has_files']:
                    # This show is missing from local collection
                    # Convert API show format to our show_info format
                    show_info = {
                        'date': show_date,
                        'location': api_show.get('city', ''),
                        'venue': api_show.get('venuename', ''),
                        'files': []  # No local files
                    }
                    
                    # Assign tour using tour manager
                    from .tours import TourManager
                    tour_manager = TourManager()
                    assigned_tour = tour_manager.assign_tour(show_info)
                    
                    missing_shows.append({
                        'show_info': show_info,
                        'tour': assigned_tour,
                        'api_data': api_show
                    })
                    
                    # Mark this show date as processed
                    processed_show_dates.add(show_date)
        
        logger.info(f"Found {len(missing_shows)} unique shows missing from local collection")
        
        if not missing_shows:
            return []
        
        # Search for candidates for each missing show
        candidates_found = []
        processed_count = 0
        
        self.console.print(f"🔍 [cyan]Searching for {len(missing_shows)} missing shows...[/cyan]")
        
        for missing_show in missing_shows:
            if len(candidates_found) >= max_results:
                break
                
            processed_count += 1
            show_info = missing_show['show_info']
            show_date = show_info.get('date', '')
            show_location = show_info.get('location', '')
            tour_name = missing_show['tour']
            
            # Show progress
            progress_text = f"[{processed_count}/{len(missing_shows)}] {show_date} - {show_location}"
            self.console.print(f"  🔎 {progress_text}", end="")
            
            candidates = self._search_missing_show_candidates(
                show_info, source_priority=source_priority
            )
            
            if candidates:
                best_candidate = candidates[0]  # Take the best match
                candidates_found.append({
                    'show_info': show_info,
                    'tour': tour_name,
                    'candidate': best_candidate,
                    'search_results_count': len(candidates)
                })
                self.console.print(f" ✅ Found: {best_candidate.get('title', 'Unknown')[:50]}...")
            else:
                self.console.print(" ❌ No candidates found")
        
        logger.info(f"Found candidates for {len(candidates_found)} missing shows")
        return candidates_found
    
    def _search_missing_show_candidates(self, show_info: Dict[str, Any], source_priority: str = "both") -> List[Dict[str, Any]]:
        """Search for download candidates for a single missing show."""
        show_date = show_info.get('date', '')
        show_location = show_info.get('location', '')
        candidates = []
        
        # 1. Try spreadsheet first if available and requested
        if source_priority in ["spreadsheet", "both"]:
            try:
                # Use existing spreadsheet integration that's already loaded
                if hasattr(self, 'spreadsheet_data') and self.spreadsheet_data:
                    # Find shows in spreadsheet that match this date
                    for spreadsheet_show in self.spreadsheet_data:
                        spreadsheet_date = spreadsheet_show.get('date', '')
                        if spreadsheet_date == show_date:
                            # Get YouTube links for this show
                            youtube_links = spreadsheet_show.get('youtube_links', [])
                            for link_info in youtube_links:
                                url = link_info.get('url', '')
                                if url:
                                    candidates.append({
                                        'webpage_url': url,
                                        'title': f"{show_date} - {show_location} (Spreadsheet)",
                                        'uploader': 'Spreadsheet Source',
                                        'source': 'spreadsheet',
                                        'priority_score': 1000,  # High priority for spreadsheet matches
                                        'description': f'From spreadsheet {link_info.get("column", "Link")} column'
                                    })
                else:
                    # Fallback to the find_youtube_links_for_show method
                    spreadsheet_matches = self.find_youtube_links_for_show(show_info)
                    
                    # Convert spreadsheet matches to candidate format
                    for match in spreadsheet_matches:
                        candidates.append({
                            'webpage_url': match.get('url', match.get('webpage_url', '')),
                            'title': match.get('title', f"{show_date} - {show_location} (Spreadsheet)"),
                            'uploader': 'Spreadsheet Source',
                            'source': 'spreadsheet',
                            'priority_score': 1000,  # High priority for spreadsheet matches
                            'description': match.get('description', 'From spreadsheet')
                        })
                
            except Exception as e:
                logger.debug(f"Spreadsheet search failed for {show_date}: {e}")
        
        # 2. Try YouTube search if requested and not enough results from spreadsheet
        if source_priority in ["youtube", "both"] and len(candidates) < 3:
            try:
                from .youtube_search import YouTubeSearcher
                youtube_searcher = YouTubeSearcher()
                
                # Search YouTube for this show
                youtube_results = youtube_searcher.search_for_upgrades_with_fallback(show_info)
                
                # Add YouTube results as candidates
                for result in youtube_results[:5]:  # Limit to top 5 YouTube results
                    result_copy = result.copy()
                    result_copy['source'] = 'youtube'
                    if 'priority_score' not in result_copy:
                        result_copy['priority_score'] = 500  # Medium priority for YouTube
                    candidates.append(result_copy)
                
            except Exception as e:
                logger.debug(f"YouTube search failed for {show_date}: {e}")
        
        # Sort candidates by priority score (highest first)
        candidates.sort(key=lambda x: x.get('priority_score', 0), reverse=True)
        
        return candidates[:10]  # Return top 10 candidates
    
    def _enhance_candidate_with_metadata(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance candidate with basic video metadata for better Discord notifications.
        
        Args:
            candidate: Basic candidate info with at least 'webpage_url'
            
        Returns:
            Enhanced candidate with metadata like height, duration, etc.
        """
        enhanced = candidate.copy()
        
        try:
            url = candidate.get('webpage_url', '')
            if not url:
                return enhanced
            
            # Skip playlists - they don't have individual video formats
            from .download import DownloadManager
            download_manager = DownloadManager()
            if download_manager._is_playlist_url(url):
                enhanced['is_playlist'] = True
                logger.debug(f"Skipping metadata enhancement for playlist URL: {url}")
                return enhanced
                
            # Use yt-dlp to get basic video metadata for individual videos
            formats = download_manager.get_available_formats(url)
            
            if formats:
                # Find the best quality format for metadata extraction
                best_format = None
                max_height = 0
                
                for fmt in formats:
                    height = fmt.get('height') or 0
                    if height > max_height:
                        max_height = height
                        best_format = fmt
                
                if best_format:
                    # Extract useful metadata
                    enhanced['height'] = best_format.get('height', 0)
                    enhanced['width'] = best_format.get('width', 0)
                    enhanced['duration'] = best_format.get('duration', 0)
                    enhanced['filesize'] = best_format.get('filesize', 0)
                    
                    # Update title if we got a better one
                    video_title = best_format.get('title', '')
                    if video_title and 'Spreadsheet' in enhanced.get('title', ''):
                        enhanced['title'] = video_title
                    
                    # Update uploader if available
                    uploader = best_format.get('uploader', '')
                    if uploader:
                        enhanced['uploader'] = uploader
                        
                    logger.debug(f"Enhanced candidate metadata: {enhanced['height']}p, {enhanced['duration']}s")
                
        except Exception as e:
            # Don't fail the whole process if metadata extraction fails
            logger.debug(f"Failed to enhance candidate metadata for {url}: {e}")
        
        return enhanced
    
    def download_missing_shows(self, missing_shows: List[Dict[str, Any]], auto_confirm: bool = True, 
                              format_id: str = 'best') -> Dict[str, int]:
        """Download videos for missing shows.
        
        Args:
            missing_shows: List from find_missing_shows()
            auto_confirm: Skip confirmation prompts
            format_id: Video format to download
            
        Returns:
            Dictionary with success/failure counts
        """
        if not missing_shows:
            logger.info("No missing shows to download")
            return {'success': 0, 'failed': 0, 'skipped': 0}
        
        success_count = 0
        failed_count = 0
        skipped_count = 0
        
        self.console.print(f"📥 [bold cyan]Starting download of {len(missing_shows)} missing shows[/bold cyan]")
        
        for i, missing_show in enumerate(missing_shows, 1):
            show_info = missing_show['show_info']
            candidate = missing_show['candidate']
            tour_name = missing_show['tour']
            
            show_date = show_info.get('date', 'Unknown Date')
            show_location = show_info.get('location', 'Unknown Location')
            candidate_title = candidate.get('title', 'Unknown Video')
            
            self.console.print(f"\n[{i}/{len(missing_shows)}] {show_date} - {show_location}")
            self.console.print(f"  📹 Candidate: {candidate_title}")
            self.console.print(f"  🎫 Tour: {tour_name}")
            self.console.print(f"  🔗 Source: {candidate.get('source', 'unknown')}")
            
            if not auto_confirm:
                from rich.prompt import Confirm
                if not Confirm.ask("  💾 Download this video?", default=True):
                    skipped_count += 1
                    self.console.print("  ⏭️  Skipped")
                    continue
            
            # Perform the download using existing upgrade infrastructure
            try:
                # Create temporary show path for download
                from .tours import TourManager
                from .naming import NamingManager
                
                tour_manager = TourManager()
                naming_manager = NamingManager()
                
                # Assign tour if not already assigned
                if 'tour' not in show_info:
                    assigned_tour = tour_manager.assign_tour(show_info)
                else:
                    assigned_tour = show_info['tour']
                
                # Create show directory structure
                tour_dir = self.collection_path / assigned_tour
                show_dir_name = naming_manager.generate_directory_name(show_info)
                show_dir = tour_dir / show_dir_name
                show_dir.mkdir(parents=True, exist_ok=True)
                
                # Use the download upgrade method
                from .download import DownloadManager
                download_manager = DownloadManager()
                
                result_path = download_manager.download_upgrade_to_existing_dir(
                    video_info=candidate,
                    show_dir=show_dir,
                    show_info=show_info,
                    backup_existing=False,  # No existing files to backup
                    format_id=format_id,
                    quiet_mode=False
                )
                
                if result_path:
                    success_count += 1
                    self.console.print("  ✅ Download completed successfully")
                    
                    # Send Discord notification for new show
                    if self.discord_notifier:
                        try:
                            # Add tour info for notification
                            show_info_with_tour = show_info.copy()
                            show_info_with_tour['tour'] = assigned_tour
                            
                            # Enhance candidate with metadata for better Discord notification
                            enhanced_candidate_info = self._enhance_candidate_with_metadata(candidate)
                            
                            # Add effective quality info
                            from .quality_config import QualityManager
                            quality_manager = QualityManager()
                            active_profile = quality_manager.get_active_profile()
                            candidate_quality = enhanced_candidate_info.get('height') or 0
                            effective_quality = min(candidate_quality, active_profile.max_resolution) if candidate_quality > 0 else candidate_quality
                            enhanced_candidate_info['effective_quality'] = effective_quality
                            
                            self.discord_notifier.notify_new_show_added(
                                show_info=show_info_with_tour,
                                candidate_info=enhanced_candidate_info
                            )
                        except Exception as e:
                            logger.warning(f"Failed to send Discord notification: {e}")
                            
                else:
                    failed_count += 1
                    self.console.print("  ❌ Download failed")
                    
            except Exception as e:
                failed_count += 1
                self.console.print(f"  ❌ Download error: {e}")
                logger.error(f"Failed to download {show_date}: {e}")
        
        # Show summary
        self.console.print(f"\n📊 [bold]Download Summary:[/bold]")
        self.console.print(f"  ✅ Success: {success_count}")
        self.console.print(f"  ❌ Failed: {failed_count}")
        self.console.print(f"  ⏭️  Skipped: {skipped_count}")
        
        return {'success': success_count, 'failed': failed_count, 'skipped': skipped_count}
    
    # Plex Integration Methods
    
    def process_new_show(self, show_path: Path, tour_name: str = None) -> Dict[str, any]:
        """
        Process a new show with complete Plex integration workflow:
        1. Verify poster placement
        2. Update Plex metadata  
        3. Add to appropriate collection
        4. Return processing results
        """
        if not self.plex_manager:
            return {
                'success': False,
                'error': 'Plex integration not available'
            }
        
        logger.info(f"🎵 Processing new show with Plex integration: {show_path}")
        
        # Use Plex manager to handle the processing
        results = self.plex_manager.process_new_show(show_path, tour_name)
        
        # Send Discord notification for successful processing
        if results['success'] and self.discord_notifier.enabled:
            try:
                # Extract show info from path for Discord notification
                show_info = self.naming_manager.parse_show_info_from_filename(show_path.name)
                if not show_info:
                    show_info = {'date': 'Unknown', 'location': 'Unknown', 'venue': ''}

                # Add additional info from processing results
                show_info['tour'] = results.get('tour_assigned', tour_name or 'Unknown Tour')
                show_info['path'] = str(show_path)
                show_info['video_count'] = results['videos_processed']
                show_info['poster_count'] = results['posters_found']

                self.discord_notifier.notify_new_show_added(show_info)
            except Exception as e:
                logger.warning(f"Failed to send Discord notification: {e}")
        
        return results
    
    def sync_collection_with_plex(self) -> Dict[str, int]:
        """
        Synchronize entire collection with Plex:
        - Process any shows missing from collections
        - Update metadata for shows without proper info
        - Ensure all collection sort titles are correct
        """
        if not self.plex_manager:
            return {
                'error': 'Plex integration not available'
            }
        
        logger.info("🔄 Synchronizing collection with Plex...")
        
        # Process shows missing from collections
        missing_results = self.plex_manager.batch_process_missing_shows()
        
        # Get updated stats
        plex_stats = self.plex_manager.get_library_stats()
        
        results = {
            'shows_processed': missing_results['processed'],
            'shows_updated': missing_results['updated'],
            'shows_failed': missing_results['failed'],
            'total_plex_items': plex_stats.get('total_items', 0),
            'total_collections': plex_stats.get('total_collections', 0)
        }
        
        logger.info(f"✅ Plex sync complete: {results['shows_updated']}/{results['shows_processed']} shows updated")
        return results
    
    def get_plex_stats(self) -> Dict[str, any]:
        """Get Plex library statistics."""
        if not self.plex_manager:
            return {'error': 'Plex integration not available'}
        
        return self.plex_manager.get_library_stats()
    
    def find_plex_shows_missing_collections(self) -> List[Dict[str, any]]:
        """Find Plex shows that aren't assigned to any collection."""
        if not self.plex_manager:
            return []

        return self.plex_manager.find_shows_missing_from_collections()

    def _get_plex_metadata_for_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Get Plex metadata for a specific file."""
        if not self.plex_manager:
            return None

        try:
            # Find the Plex item by file path
            items = self.plex_manager.library.all()
            for item in items:
                try:
                    if item.media and item.media[0].parts:
                        part = item.media[0].parts[0]
                        # Compare file paths (convert Plex path back to local path if needed)
                        plex_file = part.file
                        if plex_file.endswith(file_path.name):
                            # Found matching item
                            media = item.media[0]
                            part = media.parts[0]

                            return {
                                'title': item.title,
                                'media': media,
                                'part': part,
                                'duration': getattr(part, 'duration', 0),
                                'size': getattr(part, 'size', 0),
                                'resolution': getattr(media, 'videoResolution', 'unknown')
                            }
                except Exception:
                    continue

        except Exception as e:
            logger.debug(f"Error getting Plex metadata for {file_path}: {e}")

        return None

    def _extract_quality_from_plex(self, plex_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Extract quality information from Plex metadata."""
        try:
            resolution = plex_metadata.get('resolution', 'unknown')
            duration = plex_metadata.get('duration', 0)
            size = plex_metadata.get('size', 0)

            # Convert Plex resolution format to our format
            quality_map = {
                'sd': '480p',
                '480': '480p',
                '720': '720p',
                '1080': '1080p',
                '4k': '2160p',
                '2160': '2160p'
            }

            quality = quality_map.get(resolution, resolution)
            if quality != resolution and not quality.endswith('p'):
                quality = f"{quality}p"

            return {
                'quality': quality,
                'duration': int(duration / 1000) if duration else 0,  # Convert ms to seconds
                'resolution': f"{resolution}",
                'codec': 'unknown',  # Plex doesn't easily expose codec
                'bitrate': 0,  # Would need to calculate from size/duration
                'fps': 0  # Not easily available in Plex
            }

        except Exception as e:
            logger.warning(f"Error extracting quality from Plex metadata: {e}")
            return {
                'quality': 'unknown',
                'duration': 0,
                'resolution': 'unknown',
                'codec': 'unknown',
                'bitrate': 0,
                'fps': 0
            }