"""Comprehensive tests for Plex integration functionality."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Import the module we're testing
try:
    from kglw_manager.plex_manager import PlexManager
    PLEX_AVAILABLE = True
except ImportError:
    PLEX_AVAILABLE = False
    PlexManager = None


class StubConfig(dict):
    """Minimal stand-in for kglw_manager.config.config.

    Provides dict-style get(key, default) plus the config_file attribute that
    PlexManager references in its missing-credentials error message.
    """
    config_file = Path('/tmp/kglw-test-config.json')


PATH_CONFIG = {
    'collection_path': '/library-root/kglw',
    'plex_library_path': '/library/kglw',
}


class TestPlexManagerInitialization:
    """Test Plex manager initialization and connection."""
    
    @pytest.mark.skipif(not PLEX_AVAILABLE, reason="PlexAPI not available")
    def test_plex_manager_imports_available(self):
        """Test that Plex manager can be imported when dependencies are available."""
        assert PlexManager is not None
    
    def test_plex_manager_unavailable_handling(self):
        """Test graceful handling when PlexAPI is not available."""
        with patch.dict('sys.modules', {'plexapi': None, 'plexapi.server': None}):
            # Should handle missing PlexAPI gracefully
            try:
                # This would be caught at the collection manager level
                from kglw_manager.collection import CollectionManager
                from pathlib import Path
                
                with tempfile.TemporaryDirectory() as temp_dir:
                    # Collection manager should initialize without Plex
                    manager = CollectionManager(Path(temp_dir))
                    # Plex manager should be None when not available
                    # (This depends on configuration and availability)
            except ImportError:
                # Expected when PlexAPI is not available
                pass


@pytest.mark.skipif(not PLEX_AVAILABLE, reason="PlexAPI not available")
class TestPlexManagerCore:
    """Core Plex manager functionality tests."""
    
    @pytest.fixture
    def mock_plex_server(self):
        """Mock Plex server for testing."""
        server = Mock()
        server.library = Mock()
        server.library.section.return_value = Mock()
        return server
    
    @pytest.fixture
    def mock_kglw_api(self):
        """Mock KGLW API for testing."""
        api = Mock()
        api.get_show_by_date.return_value = {
            'setlist_notes': 'Test setlist notes',
            'poster_image': 'https://example.com/poster.jpg'
        }
        return api
    
    @pytest.fixture
    def plex_manager(self, mock_plex_server, mock_kglw_api):
        """Create PlexManager instance with mocked dependencies."""
        with patch('kglw_manager.plex_manager.PlexServer', return_value=mock_plex_server), \
             patch('kglw_manager.plex_manager.KGLWApi', return_value=mock_kglw_api):
            
            manager = PlexManager(
                server_url="http://localhost:32400",
                token="fake_token",
                library_name="Test Library"
            )
            return manager
    
    def test_plex_manager_initialization(self, plex_manager):
        """Test PlexManager initialization."""
        assert plex_manager.plex is not None
        assert plex_manager.library is not None
        assert plex_manager.kglw_api is not None
    
    def test_convert_to_plex_path(self, plex_manager):
        """Test local path to Plex path conversion.

        Uses the stub config so the result doesn't depend on whatever
        collection_path the person running the tests happens to have.
        """
        local_path = Path("/library-root/kglw/2024 Tour/2024-01-15 - Test/video.mp4")
        with patch('kglw_manager.plex_manager.config', StubConfig(PATH_CONFIG)):
            plex_path = plex_manager._convert_to_plex_path(local_path)

        expected_path = "/library/kglw/2024 Tour/2024-01-15 - Test/video.mp4"
        assert plex_path == expected_path
    
    def test_scan_show_directory(self, plex_manager):
        """Test scanning show directory for videos and posters."""
        with tempfile.TemporaryDirectory() as temp_dir:
            show_path = Path(temp_dir)
            
            # Create test files
            (show_path / "video1.mp4").touch()
            (show_path / "video2.mkv").touch()
            (show_path / "poster.jpg").touch()
            (show_path / "thumbnail.png").touch()  # Non-poster image: ignored
            (show_path / "info.json").touch()  # Should be ignored

            videos, posters = plex_manager._scan_show_directory(show_path)

            assert len(videos) == 2
            # Only files named 'poster.*' count as posters (Plex convention);
            # arbitrary images like yt-dlp thumbnails must not be picked up.
            assert len(posters) == 1
            assert all(v.suffix.lower() in ['.mp4', '.mkv'] for v in videos)
            assert posters[0].name == 'poster.jpg'
    
    def test_determine_tour_from_path(self, plex_manager):
        """Test tour determination from directory path."""
        show_path = Path("/collection/2024 Test Tour/2024-01-15 - Test City")
        tour_name = plex_manager._determine_tour_from_path(show_path)
        
        assert tour_name == "2024 Test Tour"


class TestPlexManagerLibraryOperations:
    """Test Plex library operations."""
    
    @pytest.fixture
    def plex_manager_with_mock_library(self):
        """Create Plex manager with mocked library operations."""
        with patch('kglw_manager.plex_manager.PlexServer') as mock_server_class:
            mock_server = Mock()
            mock_library = Mock()
            mock_server.library = mock_library
            mock_server.library.section.return_value = mock_library
            mock_server_class.return_value = mock_server
            
            with patch('kglw_manager.plex_manager.KGLWApi'):
                manager = PlexManager(
                    server_url="http://localhost:32400",
                    token="fake_token"
                )
                return manager, mock_library
    
    def test_get_plex_item_by_path(self, plex_manager_with_mock_library):
        """Test finding Plex item by file path."""
        manager, mock_library = plex_manager_with_mock_library

        # The implementation matches part.file against the converted path
        # while iterating library.all()
        mock_item = Mock()
        mock_item.media = [Mock()]
        mock_item.media[0].parts = [Mock()]
        mock_item.media[0].parts[0].file = "/library/kglw/test/video.mp4"

        mock_library.all.return_value = [mock_item]

        with patch('kglw_manager.plex_manager.config', StubConfig(PATH_CONFIG)):
            video_path = Path("/library-root/kglw/test/video.mp4")
            found_item = manager._get_plex_item_by_path(video_path)

        assert found_item == mock_item
        mock_library.all.assert_called()

    def test_refresh_library_path(self, plex_manager_with_mock_library):
        """Test refreshing specific library path."""
        manager, mock_library = plex_manager_with_mock_library

        with patch('kglw_manager.plex_manager.config', StubConfig(PATH_CONFIG)):
            directory_path = Path("/library-root/kglw/test_show")
            manager._refresh_library_path(directory_path)

        # Should trigger a scan of the converted path (plexapi's
        # LibrarySection.update(path=...)), not a full metadata refresh
        mock_library.update.assert_called_once_with(path="/library/kglw/test_show")


class TestPlexManagerMetadataUpdates:
    """Test metadata update operations."""
    
    @pytest.fixture
    def plex_manager_with_mock_api(self):
        """Create Plex manager with mocked API."""
        with patch('kglw_manager.plex_manager.PlexServer'), \
             patch('kglw_manager.plex_manager.KGLWApi') as mock_api_class:
            
            mock_api = mock_api_class.return_value
            mock_api.get_show_by_date.return_value = {
                'setlist_notes': 'Test setlist notes for the show',
                'poster_image': 'https://kglw.net/poster.jpg'
            }
            
            manager = PlexManager()
            return manager, mock_api
    
    def test_update_show_metadata(self, plex_manager_with_mock_api):
        """Test updating show metadata from KGLW API."""
        manager, mock_api = plex_manager_with_mock_api
        
        # Mock Plex item
        mock_plex_item = Mock()
        mock_plex_item.title = "Test Show"
        mock_plex_item.editSummary = Mock()
        mock_plex_item.edit = Mock()
        
        show_path = Path("/collection/2024 Tour/2024-01-15 - Test City")
        
        result = manager._update_show_metadata(mock_plex_item, show_path)
        
        assert result is True
        mock_api.get_show_by_date.assert_called_with('2024-01-15')
        
        # Should attempt to update summary with API method first
        mock_plex_item.editSummary.assert_called_with('Test setlist notes for the show')
    
    def test_update_show_metadata_fallback_method(self, plex_manager_with_mock_api):
        """Test metadata update with fallback edit method."""
        manager, mock_api = plex_manager_with_mock_api
        
        # Mock Plex item with editSummary failing
        mock_plex_item = Mock()
        mock_plex_item.editSummary.side_effect = Exception("API method not available")
        mock_plex_item.edit = Mock()
        
        show_path = Path("/collection/2024-01-15 - Test City")
        
        result = manager._update_show_metadata(mock_plex_item, show_path)
        
        # Should fallback to edit method
        mock_plex_item.edit.assert_called_with(summary='Test setlist notes for the show')


class TestPlexManagerCollectionOperations:
    """Test Plex collection management operations."""
    
    @pytest.fixture
    def plex_manager_with_collections(self):
        """Create Plex manager with mocked collections."""
        with patch('kglw_manager.plex_manager.PlexServer') as mock_server_class:
            mock_server = Mock()
            mock_library = Mock()
            mock_server.library = mock_library
            mock_server.library.section.return_value = mock_library
            mock_server_class.return_value = mock_server
            
            # Mock collections
            mock_collection = Mock()
            mock_collection.title = "Test Tour"
            mock_library.collections.return_value = [mock_collection]
            
            with patch('kglw_manager.plex_manager.KGLWApi'):
                manager = PlexManager()
                return manager, mock_library, mock_collection
    
    def test_add_to_collection(self, plex_manager_with_collections):
        """Test adding items to collections."""
        manager, mock_library, mock_collection = plex_manager_with_collections
        
        # Mock Plex item that is not yet in any collection
        mock_item = Mock()
        mock_item.collections = []
        mock_item.addCollection = Mock()

        # Test adding to existing collection
        success = manager._add_to_collection(mock_item, "Test Tour")

        assert success is True
        mock_item.addCollection.assert_called_with("Test Tour")
    
    def test_missing_shows_detection(self, plex_manager_with_collections):
        """Test detection of shows missing from collections."""
        manager, mock_library, mock_collection = plex_manager_with_collections
        
        # Mock library items
        mock_collection.tag = "Test Tour"

        mock_item1 = Mock()
        mock_item1.title = "Show in Collection"
        mock_item1.collections = [mock_collection]

        mock_item2 = Mock()
        mock_item2.title = "Show Missing Collection"
        mock_item2.collections = []
        mock_item2.media = []  # iterated when looking up the file path

        mock_library.all.return_value = [mock_item1, mock_item2]
        
        missing_shows = manager.find_shows_missing_from_collections()
        
        # Should find one show missing from collections
        assert len(missing_shows) == 1
        assert missing_shows[0]['title'] == "Show Missing Collection"


class TestPlexManagerErrorHandling:
    """Test error handling in Plex operations."""
    
    def test_connection_error_handling(self):
        """Test handling of Plex connection errors."""
        with patch('kglw_manager.plex_manager.PlexServer') as mock_server_class:
            mock_server_class.side_effect = Exception("Connection refused")
            
            with pytest.raises(Exception, match="Connection refused"):
                PlexManager(server_url="http://invalid:32400", token="fake")
    
    def test_library_not_found_error(self):
        """Test handling when library is not found."""
        with patch('kglw_manager.plex_manager.PlexServer') as mock_server_class:
            mock_server = Mock()
            mock_server.library.section.side_effect = Exception("Library not found")
            mock_server_class.return_value = mock_server
            
            with pytest.raises(Exception, match="Library not found"):
                PlexManager(library_name="NonExistentLibrary")
    
    def test_metadata_update_error_handling(self):
        """Test error handling in metadata updates."""
        with patch('kglw_manager.plex_manager.PlexServer'), \
             patch('kglw_manager.plex_manager.KGLWApi') as mock_api_class:
            
            # Mock API that fails
            mock_api = mock_api_class.return_value
            mock_api.get_show_by_date.side_effect = Exception("API error")
            
            manager = PlexManager()
            mock_plex_item = Mock()
            show_path = Path("/test/path")
            
            # Should handle API errors gracefully
            result = manager._update_show_metadata(mock_plex_item, show_path)
            assert result is False  # Should fail gracefully


class TestPlexManagerMultiShowHandling:
    """Test multi-show library item handling."""
    
    @pytest.fixture
    def multi_show_item(self):
        """Create mock multi-show Plex item."""
        item = Mock()
        item.title = "Multi-Show Item"
        item.ratingKey = "12345"
        
        # Mock multiple media files from two different show dates (multi-show
        # detection keys off distinct YYYY-MM-DD dates in the file paths)
        media1 = Mock()
        media1.parts = [Mock()]
        media1.parts[0].file = "/library/kglw/2024 Tour/2024-01-15 - City One/video1.mp4"

        media2 = Mock()
        media2.parts = [Mock()]
        media2.parts[0].file = "/library/kglw/2024 Tour/2024-01-16 - City Two/video2.mp4"

        item.media = [media1, media2]
        return item
    
    def test_multi_show_detection(self, multi_show_item):
        """Test detection of multi-show library items."""
        with patch('kglw_manager.plex_manager.PlexServer') as mock_server_class:
            mock_server = Mock()
            mock_library = Mock()
            mock_library.all.return_value = [multi_show_item]
            mock_server.library.section.return_value = mock_library
            mock_server_class.return_value = mock_server
            
            with patch('kglw_manager.plex_manager.KGLWApi'):
                manager = PlexManager(server_url="http://localhost:32400",
                                      token="fake_token")

                multi_items = manager.find_multi_show_library_items()

                assert len(multi_items) == 1
                assert multi_items[0]['title'] == "Multi-Show Item"
                assert len(multi_items[0]['file_paths']) == 2
    
    def test_multi_show_splitting(self, multi_show_item):
        """Test splitting of multi-show items."""
        with patch('kglw_manager.plex_manager.PlexServer') as mock_server_class:
            mock_server = Mock()
            mock_server.library.section.return_value = Mock()
            mock_server_class.return_value = mock_server
            
            with patch('kglw_manager.plex_manager.KGLWApi'):
                manager = PlexManager()
                
                # Mock the split operation
                mock_split_items = [Mock(), Mock()]
                multi_show_item.split.return_value = mock_split_items
                
                # Mock fetchItem to return our multi-show item
                manager.plex.fetchItem = Mock(return_value=multi_show_item)
                
                result = manager.split_multi_show_item("12345")
                
                assert result['success'] is True
                assert result['split_count'] == 2
                multi_show_item.split.assert_called_once()


class TestPlexManagerConfigurationHandling:
    """Test configuration and setup handling."""
    
    def test_default_configuration(self):
        """Test config-driven credentials and default library name."""
        # Credentials come from config (explicit arg > env > config); no
        # hardcoded fallback exists.
        stub = StubConfig({'plex_url': 'http://localhost:32400',
                           'plex_token': 'config_token'})
        with patch('kglw_manager.plex_manager.PlexServer'), \
             patch('kglw_manager.plex_manager.KGLWApi'), \
             patch.dict('os.environ', {}, clear=False), \
             patch('kglw_manager.plex_manager.config', stub):
            import os
            os.environ.pop('KGLW_PLEX_URL', None)
            os.environ.pop('KGLW_PLEX_TOKEN', None)

            manager = PlexManager()

            assert manager.plex_url == 'http://localhost:32400'
            assert manager.plex_token == 'config_token'
            # Should use default library name
            assert manager.library_name == 'KGLW'

    def test_missing_credentials_raise(self):
        """Without any configured URL/token, connecting must fail clearly."""
        stub = StubConfig()  # no plex_url / plex_token anywhere
        with patch('kglw_manager.plex_manager.PlexServer'), \
             patch('kglw_manager.plex_manager.KGLWApi'), \
             patch.dict('os.environ', {}, clear=False), \
             patch('kglw_manager.plex_manager.config', stub):
            import os
            os.environ.pop('KGLW_PLEX_URL', None)
            os.environ.pop('KGLW_PLEX_TOKEN', None)

            with pytest.raises(ValueError, match="not configured"):
                PlexManager()
    
    def test_custom_configuration(self):
        """Test custom configuration values."""
        with patch('kglw_manager.plex_manager.PlexServer'), \
             patch('kglw_manager.plex_manager.KGLWApi'):
            
            manager = PlexManager(
                server_url="http://custom:32400",
                token="custom_token",
                library_name="Custom Library"
            )
            
            assert manager.library_name == "Custom Library"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])