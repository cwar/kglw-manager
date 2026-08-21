"""
Pytest configuration and shared fixtures.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock
from typing import Dict, Any, List

# Import the modules we'll be testing
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from kglw_manager.collection import CollectionManager
from kglw_manager.kglw_api import KGLWApi
from kglw_manager.naming import NamingManager
from kglw_manager.tours import TourManager


@pytest.fixture(autouse=True)
def isolate_user_spreadsheet_config(monkeypatch):
    """Keep tests independent of the developer's ~/.kglw_manager/config.json.

    CollectionManager auto-loads the configured community spreadsheet on
    construction, so whether "no spreadsheet loaded" tests passed depended on
    whether the person running them happened to have one configured.
    """
    from kglw_manager.config import config as _config

    real_get = _config.get
    overrides = {'spreadsheet_path': None, 'auto_load_spreadsheet': False}

    def isolated_get(key, default=None):
        if key in overrides:
            return overrides[key]
        return real_get(key, default)

    monkeypatch.setattr(_config, 'get', isolated_get)


@pytest.fixture
def temp_collection_dir():
    """Create a temporary directory for test collections."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def collection_manager(temp_collection_dir):
    """CollectionManager backed by a temporary collection directory.

    Shared here so test classes outside the one defining their own
    class-scoped fixture (e.g. TestCollectionIntegration) can use it.
    """
    return CollectionManager(temp_collection_dir)


@pytest.fixture
def temp_download_dir():
    """Create a temporary download directory.

    Shared here rather than class-scoped so every download test class can use
    it (several classes previously errored at setup with 'fixture not found').
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def sample_show_info():
    """Provide sample show information for testing."""
    return {
        'date': '2024-03-15',
        'location': 'Austin',
        'venue': 'Moody Center',
        'path': '/test/path/2024-03-15 - Austin',
        'files': [
            {
                'path': '/test/path/video.mp4',
                'title': 'King Gizzard - Live Austin 2024',
                'quality': '720p',
                'duration': 4800,  # 80 minutes
                'size': 2000000000  # 2GB
            }
        ]
    }


@pytest.fixture
def sample_video_candidates():
    """Provide sample video candidates for upgrade testing."""
    return [
        {
            'title': 'King Gizzard & The Lizard Wizard - Austin 2024 Full Show',
            'height': 1080,
            'duration': 5100,  # 85 minutes
            'webpage_url': 'https://youtube.com/watch?v=test1',
            'uploader': 'TestChannel1',
            'channel': 'TestChannel1'
        },
        {
            'title': 'KGLW Austin 2024 - Phone Recording',
            'height': 480,
            'duration': 4500,  # 75 minutes
            'webpage_url': 'https://youtube.com/watch?v=test2',
            'uploader': 'TestChannel2',
            'channel': 'TestChannel2'
        },
        {
            'title': 'Rattlesnake - King Gizzard Austin 2024',
            'height': 720,
            'duration': 450,  # 7.5 minutes - single song
            'webpage_url': 'https://youtube.com/watch?v=test3',
            'uploader': 'TestChannel3',
            'channel': 'TestChannel3'
        }
    ]


@pytest.fixture
def mock_kglw_api():
    """Mock KGLW API for testing without network calls."""
    mock_api = Mock(spec=KGLWApi)
    
    # Mock songs data
    mock_songs = [
        {'id': 1, 'name': 'Rattlesnake', 'isoriginal': 1, 'original_artist': 'King Gizzard & the Lizard Wizard'},
        {'id': 2, 'name': 'Nuclear Fusion', 'isoriginal': 1, 'original_artist': 'King Gizzard & the Lizard Wizard'},
        {'id': 3, 'name': 'Crumbling Castle', 'isoriginal': 1, 'original_artist': 'King Gizzard & the Lizard Wizard'},
    ]
    mock_api.get_songs.return_value = mock_songs
    
    # Mock song identification
    def mock_identify_song(title):
        title_lower = title.lower()
        if 'rattlesnake' in title_lower:
            return {'song': mock_songs[0], 'similarity': 0.9}
        elif 'nuclear fusion' in title_lower:
            return {'song': mock_songs[1], 'similarity': 0.9}
        elif 'crumbling castle' in title_lower:
            return {'song': mock_songs[2], 'similarity': 0.9}
        return None
    
    mock_api.identify_song_from_title.side_effect = mock_identify_song
    
    # Mock same song comparison
    def mock_is_same_song(title1, title2):
        song1 = mock_identify_song(title1)
        song2 = mock_identify_song(title2)
        if song1 and song2:
            is_same = song1['song']['id'] == song2['song']['id']
            return is_same, song1['song']['name']
        return False, None
    
    mock_api.is_same_song.side_effect = mock_is_same_song
    
    return mock_api


@pytest.fixture
def collection_manager_with_temp_dir(temp_collection_dir):
    """Create a CollectionManager instance with a temporary directory."""
    return CollectionManager(str(temp_collection_dir))


@pytest.fixture
def sample_tour_data():
    """Provide sample tour data for testing."""
    return {
        '2024 USA/Canada Spring': {
            'shows': {
                'show1': {
                    'date': '2024-03-14',
                    'city': 'Austin',
                    'venue': 'Moody Center'
                },
                'show2': {
                    'date': '2024-03-15',
                    'city': 'Houston',
                    'venue': 'Toyota Center'
                }
            },
            'api_show_count': 2,
            'local_show_count': 0
        }
    }


@pytest.fixture
def mock_youtube_searcher():
    """Mock YouTube searcher for testing without network calls."""
    mock_searcher = Mock()
    mock_searcher.search_youtube.return_value = []
    mock_searcher.validate_youtube_url.return_value = (True, "Valid")
    return mock_searcher


@pytest.fixture
def mock_download_manager():
    """Mock download manager for testing without actual downloads."""
    mock_manager = Mock()
    mock_manager.download_upgrade_to_existing_dir.return_value = Path('/fake/downloaded/file.mp4')
    return mock_manager


def create_test_show_directory(base_dir: Path, show_info: Dict[str, Any], tour_name: str = "2024 USA_Canada Spring") -> Path:
    """Helper function to create a test show directory with files inside a tour directory."""
    # Create tour directory first
    tour_dir = base_dir / tour_name
    tour_dir.mkdir(parents=True, exist_ok=True)
    
    # Create show directory inside tour
    show_dir = tour_dir / f"{show_info['date']} - {show_info['location']}"
    show_dir.mkdir(parents=True, exist_ok=True)
    
    # Create fake video files with unique names
    for i, file_info in enumerate(show_info.get('files', [])):
        suffix = f"_{i+1}" if i > 0 else ""  # Add suffix for multiple files
        file_path = show_dir / f"King Gizzard & The Lizard Wizard - {show_info['date']} {show_info['location']}{suffix} - concert.mp4"
        file_path.write_text(f"fake video content for {file_info['title']}")
    
    return show_dir


@pytest.fixture
def sample_collection_with_shows(temp_collection_dir, sample_show_info):
    """Create a sample collection with test show directories."""
    show_dir = create_test_show_directory(temp_collection_dir, sample_show_info)
    
    # Create additional test shows
    additional_shows = [
        {
            'date': '2024-03-16',
            'location': 'Dallas',
            'venue': 'American Airlines Center',
            'files': [{'title': 'KGLW Dallas 2024', 'quality': '480p', 'duration': 3600}]
        },
        {
            'date': '2024-03-17', 
            'location': 'Phoenix',
            'venue': 'Talking Stick Resort Arena',
            'files': [{'title': 'King Gizzard Phoenix 2024', 'quality': '1080p', 'duration': 5400}]
        }
    ]
    
    # Create shows in the same tour as the first show
    for show in additional_shows:
        create_test_show_directory(temp_collection_dir, show, tour_name="2024 USA_Canada Spring")
    
    return temp_collection_dir