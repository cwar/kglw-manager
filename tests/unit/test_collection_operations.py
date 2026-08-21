"""Comprehensive tests for collection operations and data structures."""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from kglw_manager.collection import CollectionManager
from kglw_manager.diskcache_collection import DiskcacheCollectionCache as CollectionCache


class TestCollectionManager:
    """Test suite for CollectionManager functionality."""
    
    @pytest.fixture
    def temp_collection_dir(self):
        """Create temporary collection directory with realistic structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)
            
            # Create realistic tour structure
            tour1_dir = base_path / "2024 Europe Tour"
            tour1_dir.mkdir(parents=True)
            
            tour2_dir = base_path / "2023 USA Tour"
            tour2_dir.mkdir(parents=True)
            
            # Create show directories with videos
            show1_dir = tour1_dir / "2024-03-15 - London, UK (O2 Arena)"
            show1_dir.mkdir()
            (show1_dir / "concert.mp4").write_text("fake video content")
            (show1_dir / "poster.jpg").write_text("fake poster")
            
            show2_dir = tour1_dir / "2024-03-16 - Paris, France (AccorHotels Arena)"
            show2_dir.mkdir()
            (show2_dir / "concert.mkv").write_text("fake video content")
            
            show3_dir = tour2_dir / "2023-10-20 - New York, NY (Madison Square Garden)"
            show3_dir.mkdir()
            (show3_dir / "concert.mp4").write_text("fake video content")
            (show3_dir / "concert_pt2.mp4").write_text("fake video content pt2")
            
            yield base_path
    
    @pytest.fixture
    def collection_manager(self, temp_collection_dir):
        """Create CollectionManager instance."""
        return CollectionManager(temp_collection_dir)
    
    def test_initialization(self, collection_manager, temp_collection_dir):
        """Test CollectionManager initialization."""
        assert collection_manager.collection_path == temp_collection_dir
        assert hasattr(collection_manager, 'collection_cache')
        assert hasattr(collection_manager, 'video_cache')
        assert hasattr(collection_manager, 'upgrade_tracker')
    
    def test_scan_collection_structure(self, collection_manager):
        """Test collection scanning returns proper structure."""
        collection = collection_manager.scan_collection()
        
        # Verify top-level structure
        assert 'tours' in collection
        assert 'total_tours' in collection
        assert 'total_shows' in collection
        assert 'total_videos' in collection
        
        # Verify tour structure
        tours = collection['tours']
        assert len(tours) >= 2
        
        for tour_name, tour_data in tours.items():
            assert 'shows' in tour_data
            assert isinstance(tour_data['shows'], dict)
            
            # Verify show structure
            for show_dir_name, show_info in tour_data['shows'].items():
                assert isinstance(show_dir_name, str)  # Directory name
                assert isinstance(show_info, dict)     # Show data
                assert 'date' in show_info
                assert 'location' in show_info
                assert 'files' in show_info
    
    def test_show_date_parsing(self, collection_manager):
        """Test that show dates are parsed correctly from directory names."""
        collection = collection_manager.scan_collection()
        
        found_dates = []
        for tour_data in collection['tours'].values():
            for show_info in tour_data['shows'].values():
                if show_info.get('date'):
                    found_dates.append(show_info['date'])
        
        # Should find dates in YYYY-MM-DD format
        expected_dates = ['2024-03-15', '2024-03-16', '2023-10-20']
        for expected_date in expected_dates:
            assert expected_date in found_dates
    
    def test_video_file_detection(self, collection_manager):
        """Test that video files are detected correctly."""
        collection = collection_manager.scan_collection()
        
        total_files = 0
        for tour_data in collection['tours'].values():
            for show_info in tour_data['shows'].values():
                files = show_info.get('files', [])
                total_files += len(files)
                
                # Check that files have required metadata
                # (the codebase-wide contract is the 'name' key, see
                # _analyze_video_file in collection.py)
                for file_info in files:
                    assert 'name' in file_info
                    assert file_info['name'].endswith(('.mp4', '.mkv', '.avi', '.webm', '.mov'))
        
        assert total_files >= 4  # Should find at least 4 video files
    
    def test_collection_caching(self, collection_manager):
        """Test collection caching functionality."""
        # First scan should populate cache
        collection1 = collection_manager.scan_collection()
        
        # Second scan should use cache (no changes)
        collection2 = collection_manager.scan_collection()
        
        assert collection1 == collection2
        
        # Force rescan should bypass cache
        collection3 = collection_manager.scan_collection(force_rescan=True)
        assert collection3 == collection1  # Same data, but freshly scanned


class TestCollectionDataStructures:
    """Test proper handling of collection data structures."""
    
    @pytest.fixture
    def sample_collection_data(self):
        """Sample collection data for testing."""
        return {
            'tours': {
                'Test Tour 2024': {
                    'shows': {
                        '2024-01-15 - Test City (Test Venue)': {
                            'date': '2024-01-15',
                            'location': 'Test City',
                            'venue': 'Test Venue',
                            'files': [
                                {'filename': 'concert.mp4', 'size': 1000000}
                            ]
                        },
                        '2024-01-16 - Another City (Another Venue)': {
                            'date': '2024-01-16',
                            'location': 'Another City',
                            'venue': 'Another Venue',
                            'files': [
                                {'filename': 'concert.mkv', 'size': 2000000}
                            ]
                        }
                    }
                }
            },
            'total_tours': 1,
            'total_shows': 2,
            'total_videos': 2
        }
    
    def test_data_structure_iteration(self, sample_collection_data):
        """Test proper iteration over collection data structures."""
        # This tests the correct pattern that was causing the 'str' has no attribute 'date' error
        
        for tour_name, tour_data in sample_collection_data['tours'].items():
            assert isinstance(tour_name, str)
            assert 'shows' in tour_data
            
            for show_dir_name, show_info in tour_data['shows'].items():
                # show_dir_name is the directory name (string key)
                # show_info is the show data (dict value)
                assert isinstance(show_dir_name, str)
                assert isinstance(show_info, dict)
                
                # Correct way to access date
                show_date = show_info.get('date')
                assert show_date is not None
                
                # This would be WRONG and cause the error:
                # show_date = show.date  # 'str' object has no attribute 'date'
    
    def test_path_construction_from_data(self, sample_collection_data, temp_collection_dir):
        """Test path construction from collection data."""
        collection_path = Path("/test/collection")
        
        for tour_name, tour_data in sample_collection_data['tours'].items():
            for show_dir_name, show_info in tour_data['shows'].items():
                # Correct path construction
                tour_path = collection_path / tour_name
                show_path = tour_path / show_dir_name
                
                expected_path = Path("/test/collection/Test Tour 2024/2024-01-15 - Test City (Test Venue)")
                if show_info.get('date') == '2024-01-15':
                    assert show_path == expected_path


class TestCollectionUpgradeOperations:
    """Test upgrade candidate detection and processing."""
    
    @pytest.fixture
    def collection_with_upgrade_candidates(self, temp_collection_dir):
        """Create collection with shows that need upgrades."""
        # Create shows with different quality levels
        tour_dir = temp_collection_dir / "2024 Test Tour"
        tour_dir.mkdir()
        
        # Low quality show (upgrade candidate)
        low_quality_show = tour_dir / "2024-01-15 - Low Quality Show"
        low_quality_show.mkdir()
        low_q_video = low_quality_show / "concert.mp4"
        low_q_video.write_text("small video content")  # Simulates small/low quality file
        
        # High quality show (no upgrade needed)
        high_quality_show = tour_dir / "2024-01-16 - High Quality Show"
        high_quality_show.mkdir()
        high_q_video = high_quality_show / "concert.mp4"
        high_q_video.write_text("large video content " * 1000)  # Simulates larger/better quality file
        
        return CollectionManager(temp_collection_dir)
    
    def test_upgrade_candidate_detection(self, collection_with_upgrade_candidates):
        """Test detection of upgrade candidates."""
        # Mock the upgrade analysis to simulate realistic conditions.
        # find_upgrade_candidates() consults _analyze_upgrade_need (not the
        # legacy _needs_upgrade helper), so that is what must be mocked.
        with patch.object(collection_with_upgrade_candidates, '_analyze_upgrade_need') as mock_analyze:
            # First show needs upgrade, second doesn't
            mock_analyze.side_effect = [
                {'needs_upgrade': True,
                 'reasons': ['Low resolution (480p < 720p)'],
                 'current_quality': '480p'},
                {'needs_upgrade': False, 'reasons': [], 'current_quality': '1080p'},
            ]

            candidates = collection_with_upgrade_candidates.find_upgrade_candidates()

            # Should find exactly the one upgrade candidate
            assert len(candidates) == 1
            assert all('tour' in candidate for candidate in candidates)
            assert all('show' in candidate for candidate in candidates)
            assert candidates[0]['upgrade_reasons'] == ['Low resolution (480p < 720p)']
    
    def test_upgrade_tracking(self, collection_with_upgrade_candidates):
        """Test upgrade attempt tracking."""
        show_date = '2024-01-15'
        
        # Record failed attempt
        collection_with_upgrade_candidates.record_upgrade_attempt(show_date, success=False, error="Test error")
        
        # Record successful attempt
        collection_with_upgrade_candidates.record_upgrade_attempt(show_date, success=True)
        
        # Get tracking stats
        stats = collection_with_upgrade_candidates.get_upgrade_tracking_stats()
        
        assert 'failed_shows' in stats
        assert 'successful_shows' in stats
        assert stats['successful_shows'] >= 1


class TestCollectionCache:
    """Test collection caching functionality."""
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create temporary cache directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    def collection_cache(self, temp_cache_dir):
        """Create CollectionCache instance."""
        return CollectionCache(temp_cache_dir)
    
    def test_cache_initialization(self, collection_cache, temp_cache_dir):
        """Test cache initialization."""
        assert collection_cache.cache_dir == temp_cache_dir
        assert collection_cache.cache_dir.exists()
    
    def test_cache_tour_operations(self, collection_cache, temp_collection_dir):
        """Test caching individual tour data."""
        tour_data = {
            'shows': {
                'test_show': {
                    'date': '2024-01-15',
                    'location': 'Test City'
                }
            }
        }
        
        # Cache tour data
        collection_cache.update_tour_cache(temp_collection_dir, "Test Tour", tour_data)
        
        # Retrieve cached data
        cached_data = collection_cache.get_cached_collection(temp_collection_dir)
        
        assert cached_data is not None
        assert 'tours' in cached_data
        assert 'Test Tour' in cached_data['tours']
        assert cached_data['tours']['Test Tour'] == tour_data
    
    def test_cache_invalidation(self, collection_cache, temp_collection_dir):
        """Test cache invalidation when directories change."""
        # Create initial directory structure
        tour_dir = temp_collection_dir / "Test Tour"
        tour_dir.mkdir()
        
        # Get initial changed tours (all should be changed on first scan)
        changed_tours = collection_cache.get_changed_tours(temp_collection_dir)
        assert "Test Tour" in changed_tours
        
        # Update cache
        collection_cache.update_tour_cache(temp_collection_dir, "Test Tour", {'shows': {}})
        
        # Get changed tours again (should be empty now)
        changed_tours = collection_cache.get_changed_tours(temp_collection_dir)
        assert len(changed_tours) == 0
        
        # Modify directory (simulate file change)
        (tour_dir / "new_file.txt").touch()
        
        # Should detect change again
        changed_tours = collection_cache.get_changed_tours(temp_collection_dir)
        assert "Test Tour" in changed_tours


class TestCollectionErrorHandling:
    """Test error handling in collection operations."""
    
    def test_missing_directory_handling(self):
        """Test handling of missing collection directory."""
        non_existent_path = Path("/non/existent/path")
        manager = CollectionManager(non_existent_path)
        
        # Should handle missing directory gracefully
        collection = manager.scan_collection()
        
        assert collection['tours'] == {}
        assert collection['total_tours'] == 0
        assert collection['total_shows'] == 0
        assert collection['total_videos'] == 0
    
    def test_corrupted_file_handling(self, temp_collection_dir):
        """Test handling of corrupted or problematic files."""
        manager = CollectionManager(temp_collection_dir)
        
        # Create directory with problematic files
        tour_dir = temp_collection_dir / "Problematic Tour"
        tour_dir.mkdir()
        
        show_dir = tour_dir / "2024-01-15 - Test Show"
        show_dir.mkdir()
        
        # Create files that might cause issues
        (show_dir / "corrupted.mp4").write_bytes(b"not a real video file")
        (show_dir / "file with spaces.mkv").write_text("fake video")
        (show_dir / "файл.mp4").write_text("unicode filename")  # Unicode filename
        (show_dir / ".hidden_file.mp4").write_text("hidden file")
        
        # Should scan without crashing
        collection = manager.scan_collection()
        
        # Should find the tour and show
        assert "Problematic Tour" in collection['tours']
        assert len(collection['tours']["Problematic Tour"]['shows']) >= 1
    
    def test_permission_error_handling(self, temp_collection_dir):
        """Test handling of permission errors."""
        import os
        import stat
        
        if os.name != 'posix':  # Skip on Windows
            pytest.skip("Permission tests only on POSIX systems")
        
        manager = CollectionManager(temp_collection_dir)
        
        # Create directory with restrictive permissions
        restricted_dir = temp_collection_dir / "Restricted Tour"
        restricted_dir.mkdir()
        restricted_dir.chmod(stat.S_IREAD)  # Read-only
        
        try:
            # Should handle permission errors gracefully
            collection = manager.scan_collection()
            # Test passes if no exception is raised
        except PermissionError:
            pytest.fail("Should handle permission errors gracefully")
        finally:
            # Cleanup: restore permissions
            restricted_dir.chmod(stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)


class TestCollectionIntegration:
    """Test integration with other components."""
    
    def test_tour_manager_integration(self, collection_manager):
        """Test integration with tour management."""
        # Mock tour manager (collection.py imports TourManager lazily from
        # kglw_manager.tours, so patch it at its source module)
        with patch('kglw_manager.tours.TourManager') as mock_tour_manager_class:
            mock_tour_manager = mock_tour_manager_class.return_value
            mock_tour_manager.assign_tour.return_value = "Assigned Tour Name"
            
            collection = collection_manager.scan_collection()
            
            # Tour assignments should be made during scanning
            for tour_data in collection['tours'].values():
                for show_info in tour_data['shows'].values():
                    # Shows should have tour information
                    assert isinstance(show_info, dict)
    
    def test_plex_manager_integration(self, collection_manager):
        """Test optional Plex integration."""
        # Test with Plex available
        with patch('kglw_manager.collection.PlexManager') as mock_plex_class:
            mock_plex = mock_plex_class.return_value
            collection_manager.plex_manager = mock_plex
            
            assert collection_manager.plex_manager is not None
        
        # Test with Plex unavailable
        collection_manager.plex_manager = None
        assert collection_manager.plex_manager is None
    
    def test_discord_integration(self, collection_manager):
        """Test Discord notification integration."""
        with patch('kglw_manager.collection.DiscordNotifier') as mock_discord_class:
            mock_notifier = mock_discord_class.return_value
            collection_manager.discord_notifier = mock_notifier
            
            # Should be able to send notifications
            assert hasattr(collection_manager, 'discord_notifier')


class TestCollectionPerformance:
    """Test collection performance and optimization."""
    
    def test_large_collection_handling(self, temp_collection_dir):
        """Test handling of large collections."""
        # Create a larger collection structure
        for tour_num in range(5):
            tour_dir = temp_collection_dir / f"Tour {2020 + tour_num}"
            tour_dir.mkdir()
            
            for show_num in range(20):  # 20 shows per tour
                show_dir = tour_dir / f"2024-{tour_num+1:02d}-{show_num+1:02d} - City {show_num}"
                show_dir.mkdir()
                
                # Create multiple video files per show
                for video_num in range(2):
                    (show_dir / f"concert_part{video_num+1}.mp4").write_text("video content")
        
        manager = CollectionManager(temp_collection_dir)
        
        # Should handle large collection without issues
        import time
        start_time = time.time()
        collection = manager.scan_collection()
        scan_time = time.time() - start_time
        
        # Basic performance check
        assert collection['total_tours'] == 5
        assert collection['total_shows'] == 100  # 5 tours * 20 shows
        assert collection['total_videos'] == 200  # 100 shows * 2 videos
        
        # Should complete in reasonable time (adjust as needed)
        assert scan_time < 10.0  # Should scan in under 10 seconds
    
    def test_caching_performance_benefit(self, temp_collection_dir):
        """Test that caching provides performance benefits."""
        # Create moderate-sized collection
        for i in range(3):
            tour_dir = temp_collection_dir / f"Test Tour {i}"
            tour_dir.mkdir()
            for j in range(10):
                show_dir = tour_dir / f"2024-0{i+1}-{j+1:02d} - Test Show {j}"
                show_dir.mkdir()
                (show_dir / "concert.mp4").write_text("content")
        
        manager = CollectionManager(temp_collection_dir)
        
        # First scan (no cache)
        import time
        start_time = time.time()
        collection1 = manager.scan_collection()
        first_scan_time = time.time() - start_time
        
        # Second scan (with cache)
        start_time = time.time()
        collection2 = manager.scan_collection()
        cached_scan_time = time.time() - start_time
        
        # Cached scan should be faster
        assert cached_scan_time < first_scan_time
        assert collection1 == collection2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])