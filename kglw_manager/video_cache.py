"""Video metadata caching system."""

import json
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from .utils import setup_logging

logger = setup_logging()


class VideoMetadataCache:
    """Cache for video metadata to avoid repeated ffprobe calls."""
    
    def __init__(self, cache_dir: Path = None):
        """Initialize cache."""
        if cache_dir is None:
            cache_dir = Path.home() / '.kglw_manager' / 'cache'
        
        self.cache_dir = cache_dir
        self.cache_file = cache_dir / 'video_metadata.json'
        self.cache_data = {}
        
        # Create cache directory
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Load existing cache
        self._load_cache()
    
    def _load_cache(self):
        """Load cache from disk."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    self.cache_data = json.load(f)
                logger.debug(f"Loaded {len(self.cache_data)} cached entries")
            except (json.JSONDecodeError, FileNotFoundError):
                logger.warning("Failed to load cache, starting fresh")
                self.cache_data = {}
    
    def _save_cache(self):
        """Save cache to disk."""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache_data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")
    
    def _get_cache_key(self, file_path: Path) -> str:
        """Generate cache key for file."""
        return str(file_path.absolute())
    
    def _get_file_signature(self, file_path: Path) -> str:
        """Generate a signature for the file based on size and modification time."""
        try:
            stat = file_path.stat()
            signature = f"{stat.st_size}:{stat.st_mtime_ns}"
            return hashlib.md5(signature.encode()).hexdigest()
        except OSError:
            return ""
    
    def get_metadata(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Get cached metadata for a file."""
        cache_key = self._get_cache_key(file_path)
        
        if cache_key not in self.cache_data:
            return None
        
        cached_entry = self.cache_data[cache_key]
        current_signature = self._get_file_signature(file_path)
        
        # Check if file has changed
        if cached_entry.get('signature') != current_signature:
            logger.debug(f"File changed, invalidating cache: {file_path.name}")
            del self.cache_data[cache_key]
            # Persist the invalidation, otherwise the stale entry resurrects
            # from disk if the process exits before the next set_metadata().
            self._save_cache()
            return None
        
        return cached_entry.get('metadata')
    
    def set_metadata(self, file_path: Path, metadata: Dict[str, Any]):
        """Cache metadata for a file."""
        cache_key = self._get_cache_key(file_path)
        file_signature = self._get_file_signature(file_path)
        
        self.cache_data[cache_key] = {
            'signature': file_signature,
            'metadata': metadata,
            'file_name': file_path.name  # For debugging
        }
        
        logger.debug(f"Cached metadata: {file_path.name}")
        
        # Save to disk after each entry for better reliability
        self._save_cache()
    
    def invalidate(self, file_path: Path):
        """Remove cached entry for a file."""
        cache_key = self._get_cache_key(file_path)
        if cache_key in self.cache_data:
            del self.cache_data[cache_key]
            self._save_cache()
    
    def cleanup_stale_entries(self):
        """Remove cache entries for files that no longer exist."""
        stale_keys = []
        
        for cache_key, entry in self.cache_data.items():
            file_path = Path(cache_key)
            if not file_path.exists():
                stale_keys.append(cache_key)
        
        if stale_keys:
            for key in stale_keys:
                del self.cache_data[key]
            self._save_cache()
            logger.debug(f"Cleaned up {len(stale_keys)} stale cache entries")
    
    def clear_cache(self):
        """Clear all cached data."""
        self.cache_data = {}
        if self.cache_file.exists():
            self.cache_file.unlink()
        logger.info("Cleared video metadata cache")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_entries = len(self.cache_data)
        cache_size = 0
        
        if self.cache_file.exists():
            cache_size = self.cache_file.stat().st_size
        
        return {
            'total_entries': total_entries,
            'cache_file_size': cache_size,
            'cache_file_path': str(self.cache_file)
        }