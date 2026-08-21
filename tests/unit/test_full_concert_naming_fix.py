"""Test full concert vs individual song naming logic."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile
import shutil
from kglw_manager.download import DownloadManager


class TestFullConcertNamingFix:
    """Test that full concerts don't get song name suffixes."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def download_manager(self):
        """Create DownloadManager for testing."""
        return DownloadManager()
    
    def test_full_concert_replaces_existing_file(self, download_manager, temp_dir):
        """Test that full concerts replace existing files without song suffixes."""
        show_dir = temp_dir / "test_show"
        show_dir.mkdir()
        
        # Create existing concert file (current naming deliberately omits the
        # artist name - it makes Plex group different shows together)
        existing_file = show_dir / "2024-05-18 - Prague (Forum Karlin) - concert.mp4"
        existing_file.write_text("existing content")

        # Mock downloaded file
        downloaded_file = show_dir / "downloaded.mp4"
        downloaded_file.write_text("new content")

        # Mock video info for full concert
        video_info = {
            'title': 'King Gizzard and the Lizard Wizard, Prague, 2024 May 18, Full Concert',
            'duration': 5400,  # 90 minutes
            'webpage_url': 'https://example.com/video'
        }

        show_info = {
            'date': '2024-05-18',
            'location': 'Prague',
            'venue': 'Forum Karlin'
        }

        with patch.object(download_manager, 'download_video', return_value=True):
            with patch.object(download_manager, '_find_downloaded_file', return_value=downloaded_file):
                with patch.object(download_manager, '_backup_existing_files'):
                    result = download_manager.download_upgrade_to_existing_dir(
                        video_info=video_info,
                        show_dir=show_dir,
                        show_info=show_info,
                        backup_existing=False  # This triggers the logic
                    )

        # Should replace the existing concert file, without a song suffix
        assert result.name == "2024-05-18 - Prague (Forum Karlin) - concert.mp4"
        # Should not have any song names or numbering
        assert "Space Cadet" not in result.name
        assert "Song" not in result.name
    
    def test_individual_song_gets_unique_filename(self, download_manager, temp_dir):
        """Test that individual songs get unique filenames when concert file exists."""
        show_dir = temp_dir / "test_show"
        show_dir.mkdir()
        
        # Create existing concert file in the current (artist-less) naming
        existing_file = show_dir / "2024-05-18 - Prague (Forum Karlin) - concert.mp4"
        existing_file.write_text("existing content")

        # Mock downloaded file
        downloaded_file = show_dir / "downloaded.mp4"
        downloaded_file.write_text("new content")

        # Mock video info for individual song (short title, short duration)
        video_info = {
            'title': 'Space Cadet',  # Individual song title
            'duration': 240,  # 4 minutes
            'webpage_url': 'https://example.com/song'
        }

        show_info = {
            'date': '2024-05-18',
            'location': 'Prague',
            'venue': 'Forum Karlin'
        }

        with patch.object(download_manager, 'download_video', return_value=True):
            with patch.object(download_manager, '_find_downloaded_file', return_value=downloaded_file):
                with patch.object(download_manager, '_backup_existing_files'):
                    # Mock song identification to return Space Cadet
                    with patch('kglw_manager.kglw_api.KGLWApi') as mock_api_class:
                        mock_api = mock_api_class.return_value
                        mock_api.identify_song_from_title.return_value = {
                            'song': {'name': 'Space Cadet'}
                        }
                        # No setlist available - falls back to counted numbering
                        mock_api.get_setlist_for_show.return_value = None

                        result = download_manager.download_upgrade_to_existing_dir(
                            video_info=video_info,
                            show_dir=show_dir,
                            show_info=show_info,
                            backup_existing=False
                        )

        # Should have created a numbered file with the song name appended
        # (one unnumbered concert file exists, so this becomes track 02)
        assert "Space Cadet" in result.name
        assert result.name == "2024-05-18 - Prague (Forum Karlin) - concert - 02 - Space Cadet.mp4"
    
    def test_full_concert_detection_by_title_keywords(self, download_manager, temp_dir):
        """Test that title keywords correctly identify full concerts."""
        show_dir = temp_dir / "test_show"
        show_dir.mkdir()
        
        downloaded_file = show_dir / "downloaded.mp4"
        downloaded_file.write_text("content")
        
        # Test various full concert title patterns
        full_concert_titles = [
            'King Gizzard Full Concert Prague 2024',
            'KGLW Complete Show Live',
            'Full Set - King Gizzard',
            'Entire Concert Prague',
            'Complete Performance Live'
        ]
        
        show_info = {
            'date': '2024-05-18',
            'location': 'Prague',
            'venue': 'Forum Karlin'
        }
        
        for i, title in enumerate(full_concert_titles):
            # Create fresh downloaded file for each iteration
            downloaded_file = show_dir / f"downloaded_{i}.mp4" 
            downloaded_file.write_text("content")
            
            video_info = {
                'title': title,
                'duration': 30 * 60,  # 30 minutes - short but has keywords
                'webpage_url': 'https://example.com/concert'
            }
            
            with patch.object(download_manager, 'download_video', return_value=True):
                with patch.object(download_manager, '_find_downloaded_file', return_value=downloaded_file):
                    with patch.object(download_manager, '_backup_existing_files'):
                        result = download_manager.download_upgrade_to_existing_dir(
                            video_info=video_info,
                            show_dir=show_dir,
                            show_info=show_info,
                            backup_existing=False
                        )
            
            # Should end with just "concert.mp4", not have song suffixes
            assert result.name.endswith("concert.mp4")
            assert "Song_" not in result.name
    
    def test_duration_based_full_concert_detection(self, download_manager, temp_dir):
        """Test that long duration videos are treated as full concerts."""
        show_dir = temp_dir / "test_show"
        show_dir.mkdir()
        
        downloaded_file = show_dir / "downloaded.mp4" 
        downloaded_file.write_text("content")
        
        # Video with no full concert keywords but long duration
        video_info = {
            'title': 'KGLW Prague Video',  # Generic title
            'duration': 60 * 60,  # 1 hour - should be detected as full concert
            'webpage_url': 'https://example.com/long-video'
        }
        
        show_info = {
            'date': '2024-05-18',
            'location': 'Prague',
            'venue': 'Forum Karlin'
        }
        
        with patch.object(download_manager, 'download_video', return_value=True):
            with patch.object(download_manager, '_find_downloaded_file', return_value=downloaded_file):
                with patch.object(download_manager, '_backup_existing_files'):
                    result = download_manager.download_upgrade_to_existing_dir(
                        video_info=video_info,
                        show_dir=show_dir,
                        show_info=show_info,
                        backup_existing=False
                    )
        
        # Should be treated as full concert due to duration
        assert result.name.endswith("concert.mp4")
        assert "Song_" not in result.name
    
    def test_backup_existing_bypasses_song_naming_logic(self, download_manager, temp_dir):
        """Test that backup_existing=True bypasses the song naming logic entirely."""
        show_dir = temp_dir / "test_show"
        show_dir.mkdir()
        
        # Create existing file in the current (artist-less) naming
        existing_file = show_dir / "2024-05-18 - Prague (Forum Karlin) - concert.mp4"
        existing_file.write_text("existing")
        
        downloaded_file = show_dir / "downloaded.mp4"
        downloaded_file.write_text("new")
        
        # Even individual song should use standard name when backup_existing=True
        video_info = {
            'title': 'Space Cadet',  # Individual song
            'duration': 240,  # Short duration
            'webpage_url': 'https://example.com/individual-song'
        }
        
        show_info = {
            'date': '2024-05-18',
            'location': 'Prague', 
            'venue': 'Forum Karlin'
        }
        
        with patch.object(download_manager, 'download_video', return_value=True):
            with patch.object(download_manager, '_find_downloaded_file', return_value=downloaded_file):
                with patch.object(download_manager, '_backup_existing_files'):
                    result = download_manager.download_upgrade_to_existing_dir(
                        video_info=video_info,
                        show_dir=show_dir,
                        show_info=show_info,
                        backup_existing=True  # Should bypass song naming
                    )
        
        # Should use standard concert name regardless of being individual song
        assert result.name == "2024-05-18 - Prague (Forum Karlin) - concert.mp4"
        assert "Space Cadet" not in result.name