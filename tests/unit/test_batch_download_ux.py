"""Test batch download UX improvements."""

import pytest
from unittest.mock import Mock, patch, call
from kglw_manager.interactive import InteractiveManager


class TestBatchDownloadUX:
    """Test batch download UX - no individual confirmations for batch operations."""
    
    @pytest.fixture
    def interactive_manager(self):
        """Create InteractiveManager for testing."""
        mock_collection_manager = Mock()
        with patch('kglw_manager.sources.DataSourceManager'):
            manager = InteractiveManager(mock_collection_manager)
            manager.console = Mock()
            return manager
    
    def test_download_all_uses_auto_confirm_true(self, interactive_manager):
        """Test that 'Download All' uses auto_confirm=True to skip individual prompts."""
        missing_shows = [
            {'show_info': {'date': '2024-01-15', 'location': 'Test City'}, 
             'candidate': {'title': 'Test Video 1'}, 'tour': 'Test Tour'},
            {'show_info': {'date': '2024-01-20', 'location': 'Another City'}, 
             'candidate': {'title': 'Test Video 2'}, 'tour': 'Test Tour'}
        ]
        
        # Mock the collection manager's download method
        mock_results = {'success': 2, 'failed': 0, 'skipped': 0}
        interactive_manager.collection_manager.download_missing_shows.return_value = mock_results
        
        # Test the download all functionality
        with patch('builtins.input', return_value=''):  # Mock Enter press for continuation
            interactive_manager._download_missing_shows(missing_shows, auto_confirm=True)
        
        # Verify that download_missing_shows was called with auto_confirm=True
        interactive_manager.collection_manager.download_missing_shows.assert_called_once_with(
            missing_shows=missing_shows, auto_confirm=True, format_id='best'
        )
    
    def test_download_all_menu_option_uses_auto_confirm_true(self, interactive_manager):
        """Test that selecting 'Download All' from menu uses auto_confirm=True."""
        missing_shows = [
            {'show_info': {'date': '2024-01-15', 'location': 'Test City'}, 
             'candidate': {'title': 'Test Video 1'}, 'tour': 'Test Tour'}
        ]
        
        with patch.object(interactive_manager, 'show_menu') as mock_show_menu:
            mock_show_menu.return_value = 0  # Select "Download All" option
            
            with patch.object(interactive_manager, '_download_missing_shows') as mock_download:
                with patch.object(interactive_manager, '_select_and_download_missing_shows'):
                    with patch.object(interactive_manager, '_view_missing_show_details'):
                        # Call the missing shows display menu
                        interactive_manager._display_and_handle_missing_shows(missing_shows)
        
        # Verify that _download_missing_shows was called with auto_confirm=True
        mock_download.assert_called_once_with(missing_shows, auto_confirm=True)
    
    def test_selected_shows_also_use_auto_confirm_true(self, interactive_manager):
        """Test that selected shows download also uses auto_confirm=True after selection."""
        missing_shows = [
            {'show_info': {'date': '2024-01-15', 'location': 'Test City'}, 
             'candidate': {'title': 'Test Video 1'}, 'tour': 'Test Tour'},
            {'show_info': {'date': '2024-01-20', 'location': 'Another City'}, 
             'candidate': {'title': 'Test Video 2'}, 'tour': 'Test Tour'}
        ]
        
        with patch('rich.prompt.Confirm.ask') as mock_confirm:
            # User selects first show, skips second
            mock_confirm.side_effect = [True, False]
            
            with patch.object(interactive_manager, '_download_missing_shows') as mock_download:
                with patch('builtins.input', return_value=''):  # Mock Enter press
                    interactive_manager._select_and_download_missing_shows(missing_shows)
        
        # Should have been called with only the first show and auto_confirm=True
        expected_selected_shows = [missing_shows[0]]
        mock_download.assert_called_once_with(expected_selected_shows, auto_confirm=True)
    
    def test_no_individual_prompts_in_batch_download(self, interactive_manager):
        """Test that batch download doesn't show individual confirmation prompts."""
        missing_shows = [
            {'show_info': {'date': '2024-01-15', 'location': 'Test City'}, 
             'candidate': {'title': 'Test Video 1'}, 'tour': 'Test Tour'},
            {'show_info': {'date': '2024-01-20', 'location': 'Another City'}, 
             'candidate': {'title': 'Test Video 2'}, 'tour': 'Test Tour'}
        ]
        
        # Mock successful downloads
        mock_results = {'success': 2, 'failed': 0, 'skipped': 0}
        interactive_manager.collection_manager.download_missing_shows.return_value = mock_results
        
        with patch('rich.prompt.Confirm.ask') as mock_confirm:
            with patch('builtins.input', return_value=''):  # Mock Enter press
                # Call with auto_confirm=True (batch download scenario)
                interactive_manager._download_missing_shows(missing_shows, auto_confirm=True)
        
        # Confirm.ask should NOT be called for individual shows in batch mode
        mock_confirm.assert_not_called()
    
    def test_individual_prompts_still_work_when_auto_confirm_false(self, interactive_manager):
        """Test that individual prompts still work when auto_confirm=False."""
        missing_shows = [
            {'show_info': {'date': '2024-01-15', 'location': 'Test City'}, 
             'candidate': {'title': 'Test Video 1'}, 'tour': 'Test Tour'}
        ]
        
        # Mock successful download
        mock_results = {'success': 1, 'failed': 0, 'skipped': 0}
        interactive_manager.collection_manager.download_missing_shows.return_value = mock_results
        
        with patch('rich.prompt.Confirm.ask') as mock_confirm:
            mock_confirm.return_value = True  # User confirms the batch
            
            with patch('builtins.input', return_value=''):  # Mock Enter press
                # Call with auto_confirm=False (should prompt for batch confirmation)
                interactive_manager._download_missing_shows(missing_shows, auto_confirm=False)
        
        # Should have prompted once for batch confirmation
        mock_confirm.assert_called_once_with(f"Download all {len(missing_shows)} shows?", default=True)
    
    def test_batch_download_default_parameter_is_true(self, interactive_manager):
        """Test that the default parameter for _download_missing_shows is auto_confirm=True."""
        missing_shows = [
            {'show_info': {'date': '2024-01-15', 'location': 'Test City'}, 
             'candidate': {'title': 'Test Video 1'}, 'tour': 'Test Tour'}
        ]
        
        # Mock successful download
        mock_results = {'success': 1, 'failed': 0, 'skipped': 0}
        interactive_manager.collection_manager.download_missing_shows.return_value = mock_results
        
        with patch('rich.prompt.Confirm.ask') as mock_confirm:
            with patch('builtins.input', return_value=''):  # Mock Enter press
                # Call without specifying auto_confirm (should default to True)
                interactive_manager._download_missing_shows(missing_shows)
        
        # Should NOT prompt since default is auto_confirm=True
        mock_confirm.assert_not_called()
        
        # Should call collection manager with auto_confirm=True
        interactive_manager.collection_manager.download_missing_shows.assert_called_once_with(
            missing_shows=missing_shows, auto_confirm=True, format_id='best'
        )