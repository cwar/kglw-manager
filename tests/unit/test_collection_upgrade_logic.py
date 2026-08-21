"""
Unit tests for collection manager upgrade logic, especially single song handling.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from kglw_manager.collection import CollectionManager


class TestCollectionUpgradeLogic:
    """Test the collection manager's upgrade decision logic."""
    
    @pytest.fixture
    def collection_manager(self, temp_collection_dir, mock_kglw_api):
        """Create a collection manager with mocked API."""
        manager = CollectionManager(str(temp_collection_dir))
        manager.kglw_api = mock_kglw_api
        return manager
    
    @pytest.mark.unit
    def test_same_song_insufficient_improvement(self, collection_manager):
        """Test that same songs with insufficient improvement are rejected."""
        # Current show with good quality Rattlesnake
        current_show_info = {
            'files': [{
                'title': 'Rattlesnake - King Gizzard HD Recording',
                'quality': '720p',
                'duration': 450
            }]
        }
        
        # Candidate with minimal improvement
        candidate = {
            'title': 'KGLW Rattlesnake Live',
            'height': 780,  # Only 60p improvement
            'duration': 460  # Only 10s improvement
        }
        
        analysis = {
            'max_quality': 720,
            'min_duration': 450,
            'has_phone_recording': False
        }
        
        is_upgrade, reason = collection_manager._is_meaningful_upgrade(
            current_show_info, candidate, analysis
        )
        
        assert is_upgrade is False
        assert "Same song" in reason
        assert "Rattlesnake" in reason
        assert "240p+ or 5min+" in reason
    
    @pytest.mark.unit
    def test_same_song_significant_improvement(self, collection_manager):
        """Test that same songs with significant improvement are accepted."""
        # Current show with low quality Rattlesnake
        current_show_info = {
            'files': [{
                'title': 'King Gizzard - Rattlesnake - Phone Recording',
                'quality': '480p',
                'duration': 420
            }]
        }
        
        # Candidate with significant improvement
        candidate = {
            'title': 'Rattlesnake - KGLW HD Recording',
            'height': 1080,  # 600p improvement
            'duration': 430
        }
        
        analysis = {
            'max_quality': 480,
            'min_duration': 420,
            'has_phone_recording': True
        }
        
        is_upgrade, reason = collection_manager._is_meaningful_upgrade(
            current_show_info, candidate, analysis
        )
        
        assert is_upgrade is True
        assert reason == ""  # No rejection reason
    
    @pytest.mark.unit
    def test_different_songs_collection(self, collection_manager):
        """Test that different songs are always collected."""
        # Current show with Rattlesnake
        current_show_info = {
            'files': [{
                'title': 'King Gizzard - Rattlesnake - Live Austin 2024',
                'quality': '720p',
                'duration': 450
            }]
        }
        
        # Candidate with Nuclear Fusion (different song, lower quality)
        candidate = {
            'title': 'Nuclear Fusion - KGLW Live Austin 2024',
            'height': 480,  # Lower quality
            'duration': 380  # Shorter duration
        }
        
        analysis = {
            'max_quality': 720,
            'min_duration': 450,
            'has_phone_recording': False
        }
        
        is_upgrade, reason = collection_manager._is_meaningful_upgrade(
            current_show_info, candidate, analysis
        )
        
        assert is_upgrade is True
        assert reason == ""  # No rejection reason
    
    @pytest.mark.unit
    def test_audio_only_content_detection(self, collection_manager):
        """Test audio-only content detection and handling."""
        # Current show with video content
        current_show_info = {
            'files': [{
                'title': 'King Gizzard - Live Show - Full Video',
                'quality': '720p',
                'duration': 4800
            }]
        }
        
        # Candidate with audio-only content
        candidate = {
            'title': 'KGLW Live Show - Audio Only',
            'height': 1080,  # Higher quality but audio-only
            'duration': 5000
        }
        
        analysis = {
            'max_quality': 720,
            'min_duration': 4800,
            'has_phone_recording': False
        }
        
        is_upgrade, reason = collection_manager._is_meaningful_upgrade(
            current_show_info, candidate, analysis
        )
        
        assert is_upgrade is False
        assert "audio-only" in reason.lower()
    
    @pytest.mark.unit
    def test_audio_only_to_video_upgrade(self, collection_manager):
        """Test that audio-only content is always upgraded to video."""
        # Current show with audio-only content
        current_show_info = {
            'files': [{
                'title': 'King Gizzard - Live Show - Audio Only',
                'quality': '720p',
                'duration': 4800
            }]
        }
        
        # Candidate with video content (even lower quality)
        candidate = {
            'title': 'KGLW Live Show - Video Recording',
            'height': 480,  # Lower quality but has video
            'duration': 4500
        }
        
        analysis = {
            'max_quality': 720,
            'min_duration': 4800,
            'has_phone_recording': False
        }
        
        is_upgrade, reason = collection_manager._is_meaningful_upgrade(
            current_show_info, candidate, analysis
        )
        
        assert is_upgrade is True
        assert reason == ""  # Any video is better than audio-only
    
    @pytest.mark.unit
    def test_incomplete_content_detection(self, collection_manager):
        """Test incomplete content detection."""
        # Current show with good content
        current_show_info = {
            'files': [{
                'title': 'King Gizzard - Full Show',
                'quality': '720p',
                'duration': 4800
            }]
        }
        
        # Candidate marked as incomplete
        candidate = {
            'title': 'KGLW Live - Last 30 Minutes Only',
            'height': 1080,
            'duration': 1800  # Only 30 minutes
        }
        
        analysis = {
            'max_quality': 720,
            'min_duration': 4800,
            'has_phone_recording': False
        }
        
        is_upgrade, reason = collection_manager._is_meaningful_upgrade(
            current_show_info, candidate, analysis
        )
        
        assert is_upgrade is False
        assert "incomplete" in reason.lower()
    
    @pytest.mark.unit
    def test_duration_category_logic(self, collection_manager):
        """Test duration categorization logic."""
        # Single song -> Full show: should upgrade
        current_show_info = {
            'files': [{'title': 'Rattlesnake Single', 'quality': '720p', 'duration': 450}]  # 7.5 min
        }
        candidate = {
            'title': 'Full King Gizzard Concert',
            'height': 720,
            'duration': 4800  # 80 minutes
        }
        analysis = {'max_quality': 720, 'min_duration': 450, 'has_phone_recording': False}
        
        is_upgrade, reason = collection_manager._is_meaningful_upgrade(
            current_show_info, candidate, analysis
        )
        assert is_upgrade is True
        
        # Full show -> Single song: should not upgrade
        current_show_info = {
            'files': [{'title': 'Full Show', 'quality': '720p', 'duration': 4800}]  # 80 minutes
        }
        candidate = {
            'title': 'Just Rattlesnake',
            'height': 1080,
            'duration': 450  # 7.5 minutes
        }
        analysis = {'max_quality': 720, 'min_duration': 4800, 'has_phone_recording': False}
        
        is_upgrade, reason = collection_manager._is_meaningful_upgrade(
            current_show_info, candidate, analysis
        )
        assert is_upgrade is False
        assert "downgrade from full show" in reason
    
    @pytest.mark.unit
    def test_get_song_label_for_video(self, collection_manager, mock_kglw_api):
        """Test song labeling functionality."""
        # Test single song labeling
        video_info = {
            'title': 'King Gizzard - Rattlesnake - Live 2024',
            'duration': 450  # 7.5 minutes
        }
        
        label = collection_manager.get_song_label_for_video(video_info)
        assert label == " (Rattlesnake)"
        
        # Test full show (no labeling)
        video_info = {
            'title': 'King Gizzard - Full Show 2024',
            'duration': 4800  # 80 minutes
        }
        
        label = collection_manager.get_song_label_for_video(video_info)
        assert label == ""
        
        # Test original song labeling with Nuclear Fusion (already mocked)
        video_info = {
            'title': 'Nuclear Fusion - Live Recording',
            'duration': 600  # 10 minutes
        }
        
        label = collection_manager.get_song_label_for_video(video_info)
        assert label == " (Nuclear Fusion)"
    
    @pytest.mark.unit
    def test_identify_and_label_song(self, collection_manager, mock_kglw_api):
        """Test song identification and labeling."""
        # Test successful identification
        video_info = {
            'title': 'Nuclear Fusion - Live Recording',
            'duration': 600  # 10 minutes
        }
        
        song_info = collection_manager.identify_and_label_song(video_info)
        
        assert song_info is not None
        assert song_info['song_name'] == 'Nuclear Fusion'
        assert song_info['duration'] == 600
        assert song_info['is_original'] is True
        
        # Test with video too long (should return None)
        video_info = {
            'title': 'Full Concert Recording',
            'duration': 5400  # 90 minutes
        }
        
        song_info = collection_manager.identify_and_label_song(video_info)
        assert song_info is None
        
        # Test with unidentifiable song
        mock_kglw_api.identify_song_from_title.return_value = None
        
        video_info = {
            'title': 'Unknown Song Title',
            'duration': 300  # 5 minutes
        }
        
        song_info = collection_manager.identify_and_label_song(video_info)
        assert song_info is None