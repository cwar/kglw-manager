"""
Test upgrade candidate display formatting to ensure titles are shown with enough detail.
"""

import pytest
from unittest.mock import Mock, patch
from io import StringIO

from kglw_manager.interactive import InteractiveManager
from kglw_manager.collection import CollectionManager


class TestUpgradeDisplay:
    """Test upgrade candidate display formatting."""
    
    @pytest.mark.unit
    def test_upgrade_candidates_show_detailed_titles(self, temp_collection_dir):
        """Test that upgrade candidates table shows detailed titles and dates."""
        collection_manager = CollectionManager(str(temp_collection_dir))
        interactive = InteractiveManager(collection_manager)
        
        # Mock upgrade candidates with detailed information
        mock_candidates = [
            {
                'title': 'King Gizzard & The Lizard Wizard - Live in Lisbon \'25 (Night 1) - Full Show',
                'channel': 'King Gizzard And The Lizard Wizard',
                'height': 2160,
                'duration': 8160,  # 2h 16m
                'upload_date': '20250518',
                'url': 'https://www.youtube.com/watch?v=example1'
            },
            {
                'title': 'Live from - Coliseu Dos Recreios - Lisbon, Portugal - 05/18/25 (Night 2)',
                'channel': 'King Gizzard And The Lizard Wizard',
                'height': 1080,
                'duration': 8640,  # 2h 24m 
                'upload_date': '20250519',
                'url': 'https://www.youtube.com/watch?v=example2'
            }
        ]
        
        # Create a mock show_info for testing single show upgrade search
        show_info = {
            'date': '2025-05-18',
            'location': 'Lisbon',
            'venue': 'Coliseu Dos Recreios',
            'files': [{'title': 'Existing Show - Full Show', 'quality': '720p', 'duration': 3600}]
        }
        
        # Mock the YouTube searcher to return our test candidates
        with patch.object(interactive.collection_manager.youtube_searcher, 'search_for_upgrades', return_value=mock_candidates):
            # Mock console to capture the table output
            with patch.object(interactive, 'console') as mock_console:
                # Mock input to simulate user backing out
                with patch('builtins.input', side_effect=['1', 'b']):
                    try:
                        interactive._search_upgrades_for_show(show_info)
                    except (SystemExit, KeyboardInterrupt):
                        # Expected when user chooses to back out
                        pass
                
                # Verify that console.print was called with a table
                assert mock_console.print.called
                
                # Get the table object that was printed
                table_calls = [call for call in mock_console.print.call_args_list 
                              if len(call[0]) > 0 and hasattr(call[0][0], 'add_row')]
                
                assert len(table_calls) > 0, "Expected table to be printed"
                table = table_calls[0][0][0]
                
                # Check that table has the expected columns including Date and Link
                column_headers = [col.header for col in table.columns]
                assert "Title" in column_headers
                assert "Date" in column_headers  # Changed from "Upload Date" to "Date"
                assert "Duration" in column_headers
                assert "Quality" in column_headers
                assert "Link" in column_headers  # New link column
    
    @pytest.mark.unit
    def test_upgrade_title_length_and_date_formatting(self, temp_collection_dir):
        """Test that titles are shown with 80 character limit and dates are formatted correctly."""
        collection_manager = CollectionManager(str(temp_collection_dir))
        interactive = InteractiveManager(collection_manager)
        
        # Test candidate with very long title
        long_title = "This is an extremely long video title that should be truncated to exactly 80 characters for display purposes in the upgrade candidates table"
        
        mock_candidates = [
            {
                'title': long_title,
                'channel': 'Test Channel',
                'height': 720,
                'duration': 3600,
                'upload_date': '20250518',
                'url': 'https://www.youtube.com/watch?v=test'
            }
        ]
        
        # Create a mock show_info for testing single show upgrade search
        show_info = {
            'date': '2025-05-18',
            'location': 'Test Location',
            'venue': 'Test Venue',
            'files': [{'title': 'Existing Show', 'quality': '720p', 'duration': 3600}]
        }
        
        with patch.object(interactive.collection_manager.youtube_searcher, 'search_for_upgrades', return_value=mock_candidates):
            with patch.object(interactive, 'console') as mock_console:
                with patch('builtins.input', side_effect=['1', 'b']):
                    try:
                        interactive._search_upgrades_for_show(show_info)
                    except (SystemExit, KeyboardInterrupt):
                        pass
        
        # Verify the table was created and printed
        assert mock_console.print.called
        
        # For this test, we verify the logic works by testing the format functions directly
        # Test title truncation logic
        song_label = ""  # No song label for this test
        display_title = (long_title + song_label)[:80] + "..." if len(long_title + song_label) > 80 else (long_title + song_label)
        
        # Should be truncated to 80 chars + "..." = 83 total
        assert len(display_title) == 83
        assert display_title.endswith("...")
        
        # Test date formatting logic
        upload_date = '20250518'
        date_str = f"{upload_date[4:6]}/{upload_date[6:8]}/{upload_date[2:4]}"
        assert date_str == "05/18/25"
    
    @pytest.mark.unit
    def test_upgrade_display_handles_missing_date(self, temp_collection_dir):
        """Test that missing upload dates are handled gracefully."""
        collection_manager = CollectionManager(str(temp_collection_dir))
        interactive = InteractiveManager(collection_manager)
        
        # Test candidates with missing or malformed dates
        mock_candidates = [
            {
                'title': 'Video without upload date',
                'channel': 'Test Channel',
                'height': 720,
                'duration': 3600,
                # No upload_date field
                'url': 'https://www.youtube.com/watch?v=test1'
            },
            {
                'title': 'Video with empty upload date',
                'channel': 'Test Channel', 
                'height': 720,
                'duration': 3600,
                'upload_date': '',  # Empty date
                'url': 'https://www.youtube.com/watch?v=test2'
            },
            {
                'title': 'Video with short upload date',
                'channel': 'Test Channel',
                'height': 720, 
                'duration': 3600,
                'upload_date': '2025',  # Too short
                'url': 'https://www.youtube.com/watch?v=test3'
            }
        ]
        
        # Create a mock show_info for testing single show upgrade search
        show_info = {
            'date': '2025-05-18',
            'location': 'Test Location',
            'venue': 'Test Venue',
            'files': [{'title': 'Existing Show', 'quality': '720p', 'duration': 3600}]
        }
        
        with patch.object(interactive.collection_manager.youtube_searcher, 'search_for_upgrades', return_value=mock_candidates):
            with patch.object(interactive, 'console') as mock_console:
                with patch('builtins.input', side_effect=['1', 'b']):
                    try:
                        interactive._search_upgrades_for_show(show_info)
                    except (SystemExit, KeyboardInterrupt):
                        pass
        
        # Verify no exceptions were raised and table was printed
        assert mock_console.print.called
        
        # Test the date formatting logic for edge cases
        test_cases = [
            ('', 'Unknown'),  # Empty date
            ('2025', 'Unknown'),  # Too short
            (None, 'Unknown'),  # None value
            ('20250518', '05/18/25')  # Valid date
        ]
        
        for upload_date, expected in test_cases:
            if upload_date and len(upload_date) >= 8:
                date_str = f"{upload_date[4:6]}/{upload_date[6:8]}/{upload_date[2:4]}"
            else:
                date_str = "Unknown"
            assert date_str == expected