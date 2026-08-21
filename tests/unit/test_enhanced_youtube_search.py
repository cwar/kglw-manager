"""Unit tests for enhanced YouTube search with fallback logic."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, call

from kglw_manager.youtube_search import YouTubeSearcher
from kglw_manager.link_failure_tracker import FailureReason
from kglw_manager.google_sheets_parser import GoogleSheetsParser


class TestEnhancedYouTubeSearch(unittest.TestCase):
    """Test the enhanced YouTube search functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.searcher = YouTubeSearcher()
        
        # Mock the spreadsheet parser
        self.mock_parser = MagicMock(spec=GoogleSheetsParser)
        self.mock_parser.shows_data = {}  # Add the shows_data attribute
        self.searcher.spreadsheet_parser = self.mock_parser
        
        # Test show data
        self.test_show = {
            'date': '2024-05-22',
            'location': 'Hamburg, Germany',
            'venue': 'Stadtpark Open Air'
        }
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    @patch('kglw_manager.youtube_search.official_db')
    def test_search_for_upgrades_with_fallback_spreadsheet_success(self, mock_official_db):
        """Test successful fallback search with working spreadsheet links."""
        # Mock successful spreadsheet candidates
        mock_candidates = [
            {
                'url': 'https://youtube.com/watch?v=test123',
                'title': 'Test Video 1',
                'quality_score': 100,
                'height': 1080,
                'duration': 7200,
                'source': 'spreadsheet'
            }
        ]
        
        with patch.object(self.searcher, '_get_all_spreadsheet_candidates_with_tracking') as mock_get_candidates:
            mock_get_candidates.return_value = mock_candidates
            mock_official_db.get_priority_video.return_value = None

            with patch.object(self.searcher, '_search_youtube_with_tracking') as mock_youtube:
                mock_youtube.return_value = []

                result = self.searcher.search_for_upgrades_with_fallback(self.test_show)

            # Every source is consulted, with curated spreadsheet links first so
            # the download logic can fall through if one link is dead.
            self.assertEqual(result, mock_candidates)
            mock_get_candidates.assert_called_once_with('2024-05-22', 'Hamburg, Germany')
    
    @patch('kglw_manager.youtube_search.official_db')
    def test_search_for_upgrades_with_fallback_official_db(self, mock_official_db):
        """Test fallback to official database when spreadsheet fails."""
        # Mock no spreadsheet candidates
        with patch.object(self.searcher, '_get_all_spreadsheet_candidates_with_tracking') as mock_get_candidates:
            mock_get_candidates.return_value = []
            
            # Mock official database result
            mock_official_video = {
                'url': 'https://youtube.com/watch?v=official123',
                'title': 'Official Video',
                'source': 'official_db'
            }
            mock_official_db.get_priority_video.return_value = mock_official_video

            with patch.object(self.searcher, '_search_youtube_with_tracking') as mock_youtube:
                mock_youtube.return_value = []
                result = self.searcher.search_for_upgrades_with_fallback(self.test_show)

            # Should include the official database result
            self.assertEqual(result, [mock_official_video])
            mock_official_db.get_priority_video.assert_called_once_with('2024-05-22', 'Hamburg, Germany')
    
    @patch('kglw_manager.youtube_search.official_db')
    def test_search_for_upgrades_with_fallback_youtube_search(self, mock_official_db):
        """Test fallback to YouTube search when other sources fail."""
        # Mock no spreadsheet candidates and no official database
        with patch.object(self.searcher, '_get_all_spreadsheet_candidates_with_tracking') as mock_get_candidates:
            mock_get_candidates.return_value = []
            mock_official_db.get_priority_video.return_value = None
            
            # Mock YouTube search result
            mock_youtube_results = [
                {
                    'url': 'https://youtube.com/watch?v=youtube123',
                    'title': 'YouTube Search Result',
                    'source': 'youtube'
                }
            ]
            
            with patch.object(self.searcher, '_search_youtube_with_tracking') as mock_youtube_search:
                mock_youtube_search.return_value = mock_youtube_results
                
                result = self.searcher.search_for_upgrades_with_fallback(self.test_show)
                
                # Should return YouTube search results
                self.assertEqual(result, mock_youtube_results)
                mock_youtube_search.assert_called_once_with(self.test_show)
    
    def test_get_all_spreadsheet_candidates_with_tracking_success(self):
        """Test getting spreadsheet candidates with successful links."""
        # Ensure shows_data is not empty for the test
        self.mock_parser.shows_data = {'test': 'data'}
        
        # Mock spreadsheet data
        mock_youtube_links = [
            {
                'url': 'https://youtube.com/watch?v=test123',
                'column': 'Link',
                'text': 'Test Video'
            },
            {
                'url': 'https://youtube.com/watch?v=test456',
                'column': 'Link 2',
                'text': 'Test Video 2'
            }
        ]
        
        with patch.object(self.searcher, '_get_spreadsheet_videos_raw') as mock_get_raw:
            mock_get_raw.return_value = mock_youtube_links
            
            # Mock successful link testing
            mock_test_results = [
                {
                    'success': True,
                    'candidate': {
                        'url': 'https://youtube.com/watch?v=test123',
                        'quality_score': 100,
                        'title': 'Test Video'
                    }
                },
                {
                    'success': True,
                    'candidate': {
                        'url': 'https://youtube.com/watch?v=test456',
                        'quality_score': 80,
                        'title': 'Test Video 2'
                    }
                }
            ]
            
            with patch.object(self.searcher, '_test_single_link_with_tracking') as mock_test_link:
                mock_test_link.side_effect = mock_test_results
                
                result = self.searcher._get_all_spreadsheet_candidates_with_tracking('2024-05-22', 'Hamburg, Germany')
                
                # Should return candidates sorted by quality score
                self.assertEqual(len(result), 2)
                self.assertEqual(result[0]['quality_score'], 100)  # Higher quality first
                self.assertEqual(result[1]['quality_score'], 80)
    
    def test_get_all_spreadsheet_candidates_with_tracking_failures(self):
        """Test handling of failed links with tracking."""
        # Ensure shows_data is not empty for the test
        self.mock_parser.shows_data = {'test': 'data'}
        
        # Mock spreadsheet data with one working and one failing link
        mock_youtube_links = [
            {
                'url': 'https://youtube.com/watch?v=working',
                'column': 'Link',
                'text': 'Working Video'
            },
            {
                'url': 'https://youtube.com/watch?v=broken',
                'column': 'Link 2',
                'text': 'Broken Video'
            }
        ]
        
        with patch.object(self.searcher, '_get_spreadsheet_videos_raw') as mock_get_raw:
            mock_get_raw.return_value = mock_youtube_links
            
            # Mock one success, one failure
            def mock_test_side_effect(url, *args):
                if 'working' in url:
                    return {
                        'success': True,
                        'candidate': {
                            'url': url,
                            'quality_score': 90,
                            'title': 'Working Video'
                        }
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Video not found',
                        'failure_reason': 'video_not_found'
                    }
            
            with patch.object(self.searcher, '_test_single_link_with_tracking') as mock_test_link:
                mock_test_link.side_effect = mock_test_side_effect
                
                result = self.searcher._get_all_spreadsheet_candidates_with_tracking('2024-05-22', 'Hamburg, Germany')
                
                # Should return only working candidates
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0]['url'], 'https://youtube.com/watch?v=working')
    
    def test_get_all_spreadsheet_candidates_skip_known_failures(self):
        """Test skipping links that are known to have failed."""
        # Ensure shows_data is not empty for the test
        self.mock_parser.shows_data = {'test': 'data'}
        
        # Mock spreadsheet data
        mock_youtube_links = [
            {
                'url': 'https://youtube.com/watch?v=known_failure',
                'column': 'Link',
                'text': 'Known Failed Video'
            },
            {
                'url': 'https://youtube.com/watch?v=unknown',
                'column': 'Link 2',
                'text': 'Unknown Video'
            }
        ]
        
        with patch.object(self.searcher, '_get_spreadsheet_videos_raw') as mock_get_raw:
            mock_get_raw.return_value = mock_youtube_links
            
            # Mock failure tracker to return True for known failure
            with patch.object(self.searcher.failure_tracker, 'is_known_failed') as mock_is_failed:
                def mock_is_failed_side_effect(url):
                    return 'known_failure' in url
                
                mock_is_failed.side_effect = mock_is_failed_side_effect
                
                # Mock successful test for unknown URL
                with patch.object(self.searcher, '_test_single_link_with_tracking') as mock_test_link:
                    mock_test_link.return_value = {
                        'success': True,
                        'candidate': {
                            'url': 'https://youtube.com/watch?v=unknown',
                            'quality_score': 85,
                            'title': 'Unknown Video'
                        }
                    }
                    
                    result = self.searcher._get_all_spreadsheet_candidates_with_tracking('2024-05-22', 'Hamburg, Germany')
                    
                    # Should only test the unknown URL
                    mock_test_link.assert_called_once()
                    self.assertEqual(len(result), 1)
                    self.assertEqual(result[0]['url'], 'https://youtube.com/watch?v=unknown')
    
    @patch('subprocess.run')
    def test_test_single_link_with_tracking_success(self, mock_subprocess):
        """Test successful single link testing."""
        url = 'https://youtube.com/watch?v=test123'
        
        # Mock successful video quality info
        mock_quality_info = {
            'height': 1080,
            'duration': 7200,
            'title': 'Test Video'
        }
        
        with patch.object(self.searcher, 'get_video_quality_info') as mock_get_quality:
            mock_get_quality.return_value = mock_quality_info
            
            result = self.searcher._test_single_link_with_tracking(
                url, '2024-05-22', 'Hamburg, Germany', 'Link'
            )
            
            self.assertTrue(result['success'])
            self.assertIn('candidate', result)
            
            candidate = result['candidate']
            self.assertEqual(candidate['url'], url)
            self.assertEqual(candidate['height'], 1080)
            self.assertEqual(candidate['quality_score'], 120)  # 100 + 20 for good duration
    
    @patch('subprocess.run')
    def test_test_single_link_with_tracking_failure(self, mock_subprocess):
        """Test single link testing with failure tracking."""
        url = 'https://youtube.com/watch?v=test123'
        
        # Mock failed video quality info
        with patch.object(self.searcher, 'get_video_quality_info') as mock_get_quality:
            mock_get_quality.return_value = None
            
            # Mock subprocess for detailed error
            mock_subprocess.return_value = MagicMock(
                returncode=1,
                stderr="ERROR: Video unavailable"
            )
            
            # Mock failure tracker
            with patch.object(self.searcher.failure_tracker, 'record_failure') as mock_record:
                with patch.object(self.searcher.failure_tracker, 'classify_error') as mock_classify:
                    mock_classify.return_value = FailureReason.VIDEO_NOT_FOUND
                    
                    result = self.searcher._test_single_link_with_tracking(
                        url, '2024-05-22', 'Hamburg, Germany', 'Link'
                    )
                    
                    self.assertFalse(result['success'])
                    self.assertEqual(result['failure_reason'], 'video_not_found')
                    
                    # Should record the failure
                    mock_record.assert_called_once()
                    mock_classify.assert_called_once()
    
    def test_get_spreadsheet_videos_raw_exact_match(self):
        """Test getting raw spreadsheet videos with exact date match."""
        mock_youtube_links = [
            {
                'url': 'https://youtube.com/watch?v=test123',
                'column': 'Link',
                'text': 'Test Video'
            }
        ]
        
        self.mock_parser.get_youtube_links_for_show.return_value = mock_youtube_links
        
        result = self.searcher._get_spreadsheet_videos_raw('2024-05-22', 'Hamburg, Germany')
        
        self.assertEqual(result, mock_youtube_links)
        self.mock_parser.get_youtube_links_for_show.assert_called_once_with(
            date='2024-05-22', location='Hamburg, Germany'
        )
    
    def test_get_spreadsheet_videos_raw_location_fallback(self):
        """Test getting raw spreadsheet videos with location fallback."""
        # Mock no exact match
        self.mock_parser.get_youtube_links_for_show.return_value = []
        
        # Mock location search
        mock_location_matches = [
            {
                'date': '2024-05-22',
                'youtube_links': [
                    {
                        'url': 'https://youtube.com/watch?v=test123',
                        'column': 'Link',
                        'text': 'Test Video'
                    }
                ]
            }
        ]
        self.mock_parser.search_shows_by_location.return_value = mock_location_matches
        
        # Mock date difference calculation
        with patch.object(self.searcher, '_date_difference_days') as mock_date_diff:
            mock_date_diff.return_value = 0  # Exact match
            
            result = self.searcher._get_spreadsheet_videos_raw('2024-05-22', 'Hamburg, Germany')
            
            expected_links = mock_location_matches[0]['youtube_links']
            self.assertEqual(result, expected_links)
    
    def test_search_youtube_with_tracking_success(self):
        """Test YouTube search with successful results."""
        mock_candidates = [
            {
                'url': 'https://youtube.com/watch?v=youtube123',
                'title': 'YouTube Result',
                'source': 'youtube'
            }
        ]
        
        with patch.object(self.searcher, 'check_yt_dlp_availability') as mock_check_ytdlp:
            mock_check_ytdlp.return_value = True
            
            with patch.object(self.searcher, '_generate_search_queries') as mock_generate:
                mock_generate.return_value = ['test query']
                
                with patch.object(self.searcher, '_search_youtube') as mock_search:
                    mock_search.return_value = mock_candidates
                    
                    result = self.searcher._search_youtube_with_tracking(self.test_show)
                    
                    self.assertEqual(result, mock_candidates)
    
    def test_search_youtube_with_tracking_no_results(self):
        """An empty YouTube search must not create a failure-tracker entry.

        The tracker is keyed by URL and feeds the maintainer's "problematic
        links" report, so a synthetic 'youtube_search:<date>' key would appear
        there as though it were a real spreadsheet link.
        """
        with patch.object(self.searcher, 'check_yt_dlp_availability') as mock_check_ytdlp:
            mock_check_ytdlp.return_value = True

            with patch.object(self.searcher, '_generate_search_queries') as mock_generate:
                mock_generate.return_value = ['test query']

                with patch.object(self.searcher, '_search_youtube') as mock_search:
                    mock_search.return_value = []  # No results

                    with patch.object(self.searcher.failure_tracker, 'record_failure') as mock_record:
                        result = self.searcher._search_youtube_with_tracking(self.test_show)

                        self.assertEqual(result, [])
                        mock_record.assert_not_called()
    
    def test_search_youtube_with_tracking_ytdlp_unavailable(self):
        """Test YouTube search when yt-dlp is not available."""
        with patch.object(self.searcher, 'check_yt_dlp_availability') as mock_check_ytdlp:
            mock_check_ytdlp.return_value = False
            
            result = self.searcher._search_youtube_with_tracking(self.test_show)
            
            self.assertEqual(result, [])


class TestIntegrationEnhancedSearch(unittest.TestCase):
    """Integration tests for enhanced search functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.searcher = YouTubeSearcher()
        
        # Test show data
        self.test_show = {
            'date': '2024-05-22',
            'location': 'Hamburg, Germany',
            'venue': 'Stadtpark Open Air'
        }
    
    def test_fallback_chain_integration(self):
        """Test the complete fallback chain integration."""
        # Mock all phases to return empty except YouTube search
        with patch.object(self.searcher, '_get_all_spreadsheet_candidates_with_tracking') as mock_spreadsheet:
            mock_spreadsheet.return_value = []
            
            with patch('kglw_manager.youtube_search.official_db') as mock_official_db:
                mock_official_db.get_priority_video.return_value = None
                
                with patch.object(self.searcher, '_search_youtube_with_tracking') as mock_youtube:
                    mock_youtube_results = [{'url': 'youtube_result', 'title': 'YouTube'}]
                    mock_youtube.return_value = mock_youtube_results
                    
                    result = self.searcher.search_for_upgrades_with_fallback(self.test_show)
                    
                    # Should go through all phases and return YouTube results
                    mock_spreadsheet.assert_called_once()
                    mock_official_db.get_priority_video.assert_called_once()
                    mock_youtube.assert_called_once()
                    
                    self.assertEqual(result, mock_youtube_results)
    
    def test_spreadsheet_results_ranked_first(self):
        """Curated spreadsheet links lead the combined candidate list.

        The search deliberately gathers every source rather than stopping at
        the first hit, so a dead spreadsheet link can fall through to the
        official database or a YouTube search.
        """
        mock_spreadsheet_results = [{'url': 'spreadsheet_result', 'title': 'Spreadsheet'}]
        mock_youtube_results = [{'url': 'youtube_result', 'title': 'YouTube'}]

        with patch.object(self.searcher, '_get_all_spreadsheet_candidates_with_tracking') as mock_spreadsheet:
            mock_spreadsheet.return_value = mock_spreadsheet_results

            with patch('kglw_manager.youtube_search.official_db') as mock_official_db:
                mock_official_db.get_priority_video.return_value = None

                with patch.object(self.searcher, '_search_youtube_with_tracking') as mock_youtube:
                    mock_youtube.return_value = mock_youtube_results

                    result = self.searcher.search_for_upgrades_with_fallback(self.test_show)

                    self.assertEqual(result[0], mock_spreadsheet_results[0])
                    self.assertIn(mock_youtube_results[0], result)


if __name__ == '__main__':
    unittest.main()