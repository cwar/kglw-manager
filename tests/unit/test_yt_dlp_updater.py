"""Tests for yt-dlp updater module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import subprocess

from kglw_manager.yt_dlp_updater import (
    get_yt_dlp_version,
    check_for_updates,
    update_yt_dlp,
    check_and_update_yt_dlp
)


@pytest.mark.unit
class TestYtDlpVersionDetection:
    """Test yt-dlp version detection."""

    @patch('subprocess.run')
    def test_get_yt_dlp_version_success(self, mock_run):
        """Test successful version retrieval."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout='2023.12.30\n',
            stderr=''
        )

        version = get_yt_dlp_version()

        assert version == '2023.12.30'
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_get_yt_dlp_version_failure(self, mock_run):
        """Test version retrieval failure."""
        mock_run.side_effect = FileNotFoundError("yt-dlp not found")

        version = get_yt_dlp_version()

        assert version is None

    @patch('subprocess.run')
    def test_get_yt_dlp_version_timeout(self, mock_run):
        """Test version retrieval timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired('yt-dlp', 10)

        version = get_yt_dlp_version()

        assert version is None


@pytest.mark.unit
class TestUpdateCheck:
    """Test update checking."""

    @patch('subprocess.run')
    def test_check_for_updates_no_update_available(self, mock_run):
        """Test check when no update is available."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout='',
            stderr='yt-dlp is already up to date'
        )

        has_updates, version = check_for_updates()

        assert has_updates is False
        assert version is None

    @patch('urllib.request.urlopen')
    @patch('subprocess.run')
    def test_check_for_updates_with_update_available(self, mock_run, mock_urlopen):
        """Test check when update is available.

        check_for_updates deliberately compares the installed version against
        PyPI instead of parsing yt-dlp's own update output (which previously
        reported an update on every run).
        """
        import json as json_module

        # Installed version (via `yt-dlp --version`)
        mock_run.return_value = Mock(
            returncode=0,
            stdout='2023.11.01\n',
            stderr=''
        )

        # PyPI reports a newer version
        mock_response = MagicMock()
        mock_response.__enter__.return_value = mock_response
        mock_response.read.return_value = json_module.dumps(
            {'info': {'version': '2023.12.31'}}
        ).encode()
        mock_urlopen.return_value = mock_response

        has_updates, version = check_for_updates()

        assert has_updates is True
        assert version == '2023.12.31'

    @patch('subprocess.run')
    def test_check_for_updates_timeout(self, mock_run):
        """Test check timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired('yt-dlp', 30)

        has_updates, version = check_for_updates()

        assert has_updates is False
        assert version is None

    @patch('subprocess.run')
    def test_check_for_updates_not_found(self, mock_run):
        """Test check when yt-dlp not found."""
        mock_run.side_effect = FileNotFoundError("yt-dlp not found")

        has_updates, version = check_for_updates()

        assert has_updates is False
        assert version is None


@pytest.mark.unit
class TestYtDlpUpdate:
    """Test yt-dlp update process."""

    @patch('subprocess.run')
    def test_update_yt_dlp_via_uv_success(self, mock_run):
        """Test successful update via uv pip."""
        mock_run.return_value = Mock(returncode=0, stdout='', stderr='')

        result = update_yt_dlp()

        assert result is True
        # Should call uv pip install
        assert any('uv' in str(call) for call in mock_run.call_args_list)

    @patch('subprocess.run')
    def test_update_yt_dlp_fallback_to_pip(self, mock_run):
        """Test fallback to regular pip when uv fails."""
        # First call (uv) fails, second call (pip) succeeds
        mock_run.side_effect = [
            Mock(returncode=1, stdout='', stderr='uv not found'),
            Mock(returncode=0, stdout='', stderr='')
        ]

        result = update_yt_dlp()

        assert result is True
        assert mock_run.call_count == 2

    @patch('subprocess.run')
    def test_update_yt_dlp_fallback_to_builtin(self, mock_run):
        """Test fallback to yt-dlp built-in updater."""
        # First two calls fail, third (built-in) succeeds
        mock_run.side_effect = [
            Mock(returncode=1, stdout='', stderr='uv failed'),
            Mock(returncode=1, stdout='', stderr='pip failed'),
            Mock(returncode=0, stdout='', stderr='')
        ]

        result = update_yt_dlp()

        assert result is True
        assert mock_run.call_count == 3

    @patch('subprocess.run')
    def test_update_yt_dlp_all_methods_fail(self, mock_run):
        """Test when all update methods fail."""
        mock_run.return_value = Mock(returncode=1, stdout='', stderr='Failed')

        result = update_yt_dlp()

        assert result is False

    @patch('subprocess.run')
    def test_update_yt_dlp_timeout(self, mock_run):
        """Test update timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired('uv', 120)

        result = update_yt_dlp()

        assert result is False


@pytest.mark.unit
class TestCheckAndUpdate:
    """Test complete check and update workflow."""

    @patch('kglw_manager.yt_dlp_updater.get_yt_dlp_version')
    @patch('kglw_manager.yt_dlp_updater.check_for_updates')
    @patch('kglw_manager.yt_dlp_updater.update_yt_dlp')
    def test_check_and_update_when_outdated(self, mock_update, mock_check, mock_version):
        """Test auto-update when version is outdated."""
        mock_version.return_value = '2023.12.01'
        mock_check.return_value = (True, '2023.12.31')  # has_updates=True, version
        mock_update.return_value = True

        result = check_and_update_yt_dlp(auto_update=True)

        assert result is True
        mock_update.assert_called_once()

    @patch('kglw_manager.yt_dlp_updater.get_yt_dlp_version')
    @patch('kglw_manager.yt_dlp_updater.check_for_updates')
    @patch('kglw_manager.yt_dlp_updater.update_yt_dlp')
    def test_check_and_update_when_current(self, mock_update, mock_check, mock_version):
        """Test no update when version is current."""
        mock_version.return_value = '2023.12.31'
        mock_check.return_value = (False, None)  # no updates available

        result = check_and_update_yt_dlp(auto_update=True)

        assert result is True
        mock_update.assert_not_called()

    @patch('kglw_manager.yt_dlp_updater.get_yt_dlp_version')
    @patch('kglw_manager.yt_dlp_updater.check_for_updates')
    @patch('kglw_manager.yt_dlp_updater.update_yt_dlp')
    def test_check_and_update_no_auto_update(self, mock_update, mock_check, mock_version):
        """Test check-only mode without auto-update."""
        mock_version.return_value = '2023.12.01'
        mock_check.return_value = (True, '2023.12.31')

        result = check_and_update_yt_dlp(auto_update=False)

        # Should detect update needed but not actually update
        mock_update.assert_not_called()

    @patch('kglw_manager.yt_dlp_updater.get_yt_dlp_version')
    def test_check_and_update_yt_dlp_not_installed(self, mock_version):
        """Test when yt-dlp is not installed."""
        mock_version.return_value = None

        result = check_and_update_yt_dlp(auto_update=True)

        assert result is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
