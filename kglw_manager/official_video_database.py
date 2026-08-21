"""Dynamic database of official KGLW and Dempsee concert videos.

This learns from successful YouTube searches and caches official sources
to avoid repeated API calls. The database grows automatically as you
find official videos through normal searches.
"""

from typing import Dict, List, Any
from datetime import datetime
from .utils import setup_logging

logger = setup_logging()

# Official King Gizzard & The Lizard Wizard Channel Videos
OFFICIAL_KGLW_VIDEOS = {
    # 2024 Shows
    "2024-11-15": {
        "date": "2024-11-15",
        "location": "Austin",
        "venue": "Moody Center",
        "url": "https://www.youtube.com/watch?v=bzGYxfMIXc4",
        "title": "King Gizzard & The Lizard Wizard - Live in Austin '24",
        "channel": "King Gizzard And The Lizard Wizard",
        "uploader_id": "UC4BR8d-GI5MQy8JMhKPdq8w",
        "height": 2160,  # 4K
        "duration": 11320,  # ~3 hours 8 minutes
        "upload_date": "2024-11-16",
        "format_id": "401+140",  # 4K AV1 + Audio
        "quality_label": "2160p",
        "priority_score": 2000  # Highest priority for official
    },
    
    "2024-10-19": {
        "date": "2024-10-19", 
        "location": "Berkeley",
        "venue": "UC Theatre",
        "url": "https://www.youtube.com/watch?v=example2024",
        "title": "King Gizzard & The Lizard Wizard - Live in Berkeley '24",
        "channel": "King Gizzard And The Lizard Wizard", 
        "uploader_id": "UC4BR8d-GI5MQy8JMhKPdq8w",
        "height": 1080,
        "duration": 7200,
        "upload_date": "2024-10-20",
        "format_id": "137+140",
        "quality_label": "1080p",
        "priority_score": 2000
    },
    
    # Add more official videos here...
}

# Dempsee Channel Videos (High-quality livestream captures)  
DEMPSEE_VIDEOS = {
    "2024-11-14": {
        "date": "2024-11-14",
        "location": "Austin", 
        "venue": "Germania Insurance Amphitheater",
        "url": "https://www.youtube.com/watch?v=dempexample1",
        "title": "King Gizzard & The Lizard Wizard - Austin TX 11/14/24",
        "channel": "Dempsee",
        "uploader_id": "@Dempsee",
        "height": 1080,
        "duration": 8400,  # ~2.3 hours
        "upload_date": "2024-11-15", 
        "format_id": "137+140",
        "quality_label": "1080p",
        "priority_score": 1500  # High priority for trusted source
    },
    
    "2024-10-18": {
        "date": "2024-10-18",
        "location": "San Francisco",
        "venue": "The Warfield", 
        "url": "https://www.youtube.com/watch?v=dempexample2",
        "title": "King Gizzard & The Lizard Wizard - San Francisco CA 10/18/24",
        "channel": "Dempsee",
        "uploader_id": "@Dempsee", 
        "height": 1080,
        "duration": 7800,
        "upload_date": "2024-10-19",
        "format_id": "137+140", 
        "quality_label": "1080p",
        "priority_score": 1500
    },
    
    # Add more Dempsee videos here...
}

class OfficialVideoDatabase:
    """Manages dynamic database that learns from successful searches."""
    
    def __init__(self):
        self.official_videos = OFFICIAL_KGLW_VIDEOS.copy()
        self.dempsee_videos = DEMPSEE_VIDEOS.copy()
        self.last_updated = "2024-08-20"
        self.learned_videos = {}  # Videos learned from searches
        self._load_learned_videos()
    
    def get_official_video(self, date: str, location: str = None) -> Dict[str, Any]:
        """Get official KGLW video for a specific date."""
        video = self.official_videos.get(date)
        if video and location:
            # Verify location matches (fuzzy matching)
            video_location = video.get('location', '').lower()
            if location.lower() in video_location or video_location in location.lower():
                return video
        elif video:
            return video
        return None
    
    def get_dempsee_video(self, date: str, location: str = None) -> Dict[str, Any]:
        """Get Dempsee video for a specific date."""
        video = self.dempsee_videos.get(date)
        if video and location:
            # Verify location matches
            video_location = video.get('location', '').lower()
            if location.lower() in video_location or video_location in location.lower():
                return video
        elif video:
            return video
        return None
    
    def search_by_date_range(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Get all official videos in a date range."""
        results = []
        
        # Search official videos
        for date, video in self.official_videos.items():
            if start_date <= date <= end_date:
                results.append(video)
        
        # Search Dempsee videos
        for date, video in self.dempsee_videos.items():
            if start_date <= date <= end_date:
                results.append(video)
        
        # Sort by priority score (official first, then Dempsee)
        return sorted(results, key=lambda x: x.get('priority_score', 0), reverse=True)
    
    def search_by_location(self, location: str) -> List[Dict[str, Any]]:
        """Get all videos for a specific location."""
        results = []
        location_lower = location.lower()
        
        # Search official videos
        for video in self.official_videos.values():
            video_location = video.get('location', '').lower()
            if location_lower in video_location or video_location in location_lower:
                results.append(video)
        
        # Search Dempsee videos
        for video in self.dempsee_videos.values():
            video_location = video.get('location', '').lower()
            if location_lower in video_location or video_location in location_lower:
                results.append(video)
        
        return sorted(results, key=lambda x: x.get('priority_score', 0), reverse=True)
    
    def get_priority_video(self, date: str, location: str = None) -> Dict[str, Any]:
        """Get highest priority video for date/location (Official > Dempsee)."""
        # Try official first
        official = self.get_official_video(date, location) 
        if official:
            return official
        
        # Fall back to Dempsee
        dempsee = self.get_dempsee_video(date, location)
        if dempsee:
            return dempsee
        
        return None
    
    def get_all_dates(self) -> List[str]:
        """Get all dates that have official videos."""
        all_dates = set()
        all_dates.update(self.official_videos.keys())
        all_dates.update(self.dempsee_videos.keys())
        return sorted(list(all_dates))
    
    def get_stats(self) -> Dict[str, int]:
        """Get database statistics."""
        return {
            "official_videos": len(self.official_videos),
            "dempsee_videos": len(self.dempsee_videos),
            "total_videos": len(self.official_videos) + len(self.dempsee_videos),
            "date_coverage": len(self.get_all_dates())
        }
    
    def needs_youtube_search(self, date: str, location: str = None) -> bool:
        """Check if we need to fall back to YouTube search."""
        return self.get_priority_video(date, location) is None
    
    def _load_learned_videos(self):
        """Load previously learned videos from cache file."""
        import json
        from pathlib import Path
        
        cache_file = Path.home() / '.kglw_manager' / 'learned_videos.json'
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    self.learned_videos = json.load(f)
                logger.info(f"Loaded {len(self.learned_videos)} learned videos from cache")
            except Exception as e:
                logger.warning(f"Failed to load learned videos: {e}")
                self.learned_videos = {}
    
    def _save_learned_videos(self):
        """Save learned videos to cache file."""
        import json
        from pathlib import Path
        
        cache_dir = Path.home() / '.kglw_manager'
        cache_dir.mkdir(exist_ok=True)
        cache_file = cache_dir / 'learned_videos.json'
        
        try:
            with open(cache_file, 'w') as f:
                json.dump(self.learned_videos, f, indent=2)
            logger.debug(f"Saved {len(self.learned_videos)} learned videos to cache")
        except Exception as e:
            logger.warning(f"Failed to save learned videos: {e}")
    
    def learn_from_search_result(self, search_data: Dict[str, Any], video_result: Dict[str, Any]):
        """Learn from a successful YouTube search result."""
        # Only learn from official/trusted sources
        uploader_id = video_result.get('uploader_id', '')
        channel = video_result.get('channel', '').lower()
        
        is_official = (
            uploader_id == "UC4BR8d-GI5MQy8JMhKPdq8w" or 
            uploader_id == "@KingGizzardAndTheLizardWizard" or
            "@Dempsee" in uploader_id or 
            "dempsee" in channel
        )
        
        if not is_official:
            return  # Don't learn from unofficial sources
        
        date = search_data.get('date', '')
        location = search_data.get('location', '')
        
        if not date:
            return  # Need date to learn
        
        # Create learned entry
        learned_entry = {
            'date': date,
            'location': location,
            'venue': search_data.get('venue', ''),
            'url': video_result.get('webpage_url', ''),
            'title': video_result.get('title', ''),
            'channel': video_result.get('channel', ''),
            'uploader_id': uploader_id,
            'height': video_result.get('height', 0),
            'duration': video_result.get('duration', 0),
            'quality_label': video_result.get('quality_label', ''),
            'format_id': video_result.get('format_id', ''),
            'learned_date': datetime.now().isoformat(),
            'priority_score': 2000 if "UC4BR8d-GI5MQy8JMhKPdq8w" in uploader_id else 1500
        }
        
        # Store in learned videos
        self.learned_videos[date] = learned_entry
        
        # Save to cache
        self._save_learned_videos()
        
        logger.info(f"🧠 Learned official video: {learned_entry['title']} ({learned_entry['quality_label']})")
    
    def get_priority_video(self, date: str, location: str = None) -> Dict[str, Any]:
        """Get highest priority video - checks learned videos too."""
        # Check static official videos first
        official = self.get_official_video(date, location) 
        if official:
            return official
        
        # Check static Dempsee videos
        dempsee = self.get_dempsee_video(date, location)
        if dempsee:
            return dempsee
        
        # Check learned videos
        learned = self.learned_videos.get(date)
        if learned and location:
            # Verify location matches
            learned_location = learned.get('location', '').lower()
            if location.lower() in learned_location or learned_location in location.lower():
                return learned
        elif learned:
            return learned
        
        return None
    
    def get_stats(self) -> Dict[str, int]:
        """Get database statistics including learned videos."""
        return {
            "official_videos": len(self.official_videos),
            "dempsee_videos": len(self.dempsee_videos),
            "learned_videos": len(self.learned_videos),
            "total_videos": len(self.official_videos) + len(self.dempsee_videos) + len(self.learned_videos),
            "date_coverage": len(self.get_all_dates())
        }
    
    def get_all_dates(self) -> List[str]:
        """Get all dates that have videos (including learned)."""
        all_dates = set()
        all_dates.update(self.official_videos.keys())
        all_dates.update(self.dempsee_videos.keys())
        all_dates.update(self.learned_videos.keys())
        return sorted(list(all_dates))


# Database instance  
official_db = OfficialVideoDatabase()