"""
yt-dlp version management and auto-update functionality.
"""

import subprocess
import logging
import sys
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def get_yt_dlp_version() -> Optional[str]:
    """Get the currently installed yt-dlp version."""
    try:
        result = subprocess.run(
            ['yt-dlp', '--version'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            return version
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.debug(f"Could not get yt-dlp version: {e}")
        return None


def check_for_updates() -> Tuple[bool, Optional[str]]:
    """Check if yt-dlp has updates available.

    Returns:
        Tuple of (has_updates, latest_version)
    """
    # NOTE: don't ask yt-dlp itself - '--update-to stable --no-update' is a
    # contradictory combination that exits non-zero with a usage error whose
    # text contains "update", which previously made this report an update on
    # every single run (and pip-upgraded yt-dlp on every CLI startup).
    current = get_yt_dlp_version()
    if not current:
        return False, None

    try:
        import json
        import urllib.request

        with urllib.request.urlopen(
            'https://pypi.org/pypi/yt-dlp/json', timeout=10
        ) as response:
            payload = json.load(response)

        latest = payload.get('info', {}).get('version')
        if not latest:
            return False, None

        if latest.strip() != current.strip():
            return True, latest
        return False, None

    except Exception as e:
        # Network problems must never block or spuriously upgrade on startup
        logger.debug(f"Could not check for yt-dlp updates: {e}")
        return False, None


def update_yt_dlp() -> bool:
    """Update yt-dlp to the latest version.

    Returns:
        True if update was successful, False otherwise
    """
    try:
        # Try using uv pip first (for uv-managed projects)
        logger.info("📥 Updating yt-dlp via uv pip...")

        result = subprocess.run(
            ['uv', 'pip', 'install', '--upgrade', 'yt-dlp'],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            logger.info("✅ yt-dlp updated successfully via uv pip")
            return True

        # Fallback: Try regular pip
        logger.info("📥 Trying regular pip...")
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '--upgrade', 'yt-dlp'],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            logger.info("✅ yt-dlp updated successfully via pip")
            return True

        # Final fallback: Try yt-dlp's built-in update mechanism
        logger.info("📥 Trying yt-dlp's built-in update...")
        result = subprocess.run(
            ['yt-dlp', '--update-to', 'stable'],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            logger.info("✅ yt-dlp updated successfully via built-in updater")
            return True
        else:
            logger.error(f"Failed to update yt-dlp: {result.stderr}")
            return False

    except (subprocess.TimeoutExpired, Exception) as e:
        logger.error(f"Error updating yt-dlp: {e}")
        return False


def check_and_update_yt_dlp(auto_update: bool = True, quiet: bool = False) -> bool:
    """Check yt-dlp version and optionally update if outdated.

    Args:
        auto_update: If True, automatically update when outdated
        quiet: If True, suppress non-error output

    Returns:
        True if yt-dlp is available and up-to-date (or updated), False otherwise
    """
    # Get current version
    current_version = get_yt_dlp_version()

    if not current_version:
        if not quiet:
            print("⚠️  yt-dlp is not installed or not in PATH")
        logger.warning("yt-dlp not found")
        return False

    if not quiet:
        logger.info(f"📦 Current yt-dlp version: {current_version}")

    # Check for updates
    has_updates, latest_version = check_for_updates()

    if not has_updates:
        if not quiet:
            logger.info("✅ yt-dlp is up to date")
        return True

    # Updates available
    update_msg = f"🔄 yt-dlp update available"
    if latest_version:
        update_msg += f": {current_version} → {latest_version}"

    if not quiet:
        print(update_msg)
    logger.info(update_msg)

    if not auto_update:
        if not quiet:
            print("💡 Update with: uv lock --upgrade-package yt-dlp && uv sync")
        return True  # Not an error, just needs manual update

    # Auto-update
    if not quiet:
        print("📥 Auto-updating yt-dlp...")

    success = update_yt_dlp()

    if success:
        # Verify new version
        new_version = get_yt_dlp_version()
        if new_version and new_version != current_version:
            if not quiet:
                print(f"✅ yt-dlp updated: {current_version} → {new_version}")
            logger.info(f"Successfully updated yt-dlp to {new_version}")
        return True
    else:
        if not quiet:
            print("⚠️  yt-dlp update failed - please update manually with: pip install --upgrade yt-dlp")
        logger.warning("yt-dlp update failed")
        return True  # Don't fail startup, just warn


if __name__ == '__main__':
    # Test the updater
    logging.basicConfig(level=logging.INFO)
    check_and_update_yt_dlp(auto_update=True, quiet=False)
