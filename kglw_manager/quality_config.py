"""Quality configuration and profile management for KGLW Manager."""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from .utils import setup_logging

logger = setup_logging()

class QualityProfile:
    """Represents a quality profile with resolution and upgrade preferences."""
    
    def __init__(self, name: str, max_resolution: int, preferred_resolution: int, 
                 allow_upgrades: bool = True, min_size_mb: int = 100, 
                 max_size_gb: float = 10.0, preferred_codecs: Optional[List[str]] = None):
        self.name = name
        self.max_resolution = max_resolution  # Maximum height (e.g., 1080, 720, 480)
        self.preferred_resolution = preferred_resolution  # Target resolution
        self.allow_upgrades = allow_upgrades
        self.min_size_mb = min_size_mb  # Minimum file size to avoid tiny files
        self.max_size_gb = max_size_gb  # Maximum file size to avoid huge files
        self.preferred_codecs = preferred_codecs or ['h264', 'av01', 'vp9']
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'name': self.name,
            'max_resolution': self.max_resolution,
            'preferred_resolution': self.preferred_resolution,
            'allow_upgrades': self.allow_upgrades,
            'min_size_mb': self.min_size_mb,
            'max_size_gb': self.max_size_gb,
            'preferred_codecs': self.preferred_codecs
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QualityProfile':
        """Create from dictionary."""
        return cls(
            name=data['name'],
            max_resolution=data['max_resolution'],
            preferred_resolution=data['preferred_resolution'],
            allow_upgrades=data.get('allow_upgrades', True),
            min_size_mb=data.get('min_size_mb', 100),
            max_size_gb=data.get('max_size_gb', 10.0),
            preferred_codecs=data.get('preferred_codecs', ['h264', 'av01', 'vp9'])
        )
    
    def should_upgrade(self, current_height: int, candidate_height: int) -> bool:
        """Check if an upgrade should be performed based on this profile."""
        if not self.allow_upgrades:
            return False
        
        # Cap candidate height to max resolution for comparison
        # (yt-dlp will automatically download at the capped resolution)
        effective_candidate_height = min(candidate_height, self.max_resolution)
        
        # Don't upgrade if current quality already meets or exceeds max resolution
        if current_height >= self.max_resolution:
            return False
        
        # Upgrade if effective candidate is better than current
        return effective_candidate_height > current_height

class QualityManager:
    """Manages quality profiles and configuration."""
    
    # Predefined quality profiles
    DEFAULT_PROFILES = {
        'uhd': QualityProfile(
            name='UHD/4K', 
            max_resolution=2160, 
            preferred_resolution=2160,
            max_size_gb=25.0
        ),
        'fhd': QualityProfile(
            name='Full HD', 
            max_resolution=1080, 
            preferred_resolution=1080,
            max_size_gb=15.0
        ),
        'hd': QualityProfile(
            name='HD', 
            max_resolution=720, 
            preferred_resolution=720,
            max_size_gb=8.0
        ),
        'sd': QualityProfile(
            name='Standard Definition', 
            max_resolution=480, 
            preferred_resolution=480,
            max_size_gb=4.0
        ),
        'any': QualityProfile(
            name='Any Quality', 
            max_resolution=2160, 
            preferred_resolution=720,
            max_size_gb=30.0
        )
    }
    
    def __init__(self):
        self.config_dir = Path.home() / '.kglw_manager'
        self.config_file = self.config_dir / 'quality_config.json'
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    logger.debug(f"Loaded quality config from {self.config_file}")
                    return config
            except Exception as e:
                logger.warning(f"Failed to load quality config: {e}, using defaults")
        
        # Create default config
        default_config = {
            'active_profile': 'fhd',  # Default to Full HD
            'custom_profiles': {},
            'settings': {
                'auto_upgrade': False,  # Require user confirmation by default
                'backup_originals': True,
                'upgrade_batch_size': 5,  # Process 5 shows at a time
                'min_improvement_threshold': 240  # Minimum height difference to consider upgrade
            }
        }
        
        self._save_config(default_config)
        return default_config
    
    def _save_config(self, config: Dict[str, Any]):
        """Save configuration to file."""
        self.config_dir.mkdir(exist_ok=True)
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            logger.debug(f"Saved quality config to {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to save quality config: {e}")
    
    def get_active_profile(self) -> QualityProfile:
        """Get the currently active quality profile."""
        profile_name = self.config.get('active_profile', 'fhd')
        
        # Check custom profiles first
        custom_profiles = self.config.get('custom_profiles', {})
        if profile_name in custom_profiles:
            return QualityProfile.from_dict(custom_profiles[profile_name])
        
        # Fall back to default profiles
        if profile_name in self.DEFAULT_PROFILES:
            return self.DEFAULT_PROFILES[profile_name]
        
        # Ultimate fallback
        logger.warning(f"Unknown profile '{profile_name}', using Full HD")
        return self.DEFAULT_PROFILES['fhd']
    
    def set_active_profile(self, profile_name: str):
        """Set the active quality profile."""
        self.config['active_profile'] = profile_name
        self._save_config(self.config)
        logger.info(f"Set active quality profile to: {profile_name}")
    
    def list_available_profiles(self) -> List[str]:
        """List all available quality profiles."""
        default_names = list(self.DEFAULT_PROFILES.keys())
        custom_names = list(self.config.get('custom_profiles', {}).keys())
        return default_names + custom_names
    
    def get_profile_info(self, profile_name: str) -> Optional[QualityProfile]:
        """Get information about a specific profile."""
        # Check custom profiles first
        custom_profiles = self.config.get('custom_profiles', {})
        if profile_name in custom_profiles:
            return QualityProfile.from_dict(custom_profiles[profile_name])
        
        # Check default profiles
        if profile_name in self.DEFAULT_PROFILES:
            return self.DEFAULT_PROFILES[profile_name]
        
        return None
    
    def create_custom_profile(self, profile: QualityProfile):
        """Create a new custom quality profile."""
        if 'custom_profiles' not in self.config:
            self.config['custom_profiles'] = {}
        
        self.config['custom_profiles'][profile.name] = profile.to_dict()
        self._save_config(self.config)
        logger.info(f"Created custom quality profile: {profile.name}")
    
    def get_format_selector_for_profile(self, profile: QualityProfile, selected_height: int) -> str:
        """Generate yt-dlp format selector based on quality profile."""
        # Cap the selected height to the profile's maximum
        max_height = min(selected_height, profile.max_resolution)
        
        # Generate format selector based on capped height
        if max_height >= 2160:
            return '401+140/313+140/271+140/137+140/18'
        elif max_height >= 1440:
            return '400+140/271+140/137+140/18'
        elif max_height >= 1080:
            return '137+140/399+140/248+140/136+140/18'
        elif max_height >= 720:
            return '136+140/135+140/18'
        elif max_height >= 480:
            return '135+140/134+140/18'
        else:
            return '18'  # 360p fallback
    
    def should_upgrade_show(self, current_files: List[Dict], candidate_height: int) -> bool:
        """Check if a show should be upgraded based on current quality profile."""
        profile = self.get_active_profile()
        
        if not profile.allow_upgrades:
            return False
        
        # Get current best quality
        current_best_height = 0
        for file_info in current_files:
            quality = file_info.get('quality', '')
            if 'x' in quality:  # e.g., "1920x1080"
                try:
                    height = int(quality.split('x')[1])
                    current_best_height = max(current_best_height, height)
                except (ValueError, IndexError):
                    continue
            elif 'p' in quality:  # e.g., "1080p"
                try:
                    height = int(quality.replace('p', ''))
                    current_best_height = max(current_best_height, height)
                except ValueError:
                    continue
        
        return profile.should_upgrade(current_best_height, candidate_height)
    
    def get_settings(self) -> Dict[str, Any]:
        """Get current settings."""
        return self.config.get('settings', {})
    
    def update_setting(self, key: str, value: Any):
        """Update a specific setting."""
        if 'settings' not in self.config:
            self.config['settings'] = {}
        
        self.config['settings'][key] = value
        self._save_config(self.config)
        logger.info(f"Updated setting {key} = {value}")
    
    def reset_to_defaults(self):
        """Reset quality configuration to defaults."""
        self.config = {
            'active_profile': 'fhd',  # Default to Full HD
            'custom_profiles': {},
            'settings': {
                'auto_upgrade': True,
                'priority_channels': True,
                'skip_audio_only': True
            }
        }
        self._save_config(self.config)
        logger.info("Quality configuration reset to defaults")