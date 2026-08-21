"""Download management with progress bars."""

import subprocess
import re
import sys
import threading
import tempfile
import shutil
import logging
import io
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
from .utils import setup_logging, clean_filename
from .naming import NamingManager
from .api_tour_manager import get_tour_manager

# NOTE: CollectionManager is imported lazily where needed - collection.py
# imports this module, so a module-level import would be circular.

# Rich imports for better progress bars
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, TransferSpeedColumn, DownloadColumn

logger = setup_logging()


@contextmanager
def capture_logging_during_progress():
    """Capture logging messages during progress bar display to prevent interference."""
    captured_logs = []
    
    class ProgressLogHandler(logging.Handler):
        def emit(self, record):
            # Capture log messages instead of printing them immediately
            try:
                msg = self.format(record)
                captured_logs.append((record.levelno, msg))
            except Exception:
                pass
    
    # Create temporary handler
    temp_handler = ProgressLogHandler()
    temp_handler.setLevel(logging.DEBUG)
    
    # Get the root logger and our specific logger
    root_logger = logging.getLogger()
    kglw_logger = logging.getLogger('kglw_manager')
    
    # Remove existing handlers temporarily
    original_handlers = root_logger.handlers[:]
    kglw_original_handlers = kglw_logger.handlers[:]
    
    root_logger.handlers = [temp_handler]
    kglw_logger.handlers = [temp_handler]
    
    try:
        yield captured_logs
    finally:
        # Restore original handlers
        root_logger.handlers = original_handlers
        kglw_logger.handlers = kglw_original_handlers
        
        # Now print captured logs after progress bar is done
        if captured_logs:
            console = Console()
            for level, msg in captured_logs:
                if level >= logging.WARNING:  # Only show warnings and errors
                    if level >= logging.ERROR:
                        console.print(f"❌ {msg}", style="red")
                    else:
                        console.print(f"⚠️  {msg}", style="yellow")


class DownloadProgress:
    """Handle download progress reporting."""
    
    def __init__(self, callback: Optional[Callable] = None):
        self.callback = callback
        self.current_percent = 0
        self.current_speed = ""
        self.eta = ""
        self.file_size = ""
    
    def update(self, percent: float, speed: str = "", eta: str = "", size: str = ""):
        """Update progress information."""
        self.current_percent = percent
        self.current_speed = speed
        self.eta = eta
        self.file_size = size
        
        if self.callback:
            self.callback(percent, speed, eta, size)
    
    def show_progress_bar(self, percent: float, speed: str = "", eta: str = "", size: str = ""):
        """Display progress bar in terminal using Rich."""
        # This method is now handled by Rich Progress in download_video method
        pass


class DownloadManager:
    """Manages video downloads with progress tracking."""

    # Single source of truth for what counts as a video file. Previously the
    # transfer loop and _find_downloaded_file disagreed, so a .mov/.flv result
    # was silently never transferred while the download still reported success.
    VIDEO_EXTENSIONS = ['.mp4', '.webm', '.mkv', '.avi', '.mov', '.flv']

    # Sidecar files worth keeping alongside the video
    SIDECAR_EXTENSIONS = ['.info.json', '.jpg', '.jpeg', '.png', '.webp', '.srt', '.vtt', '.description']

    def __init__(self):
        self.active_downloads = {}
        self.cancelled_downloads = set()
    
    def get_available_formats(self, url: str) -> List[Dict[str, Any]]:
        """Get available formats for a video URL."""
        logger.info(f"Getting formats for: {url}")
        
        try:
            # Find yt-dlp in current environment
            import shutil
            yt_dlp_path = shutil.which('yt-dlp')
            if not yt_dlp_path:
                raise FileNotFoundError("yt-dlp not found in PATH. Make sure it's installed: uv add yt-dlp")
                
            cmd = [
                yt_dlp_path,
                '--dump-json',
                '--no-download',
                '--no-check-certificate',
                '--socket-timeout', '30',
                url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                import json
                try:
                    video_info = json.loads(result.stdout)
                    formats = video_info.get('formats', [])
                    
                    # Filter and sort formats by quality
                    good_formats = []
                    seen_qualities = set()
                    
                    for fmt in formats:
                        if fmt.get('vcodec') != 'none':  # Has video
                            height = fmt.get('height', 0)
                            fps = fmt.get('fps', 0)
                            filesize = fmt.get('filesize') or fmt.get('filesize_approx', 0)
                            ext = fmt.get('ext', 'unknown')
                            format_id = fmt.get('format_id', '')
                            
                            # Create a unique quality identifier
                            quality_key = (height, fps, ext)
                            
                            # Skip duplicates of same quality
                            if quality_key in seen_qualities:
                                continue
                            seen_qualities.add(quality_key)
                            
                            # Only include reasonable video formats
                            if height > 0:
                                fps_label = f"{fps}fps" if fps > 30 else ""
                                quality_label = f"{height}p{fps_label}"
                                
                                good_formats.append({
                                    'format_id': format_id,
                                    'height': height,
                                    'fps': fps,
                                    'ext': ext,
                                    'filesize': filesize,
                                    'quality_label': quality_label,
                                    'size_mb': round(filesize / (1024 * 1024), 1) if filesize else 0
                                })
                    
                    # Sort by height (quality) descending, then by fps
                    good_formats.sort(key=lambda x: (x['height'], x['fps']), reverse=True)
                    
                    # Limit to top 8 formats to avoid overwhelming user
                    return good_formats[:8]
                    
                except json.JSONDecodeError:
                    logger.error("Failed to parse format information")
                    return []
            else:
                logger.error(f"Failed to get formats: {result.stderr}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting formats: {e}")
            return []
    
    def _is_playlist_url(self, url: str) -> bool:
        """Check if URL is a playlist."""
        return 'playlist' in url or 'list=' in url
    
    def _get_playlist_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Get playlist metadata including total duration and video count."""
        try:
            import shutil
            yt_dlp_path = shutil.which('yt-dlp')
            if not yt_dlp_path:
                logger.warning("yt-dlp not found - cannot validate playlist")
                return None
                
            cmd = [
                yt_dlp_path,
                '--dump-json',
                '--no-download',
                '--flat-playlist',
                '--no-check-certificate',
                '--socket-timeout', '30',
                url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
            
            if result.returncode != 0:
                logger.warning(f"Failed to get playlist info: {result.stderr}")
                return None
            
            # Parse the JSON output for playlist entries
            import json
            entries = []
            total_duration = 0
            
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    try:
                        entry = json.loads(line)
                        duration = entry.get('duration', 0)
                        if duration:
                            total_duration += duration
                        entries.append(entry)
                    except json.JSONDecodeError:
                        continue
            
            return {
                'entry_count': len(entries),
                'total_duration': total_duration,
                'entries': entries
            }
            
        except Exception as e:
            logger.warning(f"Error getting playlist info: {e}")
            return None
    
    def _analyze_playlist_song_titles(self, playlist_info: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze playlist titles to determine if they look like individual songs vs full concerts."""
        entries = playlist_info.get('entries', [])
        if not entries:
            return {'song_like_ratio': 0.0, 'analysis': 'No entries found'}
        
        song_like_count = 0
        total_analyzed = 0
        
        # Import KGLW song matching for analysis
        try:
            from .kglw_api import KGLWApi
            cache_dir = Path.home() / '.kglw_manager' / 'cache'
            api = KGLWApi(cache_dir)

            for entry in entries[:20]:  # Analyze first 20 titles
                title = (entry.get('title') or '').lower()
                if not title:
                    continue

                total_analyzed += 1

                # Check if title looks like an individual song
                if api.identify_song_from_title(title):
                    song_like_count += 1
                    logger.debug(f"Identified song: {title}")
                elif any(pattern in title for pattern in [
                    'full show', 'full concert', 'complete show', 'entire concert',
                    'live at', 'full set', 'complete set'
                ]):
                    # Looks like a full concert
                    logger.debug(f"Full concert title: {title}")
                    continue
                else:
                    # Check for common song-like patterns
                    if (len(title.split()) <= 5 and  # Short titles are often songs
                        not any(word in title for word in ['live', 'concert', 'show', 'festival'])):
                        song_like_count += 1
                        logger.debug(f"Song-like title: {title}")
                        
        except Exception as e:
            # Fail closed: without title analysis we can't tell a setlist from an
            # unrelated playlist, so don't green-light a bulk concatenated download.
            logger.warning(f"Error analyzing song titles, treating playlist as unverified: {e}")
            return {'song_like_ratio': 0.0, 'analysis': 'Could not analyze titles'}
        
        if total_analyzed == 0:
            return {'song_like_ratio': 0.0, 'analysis': 'No titles to analyze'}
        
        song_like_ratio = song_like_count / total_analyzed
        analysis = f"{song_like_count}/{total_analyzed} titles look like individual songs"
        
        return {'song_like_ratio': song_like_ratio, 'analysis': analysis}
    
    def _should_download_playlist_as_single_file(self, url: str) -> bool:
        """Determine if playlist should be downloaded as single concatenated file."""
        if not self._is_playlist_url(url):
            return False
        
        # Get playlist metadata to validate it's reasonable for a concert
        playlist_info = self._get_playlist_info(url)
        
        if not playlist_info:
            # Fail closed - grabbing an unvalidated playlist wholesale can pull in
            # entirely unrelated videos.
            logger.warning("Cannot validate playlist - downloading first video only")
            return False
        
        entry_count = playlist_info['entry_count']
        total_duration = playlist_info['total_duration']
        
        # Validate playlist constraints for concert recordings
        MAX_DURATION = 4 * 60 * 60  # 4 hours in seconds
        MAX_VIDEOS = 50  # Reasonable max for a concert setlist
        
        if total_duration > MAX_DURATION:
            duration_hours = total_duration / 3600
            logger.warning(f"Playlist is too long ({duration_hours:.1f} hours > 4 hours) - downloading first video only")
            return False
            
        if entry_count > MAX_VIDEOS:
            logger.warning(f"Playlist has too many videos ({entry_count} > {MAX_VIDEOS}) - downloading first video only")
            return False
        
        # Analyze titles to see if they look like individual songs
        title_analysis = self._analyze_playlist_song_titles(playlist_info)
        song_like_ratio = title_analysis['song_like_ratio']
        
        # If most titles look like songs, it's probably a setlist
        if song_like_ratio > 0.6:  # 60% of titles look like songs
            duration_hours = total_duration / 3600
            logger.info(f"Playlist validated: {entry_count} videos, {duration_hours:.1f}h total, {title_analysis['analysis']} - will download and concatenate")
            return True
        elif song_like_ratio > 0.3:  # 30-60% - uncertain but probably worth concatenating
            duration_hours = total_duration / 3600
            logger.info(f"Playlist uncertain but likely concert: {entry_count} videos, {duration_hours:.1f}h total, {title_analysis['analysis']} - will download and concatenate")
            return True
        else:
            logger.warning(f"Playlist doesn't look like individual songs ({title_analysis['analysis']}) - downloading first video only")
            return False
    
    def download_video(self, url: str, output_path: Path, 
                      show_progress: bool = True,
                      progress_callback: Optional[Callable] = None,
                      format_id: str = 'best') -> bool:
        """Download video using yt-dlp Python API with proper progress tracking."""
        logger.info(f"Starting download: {url}")
        console = Console()
        
        # Create local temp directory for faster download/merge (avoid NFS slowdown)
        temp_dir = Path(tempfile.mkdtemp(prefix='kglw_download_'))
        temp_output_path = temp_dir
        
        try:
            console.print(f"📁 [yellow]Using local temp directory: {temp_dir}[/yellow]")
            
            # Ensure final output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Import yt-dlp
            try:
                import yt_dlp
            except ImportError:
                raise ImportError("yt-dlp not found. Make sure it's installed: uv add yt-dlp")
            
            # Optimize ffmpeg performance for faster merging
            import multiprocessing
            cpu_count = multiprocessing.cpu_count()
            
            # Optimize ffmpeg for stream copying (remuxing) performance
            ffmpeg_args = f'-threads {cpu_count} -c copy -movflags +faststart -fflags +genpts -max_muxing_queue_size 4096 -avoid_negative_ts make_zero'
            console.print(f"⚡ [cyan]Optimizing merge with {cpu_count} CPU threads + 4MB I/O buffers[/cyan]")
            
            # Progress tracking variables
            current_phase = "analysis"
            download_task = None
            merge_task = None
            
            # Create progress display
            with Progress(
                    TextColumn("[progress.description]"),
                    BarColumn(),
                    "[progress.percentage]{task.percentage:>3.1f}%",
                    "•",
                    TextColumn("[cyan]{task.fields[downloaded]}/{task.fields[total_size]}"),
                    "•", 
                    TextColumn("[green]{task.fields[speed]}"),
                    "•",
                    TextColumn("[yellow]{task.fields[eta]}"),
                    console=console,
                    transient=True
                ) as progress:
                
                def progress_hook(d):
                    """Progress hook for yt-dlp downloads."""
                    nonlocal current_phase, download_task, merge_task

                    # Honour cancel_download() requests
                    if url in self.cancelled_downloads:
                        self.cancelled_downloads.discard(url)
                        raise yt_dlp.utils.DownloadCancelled(f"Download cancelled: {url}")

                    if d['status'] == 'downloading':
                        # Switch to download phase if needed
                        if current_phase != "downloading":
                            current_phase = "downloading"
                            if download_task is None:
                                download_task = progress.add_task(
                                    "📥 Downloading...", 
                                    total=100,
                                    downloaded="",
                                    total_size="",
                                    speed="",
                                    eta=""
                                )
                        
                        # Extract progress information
                        downloaded_bytes = d.get('downloaded_bytes', 0)
                        total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                        speed = d.get('speed', 0)
                        eta = d.get('eta', 0)
                        
                        # Calculate percentage
                        if total_bytes > 0:
                            percent = (downloaded_bytes / total_bytes) * 100
                        else:
                            percent = 0
                        
                        # Format display values
                        downloaded_mb = downloaded_bytes / (1024**2)
                        total_mb = total_bytes / (1024**2) if total_bytes else 0
                        speed_text = f"{speed / (1024**2):.1f} MB/s" if speed else "0 MB/s"
                        eta_text = f"{eta // 60:02d}:{eta % 60:02d}" if eta else "--:--"
                        
                        # Update progress
                        if download_task is not None:
                            progress.update(
                                download_task,
                                completed=percent,
                                downloaded=f"{downloaded_mb:.1f} MB",
                                total_size=f"{total_mb:.1f} MB" if total_mb else "Unknown",
                                speed=speed_text,
                                eta=eta_text
                            )
                    
                    elif d['status'] == 'finished':
                        # Complete download task
                        if download_task is not None:
                            progress.update(download_task, completed=100, description="✅ Download complete")
                            progress.remove_task(download_task)
                            download_task = None
                        
                        # Start merge phase if this was a video+audio download
                        if current_phase == "downloading":
                            current_phase = "merging"
                            merge_task = progress.add_task(
                                "🔧 Merging video and audio streams...", 
                                total=100,
                                downloaded="",
                                total_size="",
                                speed="",
                                eta=""
                            )
                            # Simulate merge progress
                            for i in range(0, 101, 10):
                                progress.update(merge_task, completed=i)
                                import time
                                time.sleep(0.1)  # Small delay for visual feedback
                        
                        logger.debug(f"Finished downloading: {d.get('filename', 'Unknown')}")
                    
                    elif d['status'] == 'error':
                        logger.error(f"Download error: {d.get('error', 'Unknown error')}")
                
                # Custom logger for yt-dlp
                class KGLWLogger:
                    def debug(self, msg):
                        if msg.startswith('[debug] '):
                            logger.debug(msg[8:])  # Remove '[debug] ' prefix
                        else:
                            logger.debug(msg)

                    def info(self, msg):
                        logger.info(msg)

                    def warning(self, msg):
                        logger.warning(msg)

                    def error(self, msg):
                        logger.error(msg)
                
                # Configure yt-dlp options with YouTube 403 error mitigation
                ydl_opts = {
                    # YouTube now serves a JS "n challenge"; without a solver
                    # only image formats are offered and every download fails
                    # with "Requested format is not available".
                    'remote_components': ['ejs:github'],
                    'format': format_id,
                    'outtmpl': str(temp_output_path / '%(title)s.%(ext)s'),
                    'writeinfojson': False,  # Don't write .info.json files (we use .kglw_metadata.json)
                    'writethumbnail': False,  # Don't write thumbnails (we use KGLW API posters)
                    'socket_timeout': 30,
                    'retries': 3,  # Increased retries for 403 errors
                    'fragment_retries': 3,  # Retry individual fragments
                    'merge_output_format': 'mp4',
                    'postprocessor_args': {'ffmpeg': ffmpeg_args.split()},
                    'progress_hooks': [progress_hook],
                    'logger': KGLWLogger(),
                    'no_warnings': True,
                    # YouTube 403 error mitigation
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                    },
                    'extractor_args': {
                        'youtube': {
                            'skip': ['translated_subs'],  # Skip auto-translated subtitles
                            'player_skip': ['configs'],   # Skip some player configs that might trigger blocks
                        }
                    },
                }
                
                # Handle playlist URLs - download and concatenate all videos if reasonable
                if self._is_playlist_url(url):
                    if self._should_download_playlist_as_single_file(url):
                        ydl_opts.update({
                            'yes_playlist': True,  # Download entire playlist
                            'outtmpl': str(temp_output_path / '%(playlist_index)02d-%(title)s.%(ext)s'),
                            'postprocessors': [
                                {
                                    'key': 'FFmpegConcat',
                                    'when': 'playlist',
                                }
                            ]
                        })
                        console.print("🎵 [cyan]Playlist detected - will download all videos and concatenate into single file[/cyan]")
                    else:
                        # Playlist too long - download first video only
                        console.print("⚠️  [yellow]Playlist too large for concert - downloading first video only[/yellow]")
                        ydl_opts.update({
                            'noplaylist': True,  # Download only the first video
                        })
                
                # Add initial analysis task
                analysis_task = progress.add_task(
                    "🔍 Analyzing video and selecting formats...", 
                    total=100,
                    downloaded="",
                    total_size="",
                    speed="",
                    eta=""
                )
                progress.update(analysis_task, completed=30)
                
                # Download the video
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        # Update analysis progress
                        progress.update(analysis_task, completed=60, description="📋 Extracting video info...")
                        
                        # Store reference to active download
                        self.active_downloads[url] = ydl
                        
                        # Perform the download
                        progress.update(analysis_task, completed=100, description="✅ Analysis complete")
                        progress.remove_task(analysis_task)
                        
                        ydl.download([url])
                        
                        # Complete any remaining tasks
                        if merge_task is not None:
                            progress.update(merge_task, completed=100, description="✅ Merge completed!")
                            progress.remove_task(merge_task)
                        
                        # Clean up
                        if url in self.active_downloads:
                            del self.active_downloads[url]
                        
                        logger.info("Download completed successfully")
                        
                        # Find the finished video: pick the LARGEST video file so
                        # leftover stream fragments (.f140.m4a etc.) can't win.
                        video_files = [f for f in temp_output_path.glob('*')
                                       if f.is_file() and f.suffix.lower() in self.VIDEO_EXTENSIONS]
                        downloaded_file = max(video_files, key=lambda f: f.stat().st_size) if video_files else None

                        if not downloaded_file:
                            # Nothing usable was produced. Report failure so the
                            # caller restores its backups instead of deleting them.
                            logger.error(f"Download produced no video file in {temp_output_path}")
                            console.print("❌ [red]Download produced no video file[/red]")
                            return False

                        # Transfer files from temp to final location
                        console.print("🚀 [bold green]Transferring files to final location...[/bold green]")

                        final_video_path = output_path / downloaded_file.name
                        shutil.move(str(downloaded_file), str(final_video_path))
                        logger.info(f"Transferred: {downloaded_file.name}")

                        # Transfer metadata sidecars only; stream fragments and
                        # partial files stay behind and die with the temp dir.
                        for extra_file in temp_output_path.glob('*'):
                            if not extra_file.is_file():
                                continue
                            name_lower = extra_file.name.lower()
                            if any(name_lower.endswith(ext) for ext in self.SIDECAR_EXTENSIONS):
                                shutil.move(str(extra_file), str(output_path / extra_file.name))
                                logger.debug(f"Transferred: {extra_file.name}")
                            else:
                                logger.debug(f"Discarding download leftover: {extra_file.name}")

                        # NOTE: backups are intentionally NOT cleaned up here. The
                        # caller must verify and rename the new file first, so it
                        # can restore the originals if that step fails.

                        # Note: Kometa integration requires show context (use download_upgrade_to_existing_dir for full integration)
                        logger.debug("Basic download complete - Kometa sync requires show context")

                        return True
                        
                except yt_dlp.utils.DownloadError as e:
                    error_msg = str(e).lower()
                    if '403' in error_msg or 'forbidden' in error_msg:
                        logger.error(f"YouTube 403 Forbidden error - video may be geo-blocked or YouTube is blocking automated access: {e}")
                        console.print("❌ [red]YouTube blocking access (403 Forbidden)[/red]")
                        console.print("💡 [yellow]Try updating yt-dlp: uv add yt-dlp@latest[/yellow]")
                    elif '404' in error_msg or 'not found' in error_msg:
                        logger.error(f"Video not found (404): {e}")
                        console.print("❌ [red]Video not found or has been deleted[/red]")
                    else:
                        logger.error(f"yt-dlp download error: {e}")
                        console.print(f"❌ [red]Download failed: {e}[/red]")
                    return False
                except Exception as e:
                    logger.error(f"Unexpected download error: {e}")
                    return False
                
        except KeyboardInterrupt:
            logger.info("Download interrupted by user")
            if url in self.active_downloads:
                try:
                    # Try to cancel yt-dlp download
                    if hasattr(self.active_downloads[url], '_stop'):
                        self.active_downloads[url]._stop = True
                except:
                    pass
                del self.active_downloads[url]
            return False
        except Exception as e:
            logger.error(f"Download setup error: {e}")
            return False
        finally:
            # Clean up temp directory
            if temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                    logger.debug(f"Cleaned up temp directory: {temp_dir}")
                except OSError as e:
                    logger.warning(f"Failed to clean up temp directory: {e}")
            
            # Clear any remaining progress artifacts
            console.print("", end="")
    
    def _parse_progress_line(self, line: str, progress: DownloadProgress):
        """Parse yt-dlp progress line."""
        # Example: [download]   15.2% of 1.23GiB at 2.45MiB/s ETA 00:42
        
        # Extract percentage
        percent_match = re.search(r'(\d+\.?\d*)%', line)
        if percent_match:
            percent = float(percent_match.group(1))
        else:
            percent = 0
        
        # Extract speed
        speed_match = re.search(r'at\s+([0-9.]+[A-Za-z]+/s)', line)
        speed = speed_match.group(1) if speed_match else ""
        
        # Extract ETA
        eta_match = re.search(r'ETA\s+([0-9:]+)', line)
        eta = eta_match.group(1) if eta_match else ""
        
        # Extract file size
        size_match = re.search(r'of\s+([0-9.]+[A-Za-z]+)', line)
        size = size_match.group(1) if size_match else ""
        
        progress.update(percent, speed, eta, size)
    
    def _extract_progress_percent(self, line: str) -> Optional[float]:
        """Extract percentage from yt-dlp progress line."""
        percent_match = re.search(r'(\d+\.?\d*)%', line)
        if percent_match:
            return float(percent_match.group(1))
        return None
    
    def _parse_download_progress(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse complete progress information from yt-dlp output."""
        try:
            # Example line: "[download]  45.2% of 150.5MiB at 2.3MiB/s ETA 00:30"
            percent_match = re.search(r'(\d+\.?\d*)%', line)
            size_match = re.search(r'of\s+([0-9.]+)([KMGT]iB)', line)
            speed_match = re.search(r'at\s+([0-9.]+)([KMGT]iB/s)', line)
            eta_match = re.search(r'ETA\s+(\d{2}:\d{2})', line)
            
            if not percent_match:
                return None
                
            percent = float(percent_match.group(1))
            
            # Parse file size
            total_bytes = 100.0  # Default fallback
            if size_match:
                size_val = float(size_match.group(1))
                size_unit = size_match.group(2)
                multipliers = {'B': 1, 'KiB': 1024, 'MiB': 1024**2, 'GiB': 1024**3, 'TiB': 1024**4}
                total_bytes = size_val * multipliers.get(size_unit, 1024**2)
            
            completed_bytes = total_bytes * (percent / 100.0)
            
            # Parse speed
            speed_bytes_per_sec = 0
            if speed_match:
                speed_val = float(speed_match.group(1))
                speed_unit = speed_match.group(2).replace('/s', '')
                multipliers = {'B': 1, 'KiB': 1024, 'MiB': 1024**2, 'GiB': 1024**3, 'TiB': 1024**4}
                speed_bytes_per_sec = speed_val * multipliers.get(speed_unit, 1024**2)
            
            # Parse ETA
            eta_seconds = None
            if eta_match:
                eta_str = eta_match.group(1)
                minutes, seconds = map(int, eta_str.split(':'))
                eta_seconds = minutes * 60 + seconds
            
            return {
                'completed': completed_bytes,
                'total': total_bytes,
                'extra': {
                    'speed': speed_bytes_per_sec,
                    'time_remaining': eta_seconds
                }
            }
            
        except (ValueError, AttributeError) as e:
            logger.debug(f"Failed to parse progress line: {line} - {e}")
            # Fallback to simple percentage
            percent = self._extract_progress_percent(line)
            if percent is not None:
                return {
                    'completed': percent,
                    'total': 100.0,
                    'extra': {}
                }
            return None
    
    def cancel_download(self, url: str):
        """Cancel an active download.

        yt_dlp.YoutubeDL has no terminate(); flag the URL instead and let the
        progress hook raise DownloadCancelled on the next callback.
        """
        if url in self.active_downloads:
            logger.info(f"Cancelling download: {url}")
            self.cancelled_downloads.add(url)
            del self.active_downloads[url]
    
    def cancel_all_downloads(self):
        """Cancel all active downloads."""
        for url in list(self.active_downloads.keys()):
            self.cancel_download(url)
    
    def get_active_downloads(self) -> list:
        """Get list of active download URLs."""
        return list(self.active_downloads.keys())
    
    def download_upgrade(self, video_info: Dict[str, Any], 
                        output_dir: Path, show_info: Dict[str, Any],
                        backup_existing: bool = True, format_id: str = 'best') -> Optional[Path]:
        """Download an upgrade video with proper naming and backup."""
        url = video_info.get('webpage_url', video_info.get('url', ''))
        if not url:
            logger.error("No URL provided for download")
            return None
        
        title = video_info.get('title', 'Unknown Video')
        logger.info(f"Downloading upgrade: {title}")
        
        # Create output directory structure
        
        naming_manager = NamingManager()
        tour_manager = get_tour_manager()
        
        # Assign tour using API data first, then fallback
        tour_name = tour_manager.assign_tour(show_info)
        normalized_tour_name = tour_manager.normalize_tour_name_for_filesystem(tour_name)
        tour_dir = output_dir / normalized_tour_name
        
        # Log tour assignment for debugging
        api_tour = tour_manager.get_tour_for_date(show_info.get('date', ''))
        if api_tour:
            logger.info(f"🎯 API assigned tour: {api_tour} → {normalized_tour_name}")
        else:
            logger.debug(f"No API data for {show_info.get('date', '')}, using fallback: {tour_name}")
        
        # Create show directory
        show_dir_name = naming_manager.generate_directory_name(show_info)
        show_dir = tour_dir / show_dir_name
        show_dir.mkdir(parents=True, exist_ok=True)
        
        # Backup existing files if requested
        if backup_existing:
            self._backup_existing_files(show_dir)
        
        # Download the video
        success = self.download_video(url, show_dir, show_progress=True, format_id=format_id)
        
        if success:
            # Find the downloaded file and rename it to Plex format
            downloaded_file = self._find_downloaded_file(show_dir)
            if downloaded_file:
                # Check if this is a single song video
                song_name = None
                try:
                    from .kglw_api import KGLWApi
                    from pathlib import Path
                    cache_dir = Path.home() / '.kglw_manager' / 'cache'
                    api = KGLWApi(cache_dir)
                    # Use video title from show_info if available, otherwise use filename
                    video_title = show_info.get('title', '') or downloaded_file.stem
                    result = api.identify_song_from_title(video_title)
                    if result:
                        song_name = result['song']['name']
                        logger.info(f"🎵 Detected single song: {song_name}")
                except Exception as e:
                    logger.debug(f"Could not identify song from title: {e}")
                
                # Generate proper Plex filename
                plex_filename = naming_manager.generate_plex_filename(
                    show_info, downloaded_file.suffix, song_name
                )
                plex_path = show_dir / plex_filename
                
                # Rename to Plex format
                try:
                    logger.info(f"Renaming: {downloaded_file.name} → {plex_filename}")
                    downloaded_file.rename(plex_path)
                    logger.info(f"✅ Renamed successfully")
                    if backup_existing:
                        self._cleanup_backup_files(show_dir)
                    return plex_path
                except OSError as e:
                    logger.warning(f"Failed to rename file: {e}")
                    if backup_existing:
                        self._restore_backup_files(show_dir)
                    return downloaded_file

            if backup_existing:
                self._restore_backup_files(show_dir)
            return downloaded_file
        else:
            logger.error("Download failed")
            if backup_existing:
                self._restore_backup_files(show_dir)
            return None
    
    def download_upgrade_to_existing_dir(self, video_info: Dict[str, Any], 
                                        show_dir: Path, show_info: Dict[str, Any],
                                        backup_existing: bool = True, format_id: str = 'best',
                                        quiet_mode: bool = False) -> Optional[Path]:
        """Download an upgrade video directly to existing show directory."""
        url = video_info.get('webpage_url', video_info.get('url', ''))
        if not url:
            logger.error("No URL provided for download")
            return None
        
        title = video_info.get('title', 'Unknown Video')
        logger.info(f"Downloading upgrade: {title}")
        
        # Ensure show directory exists
        show_dir.mkdir(parents=True, exist_ok=True)
        
        # Backup existing files if requested
        if backup_existing:
            self._backup_existing_files(show_dir)
        
        # Download the video directly to the existing show directory
        success = self.download_video(url, show_dir, show_progress=not quiet_mode, format_id=format_id)
        
        if success:
            # Find the downloaded file and rename it to Plex format
            downloaded_file = self._find_downloaded_file(show_dir)
            if downloaded_file:
                logger.info(f"📁 Downloaded file found: {downloaded_file.name}")
                # Generate proper Plex filename
                naming_manager = NamingManager()
                plex_filename = naming_manager.generate_plex_filename(
                    show_info, downloaded_file.suffix
                )
                plex_path = show_dir / plex_filename
                
                # Check if this is likely a full concert vs individual song
                title = video_info.get('title', '').lower()
                is_likely_full_concert = any(indicator in title for indicator in [
                    'full concert', 'full show', 'complete show', 'entire concert', 
                    'complete concert', 'full set', 'complete set', 'full performance',
                    'complete performance'
                ])
                
                # Also check duration - if over 45 minutes, likely a full concert
                duration = video_info.get('duration', 0)
                if duration > 45 * 60:  # 45 minutes in seconds
                    is_likely_full_concert = True
                
                # Check if file already exists
                if plex_path.exists():
                    if backup_existing:
                        # Backup existing and use the same name (normal upgrade flow)
                        logger.debug(f"Target file exists but backup_existing=True, will replace after backup")
                    elif is_likely_full_concert:
                        # Full concerts should replace existing files without song suffixes
                        logger.info(f"Full concert detected, will replace existing file: {plex_path.name}")
                    else:
                        # Individual songs need unique filenames with proper setlist numbering
                        logger.debug(f"Individual song detected with existing file, generating unique filename")
                        base_name = plex_path.stem
                        extension = plex_path.suffix

                        # Count existing video files to determine the next song number
                        # (excluding the file we just downloaded, which is already
                        # in show_dir and would otherwise be counted twice)
                        existing_videos = [f for f in show_dir.iterdir()
                                           if f.is_file()
                                           and f.suffix.lower() in self.VIDEO_EXTENSIONS
                                           and f != downloaded_file]
                        # Filter out files that already have song numbering to get the count
                        song_number = 1
                        for video in existing_videos:
                            # Check if file has pattern "XX - " at start for song numbering
                            if video.stem.startswith(f"{base_name} - "):
                                # Extract number if present
                                remainder = video.stem[len(f"{base_name} - "):]
                                if remainder[:2].isdigit():
                                    try:
                                        existing_num = int(remainder[:2])
                                        song_number = max(song_number, existing_num + 1)
                                    except:
                                        pass

                        # If no numbered songs found, this is likely the second song (first is unnumbered)
                        if song_number == 1 and len(existing_videos) > 0:
                            song_number = len(existing_videos) + 1

                        # Try to identify the song name for a more descriptive filename
                        song_name = None
                        song_position = None
                        clean_song_name = None
                        try:
                            from .kglw_api import KGLWApi
                            from pathlib import Path
                            cache_dir = Path.home() / '.kglw_manager' / 'cache'
                            api = KGLWApi(cache_dir)

                            # Try to get setlist for this show
                            setlist = None
                            if show_info and 'date' in show_info:
                                setlist = api.get_setlist_for_show(show_info['date'])

                            # Identify song from title
                            result = api.identify_song_from_title(video_info.get('title', ''))
                            if result:
                                song_name = result['song']['name']

                                # Try to find position in setlist. get_setlist_for_show
                                # returns a list of song-name strings.
                                if setlist:
                                    for i, setlist_song in enumerate(setlist, 1):
                                        if isinstance(setlist_song, dict):
                                            setlist_name = setlist_song.get('songname') or setlist_song.get('name') or ''
                                        else:
                                            setlist_name = str(setlist_song)
                                        if setlist_name.lower() == song_name.lower():
                                            song_position = i
                                            break

                                # Use setlist position if available, otherwise use calculated number
                                if song_position:
                                    song_number = song_position

                                # Clean song name for filename
                                clean_song_name = "".join(c for c in song_name if c.isalnum() or c in (' ', '-', '_', '(', ')')).strip()

                        except Exception as e:
                            logger.debug(f"Could not identify song or get setlist: {e}")

                        # Format the filename with padded number and song name
                        padded_number = f"{song_number:02d}"

                        if song_name and clean_song_name:
                            plex_path = show_dir / f"{base_name} - {padded_number} - {clean_song_name}{extension}"
                        else:
                            # If we can't identify the song, use a generic name with number
                            plex_path = show_dir / f"{base_name} - {padded_number} - Song{extension}"

                        logger.info(f"Individual song with numbering: {plex_path.name}")
                
                # Rename to Plex format
                try:
                    logger.info(f"Renaming: {downloaded_file.name} → {plex_path.name}")
                    downloaded_file.rename(plex_path)
                    logger.info(f"✅ Renamed successfully")
                    
                    # Create download metadata file
                    try:
                        from .download_metadata import DownloadMetadataDetector
                        metadata_detector = DownloadMetadataDetector()
                        
                        metadata_path = metadata_detector.create_metadata_file(
                            download_path=plex_path,
                            candidate=video_info,
                            chosen_filename=plex_path.name,
                            show_info=show_info
                        )
                        
                        if metadata_path:
                            logger.info(f"📝 Created download metadata: {metadata_path.name}")
                        
                    except Exception as e:
                        logger.warning(f"Failed to create download metadata: {e}")
                    
                    # Process with Plex integration after successful download and rename
                    try:
                        # Try to get Plex manager from collection manager if available
                        from .collection import CollectionManager
                        from .config import config
                        from pathlib import Path
                        
                        # Create a temporary collection manager just for Plex integration
                        temp_collection_path = str(Path(plex_path).parent.parent.parent)
                        temp_manager = CollectionManager(temp_collection_path)
                        
                        if temp_manager.plex_manager:
                            logger.info("📺 Processing with Plex integration...")
                            
                            # Get tour name from directory structure
                            tour_name = show_dir.parent.name
                            
                            # Process the new show with full Plex workflow
                            results = temp_manager.process_new_show(show_dir, tour_name)
                            
                            if results['success']:
                                logger.info("✅ Plex integration completed successfully")
                                logger.info(f"   Videos processed: {results['videos_processed']}")
                                logger.info(f"   Collections updated: {'Yes' if results['collection_updated'] else 'No'}")
                                logger.info(f"   Metadata updated: {'Yes' if results['metadata_updated'] else 'No'}")
                            else:
                                logger.warning("⚠️  Plex integration had issues:")
                                for error in results.get('errors', []):
                                    logger.warning(f"   • {error}")
                        else:
                            logger.debug("Plex integration not available")
                            
                    except Exception as e:
                        logger.warning(f"Plex integration failed: {e}")

                    # The new file is verified and in place - only now is it safe
                    # to discard the originals.
                    if backup_existing:
                        self._cleanup_backup_files(show_dir)

                    return plex_path
                except OSError as e:
                    logger.error(f"Failed to rename downloaded file: {e}")
                    # Keep the download, but put the originals back so the show
                    # isn't left with only a raw YouTube-titled file.
                    if backup_existing:
                        self._restore_backup_files(show_dir)
                    return downloaded_file
            else:
                logger.error("Could not find downloaded file")
                if backup_existing:
                    self._restore_backup_files(show_dir)
                return None
        else:
            logger.error("Download failed")
            # Restore backup files on failure
            if backup_existing:
                self._restore_backup_files(show_dir)
            return None
    
    def _backup_existing_files(self, show_dir: Path):
        """Backup existing video files with non-media extension to prevent Plex detection."""
        if not show_dir.is_dir():
            logger.debug(f"No directory to back up: {show_dir}")
            return

        backup_dir = show_dir / 'backup'

        for file_path in show_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in self.VIDEO_EXTENSIONS:
                if not backup_dir.exists():
                    backup_dir.mkdir()
                
                # Use .backup extension to prevent Plex detection
                backup_name = file_path.name + '.backup'
                backup_path = backup_dir / backup_name
                try:
                    file_path.rename(backup_path)
                    logger.info(f"Backed up: {file_path.name} -> {backup_name}")
                except OSError as e:
                    logger.warning(f"Failed to backup {file_path.name}: {e}")
    
    def _cleanup_backup_files(self, show_dir: Path):
        """Clean up backup files after successful download to prevent Plex duplicates."""
        backup_dir = show_dir / 'backup'
        
        if backup_dir.exists():
            try:
                import shutil
                shutil.rmtree(backup_dir)
                logger.info("Cleaned up backup files after successful download")
            except OSError as e:
                logger.warning(f"Failed to clean up backup files: {e}")
    
    def _restore_backup_files(self, show_dir: Path):
        """Restore backup files on download failure."""
        backup_dir = show_dir / 'backup'
        
        if backup_dir.exists():
            try:
                for backup_file in backup_dir.iterdir():
                    if backup_file.is_file() and backup_file.name.endswith('.backup'):
                        # Remove .backup extension to get original name
                        original_name = backup_file.name[:-7]  # Remove '.backup'
                        original_path = show_dir / original_name
                        
                        try:
                            backup_file.rename(original_path)
                            logger.info(f"Restored backup: {original_name}")
                        except OSError as e:
                            logger.warning(f"Failed to restore {backup_file.name}: {e}")
                
                # Remove backup directory if empty
                try:
                    backup_dir.rmdir()
                    logger.debug("Cleaned up empty backup directory")
                except OSError:
                    pass  # Directory not empty or other error
                    
            except Exception as e:
                logger.warning(f"Error during backup restoration: {e}")
    
    def _find_downloaded_file(self, directory: Path) -> Optional[Path]:
        """Find the most recently downloaded video file."""
        video_extensions = self.VIDEO_EXTENSIONS

        video_files = []
        for ext in video_extensions:
            video_files.extend(directory.glob(f'*{ext}'))
        
        if not video_files:
            return None
        
        # Return the most recently modified file
        return max(video_files, key=lambda f: f.stat().st_mtime)
    
    def cleanup_incomplete_downloads(self, directory: Path):
        """Clean up .part files and other download remnants."""
        if not directory.exists():
            return
        
        cleanup_patterns = ['*.part', '*.part-*', '*.ytdl', '*.temp']
        cleaned_files = []
        
        for pattern in cleanup_patterns:
            for file_path in directory.glob(pattern):
                try:
                    file_path.unlink()
                    cleaned_files.append(file_path.name)
                    logger.info(f"Cleaned up: {file_path.name}")
                except OSError as e:
                    logger.warning(f"Failed to clean up {file_path.name}: {e}")
        
        return cleaned_files
    
    def _detect_phase_change(self, output: str) -> str:
        """Detect what phase yt-dlp is in based on output."""
        if '[info]' in output and ('format' in output.lower() or 'quality' in output.lower()):
            return "analysis"
        elif '[download]' in output:
            return "downloading"
        elif 'ffmpeg' in output.lower() or 'merging' in output.lower():
            return "merging"
        elif 'Deleting original file' in output:
            return "cleanup"
        return "analysis"  # Default
    
    def _update_analysis_progress(self, output: str, progress, task_id):
        """Update analysis phase progress."""
        if '[info]' in output:
            if 'format' in output.lower():
                progress.update(task_id, completed=30, description="📋 Analyzing available formats...")
            elif 'quality' in output.lower():
                progress.update(task_id, completed=60, description="📋 Selecting best quality...")
            elif 'extracting' in output.lower():
                progress.update(task_id, completed=90, description="📋 Extracting video metadata...")
    
    def _update_merge_progress(self, output: str, progress, task_id, console):
        """Update merge phase progress."""
        # Look for various merge indicators
        if 'ffmpeg' in output.lower():
            if 'starting' in output.lower() or 'input' in output.lower():
                console.print("🎬 [bold green]Download complete! Now merging streams...[/bold green]")
                progress.update(task_id, completed=10, description="🔧 Starting ffmpeg merge...")
            elif 'frame=' in output or 'size=' in output:
                # Extract more detailed progress from ffmpeg output
                try:
                    # FFmpeg shows progress like: frame= 1234 fps=30.0 q=23.0 size= 150MB time=00:02:15.67
                    if 'time=' in output and 'size=' in output:
                        # Extract size info for display
                        size_match = re.search(r'size=\s*(\d+(?:\.\d+)?)\w*B', output)
                        if size_match:
                            size_info = f" ({size_match.group(1)} MB processed)"
                        else:
                            size_info = ""
                        progress.update(task_id, completed=60, description=f"🔧 Merging streams{size_info}...")
                    else:
                        progress.update(task_id, completed=40, description="🔧 Processing video data...")
                except:
                    progress.update(task_id, completed=50, description="🔧 Merging streams...")
            elif 'muxing' in output.lower() or 'finalizing' in output.lower():
                progress.update(task_id, completed=85, description="🔧 Finalizing container...")
        elif 'deleting' in output.lower() and 'original' in output.lower():
            progress.update(task_id, completed=95, description="🧹 Cleaning up temporary files...")
        elif any(keyword in output.lower() for keyword in ['merged', 'done', 'complete']):
            progress.update(task_id, completed=100, description="✅ Merge completed!")
    
    def _get_hardware_acceleration_args(self) -> str:
        """Detect and return hardware acceleration arguments for ffmpeg."""
        import subprocess
        import os
        
        # Check for NVIDIA GPU (NVENC)
        try:
            result = subprocess.run(['nvidia-smi'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                # Test if ffmpeg has NVENC support
                test_cmd = ['ffmpeg', '-hide_banner', '-f', 'lavfi', '-i', 'testsrc=duration=1:size=32x32:rate=1', 
                           '-c:v', 'h264_nvenc', '-f', 'null', '-']
                test_result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=5)
                if test_result.returncode == 0:
                    return '-hwaccel cuda -c:v h264_nvenc'
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # Check for Intel Quick Sync (QSV)
        try:
            if os.path.exists('/dev/dri/renderD128'):
                test_cmd = ['ffmpeg', '-hide_banner', '-f', 'lavfi', '-i', 'testsrc=duration=1:size=32x32:rate=1',
                           '-c:v', 'h264_qsv', '-f', 'null', '-']
                test_result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=5)
                if test_result.returncode == 0:
                    return '-hwaccel qsv -c:v h264_qsv'
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # Check for VAAPI (Linux GPU acceleration)
        try:
            if os.path.exists('/dev/dri/renderD128'):
                test_cmd = ['ffmpeg', '-hide_banner', '-f', 'lavfi', '-i', 'testsrc=duration=1:size=32x32:rate=1',
                           '-hwaccel', 'vaapi', '-f', 'null', '-']
                test_result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=5)
                if test_result.returncode == 0:
                    return '-hwaccel vaapi'
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # Check for VideoToolbox (macOS)
        try:
            test_cmd = ['ffmpeg', '-hide_banner', '-f', 'lavfi', '-i', 'testsrc=duration=1:size=32x32:rate=1',
                       '-c:v', 'h264_videotoolbox', '-f', 'null', '-']
            test_result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=5)
            if test_result.returncode == 0:
                return '-hwaccel videotoolbox -c:v h264_videotoolbox'
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # No hardware acceleration available
        return ""