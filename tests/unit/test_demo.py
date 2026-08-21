"""
Demo tests to show pytest suite functionality.
"""

import pytest
from pathlib import Path

from kglw_manager.collection import CollectionManager
from kglw_manager.naming import NamingManager


class TestPytestDemo:
    """Demo tests showing pytest suite works correctly."""
    
    @pytest.mark.unit
    def test_basic_math(self):
        """Basic test to verify pytest is working."""
        assert 2 + 2 == 4
        assert "hello" + " world" == "hello world"
    
    @pytest.mark.unit
    def test_naming_manager_exists(self):
        """Test that we can import and create a NamingManager."""
        manager = NamingManager()
        assert manager is not None
        assert hasattr(manager, 'artist_name')
        assert manager.artist_name == "King Gizzard & The Lizard Wizard"
    
    @pytest.mark.unit
    def test_collection_manager_with_temp_dir(self, temp_collection_dir):
        """Test CollectionManager with fixture."""
        manager = CollectionManager(str(temp_collection_dir))
        assert manager.collection_path == temp_collection_dir
        assert manager.mode == "movie"
    
    @pytest.mark.unit
    def test_plex_filename_simple(self):
        """Test simple filename generation (new format without artist name)."""
        manager = NamingManager()
        show_info = {'date': '2024-01-01', 'location': 'TestCity'}
        filename = manager.generate_plex_filename(show_info)

        assert '2024-01-01' in filename
        assert 'TestCity' in filename
        # New format excludes artist name to prevent Plex grouping issues
        assert 'King Gizzard' not in filename
    
    @pytest.mark.integration
    def test_temp_directory_fixture(self, temp_collection_dir):
        """Test that temp directory fixture works."""
        assert temp_collection_dir.exists()
        assert temp_collection_dir.is_dir()
        
        # Can create files in temp directory
        test_file = temp_collection_dir / "test.txt"
        test_file.write_text("test content")
        assert test_file.read_text() == "test content"
    
    @pytest.mark.unit
    def test_sample_show_info_fixture(self, sample_show_info):
        """Test sample show info fixture."""
        assert 'date' in sample_show_info
        assert 'location' in sample_show_info
        assert 'files' in sample_show_info
        assert len(sample_show_info['files']) > 0