"""Tests for CLI module."""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from pathlib import Path
import sys

from kglw_manager import cli


@pytest.mark.unit
class TestCLIBasics:
    """Test basic CLI functionality."""

    def test_cli_module_imports(self):
        """Test that CLI module imports successfully."""
        assert hasattr(cli, 'main')
        assert callable(cli.main)

    def test_create_parser(self):
        """Test parser creation."""
        parser = cli.create_parser()
        assert parser is not None

    def test_parser_has_subparsers(self):
        """Test that parser has subcommands."""
        parser = cli.create_parser()
        # Parse with no args to get defaults
        args = parser.parse_args(['scan'])
        assert args.command == 'scan'


@pytest.mark.unit
class TestCLIScanCommand:
    """Test scan command."""

    @patch('sys.argv', ['kglw-manager.py', 'scan'])
    @patch('kglw_manager.yt_dlp_updater.check_and_update_yt_dlp')
    @patch('kglw_manager.cli.CollectionManager')
    @patch('kglw_manager.cli.handle_scan_command')
    def test_scan_command_basic(self, mock_handle_scan, mock_collection_manager, mock_ytdlp):
        """Test basic scan command."""
        mock_manager = Mock()
        mock_collection_manager.return_value = mock_manager
        mock_ytdlp.return_value = True

        cli.main()

        mock_handle_scan.assert_called_once()

    @patch('sys.argv', ['kglw-manager.py', 'scan', '--force'])
    @patch('kglw_manager.yt_dlp_updater.check_and_update_yt_dlp')
    @patch('kglw_manager.cli.CollectionManager')
    @patch('kglw_manager.cli.handle_scan_command')
    def test_scan_command_force(self, mock_handle_scan, mock_collection_manager, mock_ytdlp):
        """Test scan with --force flag."""
        mock_manager = Mock()
        mock_collection_manager.return_value = mock_manager
        mock_ytdlp.return_value = True

        cli.main()

        mock_handle_scan.assert_called_once()


@pytest.mark.unit
class TestCLIStatsCommand:
    """Test stats command."""

    @patch('sys.argv', ['kglw-manager.py', 'stats'])
    @patch('kglw_manager.yt_dlp_updater.check_and_update_yt_dlp')
    @patch('kglw_manager.cli.CollectionManager')
    @patch('kglw_manager.cli.handle_stats_command')
    def test_stats_command(self, mock_handle_stats, mock_collection_manager, mock_ytdlp):
        """Test stats command."""
        mock_manager = Mock()
        mock_collection_manager.return_value = mock_manager
        mock_ytdlp.return_value = True

        cli.main()

        mock_handle_stats.assert_called_once()


@pytest.mark.unit
class TestCLIInteractiveCommand:
    """Test interactive command."""

    @patch('sys.argv', ['kglw-manager.py', 'interactive'])
    @patch('kglw_manager.yt_dlp_updater.check_and_update_yt_dlp')
    @patch('kglw_manager.cli.CollectionManager')
    @patch('kglw_manager.cli.handle_interactive_command')
    def test_interactive_command(self, mock_handle_interactive, mock_collection_manager, mock_ytdlp):
        """Test interactive mode command."""
        mock_manager = Mock()
        mock_collection_manager.return_value = mock_manager
        mock_ytdlp.return_value = True

        cli.main()

        mock_handle_interactive.assert_called_once()


@pytest.mark.unit
class TestCLICacheCommands:
    """Test cache management commands."""

    @patch('sys.argv', ['kglw-manager.py', 'cache', 'stats'])
    @patch('kglw_manager.yt_dlp_updater.check_and_update_yt_dlp')
    @patch('kglw_manager.cli.CollectionManager')
    @patch('kglw_manager.cli.handle_cache_command')
    def test_cache_stats(self, mock_handle_cache, mock_collection_manager, mock_ytdlp):
        """Test cache stats command."""
        mock_manager = Mock()
        mock_collection_manager.return_value = mock_manager
        mock_ytdlp.return_value = True

        cli.main()

        mock_handle_cache.assert_called_once()

    @patch('sys.argv', ['kglw-manager.py', 'cache', 'clear'])
    @patch('kglw_manager.yt_dlp_updater.check_and_update_yt_dlp')
    @patch('kglw_manager.cli.CollectionManager')
    @patch('kglw_manager.cli.handle_cache_command')
    def test_cache_clear(self, mock_handle_cache, mock_collection_manager, mock_ytdlp):
        """Test cache clear command."""
        mock_manager = Mock()
        mock_collection_manager.return_value = mock_manager
        mock_ytdlp.return_value = True

        cli.main()

        mock_handle_cache.assert_called_once()

    @patch('sys.argv', ['kglw-manager.py', 'cache', 'cleanup'])
    @patch('kglw_manager.yt_dlp_updater.check_and_update_yt_dlp')
    @patch('kglw_manager.cli.CollectionManager')
    @patch('kglw_manager.cli.handle_cache_command')
    def test_cache_cleanup(self, mock_handle_cache, mock_collection_manager, mock_ytdlp):
        """Test cache cleanup command."""
        mock_manager = Mock()
        mock_collection_manager.return_value = mock_manager
        mock_ytdlp.return_value = True

        cli.main()

        mock_handle_cache.assert_called_once()


@pytest.mark.unit
class TestCLIFindUpgradesCommand:
    """Test find-upgrades command."""

    @patch('sys.argv', ['kglw-manager.py', 'find-upgrades'])
    @patch('kglw_manager.yt_dlp_updater.check_and_update_yt_dlp')
    @patch('kglw_manager.cli.CollectionManager')
    @patch('kglw_manager.cli.handle_find_upgrades_command')
    def test_find_upgrades_basic(self, mock_handle_upgrades, mock_collection_manager, mock_ytdlp):
        """Test find-upgrades command."""
        mock_manager = Mock()
        mock_collection_manager.return_value = mock_manager
        mock_ytdlp.return_value = True

        cli.main()

        mock_handle_upgrades.assert_called_once()

    @patch('sys.argv', ['kglw-manager.py', 'find-upgrades', '--year', '2024'])
    @patch('kglw_manager.yt_dlp_updater.check_and_update_yt_dlp')
    @patch('kglw_manager.cli.CollectionManager')
    @patch('kglw_manager.cli.handle_find_upgrades_command')
    def test_find_upgrades_with_year(self, mock_handle_upgrades, mock_collection_manager, mock_ytdlp):
        """Test find-upgrades with --year filter."""
        mock_manager = Mock()
        mock_collection_manager.return_value = mock_manager
        mock_ytdlp.return_value = True

        cli.main()

        mock_handle_upgrades.assert_called_once()


@pytest.mark.unit
class TestCLIYtDlpUpdate:
    """Test yt-dlp update integration."""

    @patch('sys.argv', ['kglw-manager.py', 'scan'])
    @patch('kglw_manager.yt_dlp_updater.check_and_update_yt_dlp')
    @patch('kglw_manager.cli.CollectionManager')
    @patch('kglw_manager.cli.handle_scan_command')
    def test_ytdlp_update_on_startup(self, mock_handle_scan, mock_collection, mock_ytdlp_update):
        """Test that yt-dlp update check runs on startup."""
        mock_manager = Mock()
        mock_collection.return_value = mock_manager
        mock_ytdlp_update.return_value = True

        cli.main()

        # yt-dlp update should be called before any operations
        mock_ytdlp_update.assert_called_once()


@pytest.mark.unit
class TestCLIErrorHandling:
    """Test CLI error handling."""

    @patch('sys.argv', ['kglw-manager.py', 'scan'])
    @patch('kglw_manager.yt_dlp_updater.check_and_update_yt_dlp')
    @patch('kglw_manager.cli.CollectionManager')
    def test_collection_manager_initialization_error(self, mock_collection_manager, mock_ytdlp):
        """Test handling of CollectionManager initialization errors."""
        mock_collection_manager.side_effect = Exception("Failed to initialize")
        mock_ytdlp.return_value = True

        with pytest.raises(SystemExit):
            cli.main()

    @patch('sys.argv', ['kglw-manager.py', 'scan'])
    @patch('kglw_manager.yt_dlp_updater.check_and_update_yt_dlp')
    @patch('kglw_manager.cli.CollectionManager')
    def test_command_execution_error(self, mock_collection_manager, mock_ytdlp):
        """Test handling of command execution errors."""
        mock_manager = Mock()
        mock_collection_manager.return_value = mock_manager
        mock_ytdlp.return_value = True

        # Make handle_scan_command raise an exception
        with patch('kglw_manager.cli.handle_scan_command', side_effect=Exception("Command failed")):
            with pytest.raises(SystemExit):
                cli.main()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
