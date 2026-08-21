"""
Comprehensive tests for utility functions and helper methods.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from kglw_manager.utils import (
    format_duration, format_file_size, clean_filename,
    parse_date_from_filename, is_video_file, extract_location_from_path, 
    normalize_location
)


class TestDurationFormatting:
    """Test duration formatting utilities."""
    
    @pytest.mark.unit
    def test_format_duration_basic_cases(self):
        """Test basic duration formatting."""
        test_cases = [
            (0, "0min"),
            (30, "0min"),  # Less than a minute
            (60, "1min"),
            (90, "1min"),  # 1.5 minutes rounds to 1min  
            (120, "2min"),
            (3600, "1h 0min"),
            (3660, "1h 1min"),  # 61 minutes
            (3720, "1h 2min"),
            (7200, "2h 0min"),
            (7380, "2h 3min"),  # 123 minutes
            (10800, "3h 0min"),
        ]
        
        for seconds, expected in test_cases:
            result = format_duration(seconds)
            assert result == expected, f"format_duration({seconds}) returned '{result}', expected '{expected}'"
    
    @pytest.mark.unit
    def test_format_duration_edge_cases(self):
        """Test duration formatting edge cases."""
        # Very large values
        large_duration = 24 * 3600  # 24 hours
        result = format_duration(large_duration)
        assert "24h 0min" == result
        
        # Fractional minutes are rounded down
        result = format_duration(119)  # 1 minute 59 seconds
        assert result == "1min"
    
    @pytest.mark.unit
    def test_format_duration_type_safety(self):
        """Test duration formatting type safety."""
        # Should handle int values
        assert format_duration(60) == "1min"
        
        # Test float values (should work but format differently)
        assert format_duration(60.0) == "1.0min"


class TestFileSizeFormatting:
    """Test file size formatting utilities."""
    
    @pytest.mark.unit
    def test_format_file_size_basic_units(self):
        """Test file size formatting with different units."""
        test_cases = [
            (0, "0.0 B"),
            (512, "512.0 B"),
            (1024, "1.0 KB"),
            (1536, "1.5 KB"),  # 1.5 KB
            (1024**2, "1.0 MB"),
            (1024**3, "1.0 GB"),
            (1024**4, "1.0 TB"),
            (1024**5, "1.0 PB"),
        ]
        
        for bytes_size, expected in test_cases:
            result = format_file_size(bytes_size)
            assert result == expected, f"format_file_size({bytes_size}) returned '{result}', expected '{expected}'"
    
    @pytest.mark.unit
    def test_format_file_size_precision(self):
        """Test file size formatting precision."""
        # Test that precision is reasonable
        result = format_file_size(1234567)  # ~1.18 MB
        assert "MB" in result
        assert "1." in result  # Should have decimal
        
        # Very large file
        huge_size = 15 * 1024 * 1024 * 1024  # 15 GB
        result = format_file_size(huge_size)
        assert "GB" in result
        assert "15" in result


class TestFilenameUtils:
    """Test filename utility functions."""
    
    @pytest.mark.unit
    def test_clean_filename_special_characters(self):
        """Test filename cleaning with special characters."""
        test_cases = [
            ("normal_filename.txt", "normal_filename.txt"),
            ("file with spaces.txt", "file with spaces.txt"),  # Spaces usually OK
            ("file/with/slashes.txt", "filewithslashes.txt"),  # Remove slashes
            ("file\\with\\backslashes.txt", "filewithbackslashes.txt"),
            ("file:with:colons.txt", "filewithcolons.txt"),
            ("file*with*asterisks.txt", "filewithastersks.txt"),
            ("file?with?questions.txt", "filewithquestions.txt"),
            ("file<with>brackets.txt", "filewithbrackets.txt"),
            ("file|with|pipes.txt", "filewithpipes.txt"),
            ('file"with"quotes.txt', "filewithquotes.txt"),
        ]
        
        for input_name, expected_pattern in test_cases:
            result = clean_filename(input_name)
            
            # Should not contain problematic characters
            problematic_chars = ['/', '\\', ':', '*', '?', '<', '>', '|', '"']
            for char in problematic_chars:
                assert char not in result, f"Found problematic char '{char}' in cleaned filename: {result}"
            
            # Should be a reasonable transformation
            assert len(result) > 0
            assert isinstance(result, str)
    
    @pytest.mark.unit
    def test_clean_filename_unicode(self):
        """Test filename cleaning with Unicode characters."""
        unicode_filenames = [
            "café.txt",
            "São Paulo.txt", 
            "naïve.txt",
        ]
        
        for filename in unicode_filenames:
            result = clean_filename(filename)
            
            # Should handle Unicode gracefully
            assert isinstance(result, str)
            assert len(result) > 0
    
    @pytest.mark.unit
    def test_clean_filename_whitespace_handling(self):
        """Test filename whitespace handling."""
        test_cases = [
            ("  leading_spaces.txt", "leading_spaces.txt"),
            ("trailing_spaces.txt  ", "trailing_spaces.txt"),
            ("  both_spaces.txt  ", "both_spaces.txt"),
            ("multiple   spaces.txt", "multiple spaces.txt"),  # Collapse multiple spaces
            ("...dots.txt...", "dots.txt"),  # Remove leading/trailing dots
        ]
        
        for input_name, expected in test_cases:
            result = clean_filename(input_name)
            assert result == expected, f"clean_filename('{input_name}') returned '{result}', expected '{expected}'"


class TestDateParsing:
    """Test date parsing utilities."""
    
    @pytest.mark.unit
    def test_parse_date_from_filename_standard_formats(self):
        """Test parsing standard date formats from filenames."""
        test_cases = [
            ("2024-11-15 Austin Show.mp4", "2024-11-15"),
            ("King Gizzard 2024-11-15.mp4", "2024-11-15"),
            ("11-15-2024 Concert.mp4", "2024-11-15"),  # Convert MM-DD-YYYY
            ("2024.11.15 Show.mp4", "2024-11-15"),  # Convert dots
            ("11.15.2024 Concert.mp4", "2024-11-15"),  # Convert dots MM.DD.YYYY
            ("Show without date.mp4", None),  # No date found
        ]
        
        for filename, expected in test_cases:
            result = parse_date_from_filename(filename)
            assert result == expected, f"parse_date_from_filename('{filename}') returned '{result}', expected '{expected}'"
    
    @pytest.mark.unit
    def test_parse_date_from_filename_edge_cases(self):
        """Test date parsing edge cases."""
        edge_cases = [
            ("", None),  # Empty string
            ("1234-56-78", "1234-56-78"),  # Invalid date but matches pattern
            ("2024-2-5", None),  # Single digit month/day doesn't match pattern
            ("2024-02-05 and 2024-03-15", "2024-02-05"),  # Multiple dates, returns first
        ]
        
        for filename, expected in edge_cases:
            result = parse_date_from_filename(filename)
            assert result == expected, f"parse_date_from_filename('{filename}') returned '{result}', expected '{expected}'"


class TestVideoFileUtils:
    """Test video file utilities."""
    
    @pytest.mark.unit
    def test_is_video_file_extensions(self):
        """Test video file extension detection."""
        video_files = [
            "concert.mp4", "show.mkv", "video.avi", "movie.mov",
            "clip.wmv", "stream.flv", "web.webm", "mobile.m4v",
            "old.mpg", "classic.mpeg", "phone.3gp"
        ]
        
        for filename in video_files:
            path = Path(filename)
            assert is_video_file(path) is True, f"Expected {filename} to be detected as video file"
    
    @pytest.mark.unit
    def test_is_video_file_non_videos(self):
        """Test non-video file detection."""
        non_video_files = [
            "audio.mp3", "image.jpg", "document.txt", "data.json",
            "info.xml", "readme.md", "script.py", "style.css"
        ]
        
        for filename in non_video_files:
            path = Path(filename)
            assert is_video_file(path) is False, f"Expected {filename} to NOT be detected as video file"
    
    @pytest.mark.unit
    def test_is_video_file_case_insensitive(self):
        """Test case-insensitive video file detection."""
        test_cases = [
            "VIDEO.MP4", "Show.MKV", "concert.Avi", "MOVIE.MOV"
        ]
        
        for filename in test_cases:
            path = Path(filename)
            assert is_video_file(path) is True, f"Expected {filename} to be detected as video file (case insensitive)"


class TestLocationUtils:
    """Test location extraction and normalization utilities."""
    
    @pytest.mark.unit
    def test_extract_location_from_path_standard_format(self):
        """Test location extraction from standard path formats."""
        test_cases = [
            (Path("2024-11-15 - Austin"), "Austin"),
            (Path("2024-11-15 - Austin (Moody Center)"), "Austin"),  # Venue in parentheses
            (Path("2024-11-15 - New York"), "New York"),
            (Path("2024-11-15 - São Paulo"), "São Paulo"),  # Unicode
            (Path("invalid-path-format"), None),  # No date pattern
            (Path("2024-11-15"), None),  # Date but no location
        ]
        
        for path, expected in test_cases:
            result = extract_location_from_path(path)
            assert result == expected, f"extract_location_from_path('{path}') returned '{result}', expected '{expected}'"
    
    @pytest.mark.unit
    def test_extract_location_complex_names(self):
        """Test location extraction with complex location names."""
        complex_cases = [
            (Path("2024-11-15 - Los Angeles"), "Los Angeles"),
            (Path("2024-11-15 - Mexico City"), "Mexico City"),
            (Path("2024-11-15 - New York (Madison Square Garden)"), "New York"),
            (Path("2024-11-15 - Austin (The Moody Center)"), "Austin"),
        ]
        
        for path, expected in complex_cases:
            result = extract_location_from_path(path)
            assert result == expected
    
    @pytest.mark.unit
    def test_normalize_location_basic_cases(self):
        """Test basic location normalization."""
        test_cases = [
            ("austin", "Austin"),
            ("new york", "New York"),
            ("Austin, TX", "Austin"),  # Remove state code
            ("Austin (Venue Name)", "Austin"),  # Remove venue in parentheses
            ("los angeles", "Los Angeles"),
            ("CHICAGO", "Chicago"),
        ]
        
        for input_location, expected in test_cases:
            result = normalize_location(input_location)
            assert result == expected, f"normalize_location('{input_location}') returned '{result}', expected '{expected}'"
    
    @pytest.mark.unit
    def test_normalize_location_edge_cases(self):
        """Test location normalization edge cases."""
        edge_cases = [
            ("", ""),  # Empty string
            ("  austin  ", "Austin"),  # Extra whitespace
            ("Austin (Multiple) (Venues)", "Austin (Multiple)"),  # Multiple parentheses - only removes last
            ("São Paulo", "São Paulo"),  # Unicode preservation
        ]
        
        for input_location, expected in edge_cases:
            result = normalize_location(input_location)
            assert result == expected


class TestUtilityIntegration:
    """Test integration between utility functions."""
    
    @pytest.mark.unit
    def test_filename_and_date_parsing_integration(self):
        """Test integration between filename cleaning and date parsing."""
        dirty_filename_with_date = "King Gizzard/2024-11-15\\Austin<Show>.mp4"
        
        # Clean the filename first
        clean_name = clean_filename(dirty_filename_with_date)
        
        # Then parse date from the clean filename
        parsed_date = parse_date_from_filename(clean_name)
        
        assert parsed_date == "2024-11-15"
        assert "/" not in clean_name
        assert "\\" not in clean_name
        assert "<" not in clean_name
        assert ">" not in clean_name
    
    @pytest.mark.unit
    def test_location_extraction_and_normalization_integration(self):
        """Test integration between location extraction and normalization."""
        path_with_location = Path("2024-11-15 - austin, tx (venue)")
        
        # Extract location
        extracted = extract_location_from_path(path_with_location)
        
        # Normalize the extracted location
        if extracted:
            normalized = normalize_location(extracted)
            # The actual behavior: title case but keeps state abbreviation
            assert normalized == "Austin, Tx"  # Should be title case
    
    @pytest.mark.unit
    def test_comprehensive_file_processing(self):
        """Test comprehensive file processing workflow."""
        # Simulate processing a messy filename
        original_filename = "King Gizzard & The Lizard Wizard/2024-11-15\\Austin<Concert>.mp4"
        
        # Step 1: Clean filename
        clean_name = clean_filename(original_filename)
        assert "/" not in clean_name
        assert "\\" not in clean_name
        
        # Step 2: Verify it's a video file
        is_video = is_video_file(Path(clean_name))
        assert is_video is True
        
        # Step 3: Parse date from cleaned filename
        date = parse_date_from_filename(clean_name)
        assert date == "2024-11-15"
        
        # Step 4: Check if we can extract location info
        # (This would be from directory path in real usage)
        test_path = Path("2024-11-15 - Austin")
        location = extract_location_from_path(test_path)
        assert location == "Austin"
        
        # Step 5: Normalize location
        if location:
            normalized_location = normalize_location(location)
            assert normalized_location == "Austin"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])