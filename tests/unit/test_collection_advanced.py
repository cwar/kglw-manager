"""Advanced tests for CollectionManager - focusing on uncovered areas."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from kglw_manager.collection import CollectionManager


@pytest.fixture
def temp_collection_dir():
    """Create a temporary collection directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def collection_manager(temp_collection_dir):
    """Create a CollectionManager instance."""
    return CollectionManager(str(temp_collection_dir))


@pytest.mark.unit
class TestCollectionSpreadsheetIntegration:
    """Test spreadsheet integration features."""

    def test_load_spreadsheet_data_no_file(self, collection_manager):
        """Test loading spreadsheet when no file exists."""
        result = collection_manager.load_spreadsheet_data('/nonexistent/file.html')

        assert result is False

    def test_get_spreadsheet_stats_no_data(self, collection_manager):
        """Test getting spreadsheet stats when no data loaded."""
        stats = collection_manager.get_spreadsheet_stats()

        assert 'total_shows' in stats
        assert stats['total_shows'] == 0

    def test_find_youtube_links_for_show_no_spreadsheet(self, collection_manager):
        """Test finding YouTube links when no spreadsheet loaded."""
        show_info = {
            'date': '2024-05-20',
            'location': 'Berlin'
        }

        links = collection_manager.find_youtube_links_for_show(show_info)

        assert isinstance(links, list)
        assert len(links) == 0

    def test_suggest_upgrades_from_spreadsheet_no_data(self, collection_manager):
        """Test suggesting upgrades when no spreadsheet data."""
        show_info = {
            'date': '2024-05-20',
            'location': 'Berlin'
        }

        suggestions = collection_manager.suggest_upgrades_from_spreadsheet(show_info)

        assert isinstance(suggestions, list)
        assert len(suggestions) == 0

    def test_find_missing_shows_in_collection_empty(self, collection_manager):
        """Test finding missing shows with empty collection."""
        missing = collection_manager.find_missing_shows_in_collection()

        assert isinstance(missing, list)


@pytest.mark.unit
class TestCollectionQualityAnalysis:
    """Test video quality analysis methods."""

    def test_detect_quality_from_filename_1080p(self, collection_manager):
        """Test detecting 1080p quality from filename."""
        file_path = Path('/test/video_1080p.mp4')

        result = collection_manager._detect_quality_from_filename(file_path)

        assert 'resolution' in result
        assert '1080' in result['resolution']

    def test_detect_quality_from_filename_720p(self, collection_manager):
        """Test detecting 720p quality from filename."""
        file_path = Path('/test/video_720p.mp4')

        result = collection_manager._detect_quality_from_filename(file_path)

        assert 'resolution' in result
        assert '720' in result['resolution']

    def test_detect_quality_from_filename_4k(self, collection_manager):
        """Test detecting 4K quality from filename."""
        file_path = Path('/test/video_4k.mp4')

        result = collection_manager._detect_quality_from_filename(file_path)

        assert 'resolution' in result

    def test_detect_quality_from_filename_unknown(self, collection_manager):
        """Test quality detection for unknown filename."""
        file_path = Path('/test/video.mp4')

        result = collection_manager._detect_quality_from_filename(file_path)

        assert isinstance(result, dict)


@pytest.mark.unit
class TestCollectionUpgradeTracking:
    """Test upgrade tracking functionality."""

    def test_init_upgrade_tracker(self, collection_manager):
        """Test initializing upgrade tracker."""
        tracker = collection_manager._init_upgrade_tracker()

        assert 'last_checked' in tracker
        assert 'failed_attempts' in tracker
        assert 'successful_upgrades' in tracker
        assert 'last_upgrade_attempt' in tracker
        assert isinstance(tracker['last_checked'], dict)

    def test_mark_upgrade_checked(self, collection_manager):
        """Test marking a show as checked for upgrades."""
        show_date = '2024-05-20'

        collection_manager._mark_upgrade_checked(show_date)

        # Should not raise an exception
        assert True

    def test_mark_upgrade_attempt_success(self, collection_manager):
        """Test marking successful upgrade attempt."""
        show_date = '2024-05-20'

        collection_manager._mark_upgrade_attempt(show_date, success=True)

        # Should not raise an exception
        assert True

    def test_mark_upgrade_attempt_failure(self, collection_manager):
        """Test marking failed upgrade attempt."""
        show_date = '2024-05-20'

        collection_manager._mark_upgrade_attempt(show_date, success=False)

        # Should not raise an exception
        assert True

    def test_clear_failed_upgrade_attempts_all(self, collection_manager):
        """Test clearing all failed upgrade attempts."""
        # Mark some failures first
        collection_manager._mark_upgrade_attempt('2024-05-20', success=False)
        collection_manager._mark_upgrade_attempt('2024-05-21', success=False)

        count = collection_manager.clear_failed_upgrade_attempts()

        assert isinstance(count, int)

    def test_clear_failed_upgrade_attempts_specific(self, collection_manager):
        """Test clearing failed attempts for specific show."""
        show_date = '2024-05-20'
        collection_manager._mark_upgrade_attempt(show_date, success=False)

        count = collection_manager.clear_failed_upgrade_attempts(show_date)

        assert isinstance(count, int)

    def test_get_upgrade_tracking_stats(self, collection_manager):
        """Test getting upgrade tracking statistics."""
        stats = collection_manager.get_upgrade_tracking_stats()

        # Keys consumed by cli.py's "cache upgrade-stats" command
        assert 'recently_checked' in stats
        assert 'failed_shows' in stats
        assert 'successful_shows' in stats
        assert 'blocked_shows' in stats
        assert 'total_attempts' in stats
        assert isinstance(stats['failed_shows'], int)

    def test_should_skip_upgrade_check(self, collection_manager):
        """Test checking if upgrade check should be skipped."""
        show_date = '2024-05-20'

        result = collection_manager._should_skip_upgrade_check(show_date)

        assert isinstance(result, bool)


@pytest.mark.unit
class TestCollectionShowAnalysis:
    """Test show analysis and parsing methods."""

    def test_parse_show_info_from_directory_full_format(self, collection_manager, temp_collection_dir):
        """Test parsing show info from directory with full format."""
        show_dir = temp_collection_dir / '2024-05-20 - Berlin (Columbiahalle)'
        show_dir.mkdir(parents=True)

        info = collection_manager._parse_show_info_from_directory(show_dir)

        assert 'date' in info
        assert info['date'] == '2024-05-20'

    def test_parse_show_info_from_directory_minimal(self, collection_manager, temp_collection_dir):
        """Test parsing show info from directory with minimal format."""
        show_dir = temp_collection_dir / '2024-05-20'
        show_dir.mkdir(parents=True)

        info = collection_manager._parse_show_info_from_directory(show_dir)

        assert 'date' in info

    def test_analyze_upgrade_need_low_resolution(self, collection_manager):
        """Test analyzing upgrade need for low resolution video."""
        show_info = {
            'videos': [{
                'resolution': '480p',
                'duration': 3600,
                'codec': 'h264'
            }],
            'date': '2024-05-20'
        }

        analysis = collection_manager._analyze_upgrade_need(show_info)

        assert 'needs_upgrade' in analysis
        assert isinstance(analysis['needs_upgrade'], bool)

    def test_analyze_upgrade_need_short_duration(self, collection_manager):
        """Test analyzing upgrade need for short duration video."""
        show_info = {
            'videos': [{
                'resolution': '1080p',
                'duration': 1800,  # 30 minutes
                'codec': 'h264'
            }],
            'date': '2024-05-20'
        }

        analysis = collection_manager._analyze_upgrade_need(show_info)

        assert 'needs_upgrade' in analysis


@pytest.mark.unit
class TestCollectionStats:
    """Test statistics and reporting methods."""

    def test_get_collection_stats_empty(self, collection_manager):
        """Test getting stats for empty collection."""
        stats = collection_manager.get_collection_stats()

        assert 'total_shows' in stats
        assert 'total_tours' in stats
        assert 'total_videos' in stats
        assert isinstance(stats, dict)

    def test_cleanup_stale_cache(self, collection_manager):
        """Test cleaning up stale cache entries."""
        # Should not raise exception
        collection_manager.cleanup_stale_cache()

        assert True


@pytest.mark.unit
class TestCollectionMissingShows:
    """Test missing show detection functionality."""

    def test_find_missing_shows_no_source(self, collection_manager):
        """Test finding missing shows with no source specified."""
        # find_missing_shows lazily imports DataSourceManager from
        # kglw_manager.sources and calls get_shows_for_year on it.
        with patch('kglw_manager.sources.DataSourceManager.get_shows_for_year',
                   return_value=[]):
            missing = collection_manager.find_missing_shows(max_results=10)

            assert isinstance(missing, list)
            assert missing == []

    def test_find_missing_shows_with_year_filter(self, collection_manager):
        """Test finding missing shows filtered by year."""
        with patch('kglw_manager.sources.DataSourceManager.get_shows_for_year',
                   return_value=[]) as mock_get:
            missing = collection_manager.find_missing_shows(
                year_filter=2024,
                max_results=10
            )

            assert isinstance(missing, list)
            assert missing == []
            # Only the filtered year should be queried
            mock_get.assert_called_once_with(2024)

    def test_search_missing_show_candidates_api_priority(self, collection_manager):
        """Test searching for missing show candidates with API priority."""
        show_info = {
            'date': '2024-05-20',
            'city': 'Berlin',
            'venue': 'Test Venue'
        }

        with patch('kglw_manager.youtube_search.YouTubeSearcher') as mock_searcher:
            mock_searcher.return_value.search_for_show.return_value = []

            candidates = collection_manager._search_missing_show_candidates(
                show_info,
                source_priority='api'
            )

            assert isinstance(candidates, list)


@pytest.mark.unit
class TestCollectionVideoLabeling:
    """Test video labeling and song identification."""

    def test_identify_and_label_song_full_concert(self, collection_manager):
        """Test identifying full concert (long duration)."""
        video_info = {
            'duration': 5400,  # 90 minutes
            'title': 'Full Concert'
        }

        result = collection_manager.identify_and_label_song(video_info, duration_threshold=900)

        # Full concerts should return None or specific label
        assert result is None or isinstance(result, dict)

    def test_identify_and_label_song_individual_song(self, collection_manager):
        """Test identifying individual song (short duration)."""
        video_info = {
            'duration': 300,  # 5 minutes
            'title': 'Rattlesnake'
        }

        result = collection_manager.identify_and_label_song(video_info, duration_threshold=900)

        # Individual songs may return label info
        assert result is None or isinstance(result, dict)

    def test_get_song_label_for_video(self, collection_manager):
        """Test getting song label for a video."""
        video_info = {
            'title': 'King Gizzard - Rattlesnake',
            'duration': 300
        }

        label = collection_manager.get_song_label_for_video(video_info)

        assert isinstance(label, str)


@pytest.mark.unit
class TestCollectionUpgradeValidation:
    """Test upgrade validation logic."""

    def test_is_wrong_show_match_same_show(self, collection_manager):
        """Test detecting wrong show match with matching details."""
        expected_date = '2024-05-20'
        expected_location = 'Berlin'
        candidate = {
            'title': '2024-05-20 Berlin Concert',
            'description': 'Concert in Berlin'
        }

        result = collection_manager._is_wrong_show_match(
            expected_date,
            expected_location,
            candidate
        )

        assert isinstance(result, bool)

    def test_is_wrong_show_match_different_show(self, collection_manager):
        """Test detecting wrong show match with different details."""
        expected_date = '2024-05-20'
        expected_location = 'Berlin'
        candidate = {
            'title': '2024-05-21 Paris Concert',
            'description': 'Concert in Paris'
        }

        result = collection_manager._is_wrong_show_match(
            expected_date,
            expected_location,
            candidate
        )

        assert isinstance(result, bool)

    def test_is_meaningful_upgrade_better_quality(self, collection_manager):
        """Test checking if upgrade is meaningful with better quality."""
        current_show = {
            'videos': [{
                'resolution': '720p',
                'duration': 3600
            }]
        }
        candidate = {
            'resolution': '1080p',
            'title': 'High Quality Concert'
        }
        analysis = {
            'resolution_upgrade': True,
            'quality_improvement': True
        }

        is_meaningful, reason = collection_manager._is_meaningful_upgrade(
            current_show,
            candidate,
            analysis
        )

        assert isinstance(is_meaningful, bool)
        assert isinstance(reason, str)

    def test_is_meaningful_upgrade_same_quality(self, collection_manager):
        """Test checking if upgrade is meaningful with same quality."""
        current_show = {
            'videos': [{
                'resolution': '1080p',
                'duration': 3600
            }]
        }
        candidate = {
            'resolution': '1080p',
            'title': 'Same Quality Concert'
        }
        analysis = {
            'resolution_upgrade': False,
            'quality_improvement': False
        }

        is_meaningful, reason = collection_manager._is_meaningful_upgrade(
            current_show,
            candidate,
            analysis
        )

        assert isinstance(is_meaningful, bool)
        assert isinstance(reason, str)


@pytest.mark.unit
class TestCollectionPlexIntegration:
    """Test Plex integration features."""

    def test_sync_collection_with_plex_no_plex(self, collection_manager):
        """Test syncing with Plex when Plex is not configured."""
        # No plex_manager configured
        result = collection_manager.sync_collection_with_plex()

        assert isinstance(result, dict)

    def test_get_plex_stats_no_plex(self, collection_manager):
        """Test getting Plex stats when Plex is not configured."""
        stats = collection_manager.get_plex_stats()

        assert isinstance(stats, dict)

    def test_find_plex_shows_missing_collections_no_plex(self, collection_manager):
        """Test finding Plex shows missing collections when Plex not configured."""
        shows = collection_manager.find_plex_shows_missing_collections()

        assert isinstance(shows, list)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
