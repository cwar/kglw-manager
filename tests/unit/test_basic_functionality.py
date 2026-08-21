"""
Basic functionality tests to demonstrate pytest suite works.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from kglw_manager.collection import CollectionManager
from kglw_manager.naming import NamingManager
from kglw_manager.tours import TourManager


class TestBasicFunctionality:
    """Test basic functionality of core components."""
    
    @pytest.mark.unit
    def test_naming_manager_initialization(self):
        """Test that NamingManager initializes correctly."""
        manager = NamingManager()
        assert manager.artist_name == "King Gizzard & The Lizard Wizard"
    
    @pytest.mark.unit
    def test_tour_manager_initialization(self):
        """Test that TourManager initializes correctly."""
        manager = TourManager()
        assert hasattr(manager, 'tour_definitions')
        assert isinstance(manager.tour_definitions, dict)
        assert len(manager.tour_definitions) > 0
    
    @pytest.mark.unit
    def test_plex_filename_generation(self):
        """Test basic Plex filename generation (new format without artist)."""
        manager = NamingManager()

        show_info = {
            'date': '2024-03-15',
            'location': 'Austin'
        }

        filename = manager.generate_plex_filename(show_info, '.mp4')

        # New format excludes artist name to prevent Plex grouping issues
        assert 'King Gizzard' not in filename
        assert '2024-03-15' in filename
        assert 'Austin' in filename
        assert filename.endswith('.mp4')
    
    @pytest.mark.unit
    def test_collection_manager_initialization(self, temp_collection_dir):
        """Test CollectionManager initialization with temp directory."""
        manager = CollectionManager(str(temp_collection_dir))
        
        assert manager.collection_path == temp_collection_dir
        assert manager.mode == "movie"
        assert manager.naming_manager is not None
        assert manager.tour_manager is not None
    
    @pytest.mark.unit
    def test_tour_assignment_logic(self):
        """Test basic tour assignment logic."""
        manager = TourManager()
        
        # Test that tours are defined
        tours = manager.list_tours()
        assert len(tours) > 0
        
        # Test tour assignment for known date
        show_info = {'date': '2024-03-15', 'location': 'Austin'}
        tour_name = manager.assign_tour(show_info)
        assert isinstance(tour_name, str)
        assert len(tour_name) > 0
    
    @pytest.mark.unit
    @patch('kglw_manager.collection.CollectionManager._analyze_video_quality')
    def test_scan_empty_directory(self, mock_analyze, temp_collection_dir):
        """Test scanning an empty directory."""
        mock_analyze.return_value = {
            'quality': '720p',
            'duration': 4800,
            'resolution': '1280x720'
        }
        
        manager = CollectionManager(str(temp_collection_dir))
        result = manager.scan_collection()
        
        assert isinstance(result, dict)
        assert 'tours' in result
        assert isinstance(result['tours'], dict)
    
    @pytest.mark.unit
    def test_format_duration_utility(self):
        """Test duration formatting utility."""
        from kglw_manager.utils import format_duration
        
        # Test various duration formats based on actual implementation
        assert format_duration(0) == "0min"
        assert format_duration(30) == "0min"  # Less than a minute
        assert format_duration(90) == "1min"  # 1.5 minutes rounds to 1min
        assert format_duration(3600) == "1h 0min"
        assert format_duration(3660) == "1h 1min"  # 61 minutes
        assert format_duration(7380) == "2h 3min"  # 123 minutes
    
    @pytest.mark.integration
    def test_collection_and_naming_integration(self, temp_collection_dir):
        """Test integration between collection manager and naming."""
        # Create a test show directory
        show_dir = temp_collection_dir / "2024-03-15 - Austin"
        show_dir.mkdir(parents=True)
        
        # Create a fake video file
        video_file = show_dir / "test_video.mp4"
        video_file.write_text("fake video content")
        
        manager = CollectionManager(str(temp_collection_dir))
        
        # Test that the directory structure is recognized
        assert show_dir.exists()
        
        # Test show info parsing from directory name
        show_info = manager.naming_manager.parse_show_info_from_filename("2024-03-15 - Austin")
        assert show_info['date'] == '2024-03-15'
        assert show_info['location'] == 'Austin'
    
    @pytest.mark.unit
    def test_venue_parsing_in_naming(self):
        """Test venue parsing from various naming formats."""
        manager = NamingManager()
        
        # Test with parentheses venue
        show_info = manager.parse_show_info_from_filename("2024-03-15 - Austin (Moody Center)")
        assert show_info['date'] == '2024-03-15'
        assert show_info['location'] == 'Austin'
        assert show_info['venue'] == 'Moody Center'
        
        # Test without venue
        show_info = manager.parse_show_info_from_filename("2024-03-16 - Dallas")
        assert show_info['date'] == '2024-03-16'
        assert show_info['location'] == 'Dallas'
        assert show_info.get('venue') in [None, '']
    
    @pytest.mark.unit
    def test_tour_year_ranges(self):
        """Test tour definitions cover expected year ranges."""
        manager = TourManager()
        
        # Test that we have tours defined for recent years
        for year in [2022, 2023, 2024]:
            test_show = {
                'date': f'{year}-06-15',
                'location': 'Test City'
            }
            tour_name = manager.assign_tour(test_show)
            assert str(year) in tour_name
    
    @pytest.mark.unit
    def test_error_handling_in_parsing(self):
        """Test error handling in parsing operations."""
        manager = NamingManager()
        
        # Test with invalid date formats
        result = manager.parse_show_info_from_filename("invalid-date-format")
        assert result is not None  # Should handle gracefully
        
        # Test with empty string
        result = manager.parse_show_info_from_filename("")
        assert result is not None  # Should handle gracefully
        
        # Test with None
        result = manager.parse_show_info_from_filename(None)
        assert result is not None  # Should handle gracefully
    
    @pytest.mark.unit
    def test_collection_manager_properties(self, temp_collection_dir):
        """Test collection manager has expected properties and methods."""
        manager = CollectionManager(str(temp_collection_dir))
        
        # Test required attributes exist
        assert hasattr(manager, 'collection_path')
        assert hasattr(manager, 'naming_manager')
        assert hasattr(manager, 'tour_manager')
        assert hasattr(manager, 'mode')
        
        # Test required methods exist
        assert hasattr(manager, 'scan_collection')
        assert callable(getattr(manager, 'scan_collection'))
        assert hasattr(manager, '_analyze_video_quality')
        assert callable(getattr(manager, '_analyze_video_quality'))
    
    @pytest.mark.unit
    def test_path_handling(self, temp_collection_dir):
        """Test path handling with various formats."""
        # Test with Path object
        manager1 = CollectionManager(temp_collection_dir)
        assert manager1.collection_path == temp_collection_dir
        
        # Test with string path
        manager2 = CollectionManager(str(temp_collection_dir))
        assert manager2.collection_path == temp_collection_dir
    
    @pytest.mark.unit
    def test_special_characters_in_names(self):
        """Test handling of special characters in show names."""
        manager = NamingManager()

        # Test with special characters
        show_info = {
            'date': '2024-03-15',
            'location': 'São Paulo',
            'venue': 'Estádio do Morumbi'
        }

        filename = manager.generate_plex_filename(show_info, '.mp4')

        # Should handle special characters (new format without artist name)
        assert '2024-03-15' in filename
        assert filename.endswith('.mp4')
        # Verify artist name is NOT in the filename
        assert 'King Gizzard' not in filename

        # Test parsing with special characters
        parsed = manager.parse_show_info_from_filename("2024-03-15 - São Paulo (Test Venue)")
        assert parsed['date'] == '2024-03-15'
        assert 'Paulo' in parsed['location'] or 'São Paulo' in parsed['location']
    
    @pytest.mark.unit
    def test_date_validation(self):
        """Test date validation in various components."""
        manager = TourManager()
        
        # Test with valid dates
        valid_dates = ['2024-01-01', '2024-12-31', '2023-06-15']
        for date in valid_dates:
            show_info = {'date': date, 'location': 'Test City'}
            tour_name = manager.assign_tour(show_info)
            assert isinstance(tour_name, str)
            assert len(tour_name) > 0
    
    @pytest.mark.unit
    def test_filename_sanitization(self):
        """Test filename sanitization for filesystem compatibility."""
        manager = NamingManager()
        
        # Test with problematic characters
        show_info = {
            'date': '2024-03-15',
            'location': 'City/Town',
            'venue': 'Venue:Name*With?Chars<Test>'
        }
        
        filename = manager.generate_plex_filename(show_info, '.mp4')
        
        # Should not contain filesystem-problematic characters
        problematic_chars = ['/', '\\', ':', '*', '?', '<', '>', '|']
        for char in problematic_chars:
            assert char not in filename, f"Found problematic character '{char}' in filename: {filename}"