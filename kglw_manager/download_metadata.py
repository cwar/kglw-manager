"""Download metadata detection and management."""

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from .utils import setup_logging

logger = setup_logging()


class DownloadMetadataDetector:
    """Detect and analyze metadata about downloads for better collection management."""
    
    # Known uploader categories and their characteristics
    UPLOADER_PROFILES = {
        'VHSnotdead AR': {
            'style': 'VHS Aesthetic',
            'description': 'Stylized retro VHS filter with vintage effects',
            'quality_note': 'Full show with added VHS aesthetic',
            'tags': ['vhs_style', 'stylized', 'retro_filter']
        },
        'Dempsee': {
            'style': 'High Quality Official',
            'description': 'Professional multi-camera recordings',
            'quality_note': 'Premium quality official recordings',
            'tags': ['official', 'multi_camera', 'high_quality']
        },
        'LuchoZappa': {
            'style': 'Amateur Recording',
            'description': 'Audience recordings with varying quality',
            'quality_note': 'Audience perspective recording',
            'tags': ['audience', 'amateur', 'phone_recording']
        },
        'nugsnet': {
            'style': 'Official Live',
            'description': 'Official live recordings from nugs.net',
            'quality_note': 'Professional audio/video quality',
            'tags': ['official', 'professional', 'nugs']
        }
    }
    
    # Song detection patterns - more specific to avoid false matches
    SONG_PATTERNS = [
        # Specific KGLW song titles (exact matches with word boundaries)
        r'\b(hot water|sleepwalker|nuclear fusion|rattlesnake|gamma knife|work this time|'
        r'people vultures|mars for the rich|planet b|self immolate|organ farmer|superbug|'
        r'venusian 1|venusian 2|perihelion|automation|minimum brain size|straws in the wind|'
        r'some of us|ontology|intrasport|oddlife|dripping tap|magenta mountain|gaia|'
        r'ambergris|sadie sorceress|persistence|the grim reaper|presumptuous|predator x|'
        r'red smoke|shanghai|dama tu cosita|antarctic|crumbling castle|fourth colour|'
        r'inner cell|loyalty|horology|tetrachromacy|searching|the castle in the air|'
        r'altered beast|alter me|billabong valley|anoxia|immune|evil death roll|'
        r'robot stop|big fig wasp|wah wah|road train|tezeta|cellophane|cold cadaver|'
        r'open water|muddy water|fishing for fishies|cyboogie|real\'s not real|'
        r'this thing|acarine|cyboogie|honey|boogieman sam|the cruel millennial|'
        r'supercell|candles|the book|seeing sounds|honey|ya love|mars for the rich|'
        r'organ farmer|superbug|venusian 1|venusian 2|perihelion|automation)\b'
        r'(?:\s+\([^)]*\))?',  # Optional parenthetical
        
        # Medley patterns  
        r'\b(?:medley|jam|suite)\b',
        
        # Set patterns
        r'\b(?:set\s+\d+|encore|full\s+show)\b',
        
        # Song transitions (only when clear patterns exist)
        r'(?:^|\s)([^/\n]{3,30})(?:\s*(?:into|>|→)\s*([^/\n]{3,30}))+(?:\s|$)',
    ]
    
    def __init__(self):
        """Initialize metadata detector."""
        pass
    
    def analyze_download_candidate(self, candidate: Dict[str, Any], 
                                 selected_quality: Optional[str] = None) -> Dict[str, Any]:
        """Analyze a download candidate and extract metadata.
        
        Args:
            candidate: Download candidate dictionary
            selected_quality: User-selected quality option (e.g. "1080p (mp4)")
            
        Returns:
            Dictionary with detected metadata
        """
        metadata = {
            'uploader_info': self._analyze_uploader(candidate, selected_quality),
            'content_analysis': self._analyze_content(candidate),
            'audio_video_analysis': self._analyze_audio_video(candidate),
            'song_detection': self._detect_songs(candidate),
            'filename_suggestions': self._generate_filename_suggestions(candidate),
            'selected_quality': selected_quality
        }
        
        return metadata
    
    def _analyze_uploader(self, candidate: Dict[str, Any], selected_quality: Optional[str] = None) -> Dict[str, Any]:
        """Analyze uploader and their typical content style."""
        uploader = candidate.get('uploader', candidate.get('channel', ''))
        
        if not uploader:
            return {'known': False}
        
        # Check against known uploader profiles
        uploader_profile = self.UPLOADER_PROFILES.get(uploader, {})
        
        if uploader_profile:
            return {
                'known': True,
                'name': uploader,
                'style': uploader_profile['style'],
                'description': uploader_profile['description'],
                'quality_note': uploader_profile['quality_note'],
                'tags': uploader_profile['tags'],
                'recommendation': self._get_uploader_recommendation(uploader_profile['tags'], selected_quality)
            }
        else:
            # Try to categorize unknown uploaders
            tags = self._categorize_unknown_uploader(uploader, candidate)
            return {
                'known': False,
                'name': uploader,
                'tags': tags,
                'recommendation': self._get_uploader_recommendation(tags, selected_quality)
            }
    
    def _analyze_content(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze video content characteristics."""
        title = candidate.get('title', '').lower()
        description = candidate.get('description', '').lower()
        duration = candidate.get('duration', 0)
        
        content_flags = []
        content_type = 'unknown'
        
        # Determine content type based on duration and title
        if duration > 0:
            if duration >= 3600:  # 1 hour+
                content_type = 'full_show'
                if 'full' in title or 'complete' in title:
                    content_flags.append('complete_show')
            elif duration >= 1800:  # 30+ minutes
                content_type = 'partial_show'
                content_flags.append('incomplete_show')
            else:  # Under 30 minutes
                content_type = 'single_song'
                content_flags.append('single_song')
        
        # Check for specific content characteristics
        if any(word in title for word in ['soundcheck', 'warm up', 'rehearsal']):
            content_flags.append('soundcheck')
        
        if any(word in title for word in ['interview', 'backstage', 'documentary']):
            content_flags.append('non_performance')
        
        if any(word in title for word in ['multicam', 'multi-cam', 'multiple angles']):
            content_flags.append('multicam')
        
        if any(word in title for word in ['bootleg', 'unauthorized', 'leaked']):
            content_flags.append('bootleg')
        
        return {
            'type': content_type,
            'flags': content_flags,
            'estimated_completeness': self._estimate_completeness(duration, title)
        }
    
    def _analyze_audio_video(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze audio/video characteristics."""
        title = candidate.get('title', '').lower()
        
        # Check for audio-only indicators
        audio_only_indicators = [
            'audio only', 'audio-only', '[audio]', '(audio)',
            'sound only', 'no video', 'listening party'
        ]
        
        audio_only = any(indicator in title for indicator in audio_only_indicators)
        
        # Check format information if available
        formats = candidate.get('formats', [])
        has_video_format = False
        has_audio_only_format = False
        
        for fmt in formats:
            if fmt.get('vcodec') and fmt.get('vcodec') != 'none':
                has_video_format = True
            if fmt.get('acodec') and fmt.get('vcodec') == 'none':
                has_audio_only_format = True
        
        return {
            'audio_only': audio_only,
            'has_video_formats': has_video_format,
            'has_audio_formats': has_audio_only_format,
            'likely_audio_only': audio_only or (has_audio_only_format and not has_video_format)
        }
    
    def _detect_songs(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Detect songs mentioned in title."""
        title = candidate.get('title', '')
        
        detected_songs = []
        song_indicators = []
        
        # Check each song pattern
        for pattern in self.SONG_PATTERNS:
            matches = re.finditer(pattern, title.lower(), re.IGNORECASE)
            for match in matches:
                song = match.group().strip()
                if song and len(song) > 2:  # Ignore very short matches
                    detected_songs.append(song.title())
        
        # Look for specific song indicators
        if 'medley' in title.lower():
            song_indicators.append('medley')
        if 'jam' in title.lower():
            song_indicators.append('jam')
        if re.search(r'\b(?:into|>|→)\b', title):
            song_indicators.append('song_transition')
        if re.search(r'[/+&-]', title):
            song_indicators.append('multiple_songs')
        
        # Estimate number of songs
        song_count_estimate = len(detected_songs) if detected_songs else self._estimate_song_count(title, candidate.get('duration', 0))
        
        return {
            'detected_songs': detected_songs,
            'indicators': song_indicators,
            'estimated_song_count': song_count_estimate,
            'likely_single_song': song_count_estimate == 1,
            'likely_multiple_songs': song_count_estimate > 1
        }
    
    def _generate_filename_suggestions(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Generate filename suggestions with metadata."""
        base_title = candidate.get('title', 'Unknown')
        uploader = candidate.get('uploader', candidate.get('channel', ''))
        
        suggestions = {}
        
        # Basic filename (current behavior)
        suggestions['basic'] = base_title
        
        # With uploader suffix
        if uploader:
            uploader_clean = re.sub(r'[^\w\s-]', '', uploader).strip()
            suggestions['with_uploader'] = f"{base_title} [{uploader_clean}]"
        
        # With style annotation
        uploader_info = self._analyze_uploader(candidate, None)
        if uploader_info.get('known') and uploader_info.get('style'):
            style = uploader_info['style'].replace(' ', '_')
            suggestions['with_style'] = f"{base_title} [_{style}]"
        
        # With audio-only indicator
        audio_video = self._analyze_audio_video(candidate)
        if audio_video.get('likely_audio_only'):
            suggestions['with_audio_flag'] = f"{base_title} [_Audio_Only]"
        
        # With song count for singles
        song_detection = self._detect_songs(candidate)
        if song_detection.get('likely_single_song') and song_detection.get('detected_songs'):
            song = song_detection['detected_songs'][0]
            suggestions['with_song'] = f"{base_title} [_{song}]"
        
        return suggestions
    
    def create_metadata_file(self, download_path: Path, candidate: Dict[str, Any], 
                           chosen_filename: str = None, show_info: Dict[str, Any] = None) -> Path:
        """Create a metadata file for the downloaded content.
        
        Args:
            download_path: Path where the download was saved
            candidate: Original candidate information
            chosen_filename: The filename that was actually used
            show_info: Show information with date, location, etc.
            
        Returns:
            Path to the created metadata file
        """
        metadata = self.analyze_download_candidate(candidate)
        
        # Get KGLW.net API information if available
        api_info = self._get_kglw_api_info(show_info) if show_info else {}
        
        # Add download-specific information
        download_metadata = {
            'download_info': {
                'original_url': candidate.get('webpage_url', ''),
                'downloaded_filename': chosen_filename or download_path.name,
                'download_date': str(candidate.get('upload_date', '')),
                'original_title': candidate.get('title', ''),
                'source': candidate.get('source', 'youtube')
            },
            'kglw_api_info': api_info,
            'analysis': metadata,
            'user_notes': {
                'quality_assessment': '',
                'completeness_notes': '',
                'user_tags': [],
                'rating': None
            }
        }
        
        # Write metadata file
        metadata_path = download_path.parent / f"{download_path.stem}.kglw_metadata.json"
        
        try:
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(download_metadata, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Created metadata file: {metadata_path}")
            return metadata_path
            
        except Exception as e:
            logger.error(f"Failed to create metadata file: {e}")
            return None
    
    def _categorize_unknown_uploader(self, uploader: str, candidate: Dict[str, Any]) -> List[str]:
        """Categorize unknown uploaders based on name patterns and content."""
        tags = []
        
        uploader_lower = uploader.lower()
        title = candidate.get('title', '').lower()
        
        # Check for official indicators
        if any(word in uploader_lower for word in ['official', 'records', 'music', 'band']):
            tags.append('likely_official')
        
        # Check for professional indicators
        if any(word in uploader_lower for word in ['hd', '4k', 'pro', 'quality']):
            tags.append('quality_focused')
        
        # Check for fan/amateur indicators
        if any(word in uploader_lower for word in ['fan', 'bootleg', 'audience', 'phone']):
            tags.append('fan_recording')
        
        # Check for regional indicators
        if re.search(r'\b[A-Z]{2}\b', uploader):  # Country codes like AR, UK, US
            tags.append('regional_uploader')
        
        return tags
    
    def _get_kglw_api_info(self, show_info: Dict[str, Any]) -> Dict[str, Any]:
        """Get KGLW.net API information for the show."""
        if not show_info or 'date' not in show_info:
            return {}
        
        try:
            from .api_tour_manager import get_tour_manager
            tour_manager = get_tour_manager()
            
            # Get comprehensive show info from API
            api_show_info = tour_manager.get_show_info_for_date(show_info['date'])
            
            if api_show_info:
                return {
                    'show_id': api_show_info.get('show_id'),
                    'tour_id': api_show_info.get('tour_id'),
                    'tour_name': api_show_info.get('tour_name'),
                    'api_venue_name': api_show_info.get('venue_name'),
                    'api_location': api_show_info.get('location'),
                    'api_city': api_show_info.get('city'),
                    'api_state': api_show_info.get('state'),
                    'api_country': api_show_info.get('country'),
                    'show_title': api_show_info.get('show_title'),
                    'permalink': api_show_info.get('permalink'),
                    'api_updated_at': api_show_info.get('updated_at'),
                    'matched_date': show_info['date'],
                    'local_location': show_info.get('location', ''),
                    'local_venue': show_info.get('venue', ''),
                    'api_match_found': True
                }
            else:
                return {
                    'show_id': None,
                    'tour_id': None,
                    'tour_name': None,
                    'matched_date': show_info['date'],
                    'local_location': show_info.get('location', ''),
                    'local_venue': show_info.get('venue', ''),
                    'api_match_found': False,
                    'note': 'No API data found for this show date'
                }
                
        except Exception as e:
            logger.warning(f"Failed to get KGLW.net API info: {e}")
            return {
                'api_match_found': False,
                'error': str(e),
                'matched_date': show_info.get('date', ''),
                'local_location': show_info.get('location', ''),
                'local_venue': show_info.get('venue', '')
            }
    
    def _get_uploader_recommendation(self, tags: List[str], selected_quality: Optional[str] = None) -> str:
        """Get recommendation based on uploader tags and selected quality."""
        # Parse selected quality to determine if it's high quality
        quality_info = ""
        if selected_quality:
            if '1080p' in selected_quality or '720p' in selected_quality:
                quality_info = f" ({selected_quality})"
            elif '480p' in selected_quality or '360p' in selected_quality:
                quality_info = f" ({selected_quality} - Lower quality)"
            elif '4K' in selected_quality or '2160p' in selected_quality:
                quality_info = f" ({selected_quality} - Ultra HD)"
        
        if 'official' in tags or 'high_quality' in tags:
            return f"Recommended - High quality official content{quality_info}"
        elif 'vhs_style' in tags or 'stylized' in tags:
            return f"Stylized - Modified with visual effects{quality_info} (check preview)"
        elif 'amateur' in tags or 'phone_recording' in tags:
            return f"Audience Recording{quality_info} - Quality may vary"
        elif 'fan_recording' in tags:
            return f"Fan Recording{quality_info} - Verify quality before download"
        else:
            base_msg = f"Good Quality{quality_info}" if quality_info else "Unknown Quality"
            return f"{base_msg} - Preview recommended"
    
    def _estimate_completeness(self, duration: int, title: str) -> str:
        """Estimate how complete the show is."""
        if duration == 0:
            return "unknown"
        
        if duration >= 7200:  # 2+ hours
            return "likely_complete"
        elif duration >= 3600:  # 1+ hour
            return "probably_complete"
        elif duration >= 1800:  # 30+ minutes
            return "partial"
        else:
            return "single_song_or_excerpt"
    
    def _estimate_song_count(self, title: str, duration: int) -> int:
        """Estimate number of songs based on title and duration."""
        if duration == 0:
            return 1
        
        # Average song length estimates
        avg_song_length = 5 * 60  # 5 minutes
        
        if duration < 15 * 60:  # Under 15 minutes
            return 1
        else:
            # Rough estimate based on duration
            estimated = max(1, duration // avg_song_length)
            return min(estimated, 20)  # Cap at reasonable number