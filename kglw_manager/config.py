"""Configuration management for KGLW Manager."""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from .utils import setup_logging

logger = setup_logging()


class ConfigManager:
    """Manages KGLW Manager configuration."""
    
    def __init__(self):
        self.config_dir = Path.home() / '.kglw_manager'
        self.config_file = self.config_dir / 'config.json'
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        default_config = {
            'spreadsheet_path': None,
            'discord_webhook_url': None,
            'collection_path': os.environ.get(
                'KGLW_COLLECTION_PATH', str(Path.home() / 'kglw' / 'video' / 'live')),
            'auto_load_spreadsheet': True,
            'youtube_search_timeout': 45,
            'max_upgrade_candidates': 20,
            'kometa_enabled': False,
            'kometa_assets_path': None,
            'kometa_metadata_file': None, 
            'kometa_collections_file': None
        }
        
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    loaded_config = json.load(f)
                    # Merge with defaults to handle new keys
                    default_config.update(loaded_config)
                    return default_config
            except Exception as e:
                logger.warning(f"Error loading config: {e}, using defaults")
        
        return default_config
    
    def save_config(self) -> bool:
        """Save current configuration to file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self._config, f, indent=2)
            logger.info(f"Configuration saved to {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return False
    
    def get(self, key: str, default=None) -> Any:
        """Get configuration value."""
        return self._config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value."""
        self._config[key] = value
    
    def get_spreadsheet_path(self) -> Optional[str]:
        """Get spreadsheet path, checking environment variables too."""
        # Priority: config file > environment variable
        path = self.get('spreadsheet_path')
        if not path:
            path = os.environ.get('KGLW_SPREADSHEET_PATH')
        return path
    
    def get_discord_webhook_url(self) -> Optional[str]:
        """Get Discord webhook URL, checking environment variables too."""
        # Priority: config file > environment variable
        url = self.get('discord_webhook_url')
        if not url:
            url = os.environ.get('KGLW_DISCORD_WEBHOOK_URL')
        return url
    
    def interactive_setup(self) -> None:
        """Interactive configuration setup."""
        print("🔧 KGLW Manager Configuration Setup")
        print("=" * 40)
        
        # Collection path
        current_path = self.get('collection_path')
        print(f"\n📁 Collection Path")
        print(f"Current: {current_path}")
        new_path = input("Enter new path (or press Enter to keep current): ").strip()
        if new_path:
            if Path(new_path).exists():
                self.set('collection_path', new_path)
                print(f"✅ Collection path updated to: {new_path}")
            else:
                print(f"❌ Path does not exist: {new_path}")
        
        # Spreadsheet path
        current_spreadsheet = self.get_spreadsheet_path()
        print(f"\n📊 Spreadsheet Path")
        print(f"Current: {current_spreadsheet or 'Not set'}")
        print("This should be the path to your downloaded Sheet1.html file")
        new_spreadsheet = input("Enter spreadsheet path (or press Enter to skip): ").strip()
        if new_spreadsheet:
            if Path(new_spreadsheet).exists():
                self.set('spreadsheet_path', new_spreadsheet)
                print(f"✅ Spreadsheet path updated to: {new_spreadsheet}")
            else:
                print(f"❌ File does not exist: {new_spreadsheet}")
        
        # Discord webhook
        current_webhook = self.get_discord_webhook_url()
        print(f"\n🔔 Discord Webhook URL")
        print(f"Current: {'Set' if current_webhook else 'Not set'}")
        new_webhook = input("Enter Discord webhook URL (or press Enter to skip): ").strip()
        if new_webhook:
            if new_webhook.startswith('https://discord'):
                self.set('discord_webhook_url', new_webhook)
                print("✅ Discord webhook URL updated")
            else:
                print("❌ Invalid Discord webhook URL format")
        
        # Auto-load spreadsheet
        current_auto = self.get('auto_load_spreadsheet')
        print(f"\n⚡ Auto-load Spreadsheet")
        print(f"Current: {'Enabled' if current_auto else 'Disabled'}")
        auto_choice = input("Auto-load spreadsheet on startup? (y/n): ").strip().lower()
        if auto_choice in ['y', 'yes']:
            self.set('auto_load_spreadsheet', True)
            print("✅ Auto-load enabled")
        elif auto_choice in ['n', 'no']:
            self.set('auto_load_spreadsheet', False)
            print("✅ Auto-load disabled")
        
        # Save configuration
        if self.save_config():
            print(f"\n💾 Configuration saved to: {self.config_file}")
        else:
            print("\n❌ Failed to save configuration")
        
        print("\n🎉 Setup complete!")
    
    def show_config(self) -> None:
        """Display current configuration."""
        print("🔧 Current KGLW Manager Configuration")
        print("=" * 40)
        
        print(f"📁 Collection Path: {self.get('collection_path')}")
        print(f"📊 Spreadsheet Path: {self.get_spreadsheet_path() or 'Not set'}")
        print(f"🔔 Discord Webhook: {'Set' if self.get_discord_webhook_url() else 'Not set'}")
        print(f"⚡ Auto-load Spreadsheet: {'Enabled' if self.get('auto_load_spreadsheet') else 'Disabled'}")
        print(f"⏱️  YouTube Search Timeout: {self.get('youtube_search_timeout')}s")
        print(f"🔍 Max Upgrade Candidates: {self.get('max_upgrade_candidates')}")
        print(f"📝 Config File: {self.config_file}")


# Global config instance
config = ConfigManager()