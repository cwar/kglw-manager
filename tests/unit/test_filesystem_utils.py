"""Tests for filesystem utilities module."""

import pytest
from pathlib import Path

from kglw_manager.filesystem_utils import (
    normalize_for_filesystem,
    generate_plex_friendly_filename,
    generate_directory_name,
    needs_normalization,
    is_redundant_filename,
    extract_show_info_from_directory_name
)


@pytest.mark.unit
class TestNormalizeForFilesystem:
    """Test filesystem normalization."""

    def test_normalize_forward_slash(self):
        """Test forward slash replacement."""
        result = normalize_for_filesystem("AC/DC Concert")
        assert "/" not in result
        assert result == "AC-DC Concert"

    def test_normalize_backslash(self):
        """Test backslash replacement."""
        result = normalize_for_filesystem("Path\\To\\File")
        assert "\\" not in result
        assert result == "Path-To-File"

    def test_normalize_colon(self):
        """Test colon replacement."""
        result = normalize_for_filesystem("Show: Live")
        assert ":" not in result
        assert result == "Show- Live"

    def test_normalize_question_mark(self):
        """Test question mark removal."""
        result = normalize_for_filesystem("Who? What?")
        assert "?" not in result
        assert result == "Who What"

    def test_normalize_asterisk(self):
        """Test asterisk removal."""
        result = normalize_for_filesystem("Best * Show")
        assert "*" not in result
        assert result == "Best  Show"

    def test_normalize_angle_brackets(self):
        """Test angle bracket removal."""
        result = normalize_for_filesystem("<Live> <Show>")
        assert "<" not in result
        assert ">" not in result
        assert result == "Live Show"

    def test_normalize_double_quotes(self):
        """Test double quote replacement."""
        result = normalize_for_filesystem('The "Best" Show')
        assert '"' not in result
        assert result == "The 'Best' Show"

    def test_normalize_multiple_dashes(self):
        """Test multiple consecutive dashes cleanup."""
        result = normalize_for_filesystem("Show---Live")
        assert "---" not in result
        assert result == "Show-Live"

    def test_normalize_leading_trailing_dashes(self):
        """Test leading/trailing dash removal."""
        result = normalize_for_filesystem("- Show -")
        assert result == "Show"

    def test_normalize_empty_string(self):
        """Test empty string handling."""
        result = normalize_for_filesystem("")
        assert result == ""

    def test_normalize_none(self):
        """Test None handling."""
        result = normalize_for_filesystem(None)
        assert result is None

    def test_normalize_complex_case(self):
        """Test complex case with multiple problematic characters."""
        result = normalize_for_filesystem("AC/DC: Live <2024> \"Tour\"?")
        assert result == "AC-DC- Live 2024 'Tour'"


@pytest.mark.unit
class TestGeneratePlexFriendlyFilename:
    """Test Plex-friendly filename generation."""

    def test_generate_with_full_info(self):
        """Test filename with complete show information."""
        show_info = {
            'date': '2024-05-20',
            'location': 'Berlin',
            'venue': 'Columbiahalle'
        }
        result = generate_plex_friendly_filename(show_info)
        assert result == "2024-05-20 - Berlin (Columbiahalle)"

    def test_generate_with_date_and_location_only(self):
        """Test filename with date and location only."""
        show_info = {
            'date': '2024-05-20',
            'location': 'Berlin'
        }
        result = generate_plex_friendly_filename(show_info)
        assert result == "2024-05-20 - Berlin"

    def test_generate_with_date_only(self):
        """Test filename with date only."""
        show_info = {
            'date': '2024-05-20'
        }
        result = generate_plex_friendly_filename(show_info)
        assert result == "2024-05-20"

    def test_generate_with_empty_info(self):
        """Test filename with empty show information."""
        show_info = {}
        result = generate_plex_friendly_filename(show_info)
        assert result == ""

    def test_generate_normalizes_problematic_characters(self):
        """Test that problematic characters are normalized."""
        show_info = {
            'date': '2024-05-20',
            'location': 'São Paulo',
            'venue': 'Club: Live'
        }
        result = generate_plex_friendly_filename(show_info)
        assert ":" not in result
        assert "São Paulo (Club- Live)" in result


@pytest.mark.unit
class TestGenerateDirectoryName:
    """Test directory name generation."""

    def test_directory_with_full_info(self):
        """Test directory name with complete information."""
        show_info = {
            'date': '2024-05-20',
            'location': 'Berlin',
            'venue': 'Columbiahalle'
        }
        result = generate_directory_name(show_info)
        assert result == "2024-05-20 - Berlin (Columbiahalle)"

    def test_directory_with_partial_info(self):
        """Test directory name with partial information."""
        show_info = {
            'date': '2024-05-20',
            'location': 'Berlin'
        }
        result = generate_directory_name(show_info)
        assert result == "2024-05-20 - Berlin"

    def test_directory_normalizes_characters(self):
        """Test that directory names are normalized."""
        show_info = {
            'date': '2024-05-20',
            'location': 'New York',
            'venue': 'Madison/Square'
        }
        result = generate_directory_name(show_info)
        assert "/" not in result
        assert "Madison-Square" in result


@pytest.mark.unit
class TestNeedsNormalization:
    """Test normalization necessity detection."""

    def test_needs_normalization_with_slash(self):
        """Test detection of forward slash."""
        assert needs_normalization("AC/DC") is True

    def test_needs_normalization_with_backslash(self):
        """Test detection of backslash."""
        assert needs_normalization("Path\\File") is True

    def test_needs_normalization_with_colon(self):
        """Test detection of colon."""
        assert needs_normalization("Live: Show") is True

    def test_needs_normalization_with_question_mark(self):
        """Test detection of question mark."""
        assert needs_normalization("Who?") is True

    def test_needs_normalization_with_multiple_dashes(self):
        """Test detection of multiple consecutive dashes."""
        assert needs_normalization("Show--Live") is True

    def test_needs_normalization_with_leading_dash(self):
        """Test detection of leading dash."""
        assert needs_normalization("-Show") is True

    def test_needs_normalization_with_trailing_dash(self):
        """Test detection of trailing dash."""
        assert needs_normalization("Show-") is True

    def test_needs_normalization_clean_string(self):
        """Test clean string doesn't need normalization."""
        assert needs_normalization("Clean Show Name") is False

    def test_needs_normalization_empty_string(self):
        """Test empty string handling."""
        assert needs_normalization("") is False

    def test_needs_normalization_none(self):
        """Test None handling."""
        assert needs_normalization(None) is False


@pytest.mark.unit
class TestIsRedundantFilename:
    """Test redundant filename detection."""

    def test_redundant_king_gizzard_prefix(self):
        """Test detection of King Gizzard prefix."""
        assert is_redundant_filename("King Gizzard - 2024-05-20.mp4", "2024-05-20 - Berlin") is True

    def test_redundant_kglw_prefix(self):
        """Test detection of KGLW prefix."""
        assert is_redundant_filename("KGLW - 2024-05-20.mp4", "2024-05-20 - Berlin") is True

    def test_redundant_kg_prefix(self):
        """Test detection of KG prefix."""
        assert is_redundant_filename("KG - 2024-05-20.mp4", "2024-05-20 - Berlin") is True

    def test_non_redundant_filename(self):
        """Test non-redundant filename."""
        assert is_redundant_filename("2024-05-20 - Berlin.mp4", "2024-05-20 - Berlin") is False

    def test_redundant_case_insensitive(self):
        """Test case-insensitive detection."""
        assert is_redundant_filename("king gizzard - show.mp4", "2024-05-20 - Berlin") is True

    def test_empty_filename(self):
        """Test empty filename handling."""
        assert is_redundant_filename("", "2024-05-20 - Berlin") is False

    def test_empty_directory(self):
        """Test empty directory handling."""
        assert is_redundant_filename("show.mp4", "") is False


@pytest.mark.unit
class TestExtractShowInfoFromDirectoryName:
    """Test show information extraction from directory names."""

    def test_extract_full_info(self):
        """Test extraction with full information."""
        result = extract_show_info_from_directory_name("2024-05-20 - Berlin (Columbiahalle)")
        assert result['date'] == '2024-05-20'
        assert result['location'] == 'Berlin'
        assert result['venue'] == 'Columbiahalle'

    def test_extract_date_and_location(self):
        """Test extraction with date and location only."""
        result = extract_show_info_from_directory_name("2024-05-20 - Berlin")
        assert result['date'] == '2024-05-20'
        assert result['location'] == 'Berlin'
        assert 'venue' not in result

    def test_extract_date_only(self):
        """Test extraction with date only."""
        result = extract_show_info_from_directory_name("2024-05-20")
        assert result['date'] == '2024-05-20'
        assert 'location' not in result

    def test_extract_without_dash_separator(self):
        """Test extraction without dash separator."""
        result = extract_show_info_from_directory_name("2024-05-20 Berlin (Columbiahalle)")
        assert result['date'] == '2024-05-20'
        assert result['location'] == 'Berlin'
        assert result['venue'] == 'Columbiahalle'

    def test_extract_no_date(self):
        """Test extraction when no date pattern found."""
        result = extract_show_info_from_directory_name("Berlin (Columbiahalle)")
        assert result == {}

    def test_extract_with_complex_venue(self):
        """Test extraction with complex venue name."""
        result = extract_show_info_from_directory_name("2024-05-20 - Berlin (Madison Square Garden)")
        assert result['date'] == '2024-05-20'
        assert result['location'] == 'Berlin'
        assert result['venue'] == 'Madison Square Garden'

    def test_extract_location_with_special_characters(self):
        """Test extraction with special characters in location."""
        result = extract_show_info_from_directory_name("2024-05-20 - São Paulo (Venue)")
        assert result['date'] == '2024-05-20'
        assert result['location'] == 'São Paulo'
        assert result['venue'] == 'Venue'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
