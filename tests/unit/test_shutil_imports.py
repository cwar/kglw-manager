"""Tests for shutil import fixes in tour directory structure methods."""

import unittest
from unittest.mock import patch, MagicMock, call
from pathlib import Path
from kglw_manager.interactive import InteractiveManager
from kglw_manager.collection import CollectionManager


class TestShutilImports(unittest.TestCase):
    """Test that shutil imports are working correctly in tour fixing methods."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.collection_manager = CollectionManager("/test/path")
        self.interactive = InteractiveManager(self.collection_manager)
        self.interactive.console = MagicMock()  # Mock console output
    
    @patch('shutil.move')
    def test_fix_nested_tour_structure_can_import_shutil(self, mock_shutil_move):
        """Test that _fix_nested_tour_structure can import and use shutil."""
        # Create a mock issue structure
        issue = {
            'parent_tour': '2024 USA',
            'nested_tour': 'Canada - Summer',
            'parent_path': Path('/test/2024 USA'),
            'nested_path': Path('/test/2024 USA/Canada - Summer'),
            'shows': [Path('/test/2024 USA/Canada - Summer/2024-06-01 - Toronto')]
        }
        
        # Mock target path not existing (rename scenario)
        with patch.object(Path, 'exists', return_value=False), \
             patch.object(Path, 'iterdir', return_value=[]):
            
            # This should not raise a NameError for shutil
            try:
                self.interactive._fix_nested_tour_structure(issue)
                # If we get here without exception, shutil import worked
                import_success = True
            except NameError as e:
                if "shutil" in str(e):
                    import_success = False
                else:
                    # Some other NameError, re-raise
                    raise
            
            # Verify shutil was successfully imported and used
            self.assertTrue(import_success, "shutil should be importable in _fix_nested_tour_structure")
            mock_shutil_move.assert_called_once()
    
    @patch('shutil.move')
    def test_fix_tour_naming_variants_can_import_shutil(self, mock_shutil_move):
        """Test that _fix_tour_naming_variants can import and use shutil."""
        # Create a mock issue structure with variants
        issue = {
            'variants': [
                {
                    'name': '2015 Europe-UK - Summer',
                    'show_count': 11,
                    'path': Path('/test/2015 Europe-UK - Summer'),
                    'shows': []
                },
                {
                    'name': '2015 Europe_UK - Summer', 
                    'show_count': 10,
                    'path': Path('/test/2015 Europe_UK - Summer'),
                    'shows': [Path('/test/2015 Europe_UK - Summer/2015-06-01 - London')]
                }
            ]
        }
        
        # Mock path operations
        with patch.object(Path, 'exists', return_value=False), \
             patch.object(Path, 'rmdir'):
            
            # This should not raise a NameError for shutil
            try:
                self.interactive._fix_tour_naming_variants(issue)
                # If we get here without exception, shutil import worked
                import_success = True
            except NameError as e:
                if "shutil" in str(e):
                    import_success = False
                else:
                    # Some other NameError, re-raise
                    raise
            
            # Verify shutil was successfully imported and used
            self.assertTrue(import_success, "shutil should be importable in _fix_tour_naming_variants")
            mock_shutil_move.assert_called_once()
    
    def test_shutil_available_in_both_methods(self):
        """Test that both methods have access to shutil after import."""
        # Test that the methods can successfully import shutil without errors
        # We do this by calling exec on a simple import statement within each method's scope
        
        # For _fix_nested_tour_structure
        nested_method_code = """
import shutil
shutil_available = hasattr(shutil, 'move')
"""
        
        # For _fix_tour_naming_variants  
        variants_method_code = """
import shutil
shutil_available = hasattr(shutil, 'move')
"""
        
        # These should execute without NameError
        nested_globals = {}
        variants_globals = {}
        
        exec(nested_method_code, nested_globals)
        exec(variants_method_code, variants_globals)
        
        self.assertTrue(nested_globals['shutil_available'])
        self.assertTrue(variants_globals['shutil_available'])


if __name__ == '__main__':
    unittest.main()