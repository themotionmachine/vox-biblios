"""
RSS feed generation and management for podcast.
"""
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timezone
import xmltodict
import requests
from urllib.parse import urlparse
from pathlib import Path
import json

from podgen import Podcast, Episode, Media, Person, Category
import pandas as pd

from vox_biblios.config import config
from vox_biblios.utils.logging import get_logger
from vox_biblios.aws.s3 import S3Service
from vox_biblios.aws.cost import CostEstimationService
from vox_biblios.exceptions import RSSError

logger = get_logger(__name__)


class PodcastRSSManager:
    """Manager for podcast RSS feed generation and updates."""
    
    def __init__(self, 
                 podcast_name: Optional[str] = None,
                 podcast_description: Optional[str] = None,
                 podcast_website: Optional[str] = None,
                 podcast_image: Optional[str] = None,
                 rss_filename: Optional[str] = None):
        """
        Initialize the podcast RSS manager.
        
        Args:
            podcast_name: Name of the podcast (default from config)
            podcast_description: Description of the podcast (default from config)
            podcast_website: Website URL (default from config)
            podcast_image: Image URL (default from config)
            rss_filename: RSS filename (default from config)
        """
        self.podcast_name = podcast_name or config.app.podcast_name
        self.podcast_description = podcast_description or config.app.podcast_description
        self.podcast_website = podcast_website or config.app.podcast_website
        self.podcast_image = podcast_image or config.app.podcast_image
        self.rss_filename = rss_filename or config.app.rss_filename
        
        self.s3_service = S3Service()
        self.cost_service = CostEstimationService()
        
        logger.debug(f"Initialized PodcastRSSManager for podcast '{self.podcast_name}'")
    
    def create_new_podcast(self) -> Podcast:
        """
        Create a new podcast object.
        
        Returns:
            Podcast object
        """
        logger.info("Creating new podcast object")
        
        # Get cost summary for description
        try:
            cost_summary = self.cost_service.format_cost_summary()
            description = f"{cost_summary}\n\n{self.podcast_description}"
        except Exception as e:
            logger.error(f"Failed to get cost summary: {str(e)}")
            description = self.podcast_description
        
        # Create podcast object
        podcast = Podcast(
            name=self.podcast_name,
            description=description,
            website=self.podcast_website,
            explicit=config.app.podcast_explicit
        )
        
        # Set image
        podcast.image = self.podcast_image
        
        # Set basic metadata
        podcast.language = "en-us"
        podcast.authors = [Person("Vox Biblios")]
        podcast.copyright = f"Copyright {datetime.now().year}"
        
        # Add categories - using "Tech News" as a valid subcategory
        podcast.category = Category("Technology", "Tech News")
        
        return podcast
    
    def create_episode(self, 
                       title: str, 
                       audio_url: str, 
                       description: Optional[str] = None,
                       publication_date: Optional[datetime] = None) -> Episode:
        """
        Create a podcast episode.
        
        Args:
            title: Episode title
            audio_url: URL to the audio file
            description: Episode description (defaults to title)
            publication_date: Publication date (defaults to now)
            
        Returns:
            Episode object
        """
        logger.debug(f"Creating episode: {title}")
        
        # Ensure publication date has timezone info
        if publication_date is None:
            publication_date = datetime.now()
        
        if publication_date.tzinfo is None:
            # Add UTC timezone if none exists
            publication_date = publication_date.replace(tzinfo=timezone.utc)
        
        # Create episode
        episode = Episode(
            title=title,
            media=Media(audio_url),
            summary=description or title,
            publication_date=publication_date
        )
        
        return episode
    
    def fetch_current_rss(self) -> Optional[str]:
        """
        Fetch the current RSS feed from S3.
        
        Returns:
            RSS feed content or None if not found
        """
        logger.info("Fetching current RSS feed")
        
        rss_url = config.get_rss_url
        
        try:
            response = requests.get(rss_url)
            response.raise_for_status()
            logger.info("Current RSS feed fetched successfully")
            return response.text
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch RSS feed: {str(e)}")
            return None
    
    def parse_episodes_from_rss(self, rss_content: str) -> List[Dict[str, Any]]:
        """
        Parse episodes from RSS content.
        
        Args:
            rss_content: RSS feed content
            
        Returns:
            List of episode dictionaries
        """
        logger.info("Parsing episodes from RSS content")
        
        try:
            # Parse XML
            xml_dict = xmltodict.parse(rss_content)
            
            # Extract items (episodes)
            channel = xml_dict.get('rss', {}).get('channel', {})
            items = channel.get('item', [])
            
            # Ensure items is a list
            if not isinstance(items, list):
                items = [items] if items else []
            
            # Convert to list of dictionaries
            episodes = []
            for item in items:
                try:
                    # Extract enclosure URL
                    url = item.get('enclosure', {}).get('@url') if item.get('enclosure') else None
                    
                    if not url:
                        continue
                    
                    # Create episode dictionary
                    episode = {
                        'title': item.get('title', ''),
                        'url': url,
                        'description': item.get('description', ''),
                        'pubDate': item.get('pubDate', '')
                    }
                    
                    episodes.append(episode)
                except Exception as e:
                    logger.warning(f"Failed to parse episode: {str(e)}")
            
            logger.info(f"Parsed {len(episodes)} episodes from RSS feed")
            return episodes
            
        except Exception as e:
            error_msg = f"Failed to parse RSS content: {str(e)}"
            logger.error(error_msg)
            raise RSSError(error_msg) from e
    
    def extract_s3_keys_from_urls(self, episodes: List[Dict[str, Any]]) -> List[str]:
        """
        Extract S3 keys from episode URLs.
        
        Args:
            episodes: List of episode dictionaries
            
        Returns:
            List of S3 keys
        """
        logger.debug("Extracting S3 keys from episode URLs")
        
        s3_keys = []
        
        for episode in episodes:
            try:
                url = episode.get('url', '')
                if url:
                    parsed_url = urlparse(url)
                    key = parsed_url.path.lstrip('/')
                    s3_keys.append(key)
            except Exception as e:
                logger.warning(f"Failed to extract S3 key from URL {episode.get('url', '')}: {str(e)}")
        
        logger.debug(f"Extracted {len(s3_keys)} S3 keys")
        return s3_keys
    
    def recreate_podcast_with_episodes(self, 
                                      existing_episodes: List[Dict[str, Any]], 
                                      new_episodes: List[Dict[str, Any]]) -> Podcast:
        """
        Recreate podcast with existing and new episodes.
        
        Args:
            existing_episodes: List of existing episode dictionaries
            new_episodes: List of new episode dictionaries
            
        Returns:
            Podcast object with all episodes
        """
        logger.info(f"Recreating podcast with {len(existing_episodes)} existing and {len(new_episodes)} new episodes")
        
        # Create podcast object
        podcast = self.create_new_podcast()
        episodes = []
        
        # Track URLs to avoid duplicates
        urls = set()
        
        # Add existing episodes
        for ep_data in existing_episodes:
            if ep_data.get('url') in urls:
                logger.debug(f"Skipping duplicate episode: {ep_data.get('title')}")
                continue
            
            try:
                pub_date = datetime.strptime(ep_data.get('pubDate', ''), '%a, %d %b %Y %H:%M:%S %z') \
                    if ep_data.get('pubDate') else None
                
                episode = self.create_episode(
                    title=ep_data.get('title', ''),
                    audio_url=ep_data.get('url', ''),
                    description=ep_data.get('description', ''),
                    publication_date=pub_date
                )
                
                episodes.append(episode)
                urls.add(ep_data.get('url'))
                
            except Exception as e:
                logger.warning(f"Failed to create episode for {ep_data.get('title')}: {str(e)}")
        
        # Add new episodes
        for ep_data in new_episodes:
            if ep_data.get('url') in urls:
                logger.debug(f"Skipping duplicate new episode: {ep_data.get('title')}")
                continue
            
            try:
                episode = self.create_episode(
                    title=ep_data.get('title', ''),
                    audio_url=ep_data.get('url', ''),
                    description=ep_data.get('description', ''),
                    publication_date=ep_data.get('pubDate') if isinstance(ep_data.get('pubDate'), datetime) else None
                )
                
                episodes.append(episode)
                urls.add(ep_data.get('url'))
                
            except Exception as e:
                logger.warning(f"Failed to create new episode: {str(e)}")
        
        # Add episodes to podcast
        podcast.episodes = episodes
        
        logger.info(f"Recreated podcast with {len(podcast.episodes)} total episodes")
        return podcast
    
    def generate_rss(self, podcast: Podcast, output_path: Optional[Union[str, Path]] = None) -> str:
        """
        Generate RSS feed from podcast object.
        
        Args:
            podcast: Podcast object
            output_path: Path to write RSS file (optional)
            
        Returns:
            RSS content as string
        """
        logger.info("Generating RSS feed")
        
        # Generate RSS string
        rss_content = podcast.rss_str()
        
        # Write to file if path provided
        if output_path:
            output_path = Path(output_path)
            
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(rss_content)
                logger.info(f"RSS feed written to {output_path}")
            except Exception as e:
                logger.error(f"Failed to write RSS to {output_path}: {str(e)}")
        
        return rss_content
    
    def upload_rss_to_s3(self, rss_content: str) -> str:
        """
        Upload RSS feed to S3.
        
        Args:
            rss_content: RSS feed content
            
        Returns:
            S3 URL of the uploaded RSS feed
        """
        logger.info(f"Uploading RSS feed to S3 as {self.rss_filename}")
        
        try:
            # Write content to temporary file
            temp_path = Path(self.rss_filename)
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(rss_content)
            
            # Upload to S3
            s3_url = self.s3_service.upload_file(
                file_path=temp_path,
                object_key=self.rss_filename,
                content_type='application/rss+xml'
            )
            
            # Clean up temporary file
            temp_path.unlink()
            
            logger.info(f"RSS feed uploaded successfully to {s3_url}")
            return s3_url
            
        except Exception as e:
            error_msg = f"Failed to upload RSS feed to S3: {str(e)}"
            logger.error(error_msg)
            raise RSSError(error_msg) from e
    
    def clear_podcast_feed(self) -> str:
        """
        Clear all episodes from the podcast feed.
        
        Returns:
            S3 URL of the updated RSS feed
        """
        logger.info("Clearing podcast feed")
        
        try:
            # Fetch current RSS to get audio file keys
            current_rss = self.fetch_current_rss()
            
            if current_rss:
                # Parse episodes and get S3 keys
                episodes = self.parse_episodes_from_rss(current_rss)
                s3_keys = self.extract_s3_keys_from_urls(episodes)
                
                # Delete audio files from S3
                for key in s3_keys:
                    try:
                        self.s3_service.delete_file(key)
                        logger.info(f"Deleted file from S3: {key}")
                    except Exception as e:
                        logger.warning(f"Failed to delete file from S3: {key}. Error: {str(e)}")
            
            # Create new empty podcast
            podcast = self.create_new_podcast()
            
            # Generate RSS
            rss_content = self.generate_rss(podcast)
            
            # Upload to S3
            s3_url = self.upload_rss_to_s3(rss_content)
            
            logger.info("Podcast feed cleared successfully")
            return s3_url
            
        except Exception as e:
            error_msg = f"Failed to clear podcast feed: {str(e)}"
            logger.error(error_msg)
            raise RSSError(error_msg) from e
    
    def update_feed_with_episodes(self, new_episode_data: List[Dict[str, Any]]) -> str:
        """
        Update the podcast feed with new episodes.
        
        Args:
            new_episode_data: List of dictionaries with new episode data
            
        Returns:
            S3 URL of the updated RSS feed
        """
        logger.info(f"Updating podcast feed with {len(new_episode_data)} new episodes")
        
        try:
            # Fetch current RSS
            current_rss = self.fetch_current_rss()
            existing_episodes = []
            
            if current_rss:
                # Parse existing episodes
                existing_episodes = self.parse_episodes_from_rss(current_rss)
            
            # Recreate podcast with all episodes
            podcast = self.recreate_podcast_with_episodes(existing_episodes, new_episode_data)
            
            # Generate RSS
            rss_content = self.generate_rss(podcast, self.rss_filename)
            
            # Upload to S3
            s3_url = self.upload_rss_to_s3(rss_content)
            
            logger.info(f"Podcast feed updated successfully with {len(new_episode_data)} new episodes")
            return s3_url
            
        except Exception as e:
            error_msg = f"Failed to update podcast feed: {str(e)}"
            logger.error(error_msg)
            raise RSSError(error_msg) from e