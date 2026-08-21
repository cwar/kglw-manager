"""Diskcache-based collection caching system to replace the unreliable JSON cache."""

import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, Set
from diskcache import Cache
from .utils import setup_logging

logger = setup_logging()


class DiskcacheCollectionCache:
    """High-performance, reliable collection cache using diskcache."""

    def __init__(self, cache_dir: Path = None):
        """Initialize diskcache collection cache."""
        if cache_dir is None:
            cache_dir = Path.home() / '.kglw_manager' / 'diskcache'

        self.cache_dir = cache_dir

        # Create cache directory and initialize diskcache
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Initialize diskcache with optimized settings
        self.cache = Cache(
            directory=str(cache_dir),
            size_limit=500 * 1024 * 1024,  # 500MB cache limit
            eviction_policy='least-recently-stored'  # Evict old scans first
        )

        logger.debug(f"Initialized diskcache collection cache at {cache_dir}")

        # Add compatibility properties for tests
        self.cache_file = self.cache_dir / 'collection_structure.json'

    @property
    def cache_data(self) -> Dict[str, Any]:
        """Legacy compatibility property - returns all cached collections."""
        try:
            result = {}
            for key in self.cache:
                if key.startswith('collection:'):
                    cached_entry = self.cache.get(key)
                    if cached_entry:
                        result[key] = cached_entry.get('data', {})
            return result
        except Exception:
            return {}

    def is_empty(self) -> bool:
        """Check if the cache is completely empty."""
        try:
            # Check if there are any keys in the cache
            return len(self.cache) == 0
        except Exception:
            return True

    def get_cached_show(self, show_path: Path, skip_signature_check: bool = False) -> Optional[Dict[str, Any]]:
        """Get cached show data if still valid."""
        cache_key = f"show:{show_path.absolute()}"

        try:
            cached_entry = self.cache.get(cache_key)
            if cached_entry is None:
                return None

            # Skip expensive signature check if requested (for bulk operations)
            if skip_signature_check:
                return cached_entry.get('data')

            # Check if show directory signature matches
            current_sig = self._get_directory_signature(show_path)
            cached_sig = cached_entry.get('signature')

            if current_sig != cached_sig:
                # Directory changed, remove invalid cache
                self.cache.delete(cache_key)
                return None

            return cached_entry.get('data')

        except Exception as e:
            logger.warning(f"Error retrieving cached show {show_path}: {e}")
            return None

    def cache_show(self, show_path: Path, show_data: Dict[str, Any]):
        """Cache show data with signature."""
        cache_key = f"show:{show_path.absolute()}"

        try:
            cache_entry = {
                'signature': self._get_directory_signature(show_path),
                'data': show_data
            }
            self.cache[cache_key] = cache_entry
            logger.debug(f"Cached show data for {show_path}")

        except Exception as e:
            logger.warning(f"Failed to cache show {show_path}: {e}")

    def get_changed_shows(self, collection_path: Path) -> Set[Path]:
        """Get list of show directories that have changed since last cache."""
        changed_shows = set()

        try:
            if not collection_path.exists():
                return set()

            # Scan all show directories
            for tour_dir in collection_path.iterdir():
                if tour_dir.is_dir():
                    for show_dir in tour_dir.iterdir():
                        if show_dir.is_dir():
                            # Check if show is cached and valid
                            cached_show = self.get_cached_show(show_dir)
                            if cached_show is None:
                                changed_shows.add(show_dir)

            return changed_shows

        except Exception as e:
            logger.warning(f"Error checking changed shows: {e}")
            return set()

    def _get_directory_signature(self, dir_path: Path) -> str:
        """Generate robust signature based on actual file content, not timestamps."""
        try:
            if not dir_path.exists():
                return ""

            # Get list of all relevant files and their sizes
            file_info = []
            video_extensions = {'.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv'}

            try:
                for child in dir_path.iterdir():
                    if child.is_file() and child.suffix.lower() in video_extensions:
                        # Use filename + size as signature (much more reliable than timestamps)
                        file_size = child.stat().st_size
                        file_info.append(f"{child.name}:{file_size}")
                    elif child.is_dir():
                        # For subdirectories, just track their existence
                        file_info.append(f"dir:{child.name}")
            except (PermissionError, OSError) as e:
                logger.warning(f"Could not scan {dir_path}: {e}")
                return ""

            # Sort for consistent signature regardless of filesystem order
            file_info.sort()

            # Create signature from file list
            content = "|".join(file_info)
            return hashlib.md5(content.encode()).hexdigest()
        except Exception as e:
            logger.warning(f"Failed to generate directory signature for {dir_path}: {e}")
            return ""

    def _get_tour_directory_signature(self, tour_dir: Path) -> str:
        """Generate signature for a tour directory (show dir names + any direct files).

        Tracks subdirectory names (show folders) plus the name/size of any file
        placed directly in the tour directory, so adding/removing shows or files
        invalidates the tour. Contents *inside* show directories are covered by
        the per-show signatures instead.
        """
        try:
            if not tour_dir.exists():
                return ""

            entries = []

            try:
                for child in tour_dir.iterdir():
                    if child.is_dir():
                        # Track show directory names (not their contents)
                        entries.append(f"dir:{child.name}")
                    elif child.is_file():
                        entries.append(f"{child.name}:{child.stat().st_size}")
            except (PermissionError, OSError) as e:
                logger.warning(f"Could not scan tour directory {tour_dir}: {e}")
                return ""

            # Sort for consistent signature regardless of filesystem order
            entries.sort()

            content = "|".join(entries)
            return hashlib.md5(content.encode()).hexdigest()
        except Exception as e:
            logger.warning(f"Failed to generate tour directory signature for {tour_dir}: {e}")
            return ""

    def _resolve_tour_path(self, collection_path: Path, tour_name: str,
                           tour_data: Dict[str, Any]) -> Path:
        """Resolve a tour directory path from its data or its name."""
        path_value = tour_data.get('path')
        if path_value:
            return Path(path_value)
        return collection_path / tour_name

    def get_cached_collection(self, collection_path: Path) -> Optional[Dict[str, Any]]:
        """Get cached collection structure if still valid."""
        cache_key = f"collection:{collection_path.absolute()}"

        try:
            cached_entry = self.cache.get(cache_key)
            if cached_entry is None:
                logger.debug("No cache entry found for collection")
                return None

            # Check if root collection directory signature matches
            current_signature = self._get_directory_signature(collection_path)
            if cached_entry.get('signature') != current_signature:
                logger.debug("Collection directory changed, cache invalid")
                # Remove invalid cache entry
                self.cache.delete(cache_key)
                return None

            # Check signatures of individual tour directories
            cached_tours = cached_entry.get('data', {}).get('tours', {})
            tour_signatures = cached_entry.get('tour_signatures', {})
            for tour_name, tour_data in cached_tours.items():
                tour_path = self._resolve_tour_path(collection_path, tour_name, tour_data)
                if tour_path.exists():
                    current_tour_sig = self._get_tour_directory_signature(tour_path)
                    # Fall back to legacy in-data signature for old cache entries
                    cached_tour_sig = tour_signatures.get(tour_name, tour_data.get('signature'))

                    if current_tour_sig != cached_tour_sig:
                        logger.debug(f"Tour directory changed: {tour_name}, cache invalid")
                        # Remove invalid cache entry
                        self.cache.delete(cache_key)
                        return None

            logger.info("Using cached collection structure")
            return cached_entry.get('data')

        except Exception as e:
            logger.warning(f"Error retrieving cached collection: {e}")
            # Remove corrupted cache entry
            try:
                self.cache.delete(cache_key)
            except:
                pass
            return None

    def cache_collection(self, collection_path: Path, collection_data: Dict[str, Any]):
        """Cache collection structure with signatures."""
        cache_key = f"collection:{collection_path.absolute()}"

        try:
            # Compute tour signatures, stored alongside (not inside) the tour data
            # so cached data round-trips identical to what was scanned.
            tours = collection_data.get('tours', {})
            tour_signatures = {
                tour_name: self._get_tour_directory_signature(
                    self._resolve_tour_path(collection_path, tour_name, tour_data))
                for tour_name, tour_data in tours.items()
            }

            # Create cache entry
            cache_entry = {
                'signature': self._get_directory_signature(collection_path),
                'tour_signatures': tour_signatures,
                'data': {
                    'tours': tours,
                    'total_tours': collection_data.get('total_tours', 0),
                    'total_shows': collection_data.get('total_shows', 0),
                    'total_videos': collection_data.get('total_videos', 0)
                }
            }

            # Store in diskcache (automatically handles serialization)
            self.cache.set(cache_key, cache_entry)
            logger.info("Cached collection structure")

        except Exception as e:
            logger.warning(f"Failed to cache collection: {e}")

    def get_changed_tours(self, collection_path: Path) -> Set[str]:
        """Get list of tour directories that have changed since last cache.

        A tour is considered changed when:
        - it has no cached signature (new tour / cache cleared), or
        - its directory signature differs (shows or files added/removed), or
        - any of its show directories' contents changed.
        """
        try:
            if not collection_path.exists():
                return set()

            changed_tours = set()

            # Compare tour directory signatures against the cached collection
            cache_key = f"collection:{collection_path.absolute()}"
            cached_entry = self.cache.get(cache_key) or {}
            tour_signatures = cached_entry.get('tour_signatures', {})

            for tour_dir in collection_path.iterdir():
                if not tour_dir.is_dir():
                    continue
                cached_sig = tour_signatures.get(tour_dir.name)
                if cached_sig is None:
                    changed_tours.add(tour_dir.name)
                    continue
                if self._get_tour_directory_signature(tour_dir) != cached_sig:
                    changed_tours.add(tour_dir.name)

            # Also include tours whose shows' contents changed (a modified file
            # inside a show doesn't alter the tour-level signature).
            for show_dir in self.get_changed_shows(collection_path):
                changed_tours.add(show_dir.parent.name)

            return changed_tours

        except Exception as e:
            logger.warning(f"Error checking changed tours: {e}")
            # If there's an error, assume all tours changed
            if collection_path.exists():
                return {d.name for d in collection_path.iterdir() if d.is_dir()}
            return set()

    def update_tour_cache(self, collection_path: Path, tour_name: str, tour_data: Dict[str, Any]):
        """Update cache for a specific tour."""
        cache_key = f"collection:{collection_path.absolute()}"

        try:
            # Get existing cache entry or create new one
            cached_entry = self.cache.get(cache_key)
            if cached_entry is None:
                cached_entry = {
                    'signature': self._get_directory_signature(collection_path),
                    'tour_signatures': {},
                    'data': {'tours': {}, 'total_tours': 0, 'total_shows': 0, 'total_videos': 0}
                }

            # Store tour signature alongside (not inside) the tour data
            tour_path = self._resolve_tour_path(collection_path, tour_name, tour_data)
            cached_entry.setdefault('tour_signatures', {})[tour_name] = \
                self._get_tour_directory_signature(tour_path)

            # Update tour in cache
            cached_entry['data']['tours'][tour_name] = tour_data

            # Recalculate totals
            all_tours = cached_entry['data']['tours']
            cached_entry['data']['total_tours'] = len(all_tours)
            cached_entry['data']['total_shows'] = sum(
                len(tour.get('shows', {})) for tour in all_tours.values()
            )
            cached_entry['data']['total_videos'] = sum(
                sum(len(show.get('files', [])) for show in tour.get('shows', {}).values())
                for tour in all_tours.values()
            )

            # Store updated entry
            self.cache.set(cache_key, cached_entry)
            logger.debug(f"Updated cache for tour: {tour_name}")

        except Exception as e:
            logger.warning(f"Failed to update tour cache: {e}")

    def clear_cache(self):
        """Clear all cached data."""
        try:
            self.cache.clear()
            logger.info("Cleared collection cache")
        except Exception as e:
            logger.warning(f"Failed to clear cache: {e}")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            stats = {
                'total_collections': len([k for k in self.cache if k.startswith('collection:')]),
                'cache_size_bytes': self.cache.volume(),
                'cache_file_size': self.cache.volume(),  # Compatibility alias
                'cache_directory': str(self.cache_dir),
                'cache_file_path': str(self.cache_file),  # Compatibility field
                'cache_settings': {
                    'size_limit_mb': self.cache.size_limit / (1024 * 1024),
                    'eviction_policy': self.cache.eviction_policy,
                    'disk_min_file_size': self.cache.disk_min_file_size
                }
            }
            return stats
        except Exception as e:
            logger.warning(f"Failed to get cache stats: {e}")
            return {
                'error': str(e),
                'cache_directory': str(self.cache_dir),
                'cache_file_path': str(self.cache_file),
                'total_collections': 0,
                'cache_file_size': 0
            }