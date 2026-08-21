"""Naming conventions and filename handling for KGLW Manager."""

import re
from pathlib import Path
from typing import Dict, Any, Optional
from .utils import clean_filename


class NamingManager:
    """Handles naming conventions for KGLW concert files."""
    
    def __init__(self):
        self.artist_name = "King Gizzard & The Lizard Wizard"
    
    def generate_plex_filename(self, show_info: Dict[str, Any],
                              file_extension: str = ".mp4",
                              song_name: Optional[str] = None) -> str:
        """Generate Plex-compatible filename.

        Format: "Date - Location (Venue) - concert.ext"
        Note: Artist name is NOT included since this is a dedicated King Gizzard library.
        Including the artist name causes Plex to incorrectly group shows together.
        """
        date = show_info.get('date', '')
        location = show_info.get('location', '')
        venue = show_info.get('venue', '')

        # Create base filename without artist name
        # Format: "Date - Location (Venue) - concert"
        filename_parts = []

        if date and location:
            # Check if location already starts with date
            if location.startswith(date):
                filename_parts.append(location)
            else:
                filename_parts.append(f"{date} - {location}")
        elif date:
            filename_parts.append(date)
        elif location:
            filename_parts.append(location)

        # Add venue in parentheses if different from location
        if venue and venue != location and venue not in location:
            filename_parts[-1] += f" ({venue})"

        # Add concert or song name suffix
        if song_name:
            # Clean song name for filename
            clean_song_name = "".join(c for c in song_name if c.isalnum() or c in (' ', '-', '_', "'")).strip()
            filename_parts.append(f"({clean_song_name})")
        else:
            filename_parts.append("concert")

        # Join with " - " and clean
        filename = " - ".join(filename_parts) + file_extension
        return clean_filename(filename)
    
    
    def is_plex_named(self, filename: str) -> bool:
        """Check if filename follows Plex naming convention.

        Matches both old format (with artist name) and new format (without).
        New format: "Date - Location - concert.ext"
        Old format: "King Gizzard... - Date Location - concert.ext"
        """
        # New format: Date at start
        new_pattern = r'^\d{4}-\d{2}-\d{2}.*?-.*?concert\.\w+$'
        if re.match(new_pattern, filename, re.IGNORECASE):
            return True

        # Old format: Artist name at start
        old_pattern = r'^King Gizzard.*?-.*?concert\.\w+$'
        return bool(re.match(old_pattern, filename, re.IGNORECASE))
    
    def parse_show_info_from_filename(self, filename: str) -> Dict[str, Any]:
        """Extract show information from filename."""
        show_info = {
            'date': '',
            'location': '',
            'venue': ''
        }
        
        # Handle None or invalid input
        if not filename:
            return show_info
        
        try:
            # Remove extension and artist name
            base_name = Path(filename).stem
        except (TypeError, ValueError):
            return show_info
        if base_name.lower().startswith('king gizzard'):
            base_name = re.sub(r'^king gizzard.*?-\s*', '', base_name, flags=re.IGNORECASE)
        
        # Look for date pattern
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', base_name)
        if date_match:
            show_info['date'] = date_match.group(1)
            # Remove date from remaining text
            base_name = base_name.replace(date_match.group(1), '').strip(' -')
        
        # Extract location and venue
        location_part = base_name
        
        # Remove " - concert" suffix if present
        if ' - concert' in base_name.lower():
            location_part = base_name[:base_name.lower().find(' - concert')].strip()
        
        # Check for venue in parentheses
        venue_match = re.search(r'(.+?)\s*\(([^)]+)\)$', location_part)
        if venue_match:
            show_info['location'] = venue_match.group(1).strip()
            show_info['venue'] = venue_match.group(2).strip()
        else:
            show_info['location'] = location_part.strip()
        
        return show_info
    
    def generate_directory_name(self, show_info: Dict[str, Any]) -> str:
        """Generate directory name for a show."""
        date = show_info.get('date', '')
        location = show_info.get('location', '')
        venue = show_info.get('venue', '')

        if date and location:
            dir_name = f"{date} - {location}"
            if venue and venue != location and venue not in location:
                dir_name += f" ({venue})"
        elif date:
            dir_name = date
        elif location:
            dir_name = location
        else:
            dir_name = "Unknown Show"

        return clean_filename(dir_name)

    def generate_kometa_directory_name(self, show_info: Dict[str, Any]) -> str:
        """Generate Kometa-compatible directory name for a show.

        Format: YYYY-MM-DD - Location (Venue)
        Returns empty string if required fields are missing.
        """
        date = show_info.get('date', '')
        location = show_info.get('location', '')
        venue = show_info.get('venue', '')

        # Both date and location are required for Kometa
        if not date or not location:
            return ""

        dir_name = f"{date} - {location}"
        if venue and venue != location and venue not in location:
            dir_name += f" ({venue})"

        return dir_name
    
    def is_duplicate_date_in_location(self, location: str, date: str) -> bool:
        """Check if location already contains the date."""
        if not date or not location:
            return False
        
        # Check if date appears at the start of location
        return location.strip().startswith(date)