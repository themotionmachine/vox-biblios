"""
Vox Biblios - A Personal Text-to-Podcast Generator.

This package allows users to convert text files or web content into podcast episodes
and publish them to an RSS feed.
"""

__version__ = "1.0.0"
__author__ = "themotionmachine"
__all__ = ["config", "cli"]

# Import main components for easy access
from vox_biblios.config import config
from vox_biblios.core.podcast_manager import PodcastManager