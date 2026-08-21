"""Tour management and assignment for KGLW concerts."""

import re
from datetime import datetime
from typing import Dict, Any, Optional, List
from .tour_scraper import tour_scraper


class TourManager:
    """Manages tour information and assignment."""
    
    def __init__(self):
        # Tour definitions based on date ranges and locations
        self.tour_definitions = {
            # 2025 Tours
            "2025 Europe Residency Tour": {
                "years": [2025],
                "date_ranges": [("2025-05-18", "2025-06-10")],
                "locations": ["europe", "portugal", "spain", "france", "germany", "netherlands", "belgium",
                            "uk", "england", "italy", "lisbon", "madrid", "barcelona", "paris", "berlin", 
                            "amsterdam", "london", "manchester", "rome", "milan", "porto", "athens"]
            },
            "2025 Ill Times Australia": {
                "years": [2025],
                "date_ranges": [("2025-04-04", "2025-04-12")],
                "locations": ["australia", "melbourne", "sydney", "brisbane", "fremantle", "walyalup", 
                            "naarm", "eora", "meanjin", "freo.social", "crowbar", "corner hotel", "howler"]
            },
            "2025 Phantom Island - USA": {
                "years": [2025],
                "date_ranges": [("2025-07-28", "2025-08-17")],
                "locations": ["usa", "united states", "america", "colorado", "maryland", "virginia", 
                            "california", "oregon", "washington", "buena vista", "colorado springs", 
                            "columbia", "meadow creek", "ford amphitheater", "merriweather"]
            },
            
            # 2024 Tours
            "2024 USA_Canada - Summer": {
                "years": [2024],
                "date_ranges": [("2024-08-15", "2024-09-14")],
                "locations": ["usa", "canada", "united states", "austin", "chicago", "new york", 
                            "los angeles", "san francisco", "seattle", "denver", "boston", "philadelphia",
                            "washington", "atlanta", "miami", "detroit", "toronto", "montreal", "vancouver"]
            },
            
            # 2023 Tours  
            "2023 USA Residency Tour": {
                "years": [2023],
                "date_ranges": [("2023-10-01", "2023-12-31")],
                "locations": ["usa", "united states", "los angeles", "san francisco", "chicago", 
                            "new york", "boston", "philadelphia", "washington", "austin"]
            },
            "2023 Europe-UK Summer": {
                "years": [2023],
                "date_ranges": [("2023-06-01", "2023-09-30")],
                "locations": ["uk", "england", "france", "germany", "netherlands", "belgium",
                            "london", "manchester", "bristol", "paris", "berlin", "amsterdam"]
            },
            
            # 2022 Tours
            "2022 World Tour Spring-Summer": {
                "years": [2022],
                "date_ranges": [("2022-03-01", "2022-08-31")],
                "locations": ["usa", "europe", "uk", "australia", "new zealand"]
            },
            "2022 World Tour Fall": {
                "years": [2022],
                "date_ranges": [("2022-09-30", "2022-11-02")],
                "locations": ["usa", "canada", "australia", "portland", "seattle", "san francisco", "los angeles"]
            },
            
            # 2019 Tours
            "2019 World Tour": {
                "years": [2019],
                "date_ranges": [("2019-01-01", "2019-12-31")],
                "locations": []  # Any location in 2019
            },
            
            # 2018 Tours
            "2018 Mexico": {
                "years": [2018],
                "date_ranges": [("2018-01-01", "2018-12-31")],
                "locations": ["mexico", "mexico city", "guadalajara", "tijuana"]
            },
            
            # 2017 Tours
            "2017 Australia - Winter": {
                "years": [2017],
                "date_ranges": [("2017-06-01", "2017-09-30")],
                "locations": ["australia", "melbourne", "sydney", "brisbane", "perth", "adelaide"]
            },
            
            # 2015 Tours
            "2015 Europe_UK - Summer": {
                "years": [2015],
                "date_ranges": [("2015-06-01", "2015-09-30")],
                "locations": ["uk", "europe", "england", "france", "germany"]
            },
            
            # 2014 Tours
            "2014 I'm In Your Mind Fuzz - Europe": {
                "years": [2014],
                "date_ranges": [("2014-01-01", "2014-12-31")],
                "locations": ["uk", "europe", "england", "france", "germany", "netherlands"]
            },
            
            # Special Tours
            "Princess Theatre Residency": {
                "years": [2021, 2022],
                "date_ranges": [("2021-01-01", "2022-12-31")],
                "locations": ["melbourne", "princess theatre", "australia"]
            },
            "Goat Co-Headlining Australian Tour": {
                "years": [2016, 2017],
                "date_ranges": [("2016-01-01", "2017-12-31")],
                "locations": ["australia", "goat"]
            }
        }
    
    def assign_tour(self, show_info: Dict[str, Any]) -> str:
        """Assign a show to the appropriate tour using web-scraped data first."""
        date = show_info.get('date', '')
        location = show_info.get('location', '').lower()
        venue = show_info.get('venue', '').lower()
        
        if not date:
            return f"{datetime.now().year} Not Part of a Tour"
        
        try:
            show_date = datetime.strptime(date, '%Y-%m-%d')
            year = show_date.year
        except ValueError:
            return f"{datetime.now().year} Not Part of a Tour"
        
        # Try web-scraped tour data first (more accurate)
        scraped_tour = tour_scraper.get_tour_for_date(date)
        if scraped_tour and scraped_tour != "Not Part of a Tour":
            return scraped_tour
        
        # Check each tour definition
        best_match = None
        best_score = 0
        
        for tour_name, tour_info in self.tour_definitions.items():
            score = self._calculate_tour_match_score(
                show_date, location, venue, tour_info
            )
            
            if score > best_score:
                best_score = score
                best_match = tour_name
        
        # If no good match found, assign to year-based category
        if best_match is None or best_score < 50:
            return f"{year} Not Part of a Tour"
        
        return best_match
    
    def _calculate_tour_match_score(self, show_date: datetime, location: str, 
                                   venue: str, tour_info: Dict[str, Any]) -> int:
        """Calculate how well a show matches a tour definition."""
        score = 0
        
        # Year match (mandatory)
        if show_date.year not in tour_info.get('years', []):
            return 0
        
        score += 100  # Base score for year match
        
        # Date range match
        date_str = show_date.strftime('%Y-%m-%d')
        for start_date, end_date in tour_info.get('date_ranges', []):
            if start_date <= date_str <= end_date:
                score += 200  # Strong bonus for date range match
                break
        
        # Location match
        tour_locations = tour_info.get('locations', [])
        if not tour_locations:  # If no specific locations, any location matches
            score += 100
        else:
            location_text = f"{location} {venue}".lower()
            for tour_location in tour_locations:
                if tour_location.lower() in location_text:
                    score += 150  # Bonus for location match
                    break
        
        return score
    
    def get_tour_info(self, tour_name: str) -> Dict[str, Any]:
        """Get information about a specific tour."""
        return self.tour_definitions.get(tour_name, {})
    
    def list_tours(self) -> List[str]:
        """Get list of all defined tours."""
        return list(self.tour_definitions.keys())
    
    def get_tours_for_year(self, year: int) -> List[str]:
        """Get tours that occurred in a specific year."""
        matching_tours = []
        for tour_name, tour_info in self.tour_definitions.items():
            if year in tour_info.get('years', []):
                matching_tours.append(tour_name)
        
        return matching_tours
    
    def normalize_tour_name_for_filesystem(self, tour_name: str) -> str:
        r"""Normalize tour name for safe filesystem usage.
        
        Removes or replaces characters that could cause filesystem issues:
        - Forward slashes (/) → dashes (-)
        - Backslashes (\) → dashes (-)
        - Colons (:) → dashes (-)
        - Pipes (|) → dashes (-)
        - Question marks (?) → removed
        - Asterisks (*) → removed
        - Angle brackets (<>) → removed
        - Double quotes (") → single quotes (')
        
        Args:
            tour_name: Original tour name
            
        Returns:
            Filesystem-safe tour name
        """
        if not tour_name:
            return tour_name
        
        # Replace problematic characters with dashes
        normalized = tour_name.replace('/', '-').replace('\\', '-')
        normalized = normalized.replace(':', '-').replace('|', '-')
        
        # Remove characters that are always problematic
        normalized = normalized.replace('?', '').replace('*', '')
        normalized = normalized.replace('<', '').replace('>', '')
        normalized = normalized.replace('"', "'")
        
        # Clean up multiple consecutive dashes
        while '--' in normalized:
            normalized = normalized.replace('--', '-')
        
        # Remove leading/trailing dashes and whitespace
        normalized = normalized.strip(' -')
        
        return normalized