"""Plex integration for KGLW Manager."""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from plexapi.server import PlexServer
from plexapi.exceptions import NotFound, BadRequest
from .utils import setup_logging
from .config import config
from .kglw_api import KGLWApi

logger = setup_logging()


class PlexManager:
    """Manages Plex integration for KGLW shows."""
    
    def __init__(self, plex_url: str = None, plex_token: str = None, library_name: str = "KGLW",
                 server_url: str = None, token: str = None):
        """Initialize Plex connection.

        Args:
            plex_url: Plex server URL (or use server_url for compatibility)
            plex_token: Plex authentication token (or use token for compatibility)
            library_name: Name of the Plex library
            server_url: Alias for plex_url (for test compatibility)
            token: Alias for plex_token (for test compatibility)
        """
        # Support both parameter names for compatibility.
        # Credentials resolve explicit arg > environment > config file; they are
        # deliberately NOT hardcoded here so they stay out of version control.
        self.plex_url = (plex_url or server_url
                         or os.environ.get('KGLW_PLEX_URL')
                         or config.get('plex_url'))
        self.plex_token = (plex_token or token
                           or os.environ.get('KGLW_PLEX_TOKEN')
                           or config.get('plex_token'))
        self.library_name = library_name or config.get('plex_library_name', 'KGLW')
        
        # Initialize API for metadata
        cache_dir = Path.home() / '.kglw_manager' / 'cache'
        self.kglw_api = KGLWApi(cache_dir)
        
        self.plex = None
        self.library = None
        
        self._connect()
    
    def _connect(self):
        """Connect to Plex server and get library."""
        if not self.plex_url or not self.plex_token:
            missing = 'URL' if not self.plex_url else 'token'
            raise ValueError(
                f"Plex {missing} is not configured. Set KGLW_PLEX_URL / "
                f"KGLW_PLEX_TOKEN, or add 'plex_url' / 'plex_token' to "
                f"{config.config_file}."
            )

        try:
            logger.info(f"🔗 Connecting to Plex server: {self.plex_url}")
            self.plex = PlexServer(self.plex_url, self.plex_token)
            
            logger.info(f"📚 Getting library: {self.library_name}")
            self.library = self.plex.library.section(self.library_name)
            
            logger.info("✅ Plex connection established")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Plex: {e}")
            raise
    
    def process_new_show(self, show_path: Path, tour_name: str = None) -> Dict[str, any]:
        """
        Complete processing workflow for a new show:
        1. Scan for videos and posters
        2. Update Plex metadata 
        3. Add to appropriate collection
        4. Return processing results
        """
        logger.info(f"🎵 Processing new show: {show_path}")
        
        results = {
            'show_path': str(show_path),
            'success': False,
            'videos_found': 0,
            'videos_processed': 0,
            'posters_found': 0,
            'metadata_updated': False,
            'collection_updated': False,
            'tour_assigned': tour_name,
            'errors': []
        }
        
        try:
            # 1. Scan directory for videos and posters
            videos, posters = self._scan_show_directory(show_path)
            results['videos_found'] = len(videos)
            results['posters_found'] = len(posters)
            
            if not videos:
                results['errors'].append("No video files found in directory")
                return results
            
            # 2. Determine tour if not provided
            if not tour_name:
                tour_name = self._determine_tour_from_path(show_path)
                results['tour_assigned'] = tour_name
            
            # 3. Process each video file
            processed_videos = 0
            for video_path in videos:
                try:
                    # Find or refresh the video in Plex
                    plex_item = self._get_plex_item_by_path(video_path)
                    
                    if plex_item:
                        # Update metadata
                        if self._update_show_metadata(plex_item, show_path):
                            results['metadata_updated'] = True
                        
                        # Add to collection
                        if tour_name and self._add_to_collection(plex_item, tour_name):
                            results['collection_updated'] = True
                        
                        processed_videos += 1
                        
                except Exception as e:
                    logger.error(f"❌ Error processing video {video_path}: {e}")
                    results['errors'].append(f"Video processing error: {e}")
            
            results['videos_processed'] = processed_videos
            results['success'] = processed_videos > 0
            
            logger.info(f"✅ Show processing complete: {processed_videos}/{len(videos)} videos processed")
            
        except Exception as e:
            logger.error(f"❌ Error processing show {show_path}: {e}")
            results['errors'].append(f"General processing error: {e}")
        
        return results
    
    def _scan_show_directory(self, show_path: Path) -> Tuple[List[Path], List[Path]]:
        """Scan directory for video and poster files."""
        videos = []
        posters = []
        
        if not show_path.exists():
            return videos, posters
        
        video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.m4v', '.webm'}
        poster_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
        
        for file_path in show_path.iterdir():
            if file_path.is_file():
                suffix = file_path.suffix.lower()
                if suffix in video_extensions:
                    videos.append(file_path)
                elif file_path.name.lower().startswith('poster.') and suffix in poster_extensions:
                    posters.append(file_path)
        
        # If no local poster found, try to get one from KGLW.net API
        if not posters:
            try:
                api_poster = self.kglw_api.download_poster_from_api(show_path)
                if api_poster:
                    posters.append(api_poster)
            except Exception as e:
                logger.debug(f"Failed to get poster from API: {e}")
        
        logger.debug(f"Found {len(videos)} videos and {len(posters)} posters in {show_path}")
        return videos, posters
    
    def _determine_tour_from_path(self, show_path: Path) -> str:
        """Determine tour name from directory structure."""
        # Tour should be the parent directory name
        tour_dir = show_path.parent
        tour_name = tour_dir.name
        
        logger.debug(f"Determined tour: {tour_name}")
        return tour_name
    
    def _get_plex_item_by_path(self, video_path: Path) -> Optional[any]:
        """Find Plex item by file path."""
        try:
            # Convert local path to Plex library path
            plex_path = self._convert_to_plex_path(video_path)
            
            # Search for item by file path
            for item in self.library.all():
                for media in item.media:
                    for part in media.parts:
                        if part.file == plex_path:
                            logger.debug(f"Found Plex item: {item.title}")
                            return item
            
            # If not found, trigger library refresh for this directory
            logger.info(f"🔄 Video not found in Plex, refreshing library...")
            self._refresh_library_path(video_path.parent)
            
            # Try again after refresh
            for item in self.library.all():
                for media in item.media:
                    for part in media.parts:
                        if part.file == plex_path:
                            logger.debug(f"Found Plex item after refresh: {item.title}")
                            return item
            
            logger.warning(f"⚠️  Video not found in Plex: {plex_path}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error finding Plex item: {e}")
            return None
    
    @property
    def _local_prefix(self) -> str:
        """Local collection root, always with a trailing slash."""
        return config.get('collection_path').rstrip('/') + '/'

    @property
    def _plex_prefix(self) -> str:
        """Plex-side library root, always with a trailing slash."""
        return config.get('plex_library_path', '/library/kglw').rstrip('/') + '/'

    def _convert_to_plex_path(self, local_path: Path) -> str:
        """Convert local file path to Plex library path."""
        local_str = str(local_path)
        plex_path = local_str.replace(self._local_prefix, self._plex_prefix)
        if plex_path == local_str and local_str.startswith('/'):
            logger.warning(
                f"Path {local_str} does not start with the configured collection "
                f"path {self._local_prefix} - Plex lookups will not match."
            )
        return plex_path

    def _convert_from_plex_path(self, plex_path: str) -> str:
        """Convert a Plex library path back to a local file path."""
        return plex_path.replace(self._plex_prefix, self._local_prefix)
    
    def _refresh_library_path(self, directory_path: Path):
        """Refresh specific directory in Plex library."""
        try:
            plex_path = self._convert_to_plex_path(directory_path)
            self.library.update(path=plex_path)
            logger.debug(f"Refreshed library path: {plex_path}")
        except Exception as e:
            logger.error(f"❌ Error refreshing library path: {e}")
    
    def _update_show_metadata(self, plex_item, show_path: Path) -> bool:
        """Update Plex item with enhanced metadata from KGLW.net API."""
        try:
            # Extract date and location from path
            show_name = show_path.name
            date_part = show_name.split(' - ')[0] if ' - ' in show_name else show_name
            
            # Get show info from KGLW.net API
            show_info = self._get_show_info_from_api(date_part)
            
            if show_info:
                # Update metadata using the newer API methods
                try:
                    # Update summary/description
                    if show_info.get('setlist_notes'):
                        plex_item.editSummary(show_info['setlist_notes'])
                        logger.debug(f"Updated summary for: {plex_item.title}")
                    
                    # Update other metadata fields as available
                    # Note: Some fields might not be available in all Plex versions
                    
                    return True
                    
                except Exception as e:
                    # Fallback to deprecated edit method if newer methods fail
                    logger.warning(f"New edit methods failed, trying deprecated edit: {e}")
                    try:
                        edit_data = {}
                        if show_info.get('setlist_notes'):
                            edit_data['summary'] = show_info['setlist_notes']
                        
                        if edit_data:
                            plex_item.edit(**edit_data)
                            return True
                    except Exception as e2:
                        logger.error(f"❌ Both edit methods failed: {e2}")
                        return False
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error updating metadata: {e}")
            return False
    
    def _get_show_info_from_api(self, date_str: str) -> Optional[Dict]:
        """Get show information from KGLW.net API."""
        try:
            # Try to parse date
            if len(date_str) >= 10:
                show_date = date_str[:10]  # YYYY-MM-DD format
                show_info = self.kglw_api.get_show_by_date(show_date)
                return show_info
        except Exception as e:
            logger.debug(f"No API info found for {date_str}: {e}")
        
        return None
    
    def _add_to_collection(self, plex_item, tour_name: str) -> bool:
        """Add Plex item to tour collection."""
        try:
            # Get current collections
            current_collections = [coll.tag for coll in plex_item.collections]
            
            # Skip if already in correct collection
            if tour_name in current_collections:
                logger.debug(f"Already in collection: {tour_name}")
                return True
            
            # Add to collection (Plex will auto-create if doesn't exist)
            plex_item.addCollection(tour_name)
            logger.info(f"✅ Added to collection: {tour_name}")
            
            # Set collection sort title if this is a new collection
            self._ensure_collection_sort_title(tour_name)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error adding to collection {tour_name}: {e}")
            return False
    
    def _ensure_collection_sort_title(self, tour_name: str):
        """Ensure collection has proper sort title with underscore prefix."""
        try:
            collections = self.library.collections()
            
            for collection in collections:
                if collection.title == tour_name:
                    current_sort = getattr(collection, 'titleSort', '')
                    expected_sort = f"_{tour_name}"
                    
                    if current_sort != expected_sort:
                        collection.editSortTitle(expected_sort)
                        logger.debug(f"Set collection sort title: {expected_sort}")
                    break
                    
        except Exception as e:
            logger.error(f"❌ Error setting collection sort title: {e}")
    
    def get_library_stats(self) -> Dict[str, any]:
        """Get statistics about the Plex library."""
        try:
            all_items = self.library.all()
            collections = self.library.collections()
            
            stats = {
                'total_items': len(all_items),
                'total_collections': len(collections),
                'collections': [coll.title for coll in collections],
                'recent_items': []
            }
            
            # Get recent additions (last 10)
            recent_items = sorted(all_items, key=lambda x: x.addedAt, reverse=True)[:10]
            for item in recent_items:
                stats['recent_items'].append({
                    'title': item.title,
                    'added_at': item.addedAt,
                    'collections': [coll.tag for coll in item.collections]
                })
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Error getting library stats: {e}")
            return {'error': str(e)}
    
    def find_shows_missing_from_collections(self) -> List[Dict[str, any]]:
        """Find shows that aren't assigned to any collection."""
        missing_shows = []
        
        try:
            all_items = self.library.all()
            
            for item in all_items:
                collections = [coll.tag for coll in item.collections]
                
                if not collections:
                    # Get file path to determine expected tour
                    file_path = None
                    for media in item.media:
                        for part in media.parts:
                            file_path = part.file
                            break
                        if file_path:
                            break
                    
                    expected_tour = None
                    if file_path:
                        # Convert Plex path back to local path for analysis
                        local_path = self._convert_from_plex_path(file_path)
                        tour_name = Path(local_path).parent.parent.name
                        expected_tour = tour_name
                    
                    missing_shows.append({
                        'title': item.title,
                        'rating_key': item.ratingKey,
                        'file_path': file_path,
                        'expected_tour': expected_tour,
                        'added_at': item.addedAt
                    })
            
            logger.info(f"Found {len(missing_shows)} shows missing from collections")
            return missing_shows
            
        except Exception as e:
            logger.error(f"❌ Error finding missing shows: {e}")
            return []
    
    def batch_process_missing_shows(self) -> Dict[str, int]:
        """Process all shows missing from collections."""
        results = {
            'processed': 0,
            'updated': 0,
            'failed': 0
        }
        
        missing_shows = self.find_shows_missing_from_collections()
        
        for show_data in missing_shows:
            results['processed'] += 1
            
            try:
                # Get the Plex item
                plex_item = self.plex.fetchItem(show_data['rating_key'])
                tour_name = show_data['expected_tour']
                
                if tour_name and self._add_to_collection(plex_item, tour_name):
                    results['updated'] += 1
                    logger.info(f"✅ Added {plex_item.title} to {tour_name}")
                else:
                    results['failed'] += 1
                    logger.warning(f"⚠️  Failed to add {plex_item.title} to collection")
                    
            except Exception as e:
                results['failed'] += 1
                logger.error(f"❌ Error processing {show_data['title']}: {e}")
        
        logger.info(f"Batch processing complete: {results['updated']}/{results['processed']} shows updated")
        return results
    
    def find_unmatched_items(self) -> List[Dict[str, any]]:
        """Find unmatched items in the Plex library."""
        unmatched_items = []
        
        try:
            all_items = self.library.all()
            
            for item in all_items:
                # Check if item appears to be unmatched (usually indicated by generic titles)
                if not hasattr(item, 'guid') or not item.guid or item.guid == 'local://':
                    # Get file path to determine expected info
                    file_path = None
                    for media in item.media:
                        for part in media.parts:
                            file_path = part.file
                            break
                        if file_path:
                            break
                    
                    if file_path:
                        # Extract expected show info from path
                        local_path = self._convert_from_plex_path(file_path)
                        path_obj = Path(local_path)
                        show_dir = path_obj.parent.name
                        tour_dir = path_obj.parent.parent.name
                        
                        # Parse show info from directory name
                        expected_title = self._generate_expected_title_from_path(show_dir)
                        
                        unmatched_items.append({
                            'rating_key': item.ratingKey,
                            'current_title': item.title,
                            'expected_title': expected_title,
                            'file_path': file_path,
                            'local_path': local_path,
                            'show_dir': show_dir,
                            'tour_dir': tour_dir,
                            'added_at': item.addedAt
                        })
            
            logger.info(f"Found {len(unmatched_items)} unmatched items")
            return unmatched_items
            
        except Exception as e:
            logger.error(f"❌ Error finding unmatched items: {e}")
            return []
    
    def _generate_expected_title_from_path(self, show_dir: str) -> str:
        """Generate expected Plex title from show directory name."""
        # Show directory format: "YYYY-MM-DD - Location, State/Country (Venue)"
        if ' - ' in show_dir:
            parts = show_dir.split(' - ')
            if len(parts) >= 2:
                date = parts[0]
                location_venue = parts[1]
                
                # Remove venue part if present
                if ' (' in location_venue and ')' in location_venue:
                    location = location_venue.split(' (')[0]
                else:
                    location = location_venue
                
                return f"{date} - {location}"
        
        return show_dir
    
    def auto_fix_unmatched_items(self) -> Dict[str, int]:
        """Automatically fix unmatched items by updating titles and metadata."""
        results = {
            'processed': 0,
            'fixed': 0,
            'failed': 0
        }
        
        unmatched_items = self.find_unmatched_items()
        
        for item_data in unmatched_items:
            results['processed'] += 1
            
            try:
                # Get the Plex item
                plex_item = self.plex.fetchItem(item_data['rating_key'])
                
                # Fix title
                expected_title = item_data['expected_title']
                if plex_item.title != expected_title:
                    plex_item.editTitle(expected_title)
                    logger.info(f"📝 Updated title: {plex_item.title} → {expected_title}")
                
                # Update metadata from KGLW.net API
                show_path = Path(item_data['local_path']).parent
                self._update_show_metadata(plex_item, show_path)
                
                # Add to proper collection
                tour_name = item_data['tour_dir']
                self._add_to_collection(plex_item, tour_name)
                
                results['fixed'] += 1
                logger.info(f"✅ Fixed unmatched item: {expected_title}")
                
            except Exception as e:
                results['failed'] += 1
                logger.error(f"❌ Failed to fix item {item_data['current_title']}: {e}")
        
        logger.info(f"Auto-fix complete: {results['fixed']}/{results['processed']} items fixed")
        return results
    
    def comprehensive_library_fix(self) -> Dict[str, any]:
        """Run a comprehensive fix of the entire library."""
        logger.info("🔄 Starting comprehensive library fix...")

        results = {
            'unmatched_fixed': 0,
            'collections_updated': 0,
            'metadata_updated': 0,
            'titles_fixed': 0,
            'multi_show_fixed': 0,
            'multi_show_titles_fixed': 0,
            'multi_show_collections_updated': 0,
            'errors': []
        }

        try:
            # Step 1: Fix items with multiple shows grouped together
            logger.info("1️⃣ Fixing multi-show items (items with files from different shows)...")
            multi_show_results = self.fix_multi_show_items()
            results['multi_show_fixed'] = multi_show_results['fixed']
            results['multi_show_titles_fixed'] = multi_show_results.get('titles_fixed', 0)
            results['multi_show_collections_updated'] = multi_show_results.get('collections_updated', 0)

            # Step 2: Fix unmatched items
            logger.info("2️⃣ Fixing unmatched items...")
            unmatched_results = self.auto_fix_unmatched_items()
            results['unmatched_fixed'] = unmatched_results['fixed']

            # Step 3: Fix missing collections
            logger.info("3️⃣ Processing missing collections...")
            collection_results = self.batch_process_missing_shows()
            results['collections_updated'] = collection_results['updated']

            # Step 4: Check for items with incorrect titles
            logger.info("4️⃣ Checking for title mismatches...")
            title_results = self._fix_title_mismatches()
            results['titles_fixed'] = title_results['fixed']

            logger.info("✅ Comprehensive library fix completed")

        except Exception as e:
            error_msg = f"Error in comprehensive fix: {e}"
            logger.error(f"❌ {error_msg}")
            results['errors'].append(error_msg)

        return results
    
    def _fix_title_mismatches(self) -> Dict[str, int]:
        """Fix titles that don't match the expected format."""
        results = {
            'processed': 0,
            'fixed': 0,
            'failed': 0
        }
        
        try:
            all_items = self.library.all()
            
            for item in all_items:
                results['processed'] += 1
                
                # Get file path to determine expected title
                file_path = None
                for media in item.media:
                    for part in media.parts:
                        file_path = part.file
                        break
                    if file_path:
                        break
                
                if file_path:
                    local_path = self._convert_from_plex_path(file_path)
                    path_obj = Path(local_path)
                    show_dir = path_obj.parent.name
                    
                    expected_title = self._generate_expected_title_from_path(show_dir)
                    
                    # Check if title needs fixing
                    if item.title != expected_title and not item.title.startswith(expected_title[:10]):
                        try:
                            item.editTitle(expected_title)
                            results['fixed'] += 1
                            logger.info(f"📝 Fixed title: {item.title} → {expected_title}")
                        except Exception as e:
                            results['failed'] += 1
                            logger.error(f"❌ Failed to fix title for {item.title}: {e}")
        
        except Exception as e:
            logger.error(f"❌ Error fixing title mismatches: {e}")
        
        logger.info(f"Title fix complete: {results['fixed']}/{results['processed']} titles fixed")
        return results

    def find_multi_show_items(self) -> List[Dict[str, any]]:
        """Find Plex items that have multiple media files from different shows.

        This happens when Plex incorrectly groups different shows into one item,
        typically because the filenames were too similar (e.g., all starting with artist name).
        """
        multi_show_items = []

        try:
            all_items = self.library.all()

            for item in all_items:
                # Check if item has multiple media files
                if len(item.media) <= 1:
                    continue

                # Extract dates from each media file
                dates_found = set()
                file_dates = []

                for media in item.media:
                    for part in media.parts:
                        file_path = part.file

                        # Extract date from filename/path
                        # Format: /library/kglw/2024 Tour Name/2024-11-20 - Location/video.mp4
                        import re
                        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', file_path)

                        if date_match:
                            date = date_match.group(1)
                            dates_found.add(date)
                            file_dates.append({
                                'file': file_path,
                                'date': date
                            })

                # If we found multiple different dates, this is a multi-show item
                if len(dates_found) > 1:
                    multi_show_items.append({
                        'rating_key': item.ratingKey,
                        'title': item.title,
                        'media_count': len(item.media),
                        'dates_found': sorted(list(dates_found)),
                        'file_dates': file_dates
                    })

                    logger.warning(f"⚠️  Multi-show item found: '{item.title}' has {len(item.media)} files from {len(dates_found)} different shows")

            logger.info(f"Found {len(multi_show_items)} items with multiple shows grouped together")
            return multi_show_items

        except Exception as e:
            logger.error(f"❌ Error finding multi-show items: {e}")
            return []

    def fix_multi_show_items(self, auto_confirm: bool = False) -> Dict[str, int]:
        """Fix items that have multiple shows incorrectly grouped together.

        This uses the Plex split() method to separate grouped media into individual items,
        then fixes the titles of the newly split items to match their file paths.
        """
        results = {
            'found': 0,
            'fixed': 0,
            'failed': 0,
            'titles_fixed': 0,
            'collections_updated': 0
        }

        multi_show_items = self.find_multi_show_items()
        results['found'] = len(multi_show_items)

        if not multi_show_items:
            logger.info("✅ No multi-show items found")
            return results

        # Track file paths that were split so we can fix their titles
        split_file_paths = []

        for item_data in multi_show_items:
            try:
                plex_item = self.plex.fetchItem(item_data['rating_key'])

                logger.info(f"🔧 Splitting: '{item_data['title']}' ({item_data['media_count']} files from {len(item_data['dates_found'])} shows)")

                # Collect file paths before splitting
                for file_info in item_data['file_dates']:
                    split_file_paths.append(file_info['file'])

                # Split the item - this separates all grouped media files into individual items
                try:
                    plex_item.split()
                    logger.info(f"✅ Split '{item_data['title']}' into {item_data['media_count']} separate items")
                    results['fixed'] += 1
                except Exception as e:
                    logger.error(f"❌ Failed to split: {e}")
                    results['failed'] += 1

            except Exception as e:
                logger.error(f"❌ Failed to fix multi-show item: {e}")
                results['failed'] += 1

        if results['fixed'] > 0:
            logger.info(f"🔄 Refreshing library and fixing titles of split items...")
            try:
                self.library.update()

                # Wait a moment for Plex to process the split
                import time
                time.sleep(2)

                # Now fix titles and posters of all the split items
                logger.info(f"📝 Fixing titles and posters for {len(split_file_paths)} split items...")
                for file_path in split_file_paths:
                    try:
                        # Find the item by file path
                        for item in self.library.all():
                            for media in item.media:
                                for part in media.parts:
                                    if part.file == file_path:
                                        # Generate expected title from file path
                                        local_path = self._convert_from_plex_path(file_path)
                                        from pathlib import Path
                                        show_dir = Path(local_path).parent.name
                                        expected_title = self._generate_expected_title_from_path(show_dir)

                                        # Fix title if needed
                                        if item.title != expected_title:
                                            item.editTitle(expected_title)
                                            logger.debug(f"📝 Fixed title: {item.title} → {expected_title}")
                                            results['titles_fixed'] += 1

                                        # Update all metadata from KGLW API
                                        try:
                                            # Extract date from show directory name
                                            import re
                                            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', show_dir)
                                            if date_match:
                                                show_date = date_match.group(1)
                                                show_info = self.kglw_api.get_show_by_date(show_date)

                                                if show_info:
                                                    # Update summary with setlist notes
                                                    if show_info.get('setlist_notes'):
                                                        item.editSummary(show_info['setlist_notes'])
                                                        logger.debug(f"📝 Updated summary for: {expected_title}")

                                                    # Unlock and set poster
                                                    if show_info.get('poster_image'):
                                                        poster_url = show_info['poster_image']
                                                        if poster_url.startswith(("http://", "https://")):
                                                            # Unlock poster first to allow updating
                                                            try:
                                                                item.unlockPoster()
                                                            except:
                                                                pass  # It's ok if it's already unlocked

                                                            item.uploadPoster(url=poster_url)
                                                            logger.debug(f"🎨 Set poster for: {expected_title}")

                                                    # Fix collections - remove old ones and add correct tour
                                                    if show_info.get('tourname'):
                                                        correct_tour = show_info['tourname']

                                                        # Get current collections
                                                        current_collections = [coll.tag for coll in item.collections]

                                                        # Remove all current collections
                                                        for coll in current_collections:
                                                            item.removeCollection(coll)
                                                            logger.debug(f"🗑️  Removed collection '{coll}' from {expected_title}")

                                                        # Add correct collection
                                                        item.addCollection(correct_tour)
                                                        logger.debug(f"📚 Added collection '{correct_tour}' to {expected_title}")
                                                        results['collections_updated'] = results.get('collections_updated', 0) + 1
                                        except Exception as e:
                                            logger.debug(f"Could not set metadata for {expected_title}: {e}")

                                        break
                    except Exception as e:
                        logger.warning(f"⚠️  Failed to fix title/poster for {file_path}: {e}")

                logger.info(f"✅ Fixed {results['titles_fixed']} titles, {results['collections_updated']} collections, and posters")

            except Exception as e:
                logger.warning(f"⚠️  Library refresh failed: {e}")

        logger.info(f"Multi-show fix complete: {results['fixed']}/{results['found']} items split, {results['titles_fixed']} titles fixed, {results['collections_updated']} collections updated")
        return results

    def find_multi_show_library_items(self) -> List[Dict[str, Any]]:
        """Find Plex library items with multiple shows grouped together.

        This is an alias/wrapper for find_multi_show_items() that reformats the output
        to match test expectations with 'title' and 'file_paths' keys.

        Returns:
            List of dictionaries with keys:
                - title: The Plex item title
                - file_paths: List of file paths in the item
        """
        multi_items = self.find_multi_show_items()

        # Reformat to match test expectations
        reformatted = []
        for item in multi_items:
            file_paths = [file_info['file'] for file_info in item.get('file_dates', [])]
            reformatted.append({
                'title': item['title'],
                'file_paths': file_paths,
                'rating_key': item.get('rating_key')  # Include for compatibility
            })

        return reformatted

    def split_multi_show_item(self, rating_key: str) -> Dict[str, Any]:
        """Split a single Plex item with multiple shows into separate items.

        Args:
            rating_key: The Plex rating key of the item to split

        Returns:
            Dictionary with keys:
                - success: Boolean indicating if split was successful
                - split_count: Number of items created from the split
                - error: Error message if split failed
        """
        try:
            # Fetch the item
            plex_item = self.plex.fetchItem(rating_key)

            # Get the number of media files before splitting
            media_count = len(plex_item.media)

            # Perform the split
            plex_item.split()

            logger.info(f"✅ Split item {rating_key} into {media_count} separate items")

            return {
                'success': True,
                'split_count': media_count
            }

        except Exception as e:
            logger.error(f"❌ Failed to split item {rating_key}: {e}")
            return {
                'success': False,
                'split_count': 0,
                'error': str(e)
            }

    def refresh_metadata_from_api(self) -> Dict[str, int]:
        """Refresh metadata (summaries, posters, collections) for all items from KGLW.net API."""
        results = {
            'processed': 0,
            'metadata_updated': 0,
            'posters_updated': 0,
            'collections_updated': 0,
            'failed': 0
        }

        try:
            all_items = self.library.all()
            logger.info(f"📚 Refreshing metadata for {len(all_items)} items from KGLW.net API...")

            for item in all_items:
                results['processed'] += 1

                try:
                    # Get file path to extract date
                    file_path = None
                    for media in item.media:
                        for part in media.parts:
                            file_path = part.file
                            break
                        if file_path:
                            break

                    if not file_path:
                        logger.warning(f"⚠️  No file path found for item: {item.title}")
                        continue

                    # Extract date from file path
                    import re
                    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', file_path)
                    if not date_match:
                        logger.warning(f"⚠️  No date found in path for: {item.title} ({file_path})")
                        continue

                    show_date = date_match.group(1)
                    logger.info(f"🔍 Processing {item.title} (date: {show_date})")
                    show_info = self.kglw_api.get_show_by_date(show_date)

                    if not show_info:
                        logger.warning(f"⚠️  No API data found for {item.title} ({show_date})")
                        continue

                    # Update summary with setlist notes
                    if show_info.get('setlist_notes'):
                        current_summary = getattr(item, 'summary', '')
                        if current_summary != show_info['setlist_notes']:
                            item.editSummary(show_info['setlist_notes'])
                            logger.info(f"📝 Updated summary for: {item.title}")
                            results['metadata_updated'] += 1

                    # Update poster from uploads endpoint
                    poster_url = self.kglw_api.get_poster_url_for_date(show_date)
                    if poster_url:
                        logger.info(f"🔍 Found poster URL for {item.title}: {poster_url}")
                        try:
                            # Unlock poster first
                            try:
                                item.unlockPoster()
                                logger.info(f"🔓 Unlocked poster for: {item.title}")
                            except Exception as unlock_err:
                                logger.debug(f"Poster already unlocked or unlock not needed: {unlock_err}")

                            # Upload new poster
                            item.uploadPoster(url=poster_url)
                            logger.info(f"🎨 Updated poster for: {item.title}")
                            results['posters_updated'] += 1
                        except Exception as poster_err:
                            logger.warning(f"⚠️  Failed to upload poster for {item.title}: {poster_err}")
                    else:
                        logger.debug(f"No poster found in uploads API for {item.title} ({show_date})")

                    # Fix collections - remove incorrect collections and add correct tour
                    if show_info.get('tourname'):
                        correct_tour = show_info['tourname']

                        # Get current collections
                        current_collections = [coll.tag for coll in item.collections]

                        logger.info(f"🏷️  Current collections for {item.title}: {current_collections}")
                        logger.info(f"🎯 Target collection: {correct_tour}")

                        # Only update if collections are wrong
                        if len(current_collections) != 1 or (current_collections and current_collections[0] != correct_tour):
                            # Remove all current collections by working with collection objects directly
                            for coll_obj in list(item.collections):  # Use list() to avoid modifying during iteration
                                try:
                                    coll_tag = coll_obj.tag
                                    logger.info(f"🗑️  Attempting to remove collection '{coll_tag}' from {item.title}")
                                    # Use the collection object directly
                                    item.removeCollection(coll_obj)
                                    logger.info(f"✅ Removed collection '{coll_tag}'")
                                except Exception as remove_err:
                                    logger.warning(f"⚠️  Failed to remove collection '{coll_tag}': {remove_err}")

                            # CRITICAL: Reload item after removals to ensure changes are reflected
                            logger.info(f"🔄 Reloading item after removals...")
                            item.reload()

                            # Verify removals worked
                            after_removal = [coll.tag for coll in item.collections]
                            logger.info(f"📋 Collections after removal: {after_removal}")

                            # Add correct collection only if not already present
                            if correct_tour not in after_removal:
                                try:
                                    item.addCollection(correct_tour)
                                    logger.info(f"📚 Added collection '{correct_tour}' to {item.title}")

                                    # Verify the final state
                                    item.reload()
                                    new_collections = [coll.tag for coll in item.collections]
                                    logger.info(f"✅ Final collections: {new_collections}")

                                    results['collections_updated'] += 1
                                except Exception as add_err:
                                    logger.warning(f"⚠️  Failed to add collection '{correct_tour}': {add_err}")
                            else:
                                logger.info(f"✅ Collection '{correct_tour}' already present after cleanup")

                except Exception as e:
                    results['failed'] += 1
                    logger.debug(f"Failed to update metadata for {item.title}: {e}")

            logger.info(f"✅ Metadata refresh complete: {results['metadata_updated']} summaries, {results['posters_updated']} posters, {results['collections_updated']} collections updated")

        except Exception as e:
            logger.error(f"❌ Error refreshing metadata: {e}")

        return results

    def cleanup_empty_collections(self, dry_run: bool = True) -> Dict[str, int]:
        """Remove all Plex collections with 0 items.

        Args:
            dry_run: If True, only report what would be deleted without actually deleting

        Returns:
            Dictionary with cleanup statistics
        """
        results = {
            'total': 0,
            'empty': 0,
            'deleted': 0,
            'failed': 0
        }

        try:
            logger.info("🧹 Starting empty collection cleanup...")
            if dry_run:
                logger.info("🔍 DRY RUN MODE - No collections will be deleted")

            # Get all collections
            all_collections = self.library.collections()
            results['total'] = len(all_collections)

            logger.info(f"📊 Found {results['total']} total collections")

            # Identify empty collections
            empty_collections = []
            for collection in all_collections:
                item_count = len(collection.items())
                if item_count == 0:
                    empty_collections.append(collection)
                    results['empty'] += 1

            logger.info(f"📊 Collection Summary:")
            logger.info(f"   - Total collections: {results['total']}")
            logger.info(f"   - Empty collections (0 items): {results['empty']}")
            logger.info(f"   - Collections with items: {results['total'] - results['empty']}")

            if not empty_collections:
                logger.info("✅ No empty collections found!")
                return results

            logger.info(f"🗑️  Empty collections to remove:")
            for collection in empty_collections:
                logger.info(f"   - {collection.title} (0 items)")

            if dry_run:
                logger.info("🔍 DRY RUN COMPLETE - Run with dry_run=False to actually delete")
                return results

            # Actually delete the collections
            logger.info("\n🗑️  Deleting empty collections...")
            for collection in empty_collections:
                try:
                    title = collection.title
                    collection.delete()
                    logger.info(f"✅ Deleted: {title}")
                    results['deleted'] += 1
                except Exception as e:
                    logger.warning(f"❌ Failed to delete '{collection.title}': {e}")
                    results['failed'] += 1

            logger.info(f"\n🎉 Collection cleanup completed!")
            logger.info(f"📊 Results:")
            logger.info(f"   - Deleted collections: {results['deleted']}")
            logger.info(f"   - Failed deletions: {results['failed']}")
            logger.info(f"   - Remaining collections: {results['total'] - results['deleted']}")

        except Exception as e:
            logger.error(f"❌ Error during collection cleanup: {e}")

        return results