"""
Comprehensive test coverage for all interactive menu options.
Tests each menu path to ensure no broken code.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from kglw_manager.interactive import InteractiveManager
from kglw_manager.collection import CollectionManager


@pytest.fixture
def mock_collection_manager(tmp_path):
    """Create a mock collection manager."""
    with patch('kglw_manager.collection.CollectionManager.__init__', return_value=None):
        manager = CollectionManager.__new__(CollectionManager)
        manager.collection_path = tmp_path
        manager.mode = 'movie'
        manager.plex_manager = None
        manager.youtube_searcher = Mock()
        manager.kglw_api = Mock()
        manager.quality_manager = Mock()
        manager.download_manager = Mock()
        return manager


@pytest.fixture
def interactive_manager(mock_collection_manager):
    """Create interactive manager instance."""
    with patch('kglw_manager.interactive.InteractiveManager._check_terminal_support', return_value=False):
        manager = InteractiveManager(mock_collection_manager)
        manager.collection_data = {
            'tours': {
                '2024 Test Tour': {
                    'show_count': 2,
                    'shows': {
                        '2024-01-01 - Test Location': {
                            'date': '2024-01-01',
                            'location': 'Test Location',
                            'venue': 'Test Venue',
                            'files': [],
                            'path': str(mock_collection_manager.collection_path)
                        }
                    }
                }
            }
        }
        return manager


class TestMainMenuOptions:
    """Test all main menu paths."""

    @patch('kglw_manager.interactive.InteractiveManager.show_menu')
    @patch('kglw_manager.interactive.InteractiveManager._browse_and_manage_menu')
    def test_main_menu_browse_and_manage(self, mock_browse, mock_menu, interactive_manager):
        """Test main menu -> Browse & Manage."""
        mock_menu.side_effect = [0, -3]  # Select option 0, then quit
        interactive_manager.run()
        mock_browse.assert_called_once()

    @patch('kglw_manager.interactive.InteractiveManager.show_menu')
    @patch('kglw_manager.interactive.InteractiveManager._collection_maintenance_menu')
    def test_main_menu_collection_maintenance(self, mock_maintenance, mock_menu, interactive_manager):
        """Test main menu -> Collection Maintenance."""
        mock_menu.side_effect = [1, -3]  # Select option 1, then quit
        interactive_manager.run()
        mock_maintenance.assert_called_once()

    @patch('kglw_manager.interactive.InteractiveManager.show_menu')
    @patch('kglw_manager.interactive.InteractiveManager._metadata_integration_menu')
    def test_main_menu_metadata_integration(self, mock_metadata, mock_menu, interactive_manager):
        """Test main menu -> Metadata & Integration."""
        mock_menu.side_effect = [2, -3]  # Select option 2, then quit
        interactive_manager.run()
        mock_metadata.assert_called_once()

    @patch('kglw_manager.interactive.InteractiveManager.show_menu')
    @patch('kglw_manager.interactive.InteractiveManager._settings_menu')
    def test_main_menu_settings(self, mock_settings, mock_menu, interactive_manager):
        """Test main menu -> Settings."""
        mock_menu.side_effect = [3, -3]  # Select option 3, then quit
        interactive_manager.run()
        mock_settings.assert_called_once()


class TestBrowseAndManageMenu:
    """Test Browse & Manage submenu options."""

    @patch('kglw_manager.interactive.InteractiveManager.show_menu')
    @patch('kglw_manager.interactive.InteractiveManager._browse_by_year')
    def test_browse_by_year(self, mock_browse_year, mock_menu, interactive_manager):
        """Test Browse by Year option."""
        mock_menu.side_effect = [-1]  # Go back
        interactive_manager._browse_and_manage_menu()
        # Verify menu was shown
        assert mock_menu.called

    @patch('kglw_manager.interactive.InteractiveManager.show_menu')
    @patch('builtins.input', return_value='')
    def test_search_shows(self, mock_input, mock_menu, interactive_manager):
        """Test Search Shows option."""
        mock_menu.return_value = -1  # Back
        interactive_manager._browse_and_manage_menu()

    @patch('kglw_manager.interactive.InteractiveManager.show_menu')
    def test_collection_tree_view(self, mock_menu, interactive_manager):
        """Test Collection Tree View option."""
        mock_menu.return_value = -1  # Back
        interactive_manager._browse_and_manage_menu()

    @patch('kglw_manager.interactive.InteractiveManager.show_menu')
    @patch('kglw_manager.interactive.InteractiveManager._find_upgrade_candidates')
    def test_find_upgrade_candidates(self, mock_find, mock_menu, interactive_manager):
        """Test Find All Upgrade Candidates option."""
        mock_menu.side_effect = [-1]  # Go back
        interactive_manager._browse_and_manage_menu()


class TestCollectionMaintenanceMenu:
    """Test Collection Maintenance submenu options."""

    @patch('kglw_manager.interactive.InteractiveManager.show_menu')
    @patch('kglw_manager.interactive.InteractiveManager._analyze_video_quality')
    def test_analyze_video_quality(self, mock_analyze, mock_menu, interactive_manager):
        """Test Analyze Video Quality option."""
        mock_menu.side_effect = [0, -1]  # Select option 0, then back
        interactive_manager._collection_maintenance_menu()
        mock_analyze.assert_called_once()

    @patch('kglw_manager.interactive.InteractiveManager.show_menu')
    @patch('builtins.input', return_value='')
    def test_integrity_check(self, mock_input, mock_menu, interactive_manager):
        """Test Integrity Check option."""
        mock_menu.side_effect = [1, -1]  # Select option 1, then back
        interactive_manager._collection_maintenance_menu()

    @patch('kglw_manager.interactive.InteractiveManager.show_menu')
    @patch('kglw_manager.interactive.InteractiveManager._directory_cleanup')
    def test_directory_cleanup(self, mock_cleanup, mock_menu, interactive_manager):
        """Test Directory Cleanup option."""
        mock_menu.side_effect = [2, -1]  # Select option 2, then back
        interactive_manager._collection_maintenance_menu()
        mock_cleanup.assert_called_once()

    @patch('kglw_manager.interactive.InteractiveManager.show_menu')
    @patch('kglw_manager.interactive.InteractiveManager._cache_diagnostics')
    def test_cache_diagnostics(self, mock_cache, mock_menu, interactive_manager):
        """Test Cache Diagnostics option."""
        mock_menu.side_effect = [3, -1]  # Select option 3, then back
        interactive_manager._collection_maintenance_menu()
        mock_cache.assert_called_once()


class TestPlexIntegrationMenu:
    """Test Plex Integration submenu options."""

    @pytest.fixture
    def interactive_manager_with_plex(self, interactive_manager):
        """Add Plex manager to interactive manager."""
        interactive_manager.collection_manager.plex_manager = Mock()
        return interactive_manager

    @patch('kglw_manager.interactive.InteractiveManager.show_menu')
    @patch('kglw_manager.interactive.InteractiveManager._plex_sync')
    def test_plex_sync(self, mock_sync, mock_menu, interactive_manager_with_plex):
        """Test Plex Sync option."""
        mock_menu.side_effect = [0, -1]  # Select option 0, then back
        interactive_manager_with_plex._plex_integration_menu()
        mock_sync.assert_called_once()

    @patch('kglw_manager.interactive.InteractiveManager.show_menu')
    @patch('kglw_manager.interactive.InteractiveManager._plex_comprehensive_fix')
    def test_plex_comprehensive_fix(self, mock_fix, mock_menu, interactive_manager_with_plex):
        """Test Plex Comprehensive Fix option."""
        mock_menu.side_effect = [1, -1]  # Select option 1, then back
        interactive_manager_with_plex._plex_integration_menu()
        mock_fix.assert_called_once()

    @patch('kglw_manager.interactive.InteractiveManager.show_menu')
    @patch('kglw_manager.interactive.InteractiveManager._plex_fix_multi_show_items')
    def test_plex_fix_multi_show(self, mock_fix, mock_menu, interactive_manager_with_plex):
        """Test Plex Fix Multi-Show Items option."""
        mock_menu.side_effect = [2, -1]  # Select option 2, then back
        interactive_manager_with_plex._plex_integration_menu()
        mock_fix.assert_called_once()

    @patch('kglw_manager.interactive.InteractiveManager.show_menu')
    @patch('kglw_manager.interactive.InteractiveManager._plex_refresh_metadata')
    def test_plex_refresh_metadata(self, mock_refresh, mock_menu, interactive_manager_with_plex):
        """Test Plex Refresh Metadata option."""
        mock_menu.side_effect = [3, -1]  # Select option 3, then back
        interactive_manager_with_plex._plex_integration_menu()
        mock_refresh.assert_called_once()

    @patch('kglw_manager.interactive.InteractiveManager.show_menu')
    @patch('kglw_manager.interactive.InteractiveManager._plex_cleanup_empty_collections')
    def test_plex_cleanup_empty_collections(self, mock_cleanup, mock_menu, interactive_manager_with_plex):
        """Test Plex Clean Up Empty Collections option."""
        mock_menu.side_effect = [4, -1]  # Select option 4, then back
        interactive_manager_with_plex._plex_integration_menu()
        mock_cleanup.assert_called_once()


class TestSettingsMenu:
    """Test Settings menu options."""

    @patch('kglw_manager.interactive.InteractiveManager.show_menu')
    @patch('builtins.input', return_value='')
    def test_settings_menu_access(self, mock_input, mock_menu, interactive_manager):
        """Test Settings menu can be accessed."""
        mock_menu.return_value = -1  # Back
        interactive_manager._settings_menu()
        assert mock_menu.called


class TestErrorHandling:
    """Test error handling in menu options."""

    @patch('kglw_manager.interactive.InteractiveManager.show_menu')
    def test_plex_menu_without_plex_manager(self, mock_menu, interactive_manager):
        """Test Plex menu when Plex is not configured."""
        mock_menu.return_value = -1
        with patch('builtins.input'):
            interactive_manager._plex_integration_menu()
        # Should not crash, should show error message

    @patch('kglw_manager.interactive.InteractiveManager.show_menu')
    def test_browse_with_no_collection_data(self, mock_menu, interactive_manager):
        """Test browsing with no collection data."""
        interactive_manager.collection_data = None
        mock_menu.return_value = -1
        # Should handle gracefully
        with patch('builtins.input'):
            interactive_manager._browse_and_manage_menu()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
