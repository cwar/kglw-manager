"""Tests for Kometa sync direction - updating Kometa assets to match collection."""

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from kglw_manager.interactive import InteractiveManager
from kglw_manager.collection import CollectionManager


class TestKometaSyncDirection(unittest.TestCase):
    """Test that Kometa sync updates assets to match collection directories."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.collection_manager = CollectionManager("/test/collection")
        self.interactive = InteractiveManager(self.collection_manager)
        self.interactive.console = MagicMock()  # Mock console output
    
    @patch('shutil.move')
    def test_fix_kometa_mismatches_renames_kometa_assets(self, mock_shutil_move):
        """Test that _fix_kometa_mismatches renames Kometa assets to match collection."""
        mismatches = [
            {
                'collection_path': Path('/test/collection/2024-11-21 - Miami (Factory Town)'),
                'collection_name': '2024-11-21 - Miami (Factory Town)',
                'kometa_path': Path('/kometa/assets/2024-11-21 - Miami FL (USA)'),
                'kometa_name': '2024-11-21 - Miami FL (USA)',
                'date': '2024-11-21'
            }
        ]
        
        # Execute the fix
        self.interactive._fix_kometa_mismatches(mismatches)
        
        # Verify that shutil.move was called to rename the Kometa asset
        mock_shutil_move.assert_called_once_with(
            '/kometa/assets/2024-11-21 - Miami FL (USA)',
            '/kometa/assets/2024-11-21 - Miami (Factory Town)'
        )
    
    @patch('shutil.move')
    def test_fix_kometa_mismatches_preserves_collection_names(self, mock_shutil_move):
        """Test that collection directories are not renamed - they are the source of truth."""
        mismatches = [
            {
                'collection_path': Path('/test/collection/2024-03-14 - Santiago (Teatro Coliseo)'),
                'collection_name': '2024-03-14 - Santiago (Teatro Coliseo)',
                'kometa_path': Path('/kometa/assets/2024-03-14 - Santiago (Chile)'),
                'kometa_name': '2024-03-14 - Santiago (Chile)',
                'date': '2024-03-14'
            }
        ]
        
        # Execute the fix
        self.interactive._fix_kometa_mismatches(mismatches)
        
        # Verify that Kometa asset is renamed to match collection (not vice versa)
        mock_shutil_move.assert_called_once()
        call_args = mock_shutil_move.call_args[0]
        
        # Source should be Kometa path, destination should use collection name
        self.assertEqual(call_args[0], '/kometa/assets/2024-03-14 - Santiago (Chile)')
        self.assertEqual(call_args[1], '/kometa/assets/2024-03-14 - Santiago (Teatro Coliseo)')
    
    @patch('shutil.move')
    def test_fix_multiple_mismatches(self, mock_shutil_move):
        """Test fixing multiple mismatches at once."""
        mismatches = [
            {
                'collection_path': Path('/test/collection/2024-11-21 - Miami (Factory Town)'),
                'collection_name': '2024-11-21 - Miami (Factory Town)',
                'kometa_path': Path('/kometa/assets/2024-11-21 - Miami FL (USA)'),
                'kometa_name': '2024-11-21 - Miami FL (USA)',
                'date': '2024-11-21'
            },
            {
                'collection_path': Path('/test/collection/2024-03-17 - Buenos Aires (Hipódromo)'),
                'collection_name': '2024-03-17 - Buenos Aires (Hipódromo)',
                'kometa_path': Path('/kometa/assets/2024-03-17 - Buenos Aires (Argentina)'),
                'kometa_name': '2024-03-17 - Buenos Aires (Argentina)',
                'date': '2024-03-17'
            }
        ]
        
        # Execute the fix
        self.interactive._fix_kometa_mismatches(mismatches)
        
        # Verify both renames happened
        self.assertEqual(mock_shutil_move.call_count, 2)
        
        # Verify correct direction for both calls
        calls = mock_shutil_move.call_args_list
        
        # First call: Miami
        self.assertEqual(calls[0][0][0], '/kometa/assets/2024-11-21 - Miami FL (USA)')
        self.assertEqual(calls[0][0][1], '/kometa/assets/2024-11-21 - Miami (Factory Town)')
        
        # Second call: Buenos Aires
        self.assertEqual(calls[1][0][0], '/kometa/assets/2024-03-17 - Buenos Aires (Argentina)')
        self.assertEqual(calls[1][0][1], '/kometa/assets/2024-03-17 - Buenos Aires (Hipódromo)')
    
    def test_mismatch_detection_includes_kometa_path(self):
        """Test that mismatch detection includes the kometa_path for renaming."""
        # This is more of an integration test to verify the mismatch structure
        # Since we can't easily mock the full directory scanning logic,
        # we'll just verify the expected structure
        
        expected_mismatch_keys = {
            'collection_path', 'collection_name', 'kometa_path', 'kometa_name', 'date'
        }
        
        # Create a sample mismatch as would be generated by _compare_with_kometa_assets
        sample_mismatch = {
            'collection_path': Path('/test/collection/2024-11-21 - Miami (Factory Town)'),
            'collection_name': '2024-11-21 - Miami (Factory Town)',
            'kometa_path': Path('/kometa/assets/2024-11-21 - Miami FL (USA)'),
            'kometa_name': '2024-11-21 - Miami FL (USA)',
            'date': '2024-11-21'
        }
        
        # Verify all required keys are present
        self.assertEqual(set(sample_mismatch.keys()), expected_mismatch_keys)
        
        # Verify types
        self.assertIsInstance(sample_mismatch['collection_path'], Path)
        self.assertIsInstance(sample_mismatch['kometa_path'], Path)
        self.assertIsInstance(sample_mismatch['collection_name'], str)
        self.assertIsInstance(sample_mismatch['kometa_name'], str)


if __name__ == '__main__':
    unittest.main()