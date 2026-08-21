"""Base classes for interactive operations with shared functionality."""

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.table import Table
from rich.tree import Tree
from rich import box
from typing import Dict, Any, Optional, Callable, List
from abc import ABC, abstractmethod
from contextlib import contextmanager


class InteractiveOperation(ABC):
    """Base class for all interactive operations with shared functionality."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    # === Shared UI Methods ===
    def print_header(self, text: str):
        """Print a styled header."""
        self.console.print(Panel.fit(text, style="bold green", border_style="green"))

    def print_success(self, message: str) -> None:
        """Print success message."""
        self.console.print(message, style="bold green")

    def print_info(self, message: str) -> None:
        """Print info message."""
        self.console.print(message, style="green")

    def print_warning(self, message: str) -> None:
        """Print warning message."""
        self.console.print(message, style="bold yellow")

    def print_error(self, message: str) -> None:
        """Print error message."""
        self.console.print(message, style="bold red")

    def confirm(self, message: str, default: bool = True) -> bool:
        """Get user confirmation."""
        return Confirm.ask(message, default=default)

    # === CLI Hint Generation ===
    def show_cli_hint(self, command: str, description: Optional[str] = None, **kwargs) -> None:
        """Show CLI command hint for any operation.

        Args:
            command: The main command (e.g., "analyze-quality", "find-upgrades")
            description: Optional description text to show below command
            **kwargs: Command flags and values to include
        """
        # Build the CLI command
        cmd_parts = [f"uv run python kglw-manager.py {command}"]

        # Add flags from kwargs
        for flag, value in kwargs.items():
            if value is True:
                cmd_parts.append(f"--{flag.replace('_', '-')}")
            elif value is False:
                continue  # Skip false flags
            elif value is not None:
                flag_name = flag.replace('_', '-')
                # Quote values that contain spaces
                if isinstance(value, str) and ' ' in value:
                    cmd_parts.append(f"--{flag_name} \"{value}\"")
                else:
                    cmd_parts.append(f"--{flag_name} {value}")

        cli_command = " ".join(cmd_parts)

        # Create a styled hint panel
        hint_text = f"[dim]💡 CLI Equivalent:[/dim]\n[bold cyan]{cli_command}[/bold cyan]"
        if description:
            hint_text += f"\n[dim]{description}[/dim]"

        hint_panel = Panel(
            hint_text,
            title="💻 Command Line Hint",
            title_align="left",
            border_style="dim blue",
            padding=(0, 1)
        )

        self.console.print(hint_panel)

    # === Operation Framework ===
    def execute_with_hint(self, command: str, operation_func: Callable, description: Optional[str] = None, **kwargs):
        """Execute an operation and automatically show CLI hint afterward.

        Args:
            command: The CLI command name
            operation_func: Function to execute
            description: Optional description for the hint
            **kwargs: Arguments for both the operation and CLI hint
        """
        try:
            # Run the operation
            result = operation_func()

            # Show CLI hint after successful operation
            self.show_cli_hint(command, description, **kwargs)

            return result
        except Exception as e:
            # Still show hint even if operation fails
            self.show_cli_hint(command, f"{description} (operation failed: {e})" if description else f"Operation failed: {e}", **kwargs)
            raise

    # === Abstract Methods ===
    @abstractmethod
    def get_command_name(self) -> str:
        """Return the CLI command name for this operation."""
        pass

    @abstractmethod
    def get_description(self) -> str:
        """Return a description of this operation."""
        pass

    # === Utility Methods ===
    def wait_for_enter(self, message: str = "Press Enter to continue..."):
        """Wait for user to press Enter."""
        input(f"\n{message}")

    # === Progress Bar Functionality ===
    @contextmanager
    def progress_bar(self, description: str = "Processing...", total: Optional[int] = None):
        """Create a progress bar context manager.

        Args:
            description: Initial description text
            total: Total number of items (None for indeterminate)

        Usage:
            with self.progress_bar("Analyzing videos...", total=100) as progress:
                task = progress.add_task("Current task", total=10)
                for i in range(10):
                    progress.update(task, description=f"Processing item {i}")
                    progress.advance(task)
        """
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn() if total is not None else "",
            TaskProgressColumn() if total is not None else "",
            TimeElapsedColumn(),
            console=self.console,
            transient=False
        ) as progress:
            yield progress

    def simple_progress(self, items: List[Any], description: str = "Processing items",
                       process_func: Callable[[Any], Any] = None) -> List[Any]:
        """Process a list of items with automatic progress bar.

        Args:
            items: List of items to process
            description: Progress bar description
            process_func: Function to apply to each item

        Returns:
            List of processed results
        """
        results = []

        with self.progress_bar(description, total=len(items)) as progress:
            task = progress.add_task(description, total=len(items))

            for i, item in enumerate(items):
                if process_func:
                    result = process_func(item)
                    results.append(result)
                else:
                    results.append(item)

                progress.update(task, description=f"{description} ({i+1}/{len(items)})")
                progress.advance(task)

        return results

    # === Table Creation Helpers ===
    def create_table(self, title: str = None, headers: List[str] = None,
                    show_header: bool = True, **kwargs) -> Table:
        """Create a standardized Rich table.

        Args:
            title: Table title
            headers: List of column headers
            show_header: Whether to show headers
            **kwargs: Additional Table arguments
        """
        table = Table(title=title, show_header=show_header, **kwargs)

        if headers:
            for header in headers:
                table.add_column(header, style="bold cyan")

        return table

    def create_status_table(self, data: Dict[str, Any], title: str = "Status") -> Table:
        """Create a status table with key-value pairs.

        Args:
            data: Dictionary of status information
            title: Table title
        """
        table = Table(title=title, show_header=False, box=None)
        table.add_column("Item", style="bold cyan", width=20)
        table.add_column("Status", style="white")

        for key, value in data.items():
            # Format boolean values
            if isinstance(value, bool):
                display_value = "✅ Yes" if value else "❌ No"
            else:
                display_value = str(value)

            table.add_row(f"{key}:", display_value)

        return table

    # === Panel Creation Helpers ===
    def create_info_panel(self, content: str, title: str = "Information",
                         border_style: str = "blue") -> Panel:
        """Create a standardized info panel."""
        return Panel(content, title=title, border_style=border_style, padding=(0, 1))

    def create_warning_panel(self, content: str, title: str = "Warning") -> Panel:
        """Create a warning panel."""
        return Panel(content, title=title, border_style="yellow", padding=(0, 1))

    def create_error_panel(self, content: str, title: str = "Error") -> Panel:
        """Create an error panel."""
        return Panel(content, title=title, border_style="red", padding=(0, 1))

    def create_success_panel(self, content: str, title: str = "Success") -> Panel:
        """Create a success panel."""
        return Panel(content, title=title, border_style="green", padding=(0, 1))

    # === Menu Helpers ===
    def show_menu(self, title: str, options: List[str], show_numbers: bool = True,
                 show_back: bool = True, show_quit: bool = True) -> int:
        """Show a standardized menu and get user choice.

        Args:
            title: Menu title
            options: List of menu options
            show_numbers: Whether to show option numbers
            show_back: Whether to show back option
            show_quit: Whether to show quit option

        Returns:
            Selected option index, or -1 for back, -3 for quit
        """
        # Create menu table
        menu_table = Table(title=title, show_header=False, box=box.ROUNDED)
        menu_table.add_column("Option", style="white")

        # Add numbered options
        for i, option in enumerate(options):
            if show_numbers:
                menu_table.add_row(f"   {i+1}. {option}")
            else:
                menu_table.add_row(f"   • {option}")

        # Add back/quit options
        if show_back:
            menu_table.add_row("  b. Back")
        if show_quit:
            menu_table.add_row("  q. Quit")

        self.console.print(menu_table)

        # Get user input
        while True:
            try:
                choice = input("Select option: ").strip().lower()

                if choice == 'q' and show_quit:
                    return -3  # Quit
                elif choice == 'b' and show_back:
                    return -1  # Back
                elif choice.isdigit():
                    option_num = int(choice) - 1
                    if 0 <= option_num < len(options):
                        return option_num

                self.print_warning("Please select a valid option")

            except KeyboardInterrupt:
                return -3  # Quit on Ctrl+C
            except EOFError:
                return -3  # Quit on EOF

    # === Data Display Helpers ===
    def display_summary(self, data: Dict[str, Any], title: str = "Summary"):
        """Display a summary of operation results."""
        summary_table = self.create_status_table(data, title)
        self.console.print(summary_table)

    def display_distribution(self, data: Dict[str, int], title: str = "Distribution",
                           show_percentages: bool = True):
        """Display a distribution table with counts and percentages."""
        table = Table(title=title)
        table.add_column("Item", style="bold cyan")
        table.add_column("Count", style="white")
        if show_percentages:
            table.add_column("Percentage", style="yellow")

        total = sum(data.values()) if show_percentages else 0

        for item, count in sorted(data.items()):
            row = [item, str(count)]
            if show_percentages and total > 0:
                percentage = (count / total * 100)
                row.append(f"{percentage:.1f}%")
            table.add_row(*row)

        self.console.print(table)

    # === Error Handling Helpers ===
    def handle_operation_error(self, error: Exception, operation_name: str):
        """Standardized error handling for operations."""
        error_panel = self.create_error_panel(
            f"❌ Error during {operation_name}: {error}",
            "Operation Failed"
        )
        self.console.print(error_panel)

        # Log the error (if logging is available)
        try:
            import logging
            logging.error(f"{operation_name} error: {error}")
        except:
            pass


class QualityAnalysisOperation(InteractiveOperation):
    """Quality analysis operation with CLI hint support and shared functionality."""

    def get_command_name(self) -> str:
        return "analyze-quality"

    def get_description(self) -> str:
        return "Analyze video quality for collection"

    def execute(self, collection_manager, shows: List[Any], **filters):
        """Execute quality analysis with automatic CLI hint generation."""
        # Build hint kwargs
        hint_kwargs = {}
        if filters.get('year'):
            hint_kwargs['year'] = filters['year']
        if filters.get('tour'):
            hint_kwargs['tour'] = filters['tour']
        if filters.get('disable_plex'):
            hint_kwargs['disable_plex'] = True

        def analysis_operation():
            # Use shared progress bar functionality
            analyzed_count = 0
            cached_count = 0
            error_count = 0
            quality_counts = {}

            def analyze_show(show_data):
                nonlocal analyzed_count, cached_count, error_count
                try:
                    # Simulated analysis logic
                    analyzed_count += 1
                    # Return quality analysis result
                    return {"quality": "1080p", "duration": 3600}
                except Exception as e:
                    error_count += 1
                    self.handle_operation_error(e, f"show analysis")
                    return {"quality": "unknown", "duration": 0}

            # Use shared progress bar for analysis
            results = self.simple_progress(
                shows,
                f"Analyzing {len(shows)} shows",
                analyze_show
            )

            # Count quality distribution
            for result in results:
                quality = result.get('quality', 'unknown')
                quality_counts[quality] = quality_counts.get(quality, 0) + 1

            # Display results using shared functionality
            self.display_summary({
                "Analyzed": analyzed_count,
                "From cache": cached_count,
                "Errors": error_count
            }, "📊 Analysis Results")

            self.display_distribution(
                quality_counts,
                "🎥 Quality Distribution"
            )

            return {"analyzed": analyzed_count, "cached": cached_count, "errors": error_count}

        return self.execute_with_hint(
            self.get_command_name(),
            analysis_operation,
            self.get_description(),
            **hint_kwargs
        )


class CacheOperation(InteractiveOperation):
    """Cache operation with CLI hint support."""

    def __init__(self, operation_type: str, console=None):
        super().__init__(console)
        self.operation_type = operation_type

    def get_command_name(self) -> str:
        if self.operation_type == 'rebuild':
            return "scan"
        return "cache"

    def get_description(self) -> str:
        descriptions = {
            'clear': 'Clear all caches',
            'stats': 'Show cache statistics and integrity info',
            'rebuild': 'Force a full collection rescan'
        }
        return descriptions.get(self.operation_type, f'Perform {self.operation_type} operation')

    def execute(self, operation_func):
        """Execute cache operation with appropriate CLI hint."""
        hint_kwargs = {}
        if self.operation_type == 'clear':
            hint_kwargs['action'] = 'clear'
        elif self.operation_type == 'stats':
            hint_kwargs['action'] = 'stats'
        elif self.operation_type == 'rebuild':
            hint_kwargs['force'] = True

        return self.execute_with_hint(
            self.get_command_name(),
            operation_func,
            self.get_description(),
            **hint_kwargs
        )


class UpgradeOperation(InteractiveOperation):
    """Upgrade operation with CLI hint support."""

    def get_command_name(self) -> str:
        return "find-upgrades"

    def get_description(self) -> str:
        return "Find upgrade candidates for collection"

    def execute(self, operation_func, **filters):
        """Execute find upgrades with CLI hint."""
        hint_kwargs = {}

        # Add filters to hint
        if filters.get('year'):
            hint_kwargs['year'] = filters['year']
        if filters.get('auto_download'):
            hint_kwargs['auto_download'] = True
        if filters.get('force'):
            hint_kwargs['force'] = True
        if filters.get('stats_only'):
            hint_kwargs['stats_only'] = True

        return self.execute_with_hint(
            self.get_command_name(),
            operation_func,
            self.get_description(),
            **hint_kwargs
        )


class CollectionOperation(InteractiveOperation):
    """Collection operation with CLI hint support."""

    def get_command_name(self) -> str:
        return "stats"

    def get_description(self) -> str:
        return "Show detailed collection statistics"

    def execute(self, operation_func):
        """Execute collection statistics with CLI hint."""
        return self.execute_with_hint(
            self.get_command_name(),
            operation_func,
            self.get_description()
        )


class FindUpgradesOperation(InteractiveOperation):
    """Find upgrade candidates operation with CLI hint support."""

    def __init__(self, console=None, **filters):
        super().__init__(console)
        self.filters = filters

    def get_command_name(self) -> str:
        return "find-upgrades"

    def get_description(self) -> str:
        return "Find upgrade candidates for collection"

    def execute(self, operation_func):
        """Execute find upgrades with CLI hint."""
        hint_kwargs = {}

        # Add filters to hint
        if self.filters.get('year'):
            hint_kwargs['year'] = self.filters['year']
        if self.filters.get('auto_download'):
            hint_kwargs['auto_download'] = True
        if self.filters.get('force'):
            hint_kwargs['force'] = True

        return self.execute_with_hint(
            self.get_command_name(),
            operation_func,
            self.get_description(),
            **hint_kwargs
        )


class StatsOperation(InteractiveOperation):
    """Collection statistics operation with CLI hint support."""

    def get_command_name(self) -> str:
        return "stats"

    def get_description(self) -> str:
        return "Show detailed collection statistics"

    def execute(self, operation_func):
        """Execute collection statistics with CLI hint."""
        return self.execute_with_hint(
            self.get_command_name(),
            operation_func,
            self.get_description()
        )


class SpreadsheetOperation(InteractiveOperation):
    """Spreadsheet operation with CLI hint support."""

    def __init__(self, action="stats", console=None):
        super().__init__(console)
        self.action = action

    def get_command_name(self) -> str:
        return "spreadsheet"

    def get_description(self) -> str:
        descriptions = {
            'stats': 'Show spreadsheet statistics',
            'missing': 'Find shows in spreadsheet but not in collection',
            'download': 'Download latest spreadsheet data'
        }
        return descriptions.get(self.action, f'Perform {self.action} operation')

    def execute(self, operation_func):
        """Execute spreadsheet operation with CLI hint."""
        hint_kwargs = {}
        if self.action != 'stats':
            hint_kwargs['action'] = self.action

        return self.execute_with_hint(
            self.get_command_name(),
            operation_func,
            self.get_description(),
            **hint_kwargs
        )



class CollectionScanOperation(InteractiveOperation):
    """Operation for scanning collection with progress bar support."""

    def get_command_name(self) -> str:
        return "scan-collection"

    def get_description(self) -> str:
        return "Scan collection with progress tracking"

    def execute(self, collection_manager, force_rescan: bool = False):
        """Execute collection scan with progress tracking."""
        with self.progress_bar("Loading collection data...") as progress:
            # Create a task for tracking
            task = progress.add_task("Loading collection data...", total=None)

            # Temporarily replace print calls with progress updates
            import builtins
            original_print = builtins.print

            def progress_print(*args, **kwargs):
                # Suppress all print calls during scanning - they all go through progress bar
                if args and len(args) > 0:
                    message = str(args[0])
                    # Clean up the message and filter out problematic content
                    clean_message = message.replace('\r', '').strip()

                    # Only update progress if message is meaningful and not too long
                    if clean_message and len(clean_message) < 200:
                        # Additional filtering for scanning messages
                        if any(keyword in clean_message.lower() for keyword in ['scanning', 'found', 'rescan', 'process']):
                            progress.update(task, description=clean_message)

                # Always suppress the original print to prevent text spam
                return

            # Replace print temporarily
            builtins.print = progress_print

            try:
                result = collection_manager.scan_collection(force_rescan=force_rescan)
                return result
            finally:
                # Restore original print
                builtins.print = original_print
