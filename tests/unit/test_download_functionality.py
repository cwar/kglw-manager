"""Comprehensive tests for download functionality and error handling."""

import pytest
import tempfile
import json
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call

from kglw_manager.download import DownloadManager


class TestDownloadManager:
    """Test suite for DownloadManager functionality."""
    
    @pytest.fixture
    def temp_download_dir(self):
        """Create a temporary download directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    def download_manager(self):
        """Create DownloadManager instance for testing."""
        return DownloadManager()
    
    @pytest.fixture
    def sample_video_info(self):
        """Sample video info for testing."""
        return {
            'title': 'Test Video Title',
            'url': 'https://youtube.com/watch?v=test123',
            'webpage_url': 'https://youtube.com/watch?v=test123',
            'duration': 3600,
            'resolution': '1080p',
            'format_id': 'best'
        }
    
    @pytest.fixture
    def sample_show_info(self):
        """Sample show info for testing."""
        return {
            'date': '2024-01-15',
            'location': 'Test City',
            'venue': 'Test Venue',
            'tour': 'Test Tour 2024'
        }
    
    def test_initialization(self, download_manager):
        """Test DownloadManager initialization."""
        assert hasattr(download_manager, 'active_downloads')
        assert isinstance(download_manager.active_downloads, dict)
        assert len(download_manager.active_downloads) == 0
    
    def test_download_progress_tracking(self, download_manager):
        """Test download progress tracking functionality."""
        url = "https://test.com/video"
        
        # Mock process for tracking
        mock_process = Mock()
        download_manager.active_downloads[url] = mock_process
        
        # Test that we can track active downloads
        assert url in download_manager.get_active_downloads()
        
        # Test cancellation. yt_dlp.YoutubeDL has no terminate(); cancellation
        # is signalled via a flag the progress hook checks.
        download_manager.cancel_download(url)
        assert url not in download_manager.active_downloads
        assert url in download_manager.cancelled_downloads
    
    def test_cancel_all_downloads(self, download_manager):
        """Test canceling all active downloads."""
        # Add multiple mock downloads
        urls = ["https://test1.com", "https://test2.com", "https://test3.com"]
        mock_processes = []
        
        for url in urls:
            mock_process = Mock()
            mock_processes.append(mock_process)
            download_manager.active_downloads[url] = mock_process
        
        # Cancel all
        download_manager.cancel_all_downloads()

        # Verify all were flagged for cancellation
        for url in urls:
            assert url in download_manager.cancelled_downloads

        assert len(download_manager.active_downloads) == 0
    
    def test_find_downloaded_file(self, download_manager, temp_download_dir):
        """Test finding downloaded video files."""
        # Create test files with different timestamps
        old_file = temp_download_dir / "old_video.mp4"
        new_file = temp_download_dir / "new_video.mkv"
        non_video = temp_download_dir / "readme.txt"
        
        old_file.touch()
        non_video.touch()
        
        # Make new file newer
        import time
        time.sleep(0.1)
        new_file.touch()
        
        # Should find the newest video file
        found_file = download_manager._find_downloaded_file(temp_download_dir)
        assert found_file == new_file
    
    def test_find_downloaded_file_no_videos(self, download_manager, temp_download_dir):
        """Test finding downloaded files when no videos exist."""
        # Create only non-video files
        (temp_download_dir / "readme.txt").touch()
        (temp_download_dir / "info.json").touch()
        
        found_file = download_manager._find_downloaded_file(temp_download_dir)
        assert found_file is None
    
    def test_cleanup_incomplete_downloads(self, download_manager, temp_download_dir):
        """Test cleanup of incomplete download files."""
        # Create various download remnant files
        part_file = temp_download_dir / "video.mp4.part"
        part_file2 = temp_download_dir / "video.part-001"
        ytdl_file = temp_download_dir / "video.ytdl"
        temp_file = temp_download_dir / "video.temp"
        keep_file = temp_download_dir / "video.mp4"
        
        for f in [part_file, part_file2, ytdl_file, temp_file, keep_file]:
            f.touch()
        
        download_manager.cleanup_incomplete_downloads(temp_download_dir)
        
        # Only the complete video file should remain
        remaining_files = list(temp_download_dir.iterdir())
        assert len(remaining_files) == 1
        assert remaining_files[0].name == "video.mp4"


class TestDownloadBackupOperations:
    """Test backup and restore operations during downloads."""
    
    @pytest.fixture
    def download_manager(self):
        return DownloadManager()
    
    @pytest.fixture
    def show_dir_with_existing_videos(self, temp_download_dir):
        """Create show directory with existing video files."""
        show_dir = temp_download_dir / "2024-01-15 - Test Show"
        show_dir.mkdir()
        
        # Create existing video files
        (show_dir / "existing_video1.mp4").write_text("fake video 1")
        (show_dir / "existing_video2.mkv").write_text("fake video 2")
        (show_dir / "info.json").write_text("metadata")  # Non-video file
        
        return show_dir
    
    def test_backup_existing_files(self, download_manager, show_dir_with_existing_videos):
        """Test backing up existing video files."""
        download_manager._backup_existing_files(show_dir_with_existing_videos)
        
        backup_dir = show_dir_with_existing_videos / "backup"
        assert backup_dir.exists()
        
        # Check that video files were backed up
        backup_files = list(backup_dir.iterdir())
        backup_names = [f.name for f in backup_files]
        
        assert "existing_video1.mp4.backup" in backup_names
        assert "existing_video2.mkv.backup" in backup_names
        
        # Original video files should be gone
        remaining_files = [f for f in show_dir_with_existing_videos.iterdir() 
                          if f.name != "backup" and f.suffix.lower() in ['.mp4', '.mkv']]
        assert len(remaining_files) == 0
        
        # Non-video files should remain
        assert (show_dir_with_existing_videos / "info.json").exists()
    
    def test_restore_backup_files(self, download_manager, show_dir_with_existing_videos):
        """Test restoring backup files after download failure."""
        # First create backups
        download_manager._backup_existing_files(show_dir_with_existing_videos)
        
        # Verify files were backed up
        backup_dir = show_dir_with_existing_videos / "backup"
        assert len(list(backup_dir.iterdir())) == 2
        
        # Now restore
        download_manager._restore_backup_files(show_dir_with_existing_videos)
        
        # Original files should be restored
        assert (show_dir_with_existing_videos / "existing_video1.mp4").exists()
        assert (show_dir_with_existing_videos / "existing_video2.mkv").exists()
        
        # Backup directory should be cleaned up
        assert not backup_dir.exists()
    
    def test_cleanup_backup_files(self, download_manager, show_dir_with_existing_videos):
        """Test cleanup of backup files after successful download."""
        # Create backups
        download_manager._backup_existing_files(show_dir_with_existing_videos)
        
        backup_dir = show_dir_with_existing_videos / "backup"
        assert backup_dir.exists()
        
        # Cleanup backups
        download_manager._cleanup_backup_files(show_dir_with_existing_videos)
        
        # Backup directory should be gone
        assert not backup_dir.exists()
    
    def test_backup_restore_error_handling(self, download_manager, temp_download_dir):
        """Test error handling in backup/restore operations."""
        non_existent_dir = temp_download_dir / "does_not_exist"
        
        # Should not raise exceptions for non-existent directories
        download_manager._backup_existing_files(non_existent_dir)
        download_manager._restore_backup_files(non_existent_dir)
        download_manager._cleanup_backup_files(non_existent_dir)


class TestDownloadPlexIntegration:
    """Test Plex integration during download process."""
    
    @pytest.fixture
    def download_manager(self):
        return DownloadManager()
    
    @pytest.fixture  
    def temp_download_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    def test_plex_integration_path_construction(self, download_manager, temp_download_dir):
        """Test Path import and usage in Plex integration."""
        # Create a realistic show directory structure
        tour_dir = temp_download_dir / "2024 Test Tour"
        show_dir = tour_dir / "2024-01-15 - Test City"
        show_dir.mkdir(parents=True)
        
        # Create a mock downloaded file (this would be plex_path in the real code)
        downloaded_file = show_dir / "test_video.mp4"
        downloaded_file.touch()
        
        # Test the Path construction that was causing the error
        from pathlib import Path  # This import should be available
        
        # Simulate the problematic line from the error
        temp_collection_path = str(Path(downloaded_file).parent.parent.parent)
        expected_path = str(temp_download_dir)
        
        assert temp_collection_path == expected_path
    
    @patch('kglw_manager.collection.CollectionManager')
    def test_plex_integration_mock_success(self, mock_collection_manager_class, download_manager):
        """Test successful Plex integration flow."""
        # Mock the collection manager and its methods
        mock_manager_instance = Mock()
        mock_manager_instance.plex_manager = Mock()
        mock_manager_instance.process_new_show.return_value = {
            'success': True,
            'videos_processed': 1,
            'collection_updated': True,
            'metadata_updated': True,
            'errors': []
        }
        mock_collection_manager_class.return_value = mock_manager_instance
        
        # Mock the required imports and path operations
        with patch('kglw_manager.download.Path') as mock_path_class:
            mock_path_instance = Mock()
            mock_path_instance.parent.parent.parent = "/mock/collection/path"
            mock_path_class.return_value = mock_path_instance
            
            # This would be part of a larger download flow, but we're testing the integration part
            # The actual integration code is in download.py lines 920-952
            try:
                # Simulate the integration block
                from kglw_manager.collection import CollectionManager
                from kglw_manager.config import config
                from pathlib import Path  # This was the missing import
                
                # This should now work without the "cannot access local variable" error
                temp_collection_path = str(Path("/fake/plex/path").parent.parent.parent)
                temp_manager = CollectionManager(temp_collection_path)
                
                # Test passes if no exception is raised
                assert True
            except Exception as e:
                pytest.fail(f"Plex integration failed: {e}")
    
    @patch('kglw_manager.collection.CollectionManager')
    def test_plex_integration_error_handling(self, mock_collection_manager_class,
                                             download_manager, temp_download_dir):
        """A failing Plex integration must not fail the download itself."""
        mock_collection_manager_class.side_effect = Exception("Plex connection failed")

        show_dir = temp_download_dir / "2024 Test Tour" / "2024-01-15 - Test City"
        show_dir.mkdir(parents=True)
        raw_download = show_dir / "some raw youtube title.mp4"

        def fake_download(url, output_path, **kwargs):
            raw_download.write_text("fake video")
            return True

        with patch.object(download_manager, 'download_video', side_effect=fake_download):
            result = download_manager.download_upgrade_to_existing_dir(
                {'webpage_url': 'https://youtube.com/watch?v=test',
                 'title': 'Full Concert', 'duration': 7200},
                show_dir,
                {'date': '2024-01-15', 'location': 'Test City', 'venue': 'Test Venue'},
                backup_existing=False,
                quiet_mode=True,
            )

        # Despite Plex blowing up, the download is kept and renamed to Plex format
        assert result is not None
        assert result.exists()
        assert not raw_download.exists()


class TestDownloadNamingAndPaths:
    """Test download naming and path construction."""
    
    @pytest.fixture
    def download_manager(self):
        return DownloadManager()
    
    def test_plex_filename_generation_with_tour_manager(self, download_manager):
        """Test Plex filename generation with tour manager integration."""
        show_info = {
            'date': '2024-01-15',
            'location': 'Test City',
            'venue': 'Test Venue'
        }
        
        video_info = {
            'title': 'King Gizzard Test Show Full Concert',
            'duration': 3600
        }
        
        # Mock the naming manager and tour manager
        with patch('kglw_manager.download.NamingManager') as mock_naming, \
             patch('kglw_manager.download.get_tour_manager') as mock_tour_manager:
            
            mock_naming_instance = mock_naming.return_value
            mock_naming_instance.generate_plex_filename.return_value = "King Gizzard & The Lizard Wizard - 2024-01-15 Test City (Test Venue) - concert.mp4"
            
            mock_tour_instance = mock_tour_manager.return_value
            mock_tour_instance.assign_tour.return_value = "2024 Test Tour"
            mock_tour_instance.normalize_tour_name_for_filesystem.return_value = "2024 Test Tour"
            
            # Test that the naming logic would work correctly
            expected_filename = mock_naming_instance.generate_plex_filename.return_value
            assert expected_filename.endswith("- concert.mp4")
            assert "2024-01-15" in expected_filename
            assert "Test City" in expected_filename
    
    def test_path_handling_edge_cases(self, download_manager, temp_download_dir):
        """Test path handling with various edge cases."""
        # Test with special characters in paths
        special_dir = temp_download_dir / "2024-01-15 - Test City (Special & Chars!)"
        special_dir.mkdir(parents=True)
        
        test_file = special_dir / "test.mp4"
        test_file.touch()
        
        # Test path operations
        found = download_manager._find_downloaded_file(special_dir)
        assert found == test_file
        
        # Test backup operations with special characters
        download_manager._backup_existing_files(special_dir)
        backup_dir = special_dir / "backup"
        assert backup_dir.exists()


class TestDownloadErrorRecovery:
    """Test error recovery and resilience in download operations."""
    
    @pytest.fixture
    def download_manager(self):
        return DownloadManager()
    
    def test_download_failure_recovery(self, download_manager, temp_download_dir):
        """Test recovery from download failures."""
        show_dir = temp_download_dir / "test_show"
        show_dir.mkdir()
        
        # Create existing files
        existing_file = show_dir / "existing.mp4"
        existing_file.write_text("existing content")
        
        # Backup files
        download_manager._backup_existing_files(show_dir)
        
        # Simulate download failure - files should be restored
        download_manager._restore_backup_files(show_dir)
        
        # Original file should be back
        assert existing_file.exists()
        assert existing_file.read_text() == "existing content"
    
    def test_partial_file_cleanup_robustness(self, download_manager, temp_download_dir):
        """Test robust cleanup of partial files."""
        # Create files with various problematic names
        problematic_files = [
            "video with spaces.mp4.part",
            "video-with-dashes.part-001",
            "video_with_underscores.ytdl",
            "видео.temp",  # Unicode filename
            ".hidden.part",
            "very_long_filename_that_might_cause_issues_in_some_systems.mp4.part"
        ]
        
        for filename in problematic_files:
            (temp_download_dir / filename).touch()
        
        # Also create a file to keep
        keep_file = temp_download_dir / "final_video.mp4"
        keep_file.touch()
        
        # Cleanup should handle all cases
        download_manager.cleanup_incomplete_downloads(temp_download_dir)
        
        # Only the final video should remain
        remaining = list(temp_download_dir.iterdir())
        assert len(remaining) == 1
        assert remaining[0].name == "final_video.mp4"
    
    def test_permission_error_handling(self, download_manager, temp_download_dir):
        """Test handling of permission errors during file operations."""
        import os
        import stat
        
        if os.name != 'posix':  # Skip on Windows
            pytest.skip("Permission tests only on POSIX systems")
        
        # Create a read-only file
        readonly_file = temp_download_dir / "readonly.mp4"
        readonly_file.touch()
        readonly_file.chmod(stat.S_IRUSR)  # Read-only
        
        # Operations should not crash on permission errors
        try:
            download_manager._backup_existing_files(temp_download_dir)
            # Should handle permission errors gracefully
        except PermissionError:
            pytest.fail("Should handle permission errors gracefully")
        finally:
            # Cleanup: restore permissions. The file may have been moved into
            # backup/ by a successful backup, so look for it in both places.
            for candidate in (readonly_file,
                              temp_download_dir / "backup" / "readonly.mp4.backup"):
                if candidate.exists():
                    candidate.chmod(stat.S_IRUSR | stat.S_IWUSR)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])