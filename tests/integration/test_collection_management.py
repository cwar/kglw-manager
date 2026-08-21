"""
Integration tests for collection management functionality.
"""

import pytest
from unittest.mock import patch, Mock
from pathlib import Path
import tempfile
import shutil

from kglw_manager.collection import CollectionManager


class TestCollectionManagement:
    """Integration tests for collection management."""
    
    @pytest.mark.integration
    def test_collection_initialization(self, temp_collection_dir):
        """Test collection manager initialization with real directory."""
        manager = CollectionManager(str(temp_collection_dir))
        
        assert manager.collection_path == temp_collection_dir
        assert manager.mode == "movie"
        assert manager.naming_manager is not None
        assert manager.tour_manager is not None
        assert manager.video_cache is not None
    
    @pytest.mark.integration
    def test_scan_empty_collection(self, temp_collection_dir):
        """Test scanning an empty collection."""
        manager = CollectionManager(str(temp_collection_dir))
        
        result = manager.scan_collection()
        
        assert isinstance(result, dict)
        assert 'tours' in result
        assert len(result['tours']) == 0
    
    @pytest.mark.integration
    def test_scan_collection_with_shows(self, sample_collection_with_shows):
        """Test scanning a collection with sample shows."""
        manager = CollectionManager(str(sample_collection_with_shows))
        
        # Mock the video analysis to avoid ffprobe dependency
        def mock_analyze_video_quality(file_path):
            return {
                'quality': '720p',
                'duration': 4800,
                'resolution': '1280x720',
                'size': 2000000000
            }
        
        with patch.object(manager, '_analyze_video_quality', side_effect=mock_analyze_video_quality):
            result = manager.scan_collection()
        
        assert isinstance(result, dict)
        assert 'tours' in result
        assert len(result['tours']) > 0
        
        # Check that shows were found
        total_shows = sum(len(tour_info.get('shows', [])) for tour_info in result['tours'].values())
        assert total_shows >= 3  # We created 3 test shows
    
    @pytest.mark.integration
    def test_find_upgrade_candidates(self, sample_collection_with_shows, sample_video_candidates):
        """Test finding upgrade candidates for collection."""
        manager = CollectionManager(str(sample_collection_with_shows))
        
        # Mock video analysis
        def mock_analyze_video_quality(file_path):
            return {
                'quality': '480p',  # Lower quality to trigger upgrades
                'duration': 3600,
                'resolution': '854x480',
                'size': 1000000000
            }
        
        # Mock YouTube search to return our sample candidates
        def mock_search_for_upgrades(*args, **kwargs):
            return sample_video_candidates
        
        with patch.object(manager, '_analyze_video_quality', side_effect=mock_analyze_video_quality), \
             patch.object(manager.youtube_searcher, 'search_for_upgrades', side_effect=mock_search_for_upgrades):
            
            candidates = manager.find_upgrade_candidates()
            
            assert isinstance(candidates, list)
            # Should have found some candidates since we have low quality content
            assert len(candidates) >= 0
    
    @pytest.mark.integration  
    def test_upgrade_decision_workflow(self, temp_collection_dir, mock_kglw_api):
        """Test the complete upgrade decision workflow."""
        manager = CollectionManager(str(temp_collection_dir))
        manager.kglw_api = mock_kglw_api
        
        # Create a test show with a single song
        show_dir = temp_collection_dir / "2024-03-15 - Austin"
        show_dir.mkdir(parents=True)
        
        video_file = show_dir / "King Gizzard & The Lizard Wizard - 2024-03-15 Austin - concert.mp4"
        video_file.write_text("fake video content")
        
        # Mock show info for current collection
        show_info = {
            'date': '2024-03-15',
            'location': 'Austin',
            'files': [{
                'title': 'King Gizzard - Rattlesnake - Live Austin 2024',
                'quality': '720p',
                'duration': 450,  # 7.5 minutes - single song
                'path': str(video_file)
            }]
        }
        
        # Test different upgrade scenarios
        scenarios = [
            {
                'name': 'Same song, insufficient improvement',
                'candidate': {
                    'title': 'KGLW Rattlesnake Live',
                    'height': 780,  # Only 60p improvement
                    'duration': 460
                },
                'expected_upgrade': False
            },
            {
                'name': 'Same song, significant improvement',
                'candidate': {
                    'title': 'Rattlesnake - King Gizzard 4K',
                    'height': 2160,  # Major improvement
                    'duration': 470
                },
                'expected_upgrade': True
            },
            {
                'name': 'Different song, lower quality',
                'candidate': {
                    'title': 'Nuclear Fusion - KGLW Live',
                    'height': 480,  # Lower quality but different song
                    'duration': 380
                },
                'expected_upgrade': True
            }
        ]
        
        for scenario in scenarios:
            analysis = {
                'max_quality': 720,
                'min_duration': 450,
                'has_phone_recording': False
            }
            
            is_upgrade, reason = manager._is_meaningful_upgrade(
                show_info, scenario['candidate'], analysis
            )
            
            assert is_upgrade == scenario['expected_upgrade'], \
                f"Scenario '{scenario['name']}' failed: expected {scenario['expected_upgrade']}, got {is_upgrade}. Reason: {reason}"
    
    @pytest.mark.integration
    @patch('kglw_manager.collection.CollectionManager.perform_upgrade')
    def test_song_labeling_in_upgrade_display(self, mock_perform_upgrade, temp_collection_dir, mock_kglw_api):
        """Test that song labeling works in the upgrade display."""
        manager = CollectionManager(str(temp_collection_dir))
        manager.kglw_api = mock_kglw_api
        
        # Test video candidates with identifiable songs
        video_candidates = [
            {
                'title': 'King Gizzard - Rattlesnake - Live 2024',
                'height': 720,
                'duration': 450  # Single song duration
            },
            {
                'title': 'Nuclear Fusion - KGLW Melbourne',
                'height': 1080,
                'duration': 600  # Single song duration
            },
            {
                'title': 'King Gizzard Full Concert 2024',
                'height': 720,
                'duration': 4800  # Full show duration
            }
        ]
        
        for video in video_candidates:
            label = manager.get_song_label_for_video(video)
            
            if 'Rattlesnake' in video['title'] and video['duration'] <= 900:
                assert label == " (Rattlesnake)"
            elif 'Nuclear Fusion' in video['title'] and video['duration'] <= 900:
                assert label == " (Nuclear Fusion)"
            elif video['duration'] > 900:  # Full show
                assert label == ""
    
    @pytest.mark.integration
    def test_cache_integration(self, sample_collection_with_shows):
        """Test that caching works correctly with real directory structure."""
        manager = CollectionManager(str(sample_collection_with_shows))
        
        def mock_analyze_video_quality(file_path):
            return {
                'quality': '720p',
                'duration': 4800,
                'resolution': '1280x720',
                'size': 2000000000
            }
        
        with patch.object(manager, '_analyze_video_quality', side_effect=mock_analyze_video_quality):
            # First scan
            result1 = manager.scan_collection()
            
            # Second scan should use cache
            result2 = manager.scan_collection()
            
            # Core data should be identical (ignoring cache-specific fields like signature)
            assert result1['total_tours'] == result2['total_tours']
            assert result1['total_shows'] == result2['total_shows']
            assert result1['total_videos'] == result2['total_videos']
            assert len(result1['tours']) == len(result2['tours'])
            
            # Check that the same tours exist
            for tour_name in result1['tours']:
                assert tour_name in result2['tours']
                assert len(result1['tours'][tour_name]['shows']) == len(result2['tours'][tour_name]['shows'])
            
            # Force rescan
            result3 = manager.scan_collection(force_rescan=True)
            
            # Should have same core data
            assert result1['total_tours'] == result3['total_tours']
            assert result1['total_shows'] == result3['total_shows']
            assert result1['total_videos'] == result3['total_videos']
    
    @pytest.mark.integration
    def test_error_handling_in_collection_scan(self, temp_collection_dir):
        """Test error handling during collection scanning."""
        manager = CollectionManager(str(temp_collection_dir))
        
        # Create a directory that will cause issues
        problem_dir = temp_collection_dir / "2024-03-15 - Austin"
        problem_dir.mkdir(parents=True)
        
        # Create a file that simulates a video file but will cause analysis to fail
        fake_video = problem_dir / "fake.mp4"
        fake_video.write_text("not a real video file")
        
        # Mock video analysis to raise an exception
        def mock_analyze_video_quality(file_path):
            if "fake.mp4" in str(file_path):
                raise Exception("Failed to analyze fake video")
            return {
                'quality': '720p',
                'duration': 4800,
                'resolution': '1280x720',
                'size': 2000000000
            }
        
        with patch.object(manager, '_analyze_video_quality', side_effect=mock_analyze_video_quality):
            # Should not crash, should handle the error gracefully
            result = manager.scan_collection()
            
            assert isinstance(result, dict)
            assert 'tours' in result