"""Track and report failed YouTube links for spreadsheet maintenance."""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from enum import Enum
from dataclasses import dataclass, asdict
from .utils import setup_logging

logger = setup_logging()


class FailureReason(Enum):
    """Categorize different types of link failures."""
    VIDEO_NOT_FOUND = "video_not_found"  # 404, deleted, private
    REGION_BLOCKED = "region_blocked"  # Geographic restrictions
    COPYRIGHT_CLAIM = "copyright_claim"  # Copyright/DMCA takedown
    CHANNEL_TERMINATED = "channel_terminated"  # Channel deleted/suspended
    VIDEO_RESTRICTED = "video_restricted"  # Age restriction, member-only
    QUALITY_NOT_UPGRADE = "quality_not_upgrade"  # Video exists but not better quality
    DOWNLOAD_ERROR = "download_error"  # Technical download failure
    NETWORK_ERROR = "network_error"  # Connection issues
    UNKNOWN_ERROR = "unknown_error"  # Other/unclassified errors


@dataclass
class LinkFailure:
    """Represent a failed link with detailed information."""
    url: str
    show_date: str
    show_location: str
    failure_reason: FailureReason
    error_message: str
    column_source: str  # "Link", "Link 2", "Link 3", "Archive"
    timestamp: str
    retry_count: int = 0
    last_working: Optional[str] = None  # Last known working date
    video_title: Optional[str] = None
    uploader: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result['failure_reason'] = self.failure_reason.value
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LinkFailure':
        """Create from dictionary loaded from JSON."""
        data['failure_reason'] = FailureReason(data['failure_reason'])
        return cls(**data)


class LinkFailureTracker:
    """Track and manage failed YouTube links for reporting."""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize tracker with cache directory."""
        self.cache_dir = cache_dir or (Path.home() / '.kglw_manager' / 'link_failures')
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.failures_file = self.cache_dir / 'failed_links.json'
        self.summary_file = self.cache_dir / 'failure_summary.json'
        
        # In-memory cache
        self._failures: Dict[str, LinkFailure] = {}
        self._load_failures()
    
    def _load_failures(self):
        """Load failures from disk cache."""
        if self.failures_file.exists():
            try:
                with open(self.failures_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                for url, failure_data in data.items():
                    try:
                        self._failures[url] = LinkFailure.from_dict(failure_data)
                    except Exception as e:
                        logger.warning(f"Error loading failure record for {url}: {e}")
                        
                logger.info(f"Loaded {len(self._failures)} link failure records")
            except Exception as e:
                logger.error(f"Error loading failures file: {e}")
    
    def _save_failures(self):
        """Save failures to disk cache."""
        try:
            data = {url: failure.to_dict() for url, failure in self._failures.items()}
            
            with open(self.failures_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
            logger.debug(f"Saved {len(self._failures)} failure records")
        except Exception as e:
            logger.error(f"Error saving failures: {e}")
    
    def record_failure(self, 
                      url: str,
                      show_date: str,
                      show_location: str,
                      failure_reason: FailureReason,
                      error_message: str,
                      column_source: str = "Link",
                      video_title: Optional[str] = None,
                      uploader: Optional[str] = None):
        """Record a new link failure."""
        
        # Check if we already have this failure
        existing = self._failures.get(url)
        if existing:
            # Update existing record
            existing.retry_count += 1
            existing.timestamp = datetime.now().isoformat()
            existing.error_message = error_message  # Update with latest error
            
            # Only update reason if it's more specific
            if failure_reason != FailureReason.UNKNOWN_ERROR:
                existing.failure_reason = failure_reason
                
            logger.debug(f"Updated failure record for {url} (retry #{existing.retry_count})")
        else:
            # Create new failure record
            failure = LinkFailure(
                url=url,
                show_date=show_date,
                show_location=show_location,
                failure_reason=failure_reason,
                error_message=error_message,
                column_source=column_source,
                timestamp=datetime.now().isoformat(),
                retry_count=1,
                video_title=video_title,
                uploader=uploader
            )
            
            self._failures[url] = failure
            logger.info(f"Recorded new link failure: {url} ({failure_reason.value})")
        
        self._save_failures()
    
    def is_known_failed(self, url: str, max_age_days: int = 7) -> bool:
        """Check if a URL is known to have failed recently."""
        failure = self._failures.get(url)
        if not failure:
            return False
        
        # Check age of failure
        try:
            failure_time = datetime.fromisoformat(failure.timestamp)
            age = datetime.now() - failure_time
            
            if age.days > max_age_days:
                logger.debug(f"Failure record for {url} is {age.days} days old, will retry")
                return False
            
            # Don't retry certain permanent failures
            permanent_failures = {
                FailureReason.VIDEO_NOT_FOUND,
                FailureReason.COPYRIGHT_CLAIM,
                FailureReason.CHANNEL_TERMINATED
            }
            
            if failure.failure_reason in permanent_failures:
                logger.debug(f"Skipping {url} - permanent failure: {failure.failure_reason.value}")
                return True
            
            # Don't retry if we've tried many times recently
            if failure.retry_count >= 3 and age.days < 1:
                logger.debug(f"Skipping {url} - too many recent retries ({failure.retry_count})")
                return True
                
            return False
            
        except Exception as e:
            logger.warning(f"Error checking failure age for {url}: {e}")
            return False
    
    def classify_error(self, error_message: str, url: str = "") -> FailureReason:
        """Classify an error message into a failure reason category."""
        error_lower = error_message.lower()
        
        # Video not found patterns
        if any(phrase in error_lower for phrase in [
            "video unavailable", "does not exist", "not found", "404",
            "video has been removed", "deleted", "private video"
        ]):
            return FailureReason.VIDEO_NOT_FOUND
        
        # Region blocking
        if any(phrase in error_lower for phrase in [
            "not available in your country", "blocked in your country",
            "region", "geographic", "location"
        ]):
            return FailureReason.REGION_BLOCKED
        
        # Copyright issues
        if any(phrase in error_lower for phrase in [
            "copyright", "dmca", "content claim", "blocked on copyright",
            "removed by user", "terms of service"
        ]):
            return FailureReason.COPYRIGHT_CLAIM
        
        # Channel issues
        if any(phrase in error_lower for phrase in [
            "channel terminated", "account terminated", "channel suspended",
            "account suspended", "channel does not exist"
        ]):
            return FailureReason.CHANNEL_TERMINATED
        
        # Restricted content
        if any(phrase in error_lower for phrase in [
            "age restricted", "sign in to confirm", "restricted video",
            "members-only", "membership", "private"
        ]):
            return FailureReason.VIDEO_RESTRICTED
        
        # Network/download errors
        if any(phrase in error_lower for phrase in [
            "network", "connection", "timeout", "unable to download",
            "http error 5", "server error", "connection reset"
        ]):
            return FailureReason.NETWORK_ERROR
        
        # Quality not upgrade (custom classification)
        if "not an upgrade" in error_lower or "quality not better" in error_lower:
            return FailureReason.QUALITY_NOT_UPGRADE
        
        # Generic download error
        if any(phrase in error_lower for phrase in [
            "download", "extract", "format", "codec"
        ]):
            return FailureReason.DOWNLOAD_ERROR
        
        return FailureReason.UNKNOWN_ERROR
    
    def get_failures_by_show(self, show_date: str) -> List[LinkFailure]:
        """Get all failures for a specific show."""
        return [f for f in self._failures.values() if f.show_date == show_date]
    
    def get_failures_by_reason(self, reason: FailureReason) -> List[LinkFailure]:
        """Get all failures of a specific type."""
        return [f for f in self._failures.values() if f.failure_reason == reason]
    
    def generate_report(self, max_age_days: int = 30) -> Dict[str, Any]:
        """Generate a comprehensive failure report."""
        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        
        # Filter recent failures
        recent_failures = []
        for failure in self._failures.values():
            try:
                failure_time = datetime.fromisoformat(failure.timestamp)
                if failure_time >= cutoff_date:
                    recent_failures.append(failure)
            except ValueError:
                # Include failures with invalid timestamps
                recent_failures.append(failure)
        
        # Count by reason
        reason_counts = {}
        for reason in FailureReason:
            count = len([f for f in recent_failures if f.failure_reason == reason])
            if count > 0:
                reason_counts[reason.value] = count
        
        # Count by column source
        column_counts = {}
        for failure in recent_failures:
            column = failure.column_source
            column_counts[column] = column_counts.get(column, 0) + 1
        
        # Find most problematic shows
        show_counts = {}
        for failure in recent_failures:
            key = f"{failure.show_date} - {failure.show_location}"
            show_counts[key] = show_counts.get(key, 0) + 1
        
        # Sort shows by failure count
        top_problem_shows = sorted(show_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'period_days': max_age_days,
            'total_failed_links': len(recent_failures),
            'unique_failed_urls': len(set(f.url for f in recent_failures)),
            'failures_by_reason': reason_counts,
            'failures_by_column': column_counts,
            'top_problem_shows': [{'show': show, 'failure_count': count} for show, count in top_problem_shows],
            'permanent_failures': len([f for f in recent_failures if f.failure_reason in {
                FailureReason.VIDEO_NOT_FOUND,
                FailureReason.COPYRIGHT_CLAIM,
                FailureReason.CHANNEL_TERMINATED
            }]),
            'detailed_failures': [f.to_dict() for f in recent_failures]
        }
        
        return report
    
    def export_for_spreadsheet_maintainer(self, output_file: Optional[Path] = None) -> Path:
        """Export failed links in a format useful for spreadsheet maintainers."""
        if not output_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = self.cache_dir / f'failed_links_report_{timestamp}.json'
        
        report = self.generate_report()
        
        # Create a simplified format for maintainers
        maintainer_report = {
            'report_generated': report['generated_at'],
            'summary': {
                'total_failed_links': report['total_failed_links'],
                'permanent_failures': report['permanent_failures'],
                'failures_by_column': report['failures_by_column']
            },
            'dead_links_to_remove': [],
            'problematic_links_to_check': [],
            'shows_needing_attention': report['top_problem_shows']
        }
        
        # Categorize for maintainer action
        for failure in report['detailed_failures']:
            link_info = {
                'url': failure['url'],
                'show_date': failure['show_date'],
                'show_location': failure['show_location'],
                'column': failure['column_source'],
                'reason': failure['failure_reason'],
                'error': failure['error_message'],
                'video_title': failure.get('video_title'),
                'uploader': failure.get('uploader')
            }
            
            # Permanent failures should be removed
            if failure['failure_reason'] in ['video_not_found', 'copyright_claim', 'channel_terminated']:
                maintainer_report['dead_links_to_remove'].append(link_info)
            else:
                # Other failures need investigation
                maintainer_report['problematic_links_to_check'].append(link_info)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(maintainer_report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Exported maintainer report to: {output_file}")
        return output_file
    
    def cleanup_old_failures(self, max_age_days: int = 90):
        """Remove old failure records to prevent cache bloat."""
        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        
        to_remove = []
        for url, failure in self._failures.items():
            try:
                failure_time = datetime.fromisoformat(failure.timestamp)
                if failure_time < cutoff_date:
                    to_remove.append(url)
            except ValueError:
                # Remove entries with invalid timestamps
                to_remove.append(url)
        
        for url in to_remove:
            del self._failures[url]
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old failure records")
            self._save_failures()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get quick statistics about tracked failures."""
        if not self._failures:
            return {'total_failures': 0}
        
        recent_count = 0
        cutoff = datetime.now() - timedelta(days=7)
        
        for failure in self._failures.values():
            try:
                failure_time = datetime.fromisoformat(failure.timestamp)
                if failure_time >= cutoff:
                    recent_count += 1
            except ValueError:
                pass
        
        return {
            'total_failures': len(self._failures),
            'recent_failures_7_days': recent_count,
            'oldest_failure': min((f.timestamp for f in self._failures.values()), default="N/A"),
            'newest_failure': max((f.timestamp for f in self._failures.values()), default="N/A")
        }