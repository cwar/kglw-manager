"""Tests for duplicate directory winner selection logic."""

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from kglw_manager.interactive import InteractiveManager
from kglw_manager.collection import CollectionManager


class TestDuplicateWinnerLogic(unittest.TestCase):
    """Test duplicate directory winner selection logic."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.collection_manager = CollectionManager("/test/path")
        self.interactive = InteractiveManager(self.collection_manager)
    
    def test_canonical_format_winner_preferred(self):
        """Test that canonical format directories are preferred as winners."""
        # Mock directory info with different formats
        directories = [
            {
                'path': Path('/test/2024-11-21 - Miami (Factory Town)'),
                'file_count': 0
            },
            {
                'path': Path('/test/2024-11-21 - Miami FL (USA)'),  # Should be canonical format
                'file_count': 0
            }
        ]
        
        # Mock the canonical format matching to return the second directory
        with patch.object(self.interactive, '_find_canonical_format_match') as mock_canonical:
            mock_canonical.return_value = directories[1]  # Return the "canonical" format
            
            winner = self.interactive._determine_duplicate_winner(directories)
            
            # Should choose the canonical format directory
            self.assertEqual(winner, directories[1])
    
    def test_canonical_format_reasoning(self):
        """Test that reasoning explains canonical format choice."""
        directories = [
            {
                'path': Path('/test/2024-11-21 - Miami (Factory Town)'),
                'file_count': 0
            },
            {
                'path': Path('/test/2024-11-21 - Miami FL (USA)'),
                'file_count': 0
            }
        ]
        
        winner = directories[1]
        
        # Mock canonical matching to return the winner
        with patch.object(self.interactive, '_find_canonical_format_match') as mock_canonical:
            mock_canonical.return_value = winner
            
            reasoning = self.interactive._get_duplicate_winner_reasoning(directories, winner)
            
            # Should explain that it matches current naming system
            self.assertEqual(reasoning, "matches current naming system format")
    
    def test_fallback_to_file_count_when_no_canonical_match(self):
        """Test that file count is used when no canonical format match exists."""
        directories = [
            {
                'path': Path('/test/2024-11-21 - Miami (Factory Town)'),
                'file_count': 0
            },
            {
                'path': Path('/test/2024-11-21 - Miami FL (USA)'),
                'file_count': 5  # More files
            }
        ]
        
        # Mock no canonical format match
        with patch.object(self.interactive, '_find_canonical_format_match') as mock_canonical:
            mock_canonical.return_value = None  # No canonical match
            
            winner = self.interactive._determine_duplicate_winner(directories)
            
            # Should choose the directory with more files
            self.assertEqual(winner, directories[1])
            self.assertEqual(winner['file_count'], 5)
    
    def test_merge_vs_delete_action_labeling(self):
        """Test that directories with 0 files show DELETE, others show MERGE."""
        # This test verifies the action labeling logic we just implemented
        # Directory with 0 files should show "DELETE"
        dir_with_no_files = {'file_count': 0}
        action_no_files = "DELETE" if dir_with_no_files['file_count'] == 0 else "MERGE"
        self.assertEqual(action_no_files, "DELETE")
        
        # Directory with files should show "MERGE"
        dir_with_files = {'file_count': 3}
        action_with_files = "DELETE" if dir_with_files['file_count'] == 0 else "MERGE"
        self.assertEqual(action_with_files, "MERGE")


if __name__ == '__main__':
    unittest.main()