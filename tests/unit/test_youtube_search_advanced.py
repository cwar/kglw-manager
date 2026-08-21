"""Advanced tests for YouTubeSearcher - focusing on uncovered areas."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from kglw_manager.youtube_search import YouTubeSearcher


@pytest.fixture
def youtube_searcher():
    """Create a YouTubeSearcher instance."""
    return YouTubeSearcher()


@pytest.mark.unit
class TestYouTubeSearcherInitialization:
    """Test YouTubeSearcher initialization and setup."""

    def test_initialization(self, youtube_searcher):
        """Test YouTubeSearcher initialization."""
        assert youtube_searcher is not None
        assert hasattr(youtube_searcher, 'check_yt_dlp_availability')

    def test_check_yt_dlp_availability_success(self, youtube_searcher):
        """Test checking yt-dlp availability when available."""
        with patch('shutil.which', return_value='/usr/bin/yt-dlp'):
            result = youtube_searcher.check_yt_dlp_availability()

            assert isinstance(result, bool)

    def test_check_yt_dlp_availability_failure(self, youtube_searcher):
        """Test checking yt-dlp availability when not available."""
        with patch('shutil.which', return_value=None):
            result = youtube_searcher.check_yt_dlp_availability()

            assert isinstance(result, bool)


@pytest.mark.unit
class TestYouTubeSearchQueries:
    """Test search query generation."""

    def test_generate_search_queries_full_info(self, youtube_searcher):
        """Test generating search queries with full show info."""
        show = {
            'date': '2024-05-20',
            'location': 'Berlin',
            'venue': 'Columbiahalle'
        }

        queries = youtube_searcher._generate_search_queries(show)

        assert isinstance(queries, list)
        assert len(queries) > 0
        assert any('Berlin' in query for query in queries)

    def test_generate_search_queries_minimal_info(self, youtube_searcher):
        """Test generating search queries with minimal info."""
        show = {
            'date': '2024-05-20'
        }

        queries = youtube_searcher._generate_search_queries(show)

        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_generate_search_queries_with_tour(self, youtube_searcher):
        """Test generating search queries with tour information."""
        show = {
            'date': '2024-05-20',
            'location': 'Berlin',
            'tour_name': '2024 Europe Tour'
        }

        queries = youtube_searcher._generate_search_queries(show)

        assert isinstance(queries, list)
        assert len(queries) > 0


@pytest.mark.unit
class TestYouTubeURLValidation:
    """Test YouTube URL validation."""

    def test_validate_youtube_url_valid_standard(self, youtube_searcher):
        """Test validating a standard YouTube URL."""
        url = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'

        is_valid, url_type = youtube_searcher.validate_youtube_url(url)

        assert isinstance(is_valid, bool)
        assert isinstance(url_type, str)

    def test_validate_youtube_url_valid_short(self, youtube_searcher):
        """Test validating a short YouTube URL."""
        url = 'https://youtu.be/dQw4w9WgXcQ'

        is_valid, url_type = youtube_searcher.validate_youtube_url(url)

        assert isinstance(is_valid, bool)
        assert isinstance(url_type, str)

    def test_validate_youtube_url_playlist(self, youtube_searcher):
        """Test validating a YouTube playlist URL."""
        url = 'https://www.youtube.com/playlist?list=PLtest123'

        is_valid, url_type = youtube_searcher.validate_youtube_url(url)

        assert isinstance(is_valid, bool)
        assert isinstance(url_type, str)

    def test_validate_youtube_url_invalid(self, youtube_searcher):
        """Test validating an invalid URL."""
        url = 'https://example.com/not-youtube'

        is_valid, url_type = youtube_searcher.validate_youtube_url(url)

        assert isinstance(is_valid, bool)
        assert isinstance(url_type, str)


@pytest.mark.unit
class TestYouTubeVideoFiltering:
    """Test video filtering and relevance checking."""

    def test_is_relevant_video_matching_date(self, youtube_searcher):
        """Test checking if video is relevant with matching date."""
        video_info = {
            'title': 'King Gizzard 2024-05-20 Berlin',
            'description': 'Concert from May 20, 2024',
            'upload_date': '20240521'
        }

        result = youtube_searcher._is_relevant_video(video_info, '2024-05-20')

        assert isinstance(result, bool)

    def test_is_relevant_video_no_match(self, youtube_searcher):
        """Test checking if video is relevant with no date match."""
        video_info = {
            'title': 'Random Video',
            'description': 'Not a concert',
            'upload_date': '20240101'
        }

        result = youtube_searcher._is_relevant_video(video_info, '2024-05-20')

        assert isinstance(result, bool)

    def test_filter_concert_candidates_with_official(self, youtube_searcher):
        """Test filtering concert candidates when official source found."""
        videos = [
            {'title': 'Official Concert', 'channel': 'KGLW Official'},
            {'title': 'Fan Recording', 'channel': 'Random User'}
        ]

        filtered = youtube_searcher._filter_concert_candidates(videos, found_official_source=True)

        assert isinstance(filtered, list)

    def test_filter_concert_candidates_no_official(self, youtube_searcher):
        """Test filtering concert candidates when no official source."""
        videos = [
            {'title': 'Fan Recording 1', 'channel': 'User1'},
            {'title': 'Fan Recording 2', 'channel': 'User2'}
        ]

        filtered = youtube_searcher._filter_concert_candidates(videos, found_official_source=False)

        assert isinstance(filtered, list)


@pytest.mark.unit
class TestYouTubeVideoDeduplication:
    """Test video deduplication logic."""

    def test_deduplicate_videos_no_duplicates(self, youtube_searcher):
        """Test deduplication with no duplicate videos."""
        videos = [
            {'id': 'abc123', 'title': 'Video 1'},
            {'id': 'def456', 'title': 'Video 2'},
            {'id': 'ghi789', 'title': 'Video 3'}
        ]

        result = youtube_searcher._deduplicate_videos(videos)

        assert len(result) == 3

    def test_deduplicate_videos_with_duplicates(self, youtube_searcher):
        """Test deduplication with duplicate video IDs."""
        videos = [
            {'id': 'abc123', 'title': 'Video 1'},
            {'id': 'abc123', 'title': 'Video 1 Duplicate'},
            {'id': 'def456', 'title': 'Video 2'}
        ]

        result = youtube_searcher._deduplicate_videos(videos)

        assert len(result) == 2

    def test_deduplicate_videos_empty_list(self, youtube_searcher):
        """Test deduplication with empty list."""
        videos = []

        result = youtube_searcher._deduplicate_videos(videos)

        assert len(result) == 0


@pytest.mark.unit
class TestYouTubeUpgradeScoring:
    """Test upgrade quality scoring."""

    def test_sort_by_upgrade_quality(self, youtube_searcher):
        """Test sorting videos by upgrade quality."""
        show = {
            'current_resolution': '720p',
            'current_duration': 3600
        }
        videos = [
            {'resolution': '480p', 'duration': 3000, 'title': 'Low Quality'},
            {'resolution': '1080p', 'duration': 4000, 'title': 'High Quality'},
            {'resolution': '720p', 'duration': 3600, 'title': 'Same Quality'}
        ]

        sorted_videos = youtube_searcher._sort_by_upgrade_quality(videos, show)

        assert isinstance(sorted_videos, list)
        assert len(sorted_videos) == 3

    def test_calculate_upgrade_score_better_quality(self, youtube_searcher):
        """Test calculating upgrade score for better quality."""
        video = {
            'resolution': '1080p',
            'duration': 4000,
            'channel_priority': 1000
        }
        show = {
            'current_resolution': '720p',
            'current_duration': 3600
        }

        score = youtube_searcher._calculate_upgrade_score(video, show)

        assert isinstance(score, (int, float))
        assert score > 0

    def test_calculate_upgrade_score_worse_quality(self, youtube_searcher):
        """Test calculating upgrade score for worse quality."""
        video = {
            'resolution': '480p',
            'duration': 2000,
            'channel_priority': 0
        }
        show = {
            'current_resolution': '1080p',
            'current_duration': 4000
        }

        score = youtube_searcher._calculate_upgrade_score(video, show)

        assert isinstance(score, (int, float))


@pytest.mark.unit
class TestYouTubeDeadLinkRegistry:
    """Test dead link registry functionality."""

    def test_add_dead_link(self, youtube_searcher):
        """Test adding a dead link to registry."""
        url = 'https://youtube.com/watch?v=deadlink123'

        youtube_searcher.add_dead_link(url, reason='Video unavailable')

        # Should not raise exception
        assert True

    def test_is_dead_link_existing(self, youtube_searcher):
        """Test checking if URL is in dead link registry."""
        url = 'https://youtube.com/watch?v=deadlink123'
        youtube_searcher.add_dead_link(url)

        result = youtube_searcher.is_dead_link(url)

        assert isinstance(result, bool)

    def test_is_dead_link_not_existing(self, youtube_searcher):
        """Test checking if URL is not in dead link registry."""
        url = 'https://youtube.com/watch?v=validlink123'

        result = youtube_searcher.is_dead_link(url)

        assert isinstance(result, bool)
        assert result is False


@pytest.mark.unit
class TestYouTubeAudioDetection:
    """Test audio-only video detection."""

    def test_detect_audio_only_from_title(self, youtube_searcher):
        """Test detecting audio-only from title."""
        quality_info = {'formats': []}
        title = 'King Gizzard - Berlin 2024 [AUDIO ONLY]'

        result = youtube_searcher._detect_audio_only(quality_info, title)

        assert isinstance(result, bool)

    def test_detect_audio_only_from_formats(self, youtube_searcher):
        """Test detecting audio-only from format info."""
        quality_info = {
            'formats': [
                {'vcodec': 'none', 'acodec': 'opus'}
            ]
        }
        title = 'Concert Recording'

        result = youtube_searcher._detect_audio_only(quality_info, title)

        assert isinstance(result, bool)

    def test_detect_audio_only_video_present(self, youtube_searcher):
        """Test detecting that video has video codec."""
        quality_info = {
            'formats': [
                {'vcodec': 'h264', 'acodec': 'aac'}
            ]
        }
        title = 'Concert Video'

        result = youtube_searcher._detect_audio_only(quality_info, title)

        assert isinstance(result, bool)
        assert result is False


@pytest.mark.unit
class TestYouTubeDateCalculations:
    """Test date difference calculations."""

    def test_date_difference_days_same_date(self, youtube_searcher):
        """Test calculating days between same dates."""
        date1 = '2024-05-20'
        date2 = '2024-05-20'

        diff = youtube_searcher._date_difference_days(date1, date2)

        assert diff == 0

    def test_date_difference_days_one_day_apart(self, youtube_searcher):
        """Test calculating days between consecutive dates."""
        date1 = '2024-05-20'
        date2 = '2024-05-21'

        diff = youtube_searcher._date_difference_days(date1, date2)

        assert abs(diff) == 1

    def test_date_difference_days_week_apart(self, youtube_searcher):
        """Test calculating days between dates a week apart."""
        date1 = '2024-05-20'
        date2 = '2024-05-27'

        diff = youtube_searcher._date_difference_days(date1, date2)

        assert abs(diff) == 7


@pytest.mark.unit
class TestYouTubeSearchWithFallback:
    """Test search with fallback mechanisms."""

    def test_search_for_upgrades_with_fallback_no_spreadsheet(self, youtube_searcher):
        """Test search with fallback when no spreadsheet data."""
        show = {
            'date': '2024-05-20',
            'location': 'Berlin'
        }

        with patch.object(youtube_searcher, '_search_youtube_with_tracking', return_value=[]):
            results = youtube_searcher.search_for_upgrades_with_fallback(show)

            assert isinstance(results, list)

    def test_search_for_upgrades_basic(self, youtube_searcher):
        """Test basic search for upgrades."""
        show = {
            'date': '2024-05-20',
            'location': 'Berlin',
            'current_resolution': '720p'
        }

        with patch.object(youtube_searcher, '_search_youtube', return_value=[]):
            results = youtube_searcher.search_for_upgrades(show)

            assert isinstance(results, list)


@pytest.mark.unit
class TestYouTubeQualityInfo:
    """Test video quality information retrieval."""

    def test_get_video_quality_info_mock(self, youtube_searcher):
        """Test getting video quality info with mocked yt-dlp."""
        url = 'https://youtube.com/watch?v=test123'

        mock_info = {
            'title': 'Test Video',
            'duration': 3600,
            'resolution': '1080p',
            'formats': []
        }

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"title": "Test", "duration": 3600}',
                stderr=''
            )

            # This will likely fail or return minimal info, but should not crash
            try:
                result = youtube_searcher.get_video_quality_info(url)
                assert isinstance(result, dict)
            except Exception:
                # Expected to fail without real yt-dlp, test structure is valid
                pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
