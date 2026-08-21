"""Filesystem utilities for consistent normalization and naming conventions."""

import re
from pathlib import Path
from typing import Dict, Any


def normalize_for_filesystem(name: str) -> str:
    """Normalize any name for safe filesystem usage.
    
    This is the master normalization function that should be used everywhere
    to ensure consistency.
    
    Removes or replaces characters that could cause filesystem issues:
    - Forward slashes (/) → dashes (-)
    - Backslashes (\) → dashes (-)
    - Colons (:) → dashes (-)
    - Pipes (|) → dashes (-)
    - Question marks (?) → removed
    - Asterisks (*) → removed
    - Angle brackets (<>) -> removed
    - Double quotes (") → single quotes (')
    
    Args:
        name: Original name
        
    Returns:
        Filesystem-safe name
    """
    if not name:
        return name
    
    # Replace problematic characters with dashes
    normalized = name.replace('/', '-').replace('\\', '-')
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


def generate_plex_friendly_filename(show_info: Dict[str, Any], file_type: str = "concert") -> str:
    """Generate Plex-friendly filename without redundant artist names.
    
    Format: "YYYY-MM-DD - Location (Venue).ext"
    This matches the directory naming for better Plex recognition.
    
    Args:
        show_info: Show information dictionary with date, location, venue
        file_type: Type of file (concert, etc.)
        
    Returns:
        Plex-friendly filename without artist redundancy
    """
    date = show_info.get('date', '')
    location = show_info.get('location', '')
    venue = show_info.get('venue', '')
    
    # Build filename to match directory structure
    filename_parts = []
    
    if date:
        filename_parts.append(date)
    
    if location:
        if venue:
            filename_parts.append(f"{location} ({venue})")
        else:
            filename_parts.append(location)
    
    filename = " - ".join(filename_parts)
    
    # Normalize for filesystem safety
    filename = normalize_for_filesystem(filename)
    
    return filename


def generate_directory_name(show_info: Dict[str, Any]) -> str:
    """Generate consistent directory name for shows.
    
    Format: "YYYY-MM-DD - Location (Venue)"
    
    Args:
        show_info: Show information dictionary
        
    Returns:
        Directory name
    """
    date = show_info.get('date', '')
    location = show_info.get('location', '')  
    venue = show_info.get('venue', '')
    
    # Build directory name
    name_parts = []
    
    if date:
        name_parts.append(date)
    
    if location:
        if venue:
            name_parts.append(f"{location} ({venue})")
        else:
            name_parts.append(location)
    
    directory_name = " - ".join(name_parts)
    
    # Normalize for filesystem safety
    directory_name = normalize_for_filesystem(directory_name)
    
    return directory_name


def needs_normalization(name: str) -> bool:
    """Check if a name needs filesystem normalization.
    
    Args:
        name: Name to check
        
    Returns:
        True if normalization is needed
    """
    if not name:
        return False
    
    # Check for problematic characters
    problematic_chars = ['/', '\\', ':', '|', '?', '*', '<', '>', '"']
    
    for char in problematic_chars:
        if char in name:
            return True
    
    # Check for multiple consecutive dashes
    if '--' in name:
        return True
    
    # Check for leading/trailing dashes or whitespace
    if name != name.strip(' -'):
        return True
    
    return False


def is_redundant_filename(filename: str, directory_name: str) -> bool:
    """Check if a filename has redundant artist information.
    
    Args:
        filename: Filename to check
        directory_name: Parent directory name
        
    Returns:
        True if filename has redundant information
    """
    if not filename or not directory_name:
        return False
    
    # Remove extensions for comparison
    filename_base = Path(filename).stem
    
    # Check if filename starts with "King Gizzard" variants
    artist_patterns = [
        r'^King Gizzard.*?-.*?',
        r'^KGLW.*?-.*?', 
        r'^KG.*?-.*?'
    ]
    
    for pattern in artist_patterns:
        if re.match(pattern, filename_base, re.IGNORECASE):
            return True
    
    return False


def extract_show_info_from_directory_name(directory_name: str) -> Dict[str, Any]:
    """Extract show information from directory name.
    
    Supports formats like:
    - "2024-05-20 - Berlin (Columbiahalle)"  
    - "2024-05-20 Berlin (Columbiahalle)"
    - "2024-05-20 - Berlin"
    
    Args:
        directory_name: Directory name to parse
        
    Returns:
        Dictionary with extracted show information
    """
    show_info = {}
    
    # Try to extract date (YYYY-MM-DD format)
    date_match = re.match(r'^(\d{4}-\d{2}-\d{2})', directory_name)
    if date_match:
        show_info['date'] = date_match.group(1)
        
        # Extract location and venue from the rest
        remaining = directory_name[len(date_match.group(1)):].strip(' -')
        
        # Look for venue in parentheses
        venue_match = re.search(r'^(.+?)\s*\((.+?)\)$', remaining)
        if venue_match:
            show_info['location'] = venue_match.group(1).strip()
            show_info['venue'] = venue_match.group(2).strip()
        elif remaining:
            show_info['location'] = remaining.strip()
    
    return show_info