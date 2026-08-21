#!/usr/bin/env python3
"""
KGLW Manager - King Gizzard & The Lizard Wizard Concert Collection Manager

A comprehensive tool for managing, organizing, and upgrading your King Gizzard
concert video collection with intelligent YouTube search, quality analysis,
and Plex integration.
"""

import sys
from pathlib import Path

# Add the kglw_manager package to Python path
sys.path.insert(0, str(Path(__file__).parent))

from kglw_manager.cli import main

if __name__ == '__main__':
    main()