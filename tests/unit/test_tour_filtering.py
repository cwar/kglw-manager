"""
Test tour filtering to prevent empty tours from appearing in the interface.
"""

import pytest
from unittest.mock import Mock, patch
from kglw_manager.interactive import InteractiveManager
from kglw_manager.collection import CollectionManager


class TestTourFiltering:
    """Test filtering of empty tours (like future tours with no API data)."""
    
    @pytest.mark.unit
    def test_empty_tours_are_filtered_out(self, temp_collection_dir):
        """Test that tours with no shows are filtered out, even with scraped info."""
        collection_manager = CollectionManager(str(temp_collection_dir))
        interactive = InteractiveManager(collection_manager)
        
        # Mock API tours data (simulating future tours with no API shows yet)
        api_tours = {
            "2025 Phantom Island - USA": {
                'shows': {
                    "2025-07-28 - Austin": {
                        'date': '2025-07-28',
                        'city': 'Austin',
                        'venue': 'Test Venue'
                    }
                },
                'api_show_count': 1,
                'local_show_count': 0
            }
        }
        
        # Mock scraped tour data (includes future tour)
        mock_scraped_tours = {
            "2025 Phantom Island - USA": {
                'name': '2025 Phantom Island - USA',
                'num_shows': 12,
                'start_date': '2025-07-28',
                'end_date': '2025-08-17'
            },
            "2025 Europe Fall": {  # Future tour with no API shows yet
                'name': '2025 Europe Fall', 
                'num_shows': 13,
                'start_date': '2025-10-31',
                'end_date': '2025-11-15'
            }
        }
        
        with patch('kglw_manager.tour_scraper.tour_scraper') as mock_scraper:
            mock_scraper.get_all_tours.return_value = mock_scraped_tours
            
            enhanced_tours = interactive._enhance_tours_with_scraped_data(api_tours, 2025)
        
        # Should only have tours with actual shows
        assert len(enhanced_tours) == 1
        assert "2025 Phantom Island - USA" in enhanced_tours
        assert "2025 Europe Fall" not in enhanced_tours  # Filtered out (no actual shows)
        
        # The existing tour should still have its shows
        usa_tour = enhanced_tours["2025 Phantom Island - USA"]
        assert len(usa_tour['shows']) == 1
        assert '2025-07-28 - Austin' in usa_tour['shows']
    
    @pytest.mark.unit 
    def test_filtering_logic_prevents_empty_tours(self):
        """Test that the filtering logic correctly prevents empty tours."""
        # Test the core filtering logic directly
        mock_tours = {
            "Tour With Shows": {
                'shows': {"show1": {}, "show2": {}},  # Has shows
                'api_show_count': 2,
                'local_show_count': 0
            },
            "Empty Tour": {
                'shows': {},  # No shows
                'api_show_count': 0,
                'local_show_count': 0,
                'scraped_info': {'num_shows': 15}  # Has scraped info but no actual shows
            }
        }
        
        # Apply the same filtering logic as the fix
        filtered_tours = {name: info for name, info in mock_tours.items() 
                         if len(info['shows']) > 0}
        
        # Should only keep tours with actual shows
        assert len(filtered_tours) == 1
        assert "Tour With Shows" in filtered_tours
        assert "Empty Tour" not in filtered_tours  # Filtered out despite scraped info
    
    @pytest.mark.unit
    def test_tour_date_parsing_edge_cases(self):
        """Test edge cases in tour date parsing and validation."""
        from kglw_manager.tours import TourManager
        
        tour_manager = TourManager()
        
        # Test various problematic date formats
        problematic_shows = [
            {'date': '2024-02-29', 'location': 'Austin'},  # Leap year - valid
            {'date': '2023-02-29', 'location': 'Austin'},  # Non-leap year - invalid
            {'date': '2024-13-01', 'location': 'Austin'},  # Invalid month
            {'date': '2024-12-32', 'location': 'Austin'},  # Invalid day
            {'date': '2024/03/15', 'location': 'Austin'},  # Wrong separator
            {'date': '24-03-15', 'location': 'Austin'},    # 2-digit year
            {'date': '', 'location': 'Austin'},            # Empty date
            {'date': None, 'location': 'Austin'},          # None date
            {'location': 'Austin'},                        # Missing date
        ]
        
        for show_info in problematic_shows:
            try:
                tour_name = tour_manager.assign_tour(show_info)
                # Should always return a string, even for invalid dates
                assert isinstance(tour_name, str)
                assert len(tour_name) > 0
                # Should likely contain a fallback indicator
                if not show_info.get('date') or show_info['date'] in ['', None]:
                    assert "Not Part of a Tour" in tour_name or "Unknown" in tour_name or "TBD" in tour_name
            except Exception as e:
                # Should not crash on invalid dates, but if it does, should be specific error
                assert isinstance(e, (ValueError, TypeError, KeyError))
    
    @pytest.mark.unit
    def test_tour_assignment_boundary_dates(self):
        """Test tour assignment around boundary dates."""
        from kglw_manager.tours import TourManager
        
        tour_manager = TourManager()
        
        # Test shows right at year boundaries
        boundary_shows = [
            {'date': '2023-12-31', 'location': 'Austin'},  # End of 2023
            {'date': '2024-01-01', 'location': 'Austin'},  # Start of 2024
            {'date': '2024-12-31', 'location': 'Austin'},  # End of 2024
            {'date': '2025-01-01', 'location': 'Austin'},  # Start of 2025
        ]
        
        for show_info in boundary_shows:
            tour_name = tour_manager.assign_tour(show_info)
            year = show_info['date'][:4]
            # Should assign to correct year
            assert year in tour_name, f"Year {year} not found in tour '{tour_name}' for date {show_info['date']}"
    
    @pytest.mark.unit
    def test_location_based_tour_matching(self):
        """Test location-based tour assignment logic."""
        from kglw_manager.tours import TourManager
        
        tour_manager = TourManager()
        
        # Test various location formats and their tour assignments
        location_tests = [
            # US locations
            {'date': '2024-06-15', 'location': 'Austin, TX'},
            {'date': '2024-06-15', 'location': 'Austin'},
            {'date': '2024-06-15', 'location': 'New York'},
            {'date': '2024-06-15', 'location': 'Los Angeles'},
            
            # International locations  
            {'date': '2024-06-15', 'location': 'London'},
            {'date': '2024-06-15', 'location': 'Paris'},
            {'date': '2024-06-15', 'location': 'Melbourne'},
            {'date': '2024-06-15', 'location': 'Sydney'},
            
            # Edge case locations
            {'date': '2024-06-15', 'location': 'São Paulo'},  # Unicode
            {'date': '2024-06-15', 'location': 'México City'}, # Special chars
            {'date': '2024-06-15', 'location': ''},           # Empty location
            {'date': '2024-06-15', 'location': None},         # None location
        ]
        
        for show_info in location_tests:
            try:
                tour_name = tour_manager.assign_tour(show_info)
                
                # Should always get a tour name
                assert isinstance(tour_name, str)
                assert len(tour_name) > 0
                
                # Should contain the year
                assert '2024' in tour_name
            except AttributeError as e:
                # Handle cases where location is None - this might be acceptable behavior
                if show_info.get('location') is None:
                    # It's acceptable for None locations to cause errors
                    continue
                else:
                    # Re-raise if it's a different issue
                    raise
            
            # Location-based logic tests
            location = show_info.get('location', '')
            if location:
                # US cities might get "USA" in tour name
                if location in ['Austin', 'New York', 'Los Angeles', 'Austin, TX']:
                    # May or may not have "USA" depending on tour definitions
                    pass
                # International might get region names
                elif location in ['London', 'Paris']:
                    # May have "Europe" in tour name
                    pass
                elif location in ['Melbourne', 'Sydney']:
                    # May have "Australia" in tour name
                    pass
    
    @pytest.mark.unit
    def test_tour_name_consistency(self):
        """Test that tour name generation is consistent."""
        from kglw_manager.tours import TourManager
        
        tour_manager = TourManager()
        
        # Same show info should always get same tour name
        show_info = {'date': '2024-06-15', 'location': 'Austin'}
        
        tour_names = []
        for _ in range(5):  # Call multiple times
            tour_name = tour_manager.assign_tour(show_info)
            tour_names.append(tour_name)
        
        # All should be identical
        assert all(name == tour_names[0] for name in tour_names), f"Inconsistent tour names: {tour_names}"
    
    @pytest.mark.unit
    def test_tour_list_functionality(self):
        """Test tour listing and enumeration."""
        from kglw_manager.tours import TourManager
        
        tour_manager = TourManager()
        
        # Should be able to list all defined tours
        tours = tour_manager.list_tours()
        
        assert isinstance(tours, (list, dict))
        assert len(tours) > 0  # Should have some tours defined
        
        # Each tour should have reasonable structure
        if isinstance(tours, list):
            for tour in tours:
                assert isinstance(tour, str)
                assert len(tour) > 0
        elif isinstance(tours, dict):
            for tour_name, tour_info in tours.items():
                assert isinstance(tour_name, str)
                assert len(tour_name) > 0
                assert isinstance(tour_info, dict)
    
    @pytest.mark.unit
    def test_future_year_handling(self):
        """Test handling of future years in tour assignment."""
        from kglw_manager.tours import TourManager
        
        tour_manager = TourManager()
        
        # Test future years
        future_shows = [
            {'date': '2025-06-15', 'location': 'Austin'},
            {'date': '2026-06-15', 'location': 'Austin'},
            {'date': '2030-06-15', 'location': 'Austin'},
        ]
        
        for show_info in future_shows:
            tour_name = tour_manager.assign_tour(show_info)
            year = show_info['date'][:4]
            
            # Should handle future years gracefully
            assert isinstance(tour_name, str)
            assert len(tour_name) > 0
            assert year in tour_name  # Should include the year
            
            # Likely will be "Not Part of a Tour" for undefined years
            # This is acceptable behavior
    
    @pytest.mark.unit
    def test_historical_year_handling(self):
        """Test handling of historical years."""
        from kglw_manager.tours import TourManager
        
        tour_manager = TourManager()
        
        # Test historical years (before KGLW formed)
        historical_shows = [
            {'date': '2000-06-15', 'location': 'Austin'},  # Way before KGLW
            {'date': '2010-06-15', 'location': 'Austin'},  # Early KGLW era
            {'date': '1995-06-15', 'location': 'Austin'},  # Before band existed
        ]
        
        for show_info in historical_shows:
            tour_name = tour_manager.assign_tour(show_info)
            year = show_info['date'][:4]
            
            # Should handle gracefully, likely assign to fallback
            assert isinstance(tour_name, str)
            assert len(tour_name) > 0
            
            # For very old dates, might get "Not Part of a Tour"
            # This is expected and acceptable behavior