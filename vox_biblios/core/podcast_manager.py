"""
Core podcast manager for Vox Biblios.
"""
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import os
from datetime import datetime, timezone
import time
from urllib.parse import urlparse

from vox_biblios.config import config
from vox_biblios.utils.logging import get_logger, SoundWaveAnimation
from vox_biblios.core.text_processor import TextProcessor
from vox_biblios.aws.polly import PollyService
from vox_biblios.aws.s3 import S3Service
from vox_biblios.adapters.rss import PodcastRSSManager
from vox_biblios.adapters.web_scraper import WebScraper
from vox_biblios.exceptions import PodcastManagerError

logger = get_logger(__name__)


class PodcastManager:
    """Central manager for Vox Biblios podcast generator."""
    
    def __init__(self):
        """Initialize the podcast manager with all necessary components."""
        self.text_processor = TextProcessor()
        self.polly_service = PollyService()
        self.s3_service = S3Service()
        self.rss_manager = PodcastRSSManager()
        self.web_scraper = WebScraper()
        self.animation = SoundWaveAnimation()
        
        logger.debug("Initialized PodcastManager")
    
    def process_texts_from_folder(self, folder_path: Union[str, Path]) -> List[Dict[str, Any]]:
        """
        Process all text files in a folder.
        
        Args:
            folder_path: Path to folder containing text files
            
        Returns:
            List of episode data dictionaries
            
        Raises:
            PodcastManagerError: If processing fails
        """
        logger.info(f"Processing texts from folder: {folder_path}")
        self.animation.start()
        
        try:
            # Process texts
            processed_texts = self.text_processor.process_folder(folder_path)
            
            if not processed_texts:
                logger.warning(f"No text files found in {folder_path}")
                self.animation.stop()
                return []
            
            results = []
            
            # Process each text
            for filename, text in processed_texts.items():
                logger.info(f"Processing file: {filename}")
                
                # Split text into chunks
                chunks = self.text_processor.chunk(text)
                logger.info(f"Split {filename} into {len(chunks)} chunks")
                
                # Process each chunk
                for i, chunk in enumerate(chunks):
                    chunk_title = f"{filename} (Part {i+1})" if len(chunks) > 1 else filename
                    
                    # Send to Polly
                    logger.info(f"Sending chunk {i+1}/{len(chunks)} to Polly")
                    response = self.polly_service.synthesize_speech(chunk)
                    
                    if response:
                        # Get output URI
                        output_uri = response['SynthesisTask']['OutputUri']
                        
                        # Create episode data
                        timestamp = datetime.now(timezone.utc)
                        
                        # Add text preview to description using configured preview length
                        preview_length = config.app.preview_length
                        text_preview = chunk[:preview_length].strip() + "..." if len(chunk) > preview_length else chunk.strip()
                        
                        episode_data = {
                            'title': chunk_title,
                            'url': output_uri,
                            'description': f"Generated from {filename}\n\nPreview: {text_preview}",
                            'pubDate': timestamp
                        }
                        
                        results.append(episode_data)
                        logger.info(f"Successfully processed chunk {i+1}/{len(chunks)}")
                        
                        # Small delay to avoid AWS throttling
                        time.sleep(1)
                    else:
                        logger.error(f"Failed to process chunk {i+1}/{len(chunks)}")
            
            # Clean up processed files
            if results:
                self.text_processor.delete_processed_files(folder_path)
            
            logger.info(f"Processed {len(results)} chunks from {len(processed_texts)} files")
            self.animation.stop()
            return results
            
        except Exception as e:
            self.animation.stop()
            error_msg = f"Failed to process texts from folder {folder_path}: {str(e)}"
            logger.error(error_msg)
            raise PodcastManagerError(error_msg) from e
    
    def process_url(self, url: str) -> List[Dict[str, Any]]:
        """
        Process content from a URL.
        
        Args:
            url: URL to process
            
        Returns:
            List of episode data dictionaries
            
        Raises:
            PodcastManagerError: If processing fails
        """
        logger.info(f"Processing content from URL: {url}")
        self.animation.start()
        
        try:
            # Extract content from URL
            content = self.web_scraper.extract_content(url)
            
            if not content or not content.get('text'):
                logger.warning(f"No content extracted from {url}")
                self.animation.stop()
                return []
            
            # Get title with fallbacks
            title = content.get('title', '')
            if not title:
                # Try to get title from URL path
                parsed_url = urlparse(url)
                path = parsed_url.path.strip('/')
                if path:
                    # Clean up path to make it more readable
                    title = path.replace('-', ' ').replace('_', ' ').title()
                else:
                    # Last resort: use domain name
                    title = parsed_url.netloc.replace('www.', '')
            
            # Preprocess text
            text = self.text_processor.preprocess(content['text'])
            
            # Split text into chunks
            chunks = self.text_processor.chunk(text)
            logger.info(f"Split content from {url} into {len(chunks)} chunks")
            
            results = []
            
            # Process each chunk
            for i, chunk in enumerate(chunks):
                chunk_title = f"{title} (Part {i+1})" if len(chunks) > 1 else title
                
                # Send to Polly
                logger.info(f"Sending chunk {i+1}/{len(chunks)} to Polly")
                response = self.polly_service.synthesize_speech(chunk)
                
                if response:
                    # Get output URI
                    output_uri = response['SynthesisTask']['OutputUri']
                    
                    # Create episode data
                    timestamp = datetime.now(timezone.utc)
                    
                    # Add text preview to description using configured preview length
                    preview_length = config.app.preview_length
                    text_preview = chunk[:preview_length].strip() + "..." if len(chunk) > preview_length else chunk.strip()
                    
                    episode_data = {
                        'title': chunk_title,
                        'url': output_uri,
                        'description': f"Generated from {url}\n\nPreview: {text_preview}",
                        'pubDate': timestamp
                    }
                    
                    results.append(episode_data)
                    logger.info(f"Successfully processed chunk {i+1}/{len(chunks)}")
                    
                    # Small delay to avoid AWS throttling
                    time.sleep(1)
                else:
                    logger.error(f"Failed to process chunk {i+1}/{len(chunks)}")
            
            logger.info(f"Processed {len(results)} chunks from URL {url}")
            self.animation.stop()
            return results
            
        except Exception as e:
            self.animation.stop()
            error_msg = f"Failed to process content from URL {url}: {str(e)}"
            logger.error(error_msg)
            raise PodcastManagerError(error_msg) from e
    
    def update_podcast_feed(self, new_episodes: List[Dict[str, Any]]) -> str:
        """
        Update the podcast RSS feed with new episodes.
        
        Args:
            new_episodes: List of new episode data dictionaries
            
        Returns:
            URL of the updated RSS feed
            
        Raises:
            PodcastManagerError: If update fails
        """
        logger.info(f"Updating podcast feed with {len(new_episodes)} new episodes")
        
        try:
            # Update RSS feed
            rss_url = self.rss_manager.update_feed_with_episodes(new_episodes)
            
            logger.info(f"Podcast feed updated successfully: {rss_url}")
            return rss_url
            
        except Exception as e:
            error_msg = f"Failed to update podcast feed: {str(e)}"
            logger.error(error_msg)
            raise PodcastManagerError(error_msg) from e
    
    def clear_podcast_feed(self) -> str:
        """
        Clear all episodes from the podcast feed.
        
        Returns:
            URL of the cleared RSS feed
            
        Raises:
            PodcastManagerError: If clearing fails
        """
        logger.info("Clearing podcast feed")
        
        try:
            # Clear RSS feed
            rss_url = self.rss_manager.clear_podcast_feed()
            
            logger.info(f"Podcast feed cleared successfully: {rss_url}")
            return rss_url
            
        except Exception as e:
            error_msg = f"Failed to clear podcast feed: {str(e)}"
            logger.error(error_msg)
            raise PodcastManagerError(error_msg) from e
    
    def process_and_update(self, input_source: str) -> str:
        """
        Process input source and update podcast feed.
        
        Args:
            input_source: Folder path or URL to process
            
        Returns:
            URL of the updated RSS feed
            
        Raises:
            PodcastManagerError: If processing fails
        """
        logger.info(f"Processing and updating podcast feed with input source: {input_source}")
        
        try:
            # Determine input type and process accordingly
            if input_source.startswith('http://') or input_source.startswith('https://'):
                # Process URL
                new_episodes = self.process_url(input_source)
            else:
                # Process folder
                new_episodes = self.process_texts_from_folder(input_source)
            
            if not new_episodes:
                logger.warning(f"No episodes generated from input source: {input_source}")
                return config.get_rss_url
            
            # Update podcast feed
            rss_url = self.update_podcast_feed(new_episodes)
            
            logger.info(f"Successfully processed input source and updated podcast feed: {rss_url}")
            return rss_url
            
        except Exception as e:
            error_msg = f"Failed to process and update from input source {input_source}: {str(e)}"
            logger.error(error_msg)
            raise PodcastManagerError(error_msg) from e