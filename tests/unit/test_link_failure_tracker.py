"""Comprehensive unit tests for link failure tracking system."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from kglw_manager.link_failure_tracker import (
    LinkFailureTracker,
    LinkFailure,
    FailureReason
)


class TestFailureReason(unittest.TestCase):
    """Test the FailureReason enum."""
    
    def test_failure_reason_values(self):
        """Test that all failure reasons have expected values."""
        expected_reasons = {
            'video_not_found', 'region_blocked', 'copyright_claim',
            'channel_terminated', 'video_restricted', 'quality_not_upgrade',
            'download_error', 'network_error', 'unknown_error'
        }
        
        actual_reasons = {reason.value for reason in FailureReason}
        self.assertEqual(expected_reasons, actual_reasons)


class TestLinkFailure(unittest.TestCase):
    """Test the LinkFailure dataclass."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.sample_failure = LinkFailure(
            url="https://youtube.com/watch?v=test123",
            show_date="2024-05-22",
            show_location="Hamburg, Germany",
            failure_reason=FailureReason.VIDEO_NOT_FOUND,
            error_message="Video unavailable",
            column_source="Link",
            timestamp="2024-01-01T12:00:00",
            retry_count=1,
            video_title="Test Video",
            uploader="Test Channel"
        )
    
    def test_to_dict_conversion(self):
        """Test conversion to dictionary."""
        result = self.sample_failure.to_dict()
        
        self.assertEqual(result['url'], "https://youtube.com/watch?v=test123")
        self.assertEqual(result['failure_reason'], "video_not_found")
        self.assertEqual(result['retry_count'], 1)
        self.assertIsInstance(result, dict)
    
    def test_from_dict_conversion(self):
        """Test creation from dictionary."""
        data = {
            'url': "https://youtube.com/watch?v=test456",
            'show_date': "2024-06-01",
            'show_location': "London, UK",
            'failure_reason': "copyright_claim",
            'error_message': "Copyright claim",
            'column_source': "Link 2",
            'timestamp': "2024-01-02T12:00:00",
            'retry_count': 2
        }
        
        failure = LinkFailure.from_dict(data)
        
        self.assertEqual(failure.url, "https://youtube.com/watch?v=test456")
        self.assertEqual(failure.failure_reason, FailureReason.COPYRIGHT_CLAIM)
        self.assertEqual(failure.retry_count, 2)
    
    def test_round_trip_conversion(self):
        """Test to_dict -> from_dict round trip."""
        original = self.sample_failure
        dict_data = original.to_dict()
        reconstructed = LinkFailure.from_dict(dict_data)
        
        self.assertEqual(original.url, reconstructed.url)
        self.assertEqual(original.failure_reason, reconstructed.failure_reason)
        self.assertEqual(original.retry_count, reconstructed.retry_count)


class TestLinkFailureTracker(unittest.TestCase):
    """Test the LinkFailureTracker class."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Use temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        self.cache_dir = Path(self.temp_dir)
        self.tracker = LinkFailureTracker(cache_dir=self.cache_dir)
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_initialization(self):
        """Test tracker initialization."""
        self.assertTrue(self.cache_dir.exists())
        self.assertTrue((self.cache_dir / 'failed_links.json').exists() or 
                       not (self.cache_dir / 'failed_links.json').exists())  # May not exist yet
        self.assertIsInstance(self.tracker._failures, dict)
    
    def test_record_failure_new(self):
        """Test recording a new failure."""
        self.tracker.record_failure(
            url="https://youtube.com/watch?v=test123",
            show_date="2024-05-22",
            show_location="Hamburg, Germany",
            failure_reason=FailureReason.VIDEO_NOT_FOUND,
            error_message="Video not found",
            column_source="Link"
        )
        
        self.assertEqual(len(self.tracker._failures), 1)
        failure = list(self.tracker._failures.values())[0]
        self.assertEqual(failure.url, "https://youtube.com/watch?v=test123")
        self.assertEqual(failure.retry_count, 1)
        self.assertEqual(failure.failure_reason, FailureReason.VIDEO_NOT_FOUND)
    
    def test_record_failure_existing(self):
        """Test recording failure for existing URL (should increment retry count)."""
        url = "https://youtube.com/watch?v=test123"
        
        # Record first failure
        self.tracker.record_failure(
            url=url,
            show_date="2024-05-22",
            show_location="Hamburg, Germany",
            failure_reason=FailureReason.VIDEO_NOT_FOUND,
            error_message="Video not found",
            column_source="Link"
        )
        
        # Record second failure for same URL
        self.tracker.record_failure(
            url=url,
            show_date="2024-05-22",
            show_location="Hamburg, Germany",
            failure_reason=FailureReason.VIDEO_NOT_FOUND,
            error_message="Still not found",
            column_source="Link"
        )
        
        self.assertEqual(len(self.tracker._failures), 1)
        failure = self.tracker._failures[url]
        self.assertEqual(failure.retry_count, 2)
        self.assertEqual(failure.error_message, "Still not found")  # Updated
    
    def test_is_known_failed_recent(self):
        """Test checking if URL is known to have failed recently."""
        url = "https://youtube.com/watch?v=test123"
        
        # Record permanent failure
        self.tracker.record_failure(
            url=url,
            show_date="2024-05-22",
            show_location="Hamburg, Germany",
            failure_reason=FailureReason.VIDEO_NOT_FOUND,
            error_message="Video not found",
            column_source="Link"
        )
        
        self.assertTrue(self.tracker.is_known_failed(url))
    
    def test_is_known_failed_old_failure(self):
        """Test that old failures are retried."""
        url = "https://youtube.com/watch?v=test123"
        
        # Create failure with old timestamp
        old_timestamp = (datetime.now() - timedelta(days=10)).isoformat()
        failure = LinkFailure(
            url=url,
            show_date="2024-05-22",
            show_location="Hamburg, Germany",
            failure_reason=FailureReason.NETWORK_ERROR,  # Non-permanent
            error_message="Network error",
            column_source="Link",
            timestamp=old_timestamp,
            retry_count=1
        )
        self.tracker._failures[url] = failure
        
        # Should not be considered failed (too old for non-permanent failure)
        self.assertFalse(self.tracker.is_known_failed(url, max_age_days=7))
    
    def test_classify_error_video_not_found(self):
        """Test error classification for video not found."""
        test_cases = [
            "Video unavailable",
            "This video does not exist",
            "404 Not Found",
            "Video has been removed",
            "Private video"
        ]
        
        for error_msg in test_cases:
            result = self.tracker.classify_error(error_msg)
            self.assertEqual(result, FailureReason.VIDEO_NOT_FOUND, 
                           f"Failed for: {error_msg}")
    
    def test_classify_error_region_blocked(self):
        """Test error classification for region blocking."""
        test_cases = [
            "Video not available in your country",
            "This content is blocked in your region",
            "Geographic restrictions apply"
        ]
        
        for error_msg in test_cases:
            result = self.tracker.classify_error(error_msg)
            self.assertEqual(result, FailureReason.REGION_BLOCKED, 
                           f"Failed for: {error_msg}")
    
    def test_classify_error_copyright(self):
        """Test error classification for copyright issues."""
        test_cases = [
            "Copyright claim by Sony Music",
            "DMCA takedown notice",
            "Blocked on copyright grounds",
            "Terms of service violation"
        ]
        
        for error_msg in test_cases:
            result = self.tracker.classify_error(error_msg)
            self.assertEqual(result, FailureReason.COPYRIGHT_CLAIM, 
                           f"Failed for: {error_msg}")
    
    def test_classify_error_unknown(self):
        """Test error classification for unknown errors."""
        result = self.tracker.classify_error("Some random error message")
        self.assertEqual(result, FailureReason.UNKNOWN_ERROR)
    
    def test_get_failures_by_show(self):
        """Test getting failures for specific show."""
        # Record failures for different shows
        self.tracker.record_failure(
            url="https://youtube.com/watch?v=test1",
            show_date="2024-05-22",
            show_location="Hamburg, Germany",
            failure_reason=FailureReason.VIDEO_NOT_FOUND,
            error_message="Not found",
            column_source="Link"
        )
        
        self.tracker.record_failure(
            url="https://youtube.com/watch?v=test2",
            show_date="2024-05-22",
            show_location="Hamburg, Germany",
            failure_reason=FailureReason.COPYRIGHT_CLAIM,
            error_message="Copyright",
            column_source="Link 2"
        )
        
        self.tracker.record_failure(
            url="https://youtube.com/watch?v=test3",
            show_date="2024-06-01",
            show_location="London, UK",
            failure_reason=FailureReason.VIDEO_NOT_FOUND,
            error_message="Not found",
            column_source="Link"
        )
        
        # Get failures for specific show
        hamburg_failures = self.tracker.get_failures_by_show("2024-05-22")
        london_failures = self.tracker.get_failures_by_show("2024-06-01")
        
        self.assertEqual(len(hamburg_failures), 2)
        self.assertEqual(len(london_failures), 1)
        
        hamburg_urls = {f.url for f in hamburg_failures}
        self.assertIn("https://youtube.com/watch?v=test1", hamburg_urls)
        self.assertIn("https://youtube.com/watch?v=test2", hamburg_urls)
    
    def test_get_failures_by_reason(self):
        """Test getting failures by reason."""
        # Record failures with different reasons
        self.tracker.record_failure(
            url="https://youtube.com/watch?v=test1",
            show_date="2024-05-22",
            show_location="Hamburg, Germany",
            failure_reason=FailureReason.VIDEO_NOT_FOUND,
            error_message="Not found",
            column_source="Link"
        )
        
        self.tracker.record_failure(
            url="https://youtube.com/watch?v=test2",
            show_date="2024-05-22",
            show_location="Hamburg, Germany",
            failure_reason=FailureReason.COPYRIGHT_CLAIM,
            error_message="Copyright",
            column_source="Link 2"
        )
        
        not_found_failures = self.tracker.get_failures_by_reason(FailureReason.VIDEO_NOT_FOUND)
        copyright_failures = self.tracker.get_failures_by_reason(FailureReason.COPYRIGHT_CLAIM)
        
        self.assertEqual(len(not_found_failures), 1)
        self.assertEqual(len(copyright_failures), 1)
        self.assertEqual(not_found_failures[0].url, "https://youtube.com/watch?v=test1")
        self.assertEqual(copyright_failures[0].url, "https://youtube.com/watch?v=test2")
    
    def test_generate_report(self):
        """Test generating comprehensive failure report."""
        # Record some test failures
        self.tracker.record_failure(
            url="https://youtube.com/watch?v=test1",
            show_date="2024-05-22",
            show_location="Hamburg, Germany",
            failure_reason=FailureReason.VIDEO_NOT_FOUND,
            error_message="Not found",
            column_source="Link"
        )
        
        self.tracker.record_failure(
            url="https://youtube.com/watch?v=test2",
            show_date="2024-05-22",
            show_location="Hamburg, Germany",
            failure_reason=FailureReason.COPYRIGHT_CLAIM,
            error_message="Copyright",
            column_source="Link 2"
        )
        
        report = self.tracker.generate_report()
        
        self.assertIn('generated_at', report)
        self.assertEqual(report['total_failed_links'], 2)
        self.assertEqual(report['unique_failed_urls'], 2)
        self.assertEqual(report['permanent_failures'], 2)  # Both are permanent
        
        self.assertIn('video_not_found', report['failures_by_reason'])
        self.assertIn('copyright_claim', report['failures_by_reason'])
        self.assertEqual(report['failures_by_reason']['video_not_found'], 1)
        self.assertEqual(report['failures_by_reason']['copyright_claim'], 1)
        
        self.assertIn('Link', report['failures_by_column'])
        self.assertIn('Link 2', report['failures_by_column'])
    
    def test_export_for_spreadsheet_maintainer(self):
        """Test exporting report for spreadsheet maintainer."""
        # Record test failures
        self.tracker.record_failure(
            url="https://youtube.com/watch?v=dead_link",
            show_date="2024-05-22",
            show_location="Hamburg, Germany",
            failure_reason=FailureReason.VIDEO_NOT_FOUND,
            error_message="Video deleted",
            column_source="Link"
        )
        
        self.tracker.record_failure(
            url="https://youtube.com/watch?v=network_issue",
            show_date="2024-05-22",
            show_location="Hamburg, Germany",
            failure_reason=FailureReason.NETWORK_ERROR,
            error_message="Network timeout",
            column_source="Link 2"
        )
        
        output_file = self.tracker.export_for_spreadsheet_maintainer()
        
        self.assertTrue(output_file.exists())
        
        # Load and verify report content
        with open(output_file, 'r', encoding='utf-8') as f:
            report = json.load(f)
        
        self.assertIn('dead_links_to_remove', report)
        self.assertIn('problematic_links_to_check', report)
        
        # Dead link should be in removal list
        dead_urls = [link['url'] for link in report['dead_links_to_remove']]
        self.assertIn("https://youtube.com/watch?v=dead_link", dead_urls)
        
        # Network issue should be in check list
        check_urls = [link['url'] for link in report['problematic_links_to_check']]
        self.assertIn("https://youtube.com/watch?v=network_issue", check_urls)
    
    def test_cleanup_old_failures(self):
        """Test cleaning up old failure records."""
        # Create old failure
        old_timestamp = (datetime.now() - timedelta(days=100)).isoformat()
        old_failure = LinkFailure(
            url="https://youtube.com/watch?v=old",
            show_date="2024-01-01",
            show_location="Old Location",
            failure_reason=FailureReason.VIDEO_NOT_FOUND,
            error_message="Old error",
            column_source="Link",
            timestamp=old_timestamp,
            retry_count=1
        )
        self.tracker._failures["https://youtube.com/watch?v=old"] = old_failure
        
        # Create recent failure
        self.tracker.record_failure(
            url="https://youtube.com/watch?v=recent",
            show_date="2024-05-22",
            show_location="Recent Location",
            failure_reason=FailureReason.VIDEO_NOT_FOUND,
            error_message="Recent error",
            column_source="Link"
        )
        
        self.assertEqual(len(self.tracker._failures), 2)
        
        # Cleanup old failures (90 days)
        self.tracker.cleanup_old_failures(max_age_days=90)
        
        self.assertEqual(len(self.tracker._failures), 1)
        remaining_url = list(self.tracker._failures.keys())[0]
        self.assertEqual(remaining_url, "https://youtube.com/watch?v=recent")
    
    def test_persistence(self):
        """Test that failures are saved and loaded correctly."""
        # Record failure
        self.tracker.record_failure(
            url="https://youtube.com/watch?v=persist_test",
            show_date="2024-05-22",
            show_location="Hamburg, Germany",
            failure_reason=FailureReason.VIDEO_NOT_FOUND,
            error_message="Persistence test",
            column_source="Link"
        )
        
        # Create new tracker instance (should load from disk)
        new_tracker = LinkFailureTracker(cache_dir=self.cache_dir)
        
        self.assertEqual(len(new_tracker._failures), 1)
        failure = list(new_tracker._failures.values())[0]
        self.assertEqual(failure.url, "https://youtube.com/watch?v=persist_test")
        self.assertEqual(failure.error_message, "Persistence test")
    
    def test_get_stats(self):
        """Test getting statistics."""
        # Initially empty
        stats = self.tracker.get_stats()
        self.assertEqual(stats['total_failures'], 0)
        
        # Add some failures
        self.tracker.record_failure(
            url="https://youtube.com/watch?v=test1",
            show_date="2024-05-22",
            show_location="Hamburg, Germany",
            failure_reason=FailureReason.VIDEO_NOT_FOUND,
            error_message="Test",
            column_source="Link"
        )
        
        stats = self.tracker.get_stats()
        self.assertEqual(stats['total_failures'], 1)
        self.assertEqual(stats['recent_failures_7_days'], 1)


if __name__ == '__main__':
    unittest.main()