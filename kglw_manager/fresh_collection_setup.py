#!/usr/bin/env python3
"""
Fresh collection setup system for creating organized KGLW collection from scratch.
Uses KGLW.net API data to create proper directory structure with metadata files.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

from .api_tour_manager import get_tour_manager
from .utils import setup_logging

logger = setup_logging()


class FreshCollectionSetup:
    """Sets up a fresh KGLW collection with proper API-based organization."""
    
    def __init__(self, collection_path: str):
        """Initialize fresh collection setup.
        
        Args:
            collection_path: Path where the new collection will be created
        """
        self.collection_path = Path(collection_path)
        self.tour_manager = get_tour_manager()
    
    def create_fresh_collection_structure(self, dry_run: bool = True) -> Dict[str, Any]:
        """Create complete directory structure with metadata files.
        
        Args:
            dry_run: If True, only show what would be created without making changes
            
        Returns:
            Dictionary with creation results and statistics
        """
        logger.info(f"Setting up fresh collection at: {self.collection_path}")
        
        # Get all API data
        api_data = self._get_comprehensive_api_data()
        if not api_data:
            logger.error("Failed to get API data")
            return {"success": False, "error": "No API data available"}
        
        # Organize shows by tour
        tour_shows = self._organize_shows_by_tour(api_data)
        
        # Create directory structure and metadata
        results = self._create_directories_and_metadata(tour_shows, dry_run)
        
        return results
    
    def _get_comprehensive_api_data(self) -> Dict[int, Dict[str, Any]]:
        """Get all show data from KGLW.net API."""
        logger.info("Fetching comprehensive API data...")
        
        try:
            # Get the raw API data from the tour manager
            shows_data = self.tour_manager.api_manager._get_tours_data()
            
            if not shows_data:
                logger.error("No API data available")
                return {}
            
            logger.info(f"Retrieved {len(shows_data)} shows from API")
            return shows_data
            
        except Exception as e:
            logger.error(f"Failed to get API data: {e}")
            return {}
    
    def _organize_shows_by_tour(self, api_data: Dict[int, Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Organize shows by tour for directory creation.
        
        Args:
            api_data: Raw API data keyed by show_id
            
        Returns:
            Dictionary with tour names as keys and lists of shows as values
        """
        tour_shows = defaultdict(list)
        
        for show_id, show_info in api_data.items():
            tour_name = show_info.get('tour_name', 'Not Part of a Tour')
            
            # The show_date is already in the show_info, no need to add it
            tour_shows[tour_name].append(show_info)
        
        # Sort shows within each tour by date
        for tour_name in tour_shows:
            tour_shows[tour_name].sort(key=lambda x: x.get('show_date', ''))
        
        logger.info(f"Organized shows into {len(tour_shows)} tours")
        return dict(tour_shows)
    
    def _create_directories_and_metadata(self, tour_shows: Dict[str, List[Dict[str, Any]]], 
                                       dry_run: bool) -> Dict[str, Any]:
        """Create directory structure and metadata files.
        
        Args:
            tour_shows: Tours and their shows
            dry_run: Whether to actually create directories
            
        Returns:
            Results dictionary with statistics
        """
        results = {
            "success": True,
            "dry_run": dry_run,
            "tours_created": 0,
            "shows_created": 0,
            "tour_metadata_files": 0,
            "show_metadata_files": 0,
            "errors": []
        }
        
        print(f"🎸 Setting up fresh KGLW collection")
        print(f"📁 Target path: {self.collection_path}")
        print(f"🎯 Mode: {'DRY RUN' if dry_run else 'CREATING FILES'}")
        print("="*70)
        
        # Create base collection directory
        if not dry_run:
            try:
                self.collection_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created base collection directory: {self.collection_path}")
            except Exception as e:
                error_msg = f"Failed to create base directory: {e}"
                logger.error(error_msg)
                results["errors"].append(error_msg)
                results["success"] = False
                return results
        
        # Process each tour
        for tour_name, shows in tour_shows.items():
            normalized_tour_name = self.tour_manager.normalize_tour_name_for_filesystem(tour_name)
            tour_dir = self.collection_path / normalized_tour_name
            
            print(f"\n📂 Tour: {tour_name}")
            print(f"   Normalized: {normalized_tour_name}")
            print(f"   Shows: {len(shows)}")
            
            # Create tour directory
            if not dry_run:
                try:
                    tour_dir.mkdir(parents=True, exist_ok=True)
                    results["tours_created"] += 1
                except Exception as e:
                    error_msg = f"Failed to create tour directory {normalized_tour_name}: {e}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)
                    continue
            else:
                results["tours_created"] += 1
            
            # Create tour metadata
            tour_metadata = self._create_tour_metadata(tour_name, shows)
            tour_metadata_path = tour_dir / ".tour_metadata.json"
            
            if not dry_run:
                try:
                    with open(tour_metadata_path, 'w', encoding='utf-8') as f:
                        json.dump(tour_metadata, f, indent=2, ensure_ascii=False)
                    results["tour_metadata_files"] += 1
                    print(f"   📝 Created tour metadata: {tour_metadata_path.name}")
                except Exception as e:
                    error_msg = f"Failed to create tour metadata for {normalized_tour_name}: {e}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)
            else:
                results["tour_metadata_files"] += 1
                print(f"   📝 Would create tour metadata: {tour_metadata_path.name}")
            
            # Create show directories and metadata
            # Track directory names to handle duplicates
            used_dir_names = set()
            
            for show in shows:
                show_dir_name = self._generate_show_directory_name(show)
                
                # Handle duplicate directory names by adding venue or show_id
                original_name = show_dir_name
                counter = 1
                while show_dir_name in used_dir_names:
                    # Add venue name if not already included
                    venue_name = show.get('venue_name', '')
                    if venue_name and venue_name not in original_name:
                        show_dir_name = f"{original_name} ({venue_name})"
                    else:
                        # Fall back to using show_id for uniqueness
                        show_id = show.get('show_id', '')
                        show_dir_name = f"{original_name} (show_{show_id})"
                    
                    counter += 1
                    if counter > 10:  # Prevent infinite loop
                        show_id = show.get('show_id', '')
                        show_dir_name = f"{original_name} (show_{show_id})"
                        break
                
                used_dir_names.add(show_dir_name)
                show_dir = tour_dir / show_dir_name
                
                print(f"     📁 Show: {show_dir_name}")
                
                # Create show directory
                if not dry_run:
                    try:
                        show_dir.mkdir(parents=True, exist_ok=True)
                        results["shows_created"] += 1
                    except Exception as e:
                        error_msg = f"Failed to create show directory {show_dir_name}: {e}"
                        logger.error(error_msg)
                        results["errors"].append(error_msg)
                        continue
                else:
                    results["shows_created"] += 1
                
                # Create show metadata
                show_metadata = self._create_show_metadata(show, tour_name, normalized_tour_name)
                show_metadata_path = show_dir / ".show_metadata.json"
                
                if not dry_run:
                    try:
                        with open(show_metadata_path, 'w', encoding='utf-8') as f:
                            json.dump(show_metadata, f, indent=2, ensure_ascii=False)
                        results["show_metadata_files"] += 1
                        print(f"        📝 Created show metadata: {show_metadata_path.name}")
                    except Exception as e:
                        error_msg = f"Failed to create show metadata for {show_dir_name}: {e}"
                        logger.error(error_msg)
                        results["errors"].append(error_msg)
                else:
                    results["show_metadata_files"] += 1
                    print(f"        📝 Would create show metadata: {show_metadata_path.name}")
        
        # Print summary
        print(f"\n📊 SUMMARY")
        print("="*30)
        print(f"Tours: {results['tours_created']}")
        print(f"Shows: {results['shows_created']}")
        print(f"Tour metadata files: {results['tour_metadata_files']}")
        print(f"Show metadata files: {results['show_metadata_files']}")
        
        if results["errors"]:
            print(f"Errors: {len(results['errors'])}")
            for error in results["errors"][:5]:  # Show first 5 errors
                print(f"  • {error}")
            if len(results["errors"]) > 5:
                print(f"  ... and {len(results['errors']) - 5} more")
        
        if dry_run:
            print(f"\n💡 Run with --apply to create the directories and files")
        else:
            print(f"\n✅ Fresh collection setup complete!")
        
        return results
    
    def _generate_show_directory_name(self, show: Dict[str, Any]) -> str:
        """Generate standardized show directory name.
        
        Args:
            show: Show information from API
            
        Returns:
            Formatted directory name
        """
        date = show.get('show_date', '')
        location = show.get('location', '')
        venue = show.get('venue_name', '')
        
        # Format: "2024-08-15 - Washington, DC, USA (The Anthem)"
        if venue and location:
            return f"{date} - {location} ({venue})"
        elif location:
            return f"{date} - {location}"
        else:
            return f"{date} - Unknown Location"
    
    def _create_tour_metadata(self, tour_name: str, shows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create metadata for a tour directory.
        
        Args:
            tour_name: Original tour name from API
            shows: List of shows in this tour
            
        Returns:
            Tour metadata dictionary
        """
        # Calculate tour statistics
        show_dates = [show.get('show_date') for show in shows if show.get('show_date')]
        start_date = min(show_dates) if show_dates else None
        end_date = max(show_dates) if show_dates else None
        
        # Get unique locations and countries
        locations = set()
        countries = set()
        venues = set()
        
        for show in shows:
            if show.get('location'):
                locations.add(show['location'])
            if show.get('country'):
                countries.add(show['country'])
            if show.get('venue_name'):
                venues.add(show['venue_name'])
        
        # Get tour ID (should be same for all shows in tour)
        tour_ids = set(show.get('tour_id') for show in shows if show.get('tour_id'))
        tour_id = list(tour_ids)[0] if len(tour_ids) == 1 else None
        
        return {
            "tour_info": {
                "tour_name": tour_name,
                "tour_id": tour_id,
                "normalized_name": self.tour_manager.normalize_tour_name_for_filesystem(tour_name),
                "show_count": len(shows),
                "date_range": {
                    "start_date": start_date,
                    "end_date": end_date
                }
            },
            "geographical_info": {
                "countries": sorted(list(countries)),
                "locations": sorted(list(locations)),
                "venue_count": len(venues),
                "unique_venues": len(venues)
            },
            "collection_info": {
                "videos_present": 0,  # Will be updated as videos are added
                "total_videos_expected": len(shows),  # Assuming 1 video per show
                "completeness_percentage": 0.0,
                "last_updated": datetime.now().isoformat()
            },
            "api_info": {
                "created_from_api": True,
                "api_shows_count": len(shows),
                "creation_date": datetime.now().isoformat(),
                "kglw_net_tour_id": tour_id
            }
        }
    
    def _create_show_metadata(self, show: Dict[str, Any], tour_name: str, 
                             normalized_tour_name: str) -> Dict[str, Any]:
        """Create metadata for a show directory.
        
        Args:
            show: Show information from API
            tour_name: Original tour name
            normalized_tour_name: Filesystem-safe tour name
            
        Returns:
            Show metadata dictionary
        """
        return {
            "show_info": {
                "show_date": show.get('show_date'),
                "show_id": show.get('show_id'),
                "venue_name": show.get('venue_name'),
                "location": show.get('location'),
                "city": show.get('city'),
                "state": show.get('state'),
                "country": show.get('country'),
                "show_title": show.get('show_title', ''),
                "artist": show.get('artist', 'King Gizzard & the Lizard Wizard')
            },
            "tour_info": {
                "tour_name": tour_name,
                "tour_id": show.get('tour_id'),
                "normalized_tour_name": normalized_tour_name
            },
            "collection_status": {
                "videos_present": [],  # Will list actual video files when added
                "video_count": 0,
                "has_complete_show": False,
                "has_partial_show": False,
                "has_individual_songs": False,
                "last_updated": datetime.now().isoformat()
            },
            "api_reference": {
                "permalink": show.get('permalink'),
                "api_updated_at": show.get('updated_at'),
                "created_from_api": True,
                "creation_date": datetime.now().isoformat()
            },
            "quality_info": {
                "best_quality": None,
                "upgrade_candidates": [],
                "needs_upgrade": False,
                "upgrade_reasons": []
            }
        }
    
    def get_setup_preview(self) -> Dict[str, Any]:
        """Get a preview of what would be created without creating anything.
        
        Returns:
            Preview information dictionary
        """
        api_data = self._get_comprehensive_api_data()
        if not api_data:
            return {"success": False, "error": "No API data available"}
        
        tour_shows = self._organize_shows_by_tour(api_data)
        
        preview = {
            "collection_path": str(self.collection_path),
            "total_tours": len(tour_shows),
            "total_shows": sum(len(shows) for shows in tour_shows.values()),
            "tours": {}
        }
        
        for tour_name, shows in tour_shows.items():
            normalized_name = self.tour_manager.normalize_tour_name_for_filesystem(tour_name)
            preview["tours"][tour_name] = {
                "normalized_name": normalized_name,
                "show_count": len(shows),
                "date_range": {
                    "start": min(show.get('show_date', '') for show in shows),
                    "end": max(show.get('show_date', '') for show in shows)
                },
                "sample_shows": [
                    self._generate_show_directory_name(show) 
                    for show in shows[:3]  # First 3 shows as examples
                ]
            }
        
        return preview


def create_fresh_collection(collection_path: str, dry_run: bool = True) -> Dict[str, Any]:
    """Convenience function to create a fresh collection.
    
    Args:
        collection_path: Where to create the collection
        dry_run: Whether to actually create files
        
    Returns:
        Results dictionary
    """
    setup = FreshCollectionSetup(collection_path)
    return setup.create_fresh_collection_structure(dry_run=dry_run)


def preview_fresh_collection(collection_path: str) -> Dict[str, Any]:
    """Preview what a fresh collection would look like.
    
    Args:
        collection_path: Where the collection would be created
        
    Returns:
        Preview information
    """
    setup = FreshCollectionSetup(collection_path)
    return setup.get_setup_preview()