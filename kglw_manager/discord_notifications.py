"""Discord notifications for KGLW Manager events."""

import json
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from .utils import setup_logging
from .sources import KGLWNetSource

logger = setup_logging()


class DiscordNotifier:
    """Handles Discord webhook notifications for KGLW Manager events."""
    
    def __init__(self, webhook_url: Optional[str] = None):
        """Initialize Discord notifier with webhook URL."""
        self.webhook_url = webhook_url
        self.enabled = bool(webhook_url)
        self.kglw_source = KGLWNetSource()
        
        if not self.enabled:
            logger.info("Discord notifications disabled - no webhook URL provided")
    
    def _send_webhook(self, payload: Dict[str, Any]) -> bool:
        """Send payload to Discord webhook."""
        if not self.enabled:
            return False
            
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            response.raise_for_status()
            logger.debug("Discord notification sent successfully")
            return True
            
        except requests.RequestException as e:
            logger.error(f"Failed to send Discord notification: {e}")
            return False
    
    def notify_show_upgraded(self, show_info: Dict[str, Any], upgrade_reasons: List[str], 
                           candidate_info: Dict[str, Any]) -> bool:
        """Send notification when a show is upgraded."""
        if not self.enabled:
            return False
        
        show_date = show_info.get('date', 'Unknown Date')
        show_location = show_info.get('location', 'Unknown Location')
        show_venue = show_info.get('venue', '')
        tour = show_info.get('tour', 'Unknown Tour')
        
        # Format venue information
        venue_text = f" ({show_venue})" if show_venue else ""
        
        # Format upgrade reasons
        reasons_text = "\n".join([f"• {reason}" for reason in upgrade_reasons])
        
        # Format candidate information
        candidate_title = candidate_info.get('title', 'Unknown Video')
        candidate_height = candidate_info.get('height') or 0
        candidate_duration = candidate_info.get('duration') or 0
        candidate_uploader = candidate_info.get('uploader', 'Unknown')
        candidate_url = candidate_info.get('webpage_url', '')
        is_playlist = candidate_info.get('is_playlist', False)
        
        # Format quality with effective download quality
        effective_quality = candidate_info.get('effective_quality', candidate_height)
        if candidate_height > 0:
            if effective_quality != candidate_height and effective_quality > 0:
                quality_str = f"{candidate_height}p → {effective_quality}p"
            else:
                quality_str = f"{candidate_height}p"
            if is_playlist:
                quality_str += " (Playlist)"
        elif is_playlist:
            quality_str = "Playlist"
        else:
            quality_str = "Unknown quality"
        
        # Format duration
        if candidate_duration > 0:
            duration_hours = candidate_duration // 3600
            duration_minutes = (candidate_duration % 3600) // 60
            if duration_hours > 0:
                duration_str = f"{duration_hours}h {duration_minutes}min"
            else:
                duration_str = f"{duration_minutes}min"
        else:
            duration_str = "Unknown length"
        
        # Get poster and setlist from kglw.net API
        poster_url = self.kglw_source.get_show_poster(show_date)
        setlist_summary = self.kglw_source.get_show_setlist_summary(show_date)
        
        # Create Discord embed
        embed = {
            "title": "🔄 Show Upgraded",
            "description": f"**{show_date} - {show_location}**{venue_text}",
            "color": 0x00ff00,  # Green
            "fields": [
                {
                    "name": "🎫 Tour",
                    "value": tour,
                    "inline": True
                },
                {
                    "name": "📹 New Source" if not is_playlist else "🎬 New Source (Playlist)",
                    "value": f"{candidate_title}\n**{quality_str}** • **{duration_str}** • {candidate_uploader}",
                    "inline": False
                },
                {
                    "name": "📝 Upgrade Reasons",
                    "value": reasons_text if reasons_text else "Quality improvement",
                    "inline": False
                }
            ],
            "timestamp": datetime.now().isoformat(),
            "footer": {
                "text": "KGLW Manager"
            }
        }
        
        # Add setlist information if available
        if setlist_summary:
            total_songs = setlist_summary.get('total_songs', 0)
            sets = setlist_summary.get('sets', {})
            set_count = len(sets)
            
            setlist_text = f"**{total_songs} songs** across **{set_count} set{'s' if set_count != 1 else ''}**"
            
            # Add a few highlight songs from Set 1. The API returns setnumber
            # as a string ('1'), so check both key types.
            first_set = sets.get('1') or sets.get(1) or []
            if len(first_set) > 0:
                highlights = first_set[:5]  # First 5 songs
                song_names = [song['name'] for song in highlights]
                if len(first_set) > 5:
                    setlist_text += f"\n🎵 {', '.join(song_names)}..."
                else:
                    setlist_text += f"\n🎵 {', '.join(song_names)}"
            
            # Add link to full setlist if permalink is available
            permalink = setlist_summary.get('permalink', '')
            if permalink:
                # Construct full URL if permalink is relative
                if permalink.startswith('http'):
                    full_url = permalink
                else:
                    full_url = f"https://kglw.net/setlists/{permalink}"
                setlist_text += f"\n🔗 [View Full Setlist]({full_url})"
            
            embed["fields"].append({
                "name": "🎼 Setlist",
                "value": setlist_text,
                "inline": False
            })
        
        # Add poster image if available
        if poster_url:
            embed["image"] = {"url": poster_url}
        
        # Add URL if available
        if candidate_url:
            embed["url"] = candidate_url
        
        payload = {
            "embeds": [embed],
            "username": "KGLW Manager"
        }
        
        return self._send_webhook(payload)
    
    def notify_new_show_added(self, show_info: Dict[str, Any], candidate_info: Optional[Dict[str, Any]] = None) -> bool:
        """Send notification when a new show is detected."""
        if not self.enabled:
            return False
        
        show_date = show_info.get('date', 'Unknown Date')
        show_location = show_info.get('location', 'Unknown Location')
        show_venue = show_info.get('venue', '')
        tour = show_info.get('tour', 'Unknown Tour')
        files = show_info.get('files', [])
        
        # Format venue information
        venue_text = f" ({show_venue})" if show_venue else ""
        
        # Get file information
        file_count = len(files)
        file_info = []
        
        # Only show file information if there are actual local files
        if file_count > 0:
            for file_data in files[:3]:  # Show up to 3 files
                height = file_data.get('height') or 0 or file_data.get('quality', 0)
                duration = file_data.get('duration') or 0
                filename = file_data.get('filename', '')
                
                # Format quality
                if height and str(height).replace('p', '').isdigit():
                    quality_str = f"{str(height).replace('p', '')}p"
                elif height:
                    quality_str = str(height)
                else:
                    quality_str = "Unknown"
                
                # Format duration
                if duration > 0:
                    duration_hours = duration // 3600
                    duration_minutes = (duration % 3600) // 60
                    if duration_hours > 0:
                        duration_str = f"{duration_hours}h {duration_minutes}min"
                    else:
                        duration_str = f"{duration_minutes}min"
                else:
                    duration_str = "Unknown length"
                
                # Include filename for context if available
                file_display = f"**{quality_str}** • **{duration_str}**"
                if filename:
                    file_display += f"\n`{filename[:50]}{'...' if len(filename) > 50 else ''}`"
                
                file_info.append(file_display)
            
            # Add "and X more" if there are more files
            if file_count > 3:
                file_info.append(f"and {file_count - 3} more...")
            
            files_text = "\n".join(file_info)
        else:
            # For new API shows without local files, don't show confusing file info
            files_text = None
        
        # Get poster and setlist from kglw.net API
        poster_url = self.kglw_source.get_show_poster(show_date)
        setlist_summary = self.kglw_source.get_show_setlist_summary(show_date)
        
        # Create Discord embed
        embed = {
            "title": "✨ New Show Added",
            "description": f"**{show_date} - {show_location}**{venue_text}",
            "color": 0x0099ff,  # Blue
            "fields": [
                {
                    "name": "🎫 Tour",
                    "value": tour,
                    "inline": True
                }
            ],
            "timestamp": datetime.now().isoformat(),
            "footer": {
                "text": "KGLW Manager"
            }
        }
        
        # Add file or candidate information
        if files_text is not None:
            # Show local files if they exist
            embed["fields"].append({
                "name": f"📹 Files ({file_count})",
                "value": files_text,
                "inline": False
            })
        elif candidate_info:
            # Show candidate video info for new API-detected shows
            candidate_title = candidate_info.get('title', 'Unknown Video')
            candidate_height = candidate_info.get('height') or 0
            candidate_duration = candidate_info.get('duration') or 0
            candidate_uploader = candidate_info.get('uploader', 'Unknown')
            is_playlist = candidate_info.get('is_playlist', False)
            
            # Format quality with effective download quality
            effective_quality = candidate_info.get('effective_quality', candidate_height)
            if candidate_height > 0:
                if effective_quality != candidate_height and effective_quality > 0:
                    quality_str = f"{candidate_height}p → {effective_quality}p"
                else:
                    quality_str = f"{candidate_height}p"
                if is_playlist:
                    quality_str += " (Playlist)"
            elif is_playlist:
                quality_str = "Playlist"
            else:
                quality_str = "Unknown quality"
            
            # Format duration
            if candidate_duration > 0:
                duration_hours = candidate_duration // 3600
                duration_minutes = (candidate_duration % 3600) // 60
                if duration_hours > 0:
                    duration_str = f"{duration_hours}h {duration_minutes}min"
                else:
                    duration_str = f"{duration_minutes}min"
            else:
                duration_str = "Unknown length"
            
            candidate_display = f"**{quality_str}** • **{duration_str}**\n{candidate_uploader}"
            
            embed["fields"].append({
                "name": "🎬 Available Source",
                "value": candidate_display,
                "inline": False
            })
        else:
            # For API-detected shows without candidate info, indicate it's available for download
            embed["fields"].append({
                "name": "📥 Status",
                "value": "New show detected - available for download",
                "inline": False
            })
        
        # Add setlist information if available
        if setlist_summary:
            total_songs = setlist_summary.get('total_songs', 0)
            sets = setlist_summary.get('sets', {})
            set_count = len(sets)
            
            setlist_text = f"**{total_songs} songs** across **{set_count} set{'s' if set_count != 1 else ''}**"
            
            # Add a few highlight songs from Set 1. The API returns setnumber
            # as a string ('1'), so check both key types.
            first_set = sets.get('1') or sets.get(1) or []
            if len(first_set) > 0:
                highlights = first_set[:5]  # First 5 songs
                song_names = [song['name'] for song in highlights]
                if len(first_set) > 5:
                    setlist_text += f"\n🎵 {', '.join(song_names)}..."
                else:
                    setlist_text += f"\n🎵 {', '.join(song_names)}"
            
            # Add link to full setlist if permalink is available
            permalink = setlist_summary.get('permalink', '')
            if permalink:
                # Construct full URL if permalink is relative
                if permalink.startswith('http'):
                    full_url = permalink
                else:
                    full_url = f"https://kglw.net/setlists/{permalink}"
                setlist_text += f"\n🔗 [View Full Setlist]({full_url})"
            
            embed["fields"].append({
                "name": "🎼 Setlist",
                "value": setlist_text,
                "inline": False
            })
        
        # Add poster image if available
        if poster_url:
            embed["image"] = {"url": poster_url}
        
        payload = {
            "embeds": [embed],
            "username": "KGLW Manager"
        }
        
        return self._send_webhook(payload)
    
    def notify_bulk_upgrade_summary(self, upgraded_count: int, failed_count: int, 
                                  total_candidates: int) -> bool:
        """Send summary notification for bulk upgrade operations."""
        if not self.enabled:
            return False
        
        success_rate = (upgraded_count / total_candidates * 100) if total_candidates > 0 else 0
        
        # Choose color based on success rate
        if success_rate >= 80:
            color = 0x00ff00  # Green
            emoji = "🎉"
        elif success_rate >= 50:
            color = 0xffaa00  # Orange
            emoji = "⚡"
        else:
            color = 0xff0000  # Red
            emoji = "⚠️"
        
        embed = {
            "title": f"{emoji} Bulk Upgrade Complete",
            "description": f"Processed {total_candidates} upgrade candidate{'s' if total_candidates != 1 else ''}",
            "color": color,
            "fields": [
                {
                    "name": "✅ Successfully Upgraded",
                    "value": str(upgraded_count),
                    "inline": True
                },
                {
                    "name": "❌ Failed",
                    "value": str(failed_count),
                    "inline": True
                },
                {
                    "name": "📊 Success Rate",
                    "value": f"{success_rate:.1f}%",
                    "inline": True
                }
            ],
            "timestamp": datetime.now().isoformat(),
            "footer": {
                "text": "KGLW Manager"
            }
        }
        
        payload = {
            "embeds": [embed],
            "username": "KGLW Manager"
        }
        
        return self._send_webhook(payload)
    
    def test_notification(self) -> bool:
        """Send a test notification to verify webhook is working."""
        if not self.enabled:
            logger.warning("Cannot send test notification - Discord notifications disabled")
            return False
        
        embed = {
            "title": "🧪 Test Notification",
            "description": "Discord notifications are working correctly!",
            "color": 0x7289da,  # Discord blurple
            "timestamp": datetime.now().isoformat(),
            "footer": {
                "text": "KGLW Manager"
            }
        }
        
        payload = {
            "embeds": [embed],
            "username": "KGLW Manager"
        }
        
        success = self._send_webhook(payload)
        if success:
            logger.info("Test Discord notification sent successfully")
        else:
            logger.error("Test Discord notification failed")
        
        return success