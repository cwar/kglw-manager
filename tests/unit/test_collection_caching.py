"""
Comprehensive tests for collection caching functionality.
"""

import pytest
import tempfile
import json
import shutil
import time
from pathlib import Path
from unittest.mock import Mock, patch

from kglw_manager.collection import CollectionManager
from kglw_manager.diskcache_collection import DiskcacheCollectionCache as CollectionCache


class TestCollectionCache:
    """Test collection caching functionality."""
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create temporary cache directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    def cache_instance(self, temp_cache_dir):
        """Create cache instance with temp directory."""
        return CollectionCache(temp_cache_dir)
    
    @pytest.fixture
    def sample_scan_results(self):
        """Sample collection scan results for testing."""
        return {
            'tours': {
                '2024 USA Tour': {
                    'path': '/fake/path/2024 USA Tour',
                    'shows': {
                        '2024-01-15 - Austin': {
                            'date': '2024-01-15',
                            'location': 'Austin',
                            'venue': 'Moody Center',
                            'files': [
                                {
                                    'path': '/collection/2024 USA Tour/2024-01-15 - Austin/video.mp4',
                                    'size': 2000000000,
                                    'quality': '1080p',
                                    'duration': 5400
                                }
                            ]
                        }
                    }
                }
            },
            'total_tours': 1,
            'total_shows': 1,
            'total_videos': 1
        }
    
    @pytest.mark.unit
    def test_cache_initialization(self, temp_cache_dir):
        """Test cache initialization creates necessary directories."""
        cache = CollectionCache(temp_cache_dir)
        
        # Should create cache directory if it doesn't exist
        assert temp_cache_dir.exists()
        assert temp_cache_dir.is_dir()
        
        # Should have cache file path set
        expected_cache_file = temp_cache_dir / 'collection_structure.json'
        assert cache.cache_file == expected_cache_file
    
    @pytest.mark.unit
    def test_cache_storage_and_retrieval(self, cache_instance, sample_scan_results):
        """Test basic cache storage and retrieval."""
        collection_path = Path("/fake/collection")
        
        # Store data in cache
        cache_instance.cache_collection(collection_path, sample_scan_results)
        
        # Retrieve data from cache
        retrieved = cache_instance.get_cached_collection(collection_path)
        
        assert retrieved is not None
        assert retrieved['total_tours'] == sample_scan_results['total_tours']
        assert retrieved['total_shows'] == sample_scan_results['total_shows']
        assert '2024 USA Tour' in retrieved['tours']
    
    @pytest.mark.unit  
    def test_cache_miss_on_nonexistent_path(self, cache_instance):
        """Test cache miss when path doesn't exist in cache."""
        collection_path = Path("/nonexistent/collection")
        
        result = cache_instance.get_cached_collection(collection_path)
        assert result is None
    
    @pytest.mark.unit
    def test_cache_key_generation(self, cache_instance):
        """Test cache key generation for different paths."""
        paths = [
            Path("/collection/kglw"),
            Path("/another/collection"),
            Path("/collection with spaces/kglw"),
        ]
        
        # Cache some data for each path
        sample_data = {'tours': {}, 'total_tours': 0, 'total_shows': 0, 'total_videos': 0}
        
        for path in paths:
            cache_instance.cache_collection(path, sample_data)
            
            # Should be retrievable
            result = cache_instance.get_cached_collection(path)
            assert result is not None
            assert result['total_tours'] == 0
        
        # All paths should be stored separately
        assert len(cache_instance.cache_data) >= len(paths)
    
    @pytest.mark.unit
    def test_cache_file_corruption_handling(self, temp_cache_dir):
        """Test handling of corrupted cache files."""
        # Create a corrupted cache file
        cache_file = temp_cache_dir / 'collection_structure.json'
        cache_file.write_text("invalid json content {")
        
        # Creating cache instance should handle corruption gracefully
        cache_instance = CollectionCache(temp_cache_dir)
        
        # Should start with empty cache data
        assert cache_instance.cache_data == {}
        
        # Should be able to store new data
        collection_path = Path("/fake/collection")
        sample_data = {'tours': {}, 'total_tours': 0, 'total_shows': 0, 'total_videos': 0}
        cache_instance.cache_collection(collection_path, sample_data)
        
        # Should be able to retrieve it
        result = cache_instance.get_cached_collection(collection_path)
        assert result is not None
    
    @pytest.mark.unit
    def test_cache_clear_functionality(self, cache_instance, sample_scan_results):
        """Test cache clearing functionality."""
        collection_path = Path("/fake/collection")
        
        # Store some data
        cache_instance.cache_collection(collection_path, sample_scan_results)
        assert cache_instance.get_cached_collection(collection_path) is not None
        
        # Clear cache
        cache_instance.clear_cache()
        
        # Should be empty now
        result = cache_instance.get_cached_collection(collection_path)
        assert result is None
        assert cache_instance.cache_data == {}
    
    @pytest.mark.unit
    def test_cache_stats(self, cache_instance, sample_scan_results):
        """Test cache statistics functionality."""
        # Get initial stats
        stats = cache_instance.get_cache_stats()
        assert 'total_collections' in stats
        assert 'cache_file_size' in stats
        assert 'cache_file_path' in stats
        
        # Should start with 0 collections
        assert stats['total_collections'] == 0
        
        # Add some data
        cache_instance.cache_collection(Path("/fake/collection"), sample_scan_results)
        
        # Stats should update
        new_stats = cache_instance.get_cache_stats()
        assert new_stats['total_collections'] == 1
        assert new_stats['cache_file_size'] > 0
    
    @pytest.mark.unit
    def test_directory_signature_generation(self, cache_instance, temp_cache_dir):
        """Test directory signature generation."""
        # Create a test directory with some files
        test_dir = temp_cache_dir / "test_collection"
        test_dir.mkdir()
        
        # Create some video files
        (test_dir / "video1.mp4").write_text("fake video content 1")
        (test_dir / "video2.mkv").write_text("fake video content 2")
        (test_dir / "not_video.txt").write_text("not a video")
        
        # Get signature
        signature1 = cache_instance._get_directory_signature(test_dir)
        assert isinstance(signature1, str)
        assert len(signature1) > 0
        
        # Same directory should give same signature
        signature2 = cache_instance._get_directory_signature(test_dir)
        assert signature1 == signature2
        
        # Add a file, signature should change
        (test_dir / "video3.avi").write_text("another video")
        signature3 = cache_instance._get_directory_signature(test_dir)
        assert signature3 != signature1
    
    @pytest.mark.unit
    def test_update_tour_cache(self, cache_instance):
        """Test updating cache for a specific tour."""
        collection_path = Path("/fake/collection")
        tour_data = {
            'path': '/fake/path/2024 Tour',
            'shows': {
                '2024-01-15 - Austin': {
                    'date': '2024-01-15',
                    'location': 'Austin'
                }
            }
        }
        
        # Update tour cache
        cache_instance.update_tour_cache(collection_path, "2024 Tour", tour_data)
        
        # Should be retrievable
        result = cache_instance.get_cached_collection(collection_path)
        assert result is not None
        assert "2024 Tour" in result['tours']
        assert result['total_tours'] == 1
        assert result['total_shows'] == 1


class TestCollectionManagerCaching:
    """Test collection manager caching integration."""
    
    @pytest.fixture
    def temp_collection_dir(self):
        """Create temporary collection directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    def collection_manager_with_cache(self, temp_collection_dir):
        """Create collection manager with caching."""
        return CollectionManager(str(temp_collection_dir))
    
    @pytest.mark.unit
    def test_cache_integration_basic(self, collection_manager_with_cache):
        """Test that collection manager integrates with caching."""
        # Just test that it doesn't crash
        result = collection_manager_with_cache.scan_collection()
        
        # Should return a dict with expected structure
        assert isinstance(result, dict)
        assert 'tours' in result
        assert 'total_tours' in result
        assert 'total_shows' in result


class TestCacheErrorHandling:
    """Test cache error handling and edge cases."""
    
    @pytest.mark.unit
    def test_cache_with_invalid_directory(self):
        """Test cache behavior with invalid cache directory."""
        # Try to create cache with a file as the directory path
        with tempfile.NamedTemporaryFile() as temp_file:
            # This should handle the error gracefully
            try:
                cache = CollectionCache(Path(temp_file.name))
                # If it succeeds, it should at least have empty cache
                assert hasattr(cache, 'cache_data')
            except (OSError, PermissionError):
                # It's acceptable to raise an error for invalid paths
                pass
    
    @pytest.mark.unit
    def test_empty_directory_signature(self):
        """Test signature generation for empty directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_cache_dir = Path(temp_dir)
            cache = CollectionCache(temp_cache_dir)
            
            # Create empty directory
            empty_dir = temp_cache_dir / "empty"
            empty_dir.mkdir()
            
            # Should generate a signature (even if empty)
            signature = cache._get_directory_signature(empty_dir)
            assert isinstance(signature, str)
            # Empty directory should have consistent signature
            signature2 = cache._get_directory_signature(empty_dir)
            assert signature == signature2
    
    @pytest.mark.unit
    def test_nonexistent_directory_signature(self):
        """Test signature generation for nonexistent directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_cache_dir = Path(temp_dir)
            cache = CollectionCache(temp_cache_dir)
            
            # Should handle nonexistent directory gracefully
            nonexistent = temp_cache_dir / "does_not_exist"
            signature = cache._get_directory_signature(nonexistent)
            
            # Should return empty string or handle gracefully
            assert isinstance(signature, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])