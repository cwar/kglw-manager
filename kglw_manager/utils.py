"""Utility functions for KGLW Manager."""

import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Set up logging configuration."""
    logger = logging.getLogger('kglw_manager')
    logger.setLevel(level)
    
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


def clean_filename(filename: str) -> str:
    """Clean filename for filesystem compatibility."""
    # Replace problematic characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Replace multiple spaces with single space
    filename = re.sub(r'\s+', ' ', filename)
    # Remove leading/trailing whitespace and dots
    filename = filename.strip('. ')
    return filename


def parse_date_from_filename(filename: str) -> Optional[str]:
    """Extract date in YYYY-MM-DD format from filename."""
    # Look for date patterns
    patterns = [
        r'(\d{4}-\d{2}-\d{2})',  # 2024-11-15
        r'(\d{2}-\d{2}-\d{4})',  # 11-15-2024
        r'(\d{4}\.\d{2}\.\d{2})', # 2024.11.15
        r'(\d{2}\.\d{2}\.\d{4})', # 11.15.2024
    ]
    
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            date_str = match.group(1)
            # Convert to standard format
            if re.match(r'\d{2}-\d{2}-\d{4}', date_str):
                # MM-DD-YYYY -> YYYY-MM-DD
                parts = date_str.split('-')
                return f"{parts[2]}-{parts[0]}-{parts[1]}"
            elif re.match(r'\d{4}\.\d{2}\.\d{2}', date_str):
                # 2024.11.15 -> 2024-11-15
                return date_str.replace('.', '-')
            elif re.match(r'\d{2}\.\d{2}\.\d{4}', date_str):
                # 11.15.2024 -> 2024-11-15
                parts = date_str.split('.')
                return f"{parts[2]}-{parts[0]}-{parts[1]}"
            else:
                return date_str
    
    return None


def format_duration(seconds: int) -> str:
    """Format duration in seconds to human-readable string."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    
    if hours > 0:
        return f"{hours}h {minutes}min"
    else:
        return f"{minutes}min"


def format_file_size(size_bytes: int) -> str:
    """Format file size in bytes to human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def is_video_file(file_path: Path) -> bool:
    """Check if file is a video file based on extension."""
    video_extensions = {
        '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v',
        '.mpg', '.mpeg', '.3gp', '.f4v', '.asf', '.rm', '.rmvb'
    }
    return file_path.suffix.lower() in video_extensions


def extract_location_from_path(path: Path) -> Optional[str]:
    """Extract location from directory path."""
    # Look for patterns like "YYYY-MM-DD - Location"
    match = re.search(r'\d{4}-\d{2}-\d{2}\s*-\s*(.+?)(?:\s*\([^)]+\))?$', path.name)
    if match:
        return match.group(1).strip()
    
    return None


def normalize_location(location: str) -> str:
    """Normalize location string for comparison."""
    # Remove common suffixes and normalize
    location = re.sub(r'\s*\([^)]+\)$', '', location)  # Remove (venue)
    location = re.sub(r'\s*,\s*[A-Z]{2}$', '', location)  # Remove state codes
    location = location.strip().title()
    return location