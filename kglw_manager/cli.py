"""Command-line interface for KGLW Manager."""

import argparse
import os
import sys
from pathlib import Path
from .collection import CollectionManager
from .interactive import InteractiveManager
from .utils import setup_logging
from .config import config

logger = setup_logging()


def create_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="KGLW Collection Manager - Manage King Gizzard & The Lizard Wizard concert collection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s interactive                    # Start interactive mode
  %(prog)s scan                          # Scan collection and show stats
  %(prog)s find-upgrades                 # Find shows that need upgrades
  %(prog)s find-missing                  # Find shows with no video files
  %(prog)s find-missing --download       # Find and download missing shows
  %(prog)s stats                         # Show collection statistics
        """
    )
    
    # Main commands
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Interactive mode
    interactive_parser = subparsers.add_parser(
        'interactive', 
        help='Start interactive browsing mode'
    )
    
    # Scan collection
    scan_parser = subparsers.add_parser(
        'scan',
        help='Scan collection and show basic information'
    )
    scan_parser.add_argument(
        '--force', action='store_true',
        help='Force full rescan, ignore cache'
    )
    
    # Find upgrades
    upgrade_parser = subparsers.add_parser(
        'find-upgrades',
        help='Find shows that could benefit from upgrades'
    )
    upgrade_parser.add_argument(
        '--year', type=int,
        help='Filter by specific year'
    )
    upgrade_parser.add_argument(
        '--tour',
        help='Filter by specific tour'
    )
    upgrade_parser.add_argument(
        '--auto-download', action='store_true',
        help='Automatically download the best upgrade for each show'
    )
    upgrade_parser.add_argument(
        '--force', action='store_true',
        help='Force check all shows, ignore upgrade tracking'
    )
    
    # Statistics
    stats_parser = subparsers.add_parser(
        'stats',
        help='Show detailed collection statistics'
    )

    # Quality analysis
    quality_parser = subparsers.add_parser(
        'analyze-quality',
        help='Analyze video quality for all shows in collection'
    )
    quality_parser.add_argument(
        '--year', type=int,
        help='Analyze only shows from specific year'
    )
    quality_parser.add_argument(
        '--tour',
        help='Analyze only shows from specific tour'
    )
    quality_parser.add_argument(
        '--force', action='store_true',
        help='Force re-analysis of already cached videos'
    )
    quality_parser.add_argument(
        '--disable-plex', action='store_true',
        help='Disable Plex metadata and force ffprobe analysis'
    )

    # Cache management
    cache_parser = subparsers.add_parser(
        'cache',
        help='Manage video metadata cache'
    )
    cache_subparsers = cache_parser.add_subparsers(dest='cache_action')
    
    cache_subparsers.add_parser('clear', help='Clear all caches (video metadata + collection)')
    cache_subparsers.add_parser('clear-video', help='Clear video metadata cache only')
    cache_subparsers.add_parser('clear-collection', help='Clear collection structure cache only')
    cache_subparsers.add_parser('stats', help='Show cache statistics')
    cache_subparsers.add_parser('cleanup', help='Remove stale cache entries')
    
    # Upgrade tracking management
    cache_subparsers.add_parser('clear-failed', help='Clear all failed upgrade attempts')
    clear_show_parser = cache_subparsers.add_parser('clear-show', help='Clear upgrade tracking for specific show')
    clear_show_parser.add_argument('date', help='Show date (YYYY-MM-DD format)')
    cache_subparsers.add_parser('upgrade-stats', help='Show upgrade tracking statistics')
    
    # API cache management
    cache_subparsers.add_parser('api-stats', help='Show KGLW.net API cache statistics')
    cache_subparsers.add_parser('clear-api', help='Clear KGLW.net API tour cache')
    
    # Fresh collection setup
    fresh_parser = subparsers.add_parser(
        'setup-fresh',
        help='Set up fresh collection directory structure from KGLW.net API'
    )
    fresh_parser.add_argument(
        'collection_path',
        help='Path where the new collection will be created'
    )
    fresh_parser.add_argument(
        '--apply', action='store_true',
        help='Actually create directories and files (default is dry run)'
    )
    fresh_parser.add_argument(
        '--preview', action='store_true',
        help='Show preview of what would be created'
    )
    
    # Discord test
    discord_parser = subparsers.add_parser(
        'test-discord',
        help='Test Discord webhook notifications'
    )
    
    # Spreadsheet commands
    spreadsheet_parser = subparsers.add_parser(
        'spreadsheet',
        help='Import YouTube links from live show spreadsheet'
    )
    spreadsheet_subparsers = spreadsheet_parser.add_subparsers(dest='spreadsheet_action')
    
    download_parser = spreadsheet_subparsers.add_parser('download', help='Download latest spreadsheet HTML export')
    download_parser.add_argument('--method', choices=['auto', 'script', 'manual'], default='auto',
                                help='Download method: auto (try all), script (create helper script), manual (show instructions)')
    download_parser.add_argument('--output', help='Output directory for downloaded files')
    spreadsheet_subparsers.add_parser('load', help='Load YouTube links from spreadsheet')
    spreadsheet_subparsers.add_parser('stats', help='Show spreadsheet statistics')
    spreadsheet_subparsers.add_parser('missing', help='Find shows in spreadsheet but not in collection')
    
    # Spreadsheet load with file option
    load_parser = spreadsheet_subparsers.add_parser('load-file', help='Load from local HTML file')
    load_parser.add_argument('--file', required=True, help='Path to HTML export file')
    
    # Link failure tracking commands
    failures_parser = spreadsheet_subparsers.add_parser('failures', help='Manage link failure tracking')
    failures_subparsers = failures_parser.add_subparsers(dest='failures_action')
    
    failures_subparsers.add_parser('stats', help='Show failure tracking statistics')
    failures_subparsers.add_parser('report', help='Generate comprehensive failure report')
    failures_subparsers.add_parser('export', help='Export failed links for spreadsheet maintainer')
    failures_subparsers.add_parser('cleanup', help='Clean up old failure records')
    
    failures_test_parser = failures_subparsers.add_parser('test-links', help='Test spreadsheet links for a specific show')
    failures_test_parser.add_argument('--date', required=True, help='Show date (YYYY-MM-DD)')
    failures_test_parser.add_argument('--location', help='Show location for better matching')
    
    # Find missing shows command
    missing_parser = subparsers.add_parser(
        'find-missing',
        help='Find shows with no video files and search for download candidates'
    )
    missing_parser.add_argument(
        '--source', choices=['spreadsheet', 'youtube', 'both'], default='both',
        help='Search priority: spreadsheet first, youtube only, or both (default: both)'
    )
    missing_parser.add_argument(
        '--year', type=int,
        help='Filter by specific year'
    )
    missing_parser.add_argument(
        '--max-results', type=int, default=50,
        help='Maximum number of candidates to find (default: 50)'
    )
    missing_parser.add_argument(
        '--download', action='store_true',
        help='Automatically download found candidates'
    )
    missing_parser.add_argument(
        '--auto-confirm', action='store_true',
        help='Skip download confirmations (use with --download)'
    )
    missing_parser.add_argument(
        '--format', default='best',
        help='Video format to download (default: best)'
    )
    
    # Integrity check command
    integrity_parser = subparsers.add_parser(
        'integrity',
        help='Check for date mismatches and other issues'
    )
    integrity_parser.add_argument(
        '--fix',
        action='store_true',
        help='Attempt to fix detected issues'
    )

    # Plex integration commands
    plex_parser = subparsers.add_parser(
        'plex',
        help='Plex integration and management'
    )
    plex_subparsers = plex_parser.add_subparsers(dest='plex_action')
    
    # Process new show
    process_parser = plex_subparsers.add_parser('process-show', help='Process new show with full Plex integration')
    process_parser.add_argument('show_path', help='Path to show directory')
    process_parser.add_argument('--tour', help='Tour name (auto-detected if not provided)')
    
    # Sync with Plex
    plex_subparsers.add_parser('sync', help='Synchronize collection with Plex')
    
    # Plex statistics
    plex_subparsers.add_parser('stats', help='Show Plex library statistics')
    
    # Find shows missing from collections
    plex_subparsers.add_parser('missing-collections', help='Find shows not assigned to collections')
    
    # Comprehensive library fix
    plex_subparsers.add_parser('fix-all', help='Comprehensive library fix (unmatched items, titles, collections)')

    # Fix multi-show items
    plex_subparsers.add_parser('fix-multi-show', help='Fix items with multiple shows grouped incorrectly')

    # Refresh metadata from API
    plex_subparsers.add_parser('refresh-metadata', help='Refresh summaries and posters from KGLW.net API')

    # Clean up empty collections
    cleanup_parser = plex_subparsers.add_parser('cleanup-empty-collections', help='Remove Plex collections with 0 items')
    cleanup_parser.add_argument('--no-dry-run', action='store_true', help='Actually delete (default is dry-run mode)')

    # Import video file command
    import_parser = subparsers.add_parser(
        'import',
        help='Import an existing video file into the collection'
    )
    import_parser.add_argument(
        'file_path',
        type=Path,
        help='Path to the video file to import'
    )
    import_parser.add_argument(
        '--date',
        required=True,
        help='Show date in YYYY-MM-DD format'
    )
    import_parser.add_argument(
        '--location',
        required=True,
        help='Show location (e.g., "Austin, TX")'
    )
    import_parser.add_argument(
        '--venue',
        help='Venue name (optional)'
    )
    import_parser.add_argument(
        '--url',
        help='YouTube URL for reference metadata (optional)'
    )
    import_parser.add_argument(
        '--copy',
        action='store_true',
        help='Copy file instead of moving it'
    )

    # Configuration commands
    config_parser = subparsers.add_parser(
        'config',
        help='Manage KGLW Manager configuration'
    )
    config_subparsers = config_parser.add_subparsers(dest='config_action')
    
    config_subparsers.add_parser('setup', help='Interactive configuration setup')
    config_subparsers.add_parser('show', help='Show current configuration')
    
    # Config set command
    set_parser = config_subparsers.add_parser('set', help='Set configuration value')
    set_parser.add_argument('key', help='Configuration key')
    set_parser.add_argument('value', help='Configuration value')
    
    # Global options
    parser.add_argument(
        '--collection-path', 
        default=config.get('collection_path'),
        help='Path to KGLW collection (default: %(default)s)'
    )
    parser.add_argument(
        '--mode',
        choices=['movie', 'tv'],
        default='movie',
        help='Collection mode for Plex (default: %(default)s)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true', 
        help='Suppress non-error output'
    )
    parser.add_argument(
        '--discord-webhook-url',
        help='Discord webhook URL for notifications (can also use KGLW_DISCORD_WEBHOOK_URL env var)'
    )
    
    return parser


def handle_interactive_command(args, manager: CollectionManager):
    """Handle interactive mode."""
    interactive = InteractiveManager(manager)
    interactive.start()


def handle_scan_command(args, manager: CollectionManager):
    """Handle scan command."""
    print("🔍 Scanning collection...")
    collection = manager.scan_collection(force_rescan=getattr(args, 'force', False))
    
    print("\n📊 Collection Summary")
    print("=" * 30)
    print(f"Tours: {collection['total_tours']}")
    print(f"Shows: {collection['total_shows']}")
    print(f"Videos: {collection['total_videos']}")
    
    print("\n🎫 Tours by Year:")
    tours_by_year = {}
    for tour_name in collection['tours'].keys():
        year = tour_name.split()[0]
        if year.isdigit():
            tours_by_year[year] = tours_by_year.get(year, 0) + 1
    
    for year in sorted(tours_by_year.keys(), reverse=True):
        count = tours_by_year[year]
        print(f"  {year}: {count} tour{'s' if count != 1 else ''}")


def handle_find_upgrades_command(args, manager: CollectionManager):
    """Handle find-upgrades command."""
    filters = {}
    
    if args.year:
        filters['year'] = args.year
        print(f"🔍 Finding upgrade candidates for {args.year}...")
    else:
        print("🔍 Finding upgrade candidates...")
    
    candidates = manager.find_upgrade_candidates(filters, force=args.force)

    if not candidates:
        print("✅ No upgrade candidates found!")
        if manager.video_cache.get_stats().get('total_entries', 0) == 0:
            print("💡 No videos have been quality-analyzed yet, so resolution "
                  "could not be compared.")
            print("   Run 'analyze-quality' first to enable quality-based "
                  "upgrade detection.")
        return
    
    print(f"\n🔄 Found {len(candidates)} shows that could benefit from upgrades:")
    print("-" * 60)
    
    for i, candidate in enumerate(candidates, 1):
        date = candidate.get('date', 'Unknown')
        location = candidate.get('location', 'Unknown')
        tour = candidate.get('tour', 'Unknown')
        file_count = len(candidate.get('current_files', []))
        
        print(f"{i:3d}. {date} - {location}")
        print(f"     Tour: {tour} | Files: {file_count}")
        
        # Show current quality info
        files = candidate.get('current_files', [])
        if files:
            qualities = [f.get('quality', 'unknown') for f in files]
            print(f"     Current: {', '.join(qualities)}")
        
        print()
    
    if args.auto_download:
        print("🚀 Auto-download mode - searching for upgrades...")
        
        upgraded_count = 0
        failed_count = 0
        
        for i, candidate in enumerate(candidates, 1):
            print(f"\n[{i}/{len(candidates)}] Processing: {candidate['date']} - {candidate['location']}")
            
            # Display upgrade reasons if available
            upgrade_reasons = candidate.get('upgrade_reasons', [])
            current_quality = candidate.get('current_quality', 'Unknown')
            if upgrade_reasons:
                reason_text = ", ".join(upgrade_reasons)
                print(f"  💡 Upgrade reasons: {reason_text}")
            print(f"  📊 Current: {current_quality}")
            
            # Search for upgrades
            show_info = {
                'date': candidate['date'],
                'location': candidate['location'],
                'venue': candidate['venue']
            }
            
            try:
                # Use enhanced search with comprehensive fallback (returns ALL sources)
                upgrade_candidates = manager.youtube_searcher.search_for_upgrades_with_fallback(show_info)

                if upgrade_candidates:
                    # Try ALL candidates from all sources until one succeeds
                    upgrade_success = False
                    total_candidates = len(upgrade_candidates)

                    print(f"  🔍 Found {total_candidates} candidate(s) from all sources (spreadsheet + database + YouTube)")

                    for i, upgrade_candidate in enumerate(upgrade_candidates):
                        candidate_title = upgrade_candidate.get('title', 'Unknown')
                        candidate_quality = upgrade_candidate.get('height', 'unknown')
                        source_indicator = ""

                        # Indicate source type for better logging
                        if 'source' in upgrade_candidate:
                            source_indicator = f" [{upgrade_candidate['source']}]"

                        if i == 0:
                            print(f"  📥 Trying: {candidate_title} ({candidate_quality}p){source_indicator}")
                        else:
                            print(f"  📥 Alternative {i+1}/{total_candidates}: {candidate_title} ({candidate_quality}p){source_indicator}")

                        # Attempt upgrade
                        success = manager.perform_upgrade(candidate['path'], upgrade_candidate)
                        if success:
                            print(f"  ✅ Upgrade successful (tried {i+1}/{total_candidates} candidates)")
                            upgraded_count += 1
                            upgrade_success = True
                            break
                        else:
                            if i < len(upgrade_candidates) - 1:  # More candidates available
                                print(f"  ⏭️  Failed, trying next candidate...")
                            else:
                                print(f"  ❌ All {total_candidates} candidates failed")

                    if not upgrade_success:
                        failed_count += 1
                else:
                    print("  ❌ No candidates found from any source")
                    failed_count += 1
                    
            except Exception as e:
                print(f"  ❌ Error: {e}")
                failed_count += 1
        
        # Send bulk upgrade summary notification
        if upgraded_count > 0 or failed_count > 0:
            try:
                manager.discord_notifier.notify_bulk_upgrade_summary(
                    upgraded_count=upgraded_count,
                    failed_count=failed_count,
                    total_candidates=len(candidates)
                )
            except Exception as e:
                logger.warning(f"Failed to send Discord bulk upgrade summary: {e}")


def handle_stats_command(args, manager: CollectionManager):
    """Handle stats command."""
    print("📊 Generating detailed statistics...")
    stats = manager.get_collection_stats()
    
    print("\n📈 Collection Statistics")
    print("=" * 40)
    print(f"Total Tours: {stats['total_tours']}")
    print(f"Total Shows: {stats['total_shows']}")
    print(f"Total Videos: {stats['total_videos']}")
    
    # Years breakdown
    print("\n📅 Shows by Year:")
    for year in sorted(stats['tours_by_year'].keys(), reverse=True):
        count = stats['tours_by_year'][year]
        print(f"  {year}: {count} show{'s' if count != 1 else ''}")
    
    # Quality distribution
    print("\n🎥 Quality Distribution:")
    quality_stats = stats['quality_distribution']
    for quality in sorted(quality_stats.keys(), key=lambda x: int(x.replace('p', '').replace('+', '').replace('-', '').replace('unknown', '0'))):
        count = quality_stats[quality]
        print(f"  {quality}: {count} video{'s' if count != 1 else ''}")
    
    # Plex naming compliance
    plex_stats = stats['plex_naming_compliance']
    total_files = plex_stats['compliant'] + plex_stats['non_compliant']
    compliance_pct = (plex_stats['compliant'] / total_files * 100) if total_files > 0 else 0
    
    print("\n📝 Plex Naming Compliance:")
    print(f"  Compliant: {plex_stats['compliant']} ({compliance_pct:.1f}%)")
    print(f"  Non-compliant: {plex_stats['non_compliant']}")
    
    # Cache stats
    cache_stats = stats['cache_stats']
    print("\n💾 Cache Statistics:")
    print(f"  Cached entries: {cache_stats['total_entries']}")
    print(f"  Cache file size: {cache_stats['cache_file_size']} bytes")


def handle_analyze_quality_command(args, manager: CollectionManager):
    """Handle analyze-quality command."""
    from pathlib import Path

    print("🔍 Analyzing video quality for collection...")

    # Determine analysis method
    use_plex = not args.disable_plex and hasattr(manager, 'plex_manager') and manager.plex_manager
    if use_plex:
        print("📊 Using Plex metadata for quality analysis (faster)")
    else:
        print("🔧 Using ffprobe for quality analysis")
        if args.disable_plex:
            print("   (Plex disabled by --disable-plex flag)")
        elif not hasattr(manager, 'plex_manager') or not manager.plex_manager:
            print("   (Plex not configured or unavailable)")

    # Scan collection to get all shows
    collection = manager.scan_collection()
    all_shows = []

    for tour_name, tour_data in collection['tours'].items():
        for show_date, show in tour_data['shows'].items():
            # Apply filters if specified
            if args.year:
                show_year = show_date.split('-')[0]
                if show_year != str(args.year):
                    continue

            if args.tour and args.tour.lower() not in tour_name.lower():
                continue

            all_shows.append((tour_name, show))

    if not all_shows:
        print("❌ No shows found matching filters")
        return

    print(f"📊 Analyzing {len(all_shows)} shows...")

    # Track stats
    analyzed_count = 0
    cached_count = 0
    error_count = 0
    quality_counts = {}

    # Progress tracking
    from rich.progress import Progress

    with Progress() as progress:
        task = progress.add_task("Analyzing videos...", total=len(all_shows))

        for tour_name, show in all_shows:
            progress.update(task, description=f"Analyzing {show.get('date', 'Unknown')}...")

            try:
                # Process each video file in the show
                for file_info in show.get('files', []):
                    file_path = Path(file_info['path'])

                    # Check if we should force re-analysis
                    if not args.force:
                        cached_metadata = manager.video_cache.get_metadata(file_path)
                        if cached_metadata and cached_metadata.get('quality') != 'unknown':
                            cached_count += 1
                            quality = cached_metadata.get('quality', 'unknown')
                            quality_counts[quality] = quality_counts.get(quality, 0) + 1
                            continue

                    # Use Plex metadata automatically if available (unless disabled)
                    if not args.disable_plex and hasattr(manager, 'plex_manager') and manager.plex_manager:
                        try:
                            plex_metadata = manager._get_plex_metadata_for_file(file_path)
                            if plex_metadata:
                                quality_info = manager._extract_quality_from_plex(plex_metadata)
                                if quality_info and quality_info.get('quality') != 'unknown':
                                    # Cache the Plex-derived metadata
                                    manager.video_cache.set_metadata(file_path, quality_info)
                                    analyzed_count += 1
                                    quality = quality_info.get('quality', 'unknown')
                                    quality_counts[quality] = quality_counts.get(quality, 0) + 1
                                    continue
                        except (AttributeError, Exception):
                            # Plex not available or failed, fall back to ffprobe
                            pass

                    # Perform full ffprobe analysis (bypass fast_scan)
                    quality_info = manager._analyze_video_file(file_path, fast_scan=False)
                    analyzed_count += 1

                    quality = quality_info.get('quality', 'unknown')
                    quality_counts[quality] = quality_counts.get(quality, 0) + 1

            except Exception as e:
                error_count += 1
                print(f"⚠️ Error analyzing {show.get('date', 'Unknown')}: {e}")

            progress.advance(task)

    # Display results
    print(f"\n✅ Quality analysis complete!")
    print(f"📊 Analyzed: {analyzed_count} videos")
    print(f"💾 From cache: {cached_count} videos")
    print(f"❌ Errors: {error_count} videos")

    print(f"\n🎥 Quality Distribution:")
    for quality in sorted(quality_counts.keys(), key=lambda x: int(x.replace('p', '').replace('+', '').replace('-', '').replace('unknown', '0'))):
        count = quality_counts[quality]
        print(f"  {quality}: {count} video{'s' if count != 1 else ''}")

    # Show cache statistics
    print(f"\n💾 Updated video metadata cache")
    try:
        cache_stats = manager.video_cache.get_stats()
        print(f"Cache entries: {cache_stats.get('total_entries', 0)}")
    except AttributeError:
        print("Cache statistics not available")


def handle_cache_command(args, manager: CollectionManager):
    """Handle cache management commands."""
    if args.cache_action == 'clear':
        # Clear both caches
        manager.video_cache.clear_cache() if hasattr(manager.video_cache, 'clear_cache') else None
        manager.collection_cache.clear_cache()
        print("✅ All caches cleared")
        
    elif args.cache_action == 'clear-video':
        # Clear video metadata cache only
        video_cache_file = manager.video_cache.cache_file
        if video_cache_file.exists():
            video_cache_file.unlink()
            print("✅ Video metadata cache cleared")
        else:
            print("ℹ️  Video metadata cache already empty")
            
    elif args.cache_action == 'clear-collection':
        # Clear collection structure cache only
        manager.collection_cache.clear_cache()
        print("✅ Collection structure cache cleared")
            
    elif args.cache_action == 'stats':
        # Show stats for both caches
        video_stats = manager.video_cache.get_stats()
        collection_stats = manager.collection_cache.get_cache_stats()
        
        print("💾 Cache Statistics:")
        print("\n📹 Video Metadata Cache:")
        print(f"  Entries: {video_stats['total_entries']}")
        print(f"  File size: {video_stats['cache_file_size']} bytes")
        print(f"  Location: {video_stats['cache_file_path']}")
        
        print("\n📁 Collection Structure Cache:")
        print(f"  Collections: {collection_stats['total_collections']}")
        print(f"  File size: {collection_stats['cache_file_size']} bytes")
        print(f"  Location: {collection_stats['cache_file_path']}")
        
    elif args.cache_action == 'cleanup':
        print("🧹 Cleaning up stale cache entries...")
        manager.cleanup_stale_cache()  # Video cache cleanup
        print("✅ Cache cleanup complete")
        
    elif args.cache_action == 'clear-failed':
        # Clear all failed upgrade attempts
        cleared_count = manager.clear_failed_upgrade_attempts()
        if cleared_count > 0:
            print(f"✅ Cleared failed upgrade attempts for {cleared_count} shows")
        else:
            print("ℹ️  No failed upgrade attempts to clear")
            
    elif args.cache_action == 'clear-show':
        # Clear upgrade tracking for specific show
        cleared_count = manager.clear_failed_upgrade_attempts(args.date)
        if cleared_count > 0:
            print(f"✅ Cleared upgrade tracking for {args.date}")
        else:
            print(f"ℹ️  No upgrade tracking found for {args.date}")
            
    elif args.cache_action == 'upgrade-stats':
        # Show upgrade tracking statistics
        stats = manager.get_upgrade_tracking_stats()
        print("📊 Upgrade Tracking Statistics:")
        print(f"  Shows with failed attempts: {stats['failed_shows']}")
        print(f"  Shows successfully upgraded: {stats['successful_shows']}")
        print(f"  Shows recently checked: {stats['recently_checked']}")
        print(f"  Shows blocked (5+ failures): {stats['blocked_shows']}")
        print(f"  Total failed attempts: {stats['total_attempts']}")
        
        if stats['blocked_shows'] > 0:
            print(f"\n💡 Use 'cache clear-failed' to reset blocked shows")
    
    elif args.cache_action == 'api-stats':
        # Show API cache statistics
        cache_info = manager.tour_manager.get_cache_info()
        print("🌐 KGLW.net API Cache Statistics")
        print("=" * 40)
        
        if cache_info['cached']:
            age_minutes = cache_info['age_minutes']
            status = "EXPIRED" if cache_info['expired'] else "VALID"
            print(f"  Status: {status}")
            print(f"  Age: {age_minutes:.1f} minutes")
            print(f"  Tours cached: {cache_info['tours_count']}")
            print(f"  Cache duration: 60 minutes")
        else:
            print("  Status: NO CACHE")
            print("  Tours cached: 0")
    
    elif args.cache_action == 'clear-api':
        # Clear API cache
        manager.tour_manager.clear_api_cache()
        print("✅ KGLW.net API tour cache cleared")


def handle_fresh_setup_command(args):
    """Handle fresh collection setup command."""
    from .fresh_collection_setup import create_fresh_collection, preview_fresh_collection
    
    if args.preview:
        print("🎸 Fresh Collection Preview")
        print("="*60)
        
        preview = preview_fresh_collection(args.collection_path)
        if preview.get('success', True):
            print(f"📁 Collection path: {preview['collection_path']}")
            print(f"🎪 Total tours: {preview['total_tours']}")
            print(f"🎵 Total shows: {preview['total_shows']}")
            print()
            print("📊 Sample Tours:")
            for i, (tour_name, info) in enumerate(list(preview['tours'].items())[:5]):
                print(f"{i+1:2d}. {tour_name}")
                print(f"    Directory: {info['normalized_name']}")
                print(f"    Shows: {info['show_count']}")
                print(f"    Date range: {info['date_range']['start']} to {info['date_range']['end']}")
            
            if len(preview['tours']) > 5:
                print(f"... and {len(preview['tours']) - 5} more tours")
        else:
            print(f"❌ Error: {preview.get('error', 'Unknown error')}")
    else:
        results = create_fresh_collection(args.collection_path, dry_run=not args.apply)
        
        if not results['success']:
            print(f"❌ Setup failed")
            for error in results.get('errors', []):
                print(f"   • {error}")
        # Results already printed by the function


def handle_test_discord_command(args, manager: CollectionManager):
    """Handle test Discord webhook command."""
    print("🧪 Testing Discord webhook...")
    
    if not manager.discord_notifier.enabled:
        print("❌ Discord notifications are not configured")
        print("   Set KGLW_DISCORD_WEBHOOK_URL environment variable or use --discord-webhook-url")
        return
    
    success = manager.discord_notifier.test_notification()
    if success:
        print("✅ Discord test notification sent successfully!")
    else:
        print("❌ Discord test notification failed. Check your webhook URL and network connection.")


def handle_import_command(args, manager: CollectionManager):
    """Handle import video file command."""
    print(f"📥 Importing video file: {args.file_path}")

    # Validate file exists
    if not args.file_path.exists():
        print(f"❌ File does not exist: {args.file_path}")
        return

    # Build show info
    show_info = {
        'date': args.date,
        'location': args.location,
        'venue': getattr(args, 'venue', '') or ''
    }

    # Validate date format
    import re
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', args.date):
        print("❌ Date must be in YYYY-MM-DD format")
        return

    # Display import details
    print(f"   Date: {args.date}")
    print(f"   Location: {args.location}")
    if show_info['venue']:
        print(f"   Venue: {show_info['venue']}")
    if args.url:
        print(f"   Reference URL: {args.url}")

    # Get move/copy setting
    move_file = not getattr(args, 'copy', False)
    action = "Moving" if move_file else "Copying"
    print(f"   Action: {action} file")

    # Perform import
    result_path = manager.import_video_file(
        file_path=args.file_path,
        show_info=show_info,
        youtube_url=getattr(args, 'url', None),
        move_file=move_file
    )

    if result_path:
        print(f"\n✅ Import successful!")
        print(f"   Imported to: {result_path}")
    else:
        print(f"\n❌ Import failed")
        print(f"   Check logs for details")


def handle_config_command(args):
    """Handle configuration commands."""
    if args.config_action == 'setup':
        config.interactive_setup()
    elif args.config_action == 'show':
        config.show_config()
    elif args.config_action == 'set':
        config.set(args.key, args.value)
        if config.save_config():
            print(f"✅ Set {args.key} = {args.value}")
        else:
            print("❌ Failed to save configuration")
    else:
        print("❌ Unknown config command. Use --help to see available options.")


def handle_spreadsheet_command(args, manager: CollectionManager):
    """Handle spreadsheet import commands."""
    if args.spreadsheet_action == 'download':
        from .spreadsheet_downloader import SpreadsheetDownloader
        from pathlib import Path
        
        downloader = SpreadsheetDownloader()
        
        if args.method == 'manual':
            # Show manual download instructions
            print(downloader.manual_download_instructions())
            return
            
        elif args.method == 'script':
            # Create helper script
            output_dir = Path(args.output) if args.output else Path.cwd()
            script_path = downloader.create_download_script(output_dir / 'download_spreadsheet.sh')
            print(f"📝 Created download script: {script_path}")
            print(f"📋 Run it with: bash {script_path}")
            return
            
        else:  # auto mode
            print("📥 Attempting to download Google Sheets HTML export...")
            output_dir = Path(args.output) if args.output else None
            
            # Try automatic download
            html_path = downloader.download_html_export(output_dir)
            
            if html_path and html_path.exists():
                print(f"✅ Successfully downloaded: {html_path}")
                print(f"💡 Next step: Run './kglw-manager.py spreadsheet load-file --file {html_path}'")
            else:
                print("⚠️ Automatic download failed. Showing manual instructions...")
                print(downloader.manual_download_instructions())
    
    elif args.spreadsheet_action == 'load':
        print("📊 Loading YouTube links from spreadsheet...")
        success = manager.load_spreadsheet_data()
        if success:
            stats = manager.get_spreadsheet_stats()
            print(f"✅ Loaded {stats['total_shows']} shows with {stats['total_youtube_links']} YouTube links")
            print(f"📅 Date range: {min(stats['years'].keys())} - {max(stats['years'].keys())}")
        else:
            print("❌ Failed to load spreadsheet data")
    
    elif args.spreadsheet_action == 'load-file':
        print(f"📊 Loading YouTube links from: {args.file}")
        success = manager.load_spreadsheet_data(args.file)
        if success:
            stats = manager.get_spreadsheet_stats()
            print(f"✅ Loaded {stats['total_shows']} shows with {stats['total_youtube_links']} YouTube links")
            print(f"📅 Date range: {min(stats['years'].keys())} - {max(stats['years'].keys())}")
        else:
            print("❌ Failed to load spreadsheet data")
    
    elif args.spreadsheet_action == 'stats':
        stats = manager.get_spreadsheet_stats()
        if 'error' in stats:
            print("❌ No spreadsheet data loaded. Run 'spreadsheet load' first.")
            return
        
        print("📊 Spreadsheet Statistics:")
        print(f"  Total shows: {stats['total_shows']}")
        print(f"  Shows with YouTube links: {stats['total_shows']}")
        print(f"  Total YouTube links: {stats['total_youtube_links']}")
        print(f"  Latest show: {stats['latest_show']}")
        
        print("\n📅 Shows by Year:")
        for year in sorted(stats['years'].keys(), reverse=True):
            count = stats['years'][year]
            print(f"  {year}: {count} show{'s' if count != 1 else ''}")
        
        print("\n🌍 Shows by Country:")
        for country, count in sorted(stats['countries'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {country}: {count} show{'s' if count != 1 else ''}")
    
    elif args.spreadsheet_action == 'missing':
        print("🔍 Finding shows in spreadsheet that aren't in your collection...")
        missing = manager.find_missing_shows_in_collection()
        
        if not missing:
            print("✅ No missing shows found - your collection matches the spreadsheet!")
            return
        
        print(f"\n📋 Found {len(missing)} shows in spreadsheet but not in collection:")
        print("-" * 80)
        
        # Group by year
        missing_by_year = {}
        for show in missing:
            year = show['date'][:4]
            if year not in missing_by_year:
                missing_by_year[year] = []
            missing_by_year[year].append(show)
        
        for year in sorted(missing_by_year.keys(), reverse=True):
            shows = missing_by_year[year]
            print(f"\n{year} ({len(shows)} shows):")
            
            for show in sorted(shows, key=lambda x: x['date']):
                date = show['date']
                location = show['location']
                venue = show.get('venue', '')
                link_count = len(show.get('youtube_links', []))
                
                venue_text = f" ({venue})" if venue else ""
                print(f"  {date} - {location}{venue_text} [{link_count} link{'s' if link_count != 1 else ''}]")
                
                # Show first YouTube link as example
                if show.get('youtube_links'):
                    first_link = show['youtube_links'][0]
                    print(f"    🔗 {first_link['url']}")
    
    elif args.spreadsheet_action == 'failures':
        handle_link_failures_command(args, manager)
    
    else:
        print("❌ Unknown spreadsheet command. Use --help to see available options.")


def handle_link_failures_command(args, manager: CollectionManager):
    """Handle link failure tracking commands."""
    from .link_failure_tracker import LinkFailureTracker
    
    tracker = manager.youtube_searcher.failure_tracker
    
    if args.failures_action == 'stats':
        print("📊 Link Failure Tracking Statistics")
        print("=" * 50)
        
        stats = tracker.get_stats()
        print(f"Total failed links tracked: {stats['total_failures']}")
        print(f"Recent failures (7 days): {stats['recent_failures_7_days']}")
        if stats['total_failures'] > 0:
            print(f"Oldest failure: {stats['oldest_failure']}")
            print(f"Newest failure: {stats['newest_failure']}")
    
    elif args.failures_action == 'report':
        print("📋 Generating comprehensive failure report...")
        report = tracker.generate_report()
        
        print(f"\n📊 Failure Report (last 30 days)")
        print("=" * 60)
        print(f"Total failed links: {report['total_failed_links']}")
        print(f"Unique failed URLs: {report['unique_failed_urls']}")
        print(f"Permanent failures: {report['permanent_failures']}")
        
        print(f"\n🔍 Failures by reason:")
        for reason, count in report['failures_by_reason'].items():
            print(f"  {reason.replace('_', ' ').title()}: {count}")
        
        print(f"\n📍 Failures by spreadsheet column:")
        for column, count in report['failures_by_column'].items():
            print(f"  {column}: {count}")
        
        if report['top_problem_shows']:
            print(f"\n⚠️  Most problematic shows:")
            for show_data in report['top_problem_shows'][:5]:
                show = show_data['show']
                count = show_data['failure_count']
                print(f"  {show}: {count} failed link{'s' if count != 1 else ''}")
    
    elif args.failures_action == 'export':
        print("📤 Exporting failed links report for spreadsheet maintainer...")
        output_file = tracker.export_for_spreadsheet_maintainer()
        
        print(f"✅ Report exported to: {output_file}")
        print("\n📋 This report contains:")
        print("  • Dead links that should be removed from spreadsheet")
        print("  • Problematic links that need investigation")
        print("  • Shows with multiple link failures")
        print("\n💡 Share this report with the spreadsheet maintainer!")
    
    elif args.failures_action == 'cleanup':
        print("🧹 Cleaning up old failure records...")
        tracker.cleanup_old_failures()
        print("✅ Cleanup complete")
    
    elif args.failures_action == 'test-links':
        print(f"🧪 Testing spreadsheet links for {args.date}...")
        
        show_info = {
            'date': args.date,
            'location': args.location or '',
            'venue': ''
        }
        
        # Use the enhanced search to test links
        candidates = manager.youtube_searcher._get_all_spreadsheet_candidates_with_tracking(
            args.date, args.location or ''
        )
        
        if not candidates:
            print("❌ No working links found for this show")
            
            # Check if we have failure records for this show
            failures = tracker.get_failures_by_show(args.date)
            if failures:
                print(f"\n📝 Found {len(failures)} failed link records:")
                for failure in failures:
                    print(f"  ❌ {failure.url}")
                    print(f"     Reason: {failure.failure_reason.value}")
                    print(f"     Column: {failure.column_source}")
                    print(f"     Error: {failure.error_message}")
                    print()
        else:
            print(f"✅ Found {len(candidates)} working links:")
            for i, candidate in enumerate(candidates, 1):
                quality = f"{candidate.get('height', 'Unknown')}p"
                duration = candidate.get('duration', 0)
                duration_str = f"{duration//60:.0f}min" if duration else "Unknown"
                source = candidate.get('column_source', 'Unknown')
                
                print(f"  {i}. {candidate['url']}")
                print(f"     Quality: {quality}, Duration: {duration_str}, Source: {source}")
    
    else:
        print("❌ Unknown failures command. Use --help to see available options.")


def handle_find_missing_command(args, manager: CollectionManager):
    """Handle find-missing command."""
    print("🔍 Finding shows with no video files...")
    
    # Find missing shows
    missing_shows = manager.find_missing_shows(
        source_priority=args.source,
        max_results=args.max_results,
        year_filter=args.year
    )
    
    if not missing_shows:
        print("✅ No missing shows found! All shows in collection have video files.")
        return
    
    print(f"\n📊 Found {len(missing_shows)} shows with download candidates:")
    
    # Display summary
    from rich.table import Table
    from rich.console import Console
    
    console = Console()
    table = Table(title="Missing Shows with Candidates", show_header=True)
    table.add_column("Date", style="cyan", width=12)
    table.add_column("Location", style="yellow", width=25)
    table.add_column("Tour", style="green", width=20) 
    table.add_column("Candidate Source", style="magenta", width=15)
    table.add_column("Title Preview", style="white", width=40)
    
    for missing_show in missing_shows:
        show_info = missing_show['show_info']
        candidate = missing_show['candidate']
        
        show_date = show_info.get('date', 'Unknown')
        show_location = show_info.get('location', 'Unknown')[:25]
        tour_name = missing_show.get('tour', 'Unknown')[:20]
        source = candidate.get('source', 'unknown')
        title = candidate.get('title', 'Unknown')[:40]
        
        table.add_row(show_date, show_location, tour_name, source, title)
    
    console.print(table)
    
    # Download if requested
    if args.download:
        print(f"\n📥 Starting download of {len(missing_shows)} missing shows...")
        
        results = manager.download_missing_shows(
            missing_shows=missing_shows,
            auto_confirm=args.auto_confirm,
            format_id=args.format
        )
        
        print(f"\n📊 Final Results:")
        print(f"  ✅ Successfully downloaded: {results['success']}")
        print(f"  ❌ Failed to download: {results['failed']}")
        print(f"  ⏭️  Skipped: {results['skipped']}")
        
    else:
        print(f"\nℹ️  Use --download to automatically download these {len(missing_shows)} shows")
        print("   Or use --help to see all options")


def handle_integrity_command(args, manager: CollectionManager):
    """Handle integrity check command."""
    print("🔍 Checking collection integrity...")
    
    # Scan collection to get all shows
    collection = manager.scan_collection()
    
    issues_found = []
    shows_checked = 0
    
    print("\n📁 Checking for date mismatches between folders and video files...")
    
    for tour_name, tour_data in collection['tours'].items():
        # shows is a dict of show-name -> plain dict (keys: date, location,
        # files, path); iterating the dict itself would yield bare strings.
        for show in tour_data.get('shows', {}).values():
            shows_checked += 1
            folder_date = show.get('date', '')
            folder_location = show.get('location', '')
            show_path = show.get('path', '')

            # Check each video file in the show
            for video_file in show.get('files', []):
                video_path = Path(video_file.get('path', ''))
                info_json_path = video_path.with_suffix('.info.json')
                if info_json_path.exists():
                    try:
                        import json
                        with open(info_json_path, 'r') as f:
                            info = json.load(f)
                        
                        # Get upload date from video info
                        upload_date = info.get('upload_date', '')
                        video_title = info.get('title', '')
                        
                        # Try to extract date from video title
                        import re
                        title_dates = re.findall(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4})', video_title)
                        
                        # Check if upload date is significantly different from folder date
                        if upload_date and len(upload_date) == 8:  # Format: YYYYMMDD
                            upload_year = upload_date[:4]
                            folder_year = folder_date.split('-')[0]
                            
                            if upload_year != folder_year:
                                issues_found.append({
                                    'type': 'date_mismatch',
                                    'show_path': show_path,
                                    'folder_date': folder_date,
                                    'folder_location': folder_location,
                                    'video_file': video_path.name,
                                    'upload_date': f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}",
                                    'video_title': video_title[:80] + ('...' if len(video_title) > 80 else ''),
                                    'info': info
                                })
                        
                        # Check if title suggests different location or date
                        if title_dates:
                            for title_date in title_dates:
                                # Convert title date to YYYY-MM-DD format
                                if '/' in title_date:
                                    parts = title_date.split('/')
                                elif '-' in title_date:
                                    parts = title_date.split('-')
                                else:
                                    continue
                                
                                # Handle different date formats
                                if len(parts) == 3:
                                    if len(parts[0]) == 4:  # YYYY-MM-DD or YYYY/MM/DD
                                        title_year = parts[0]
                                    elif len(parts[2]) == 4:  # MM-DD-YYYY or MM/DD/YYYY  
                                        title_year = parts[2]
                                    else:
                                        continue
                                        
                                    folder_year = folder_date.split('-')[0]
                                    if title_year != folder_year:
                                        issues_found.append({
                                            'type': 'title_date_mismatch',
                                            'show_path': show_path,
                                            'folder_date': folder_date,
                                            'folder_location': folder_location,
                                            'video_file': video_path.name,
                                            'title_date': title_date,
                                            'video_title': video_title[:80] + ('...' if len(video_title) > 80 else ''),
                                            'info': info
                                        })
                                        break
                                        
                    except Exception as e:
                        # Skip files with invalid JSON or missing info
                        continue
    
    print(f"\n📊 Integrity Check Results")
    print("=" * 40)
    print(f"Shows checked: {shows_checked}")
    print(f"Issues found: {len(issues_found)}")
    
    if issues_found:
        print("\n⚠️  Issues Detected:")
        print("-" * 40)
        
        for i, issue in enumerate(issues_found, 1):
            if issue['type'] == 'date_mismatch':
                print(f"\n{i}. DATE MISMATCH (Upload Date)")
                print(f"   📁 Folder: {issue['folder_date']} - {issue['folder_location']}")
                print(f"   🎥 Video:  {issue['upload_date']} (uploaded)")
                print(f"   📄 File:   {issue['video_file']}")
                print(f"   🏷️  Title:  {issue['video_title']}")
                print(f"   📂 Path:   {issue['show_path']}")
            
            elif issue['type'] == 'title_date_mismatch':
                print(f"\n{i}. DATE MISMATCH (Title Date)")
                print(f"   📁 Folder: {issue['folder_date']} - {issue['folder_location']}")
                print(f"   🎥 Video:  {issue['title_date']} (from title)")
                print(f"   📄 File:   {issue['video_file']}")
                print(f"   🏷️  Title:  {issue['video_title']}")
                print(f"   📂 Path:   {issue['show_path']}")
        
        if args.fix:
            print(f"\n🔧 Fix option is not yet implemented.")
            print(f"   These issues require manual review to ensure correct attribution.")
            print(f"   Consider moving shows to correct date folders or removing incorrect videos.")
        else:
            print(f"\n💡 Use --fix flag to attempt automatic fixes (when implemented)")
            print(f"   Or manually review and move shows to correct date folders")
    
    else:
        print("\n✅ No integrity issues found!")


def handle_plex_command(args, manager: CollectionManager):
    """Handle Plex integration commands."""
    if not manager.plex_manager:
        print("❌ Plex integration is not available")
        print("   Check your Plex configuration and ensure plexapi is installed")
        return
    
    if args.plex_action == 'process-show':
        show_path = Path(args.show_path)
        tour_name = getattr(args, 'tour', None)
        
        print(f"🎵 Processing show: {show_path}")
        if tour_name:
            print(f"   Tour: {tour_name}")
        else:
            print("   Tour: Auto-detect")
        
        results = manager.process_new_show(show_path, tour_name)
        
        print("\n📊 Processing Results:")
        print("=" * 40)
        if results['success']:
            print(f"✅ Success: {results['videos_processed']} videos processed")
            print(f"🎥 Videos found: {results['videos_found']}")
            print(f"🖼️  Posters found: {results['posters_found']}")
            print(f"📝 Metadata updated: {'Yes' if results['metadata_updated'] else 'No'}")
            print(f"📚 Collection updated: {'Yes' if results['collection_updated'] else 'No'}")
            if results.get('tour_assigned'):
                print(f"🎪 Tour assigned: {results['tour_assigned']}")
        else:
            print(f"❌ Processing failed")
            for error in results.get('errors', []):
                print(f"   • {error}")
    
    elif args.plex_action == 'sync':
        print("🔄 Synchronizing collection with Plex...")
        results = manager.sync_collection_with_plex()
        
        if 'error' in results:
            print(f"❌ Sync failed: {results['error']}")
            return
        
        print("\n📊 Sync Results:")
        print("=" * 40)
        print(f"Shows processed: {results['shows_processed']}")
        print(f"Shows updated: {results['shows_updated']}")
        print(f"Shows failed: {results['shows_failed']}")
        print(f"Total Plex items: {results['total_plex_items']}")
        print(f"Total collections: {results['total_collections']}")
    
    elif args.plex_action == 'stats':
        print("📊 Getting Plex library statistics...")
        stats = manager.get_plex_stats()
        
        if 'error' in stats:
            print(f"❌ Failed to get stats: {stats['error']}")
            return
        
        print("\n📺 Plex Library Statistics:")
        print("=" * 40)
        print(f"Total items: {stats['total_items']}")
        print(f"Total collections: {stats['total_collections']}")
        
        if stats.get('collections'):
            print(f"\n🎭 Collections:")
            for collection in stats['collections'][:10]:  # Show first 10
                print(f"   • {collection}")
            if len(stats['collections']) > 10:
                print(f"   ... and {len(stats['collections']) - 10} more")
        
        if stats.get('recent_items'):
            print(f"\n📅 Recent additions:")
            for item in stats['recent_items'][:5]:
                collections = ', '.join(item['collections']) if item['collections'] else 'None'
                print(f"   • {item['title']} (Collections: {collections})")
    
    elif args.plex_action == 'missing-collections':
        print("🔍 Finding shows not assigned to collections...")
        missing_shows = manager.find_plex_shows_missing_collections()
        
        if not missing_shows:
            print("✅ All shows are properly assigned to collections!")
            return
        
        print(f"\n📋 Found {len(missing_shows)} shows missing from collections:")
        print("-" * 80)
        
        for show in missing_shows:
            expected = show.get('expected_tour', 'Unknown')
            print(f"• {show['title']}")
            print(f"  Expected tour: {expected}")
            print(f"  Added: {show['added_at']}")
            print()
    
    elif args.plex_action == 'fix-all':
        print("🔧 Running comprehensive Plex library fix...")
        print("This will:")
        print("  • Fix multi-show items (shows grouped incorrectly)")
        print("  • Fix unmatched items with proper titles")
        print("  • Update metadata from KGLW.net API")
        print("  • Assign shows to proper collections")
        print("  • Fix title mismatches")

        results = manager.plex_manager.comprehensive_library_fix()

        print("\n📊 Comprehensive Fix Results:")
        print("=" * 40)
        if results.get('errors'):
            print(f"❌ Errors: {len(results['errors'])}")
            for error in results['errors']:
                print(f"   • {error}")
        else:
            print(f"🔀 Multi-show items split: {results['multi_show_fixed']}")
            if results['multi_show_fixed'] > 0:
                print(f"   ↳ Titles fixed: {results['multi_show_titles_fixed']}")
                print(f"   ↳ Collections updated: {results['multi_show_collections_updated']}")
            print(f"🔧 Unmatched items fixed: {results['unmatched_fixed']}")
            print(f"📚 Collections updated: {results['collections_updated']}")
            print(f"📝 Titles fixed: {results['titles_fixed']}")
            print(f"✅ Library fix completed successfully!")

    elif args.plex_action == 'fix-multi-show':
        print("🔀 Checking for multi-show items...")
        print("Looking for Plex items with video files from different shows grouped together...\n")

        multi_show_items = manager.plex_manager.find_multi_show_items()

        if not multi_show_items:
            print("✅ No multi-show items found! Your library is clean.")
        else:
            print(f"⚠️  Found {len(multi_show_items)} item(s) with multiple shows grouped together:\n")

            for item in multi_show_items:
                print(f"'{item['title']}'")
                print(f"  - {item['media_count']} files from {len(item['dates_found'])} different shows")
                print(f"  - Show dates: {', '.join(item['dates_found'])}")
                print()

            response = input("Would you like to split these items into separate shows? (y/n): ")
            if response.lower() == 'y':
                print("\n🔧 Splitting grouped items into separate shows...")
                results = manager.plex_manager.fix_multi_show_items()

                print(f"\n✅ Split complete!")
                print(f"Items split: {results['fixed']}/{results['found']}")
                print(f"Titles fixed: {results['titles_fixed']}")
                print(f"Collections updated: {results['collections_updated']}")

                if results['fixed'] > 0:
                    print("\nNote: Each show now has the correct title, poster, and tour collection.")

    elif args.plex_action == 'refresh-metadata':
        print("🎨 Refreshing metadata from KGLW.net API...")
        print("This will update summaries, posters, and collections for all shows in your Plex library.\n")

        response = input("Proceed with metadata refresh? (y/n): ")
        if response.lower() == 'y':
            print("\n🔄 Fetching metadata from KGLW.net API...")
            results = manager.plex_manager.refresh_metadata_from_api()

            print(f"\n✅ Metadata refresh complete!")
            print(f"Shows processed: {results['processed']}")
            print(f"Summaries updated: {results['metadata_updated']}")
            print(f"Posters updated: {results['posters_updated']}")
            print(f"Collections updated: {results['collections_updated']}")

            if results['failed'] > 0:
                print(f"⚠️  Failed: {results['failed']}")

    elif args.plex_action == 'cleanup-empty-collections':
        print("🧹 Cleaning up empty Plex collections...")
        dry_run = not args.no_dry_run

        if dry_run:
            print("🔍 DRY RUN MODE - No collections will be deleted\n")
        else:
            print("⚠️  This will permanently delete empty collections!\n")

        results = manager.plex_manager.cleanup_empty_collections(dry_run=dry_run)

        print(f"\n📊 Results:")
        print(f"Total collections: {results['total']}")
        print(f"Empty collections: {results['empty']}")

        if dry_run and results['empty'] > 0:
            print(f"\n💡 To actually delete, run with --no-dry-run flag")
        elif not dry_run:
            print(f"Deleted: {results['deleted']}")
            if results['failed'] > 0:
                print(f"⚠️  Failed: {results['failed']}")

    else:
        print("❌ Unknown Plex command. Use --help to see available options.")


def main():
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Set up logging
    if args.verbose:
        import logging
        logging.getLogger('kglw_manager').setLevel(logging.DEBUG)
    elif args.quiet:
        import logging
        logging.getLogger('kglw_manager').setLevel(logging.ERROR)

    # Check and update yt-dlp if needed (before any operations that need it)
    from kglw_manager.yt_dlp_updater import check_and_update_yt_dlp
    quiet_mode = args.quiet if hasattr(args, 'quiet') else False
    # Notify by default rather than pip-installing on every startup: this
    # project's environment is managed by uv, so a pip upgrade is reverted by
    # the next `uv run` and the "update" would repeat on every launch.
    check_and_update_yt_dlp(
        auto_update=config.get('auto_update_yt_dlp', False),
        quiet=quiet_mode,
    )

    # Get Discord webhook URL from environment variable or args
    discord_webhook_url = getattr(args, 'discord_webhook_url', None) or os.environ.get('KGLW_DISCORD_WEBHOOK_URL')

    # Initialize collection manager
    try:
        manager = CollectionManager(args.collection_path, args.mode, discord_webhook_url=discord_webhook_url)
    except Exception as e:
        print(f"❌ Failed to initialize collection manager: {e}")
        sys.exit(1)
    
    # Handle commands
    try:
        if args.command == 'interactive' or not args.command:
            handle_interactive_command(args, manager)
        elif args.command == 'scan':
            handle_scan_command(args, manager)
        elif args.command == 'find-upgrades':
            handle_find_upgrades_command(args, manager)
        elif args.command == 'stats':
            handle_stats_command(args, manager)
        elif args.command == 'analyze-quality':
            handle_analyze_quality_command(args, manager)
        elif args.command == 'cache':
            handle_cache_command(args, manager)
        elif args.command == 'setup-fresh':
            handle_fresh_setup_command(args)
        elif args.command == 'test-discord':
            handle_test_discord_command(args, manager)
        elif args.command == 'spreadsheet':
            handle_spreadsheet_command(args, manager)
        elif args.command == 'find-missing':
            handle_find_missing_command(args, manager)
        elif args.command == 'integrity':
            handle_integrity_command(args, manager)
        elif args.command == 'plex':
            handle_plex_command(args, manager)
        elif args.command == 'import':
            handle_import_command(args, manager)
        elif args.command == 'config':
            handle_config_command(args)
        else:
            print(f"❌ Unknown command: {args.command}")
            parser.print_help()
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user")
        sys.exit(0)
    except Exception as e:
        if args.verbose:
            import traceback
            traceback.print_exc()
        else:
            print(f"❌ Error: {e}")
        sys.exit(1)
    
    print("\n✅ Operation completed successfully")


if __name__ == '__main__':
    main()