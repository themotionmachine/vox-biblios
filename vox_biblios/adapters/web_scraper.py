"""
Web scraper for extracting text content from URLs.
"""
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlparse
from datetime import datetime
import tempfile
import os
from pathlib import Path

from goose3 import Goose
import requests
from bs4 import BeautifulSoup
import trafilatura

from vox_biblios.utils.logging import get_logger
from vox_biblios.exceptions import WebScraperError

logger = get_logger(__name__)


class WebScraper:
    """Scraper for extracting text content from web pages."""
    
    def __init__(self, use_trafilatura: bool = True):
        """
        Initialize the web scraper.
        
        Args:
            use_trafilatura: Whether to use trafilatura as primary extractor
        """
        self.use_trafilatura = use_trafilatura
        self.goose = Goose()
        logger.debug(f"Initialized WebScraper with use_trafilatura={use_trafilatura}")
    
    def extract_content(self, url: str) -> Dict[str, Any]:
        """
        Extract content from a URL.
        
        Args:
            url: URL to extract content from
            
        Returns:
            Dictionary with extracted content information
            
        Raises:
            WebScraperError: If extraction fails
        """
        logger.info(f"Extracting content from URL: {url}")
        
        try:
            # Try multiple extraction methods
            extracted = {}
            
            # Use trafilatura first if enabled
            if self.use_trafilatura:
                logger.debug("Attempting extraction with trafilatura")
                extracted = self._extract_with_trafilatura(url)
            
            # Fall back to Goose if trafilatura fails or is disabled
            if not extracted.get('text'):
                logger.debug("Falling back to Goose extractor")
                extracted = self._extract_with_goose(url)
            
            # Fall back to BeautifulSoup if both fail
            if not extracted.get('text'):
                logger.debug("Falling back to BeautifulSoup extractor")
                extracted = self._extract_with_bs4(url)
            
            # Generate filename from URL domain and timestamp
            domain = urlparse(url).netloc
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            filename = f"{domain}_{timestamp}.txt"
            
            result = {
                'url': url,
                'title': extracted.get('title', 'Untitled'),
                'text': extracted.get('text', ''),
                'filename': filename,
                'date': datetime.now(),
                'source': domain
            }
            
            logger.info(f"Extracted {len(result['text'])} characters from {url}")
            return result
            
        except Exception as e:
            error_msg = f"Failed to extract content from {url}: {str(e)}"
            logger.error(error_msg)
            raise WebScraperError(error_msg) from e
    
    def save_content_to_file(self, 
                             content: Dict[str, Any], 
                             output_dir: Optional[str] = None) -> Path:
        """
        Save extracted content to a file.
        
        Args:
            content: Dictionary with extracted content
            output_dir: Directory to save file in (default: temp directory)
            
        Returns:
            Path to the saved file
            
        Raises:
            WebScraperError: If saving fails
        """
        logger.info(f"Saving extracted content to file")
        
        try:
            # Determine output directory
            if output_dir:
                output_path = Path(output_dir) / content['filename']
                os.makedirs(output_dir, exist_ok=True)
            else:
                # Use temporary directory if no output directory specified
                temp_dir = tempfile.gettempdir()
                output_path = Path(temp_dir) / content['filename']
            
            # Add title as first line of text
            text_with_title = f"{content['title']}\n\nSource: {content['url']}\n\n{content['text']}"
            
            # Write content to file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(text_with_title)
            
            logger.info(f"Content saved to {output_path}")
            return output_path
            
        except Exception as e:
            error_msg = f"Failed to save content to file: {str(e)}"
            logger.error(error_msg)
            raise WebScraperError(error_msg) from e
    
    def _extract_with_trafilatura(self, url: str) -> Dict[str, Any]:
        """
        Extract content using trafilatura.
        
        Args:
            url: URL to extract from
            
        Returns:
            Dictionary with title and text
        """
        try:
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                return {'title': '', 'text': ''}
            
            result = trafilatura.extract(downloaded, output_format='json', include_comments=False)
            if not result:
                return {'title': '', 'text': ''}
            
            import json
            parsed = json.loads(result)
            
            return {
                'title': parsed.get('title', ''),
                'text': parsed.get('text', '')
            }
        except Exception as e:
            logger.warning(f"trafilatura extraction failed: {str(e)}")
            return {'title': '', 'text': ''}
    
    def _extract_with_goose(self, url: str) -> Dict[str, Any]:
        """
        Extract content using Goose.
        
        Args:
            url: URL to extract from
            
        Returns:
            Dictionary with title and text
        """
        try:
            article = self.goose.extract(url=url)
            return {
                'title': article.title,
                'text': article.cleaned_text
            }
        except Exception as e:
            logger.warning(f"Goose extraction failed: {str(e)}")
            return {'title': '', 'text': ''}
    
    def _extract_with_bs4(self, url: str) -> Dict[str, Any]:
        """
        Extract content using BeautifulSoup.
        
        Args:
            url: URL to extract from
            
        Returns:
            Dictionary with title and text
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract title
            title = ''
            title_elem = soup.find('title')
            if title_elem:
                title = title_elem.get_text().strip()
            
            # Extract text
            paragraphs = []
            for p in soup.find_all('p'):
                text = p.get_text().strip()
                if text and len(text) > 20:  # Skip short paragraphs
                    paragraphs.append(text)
            
            text = '\n\n'.join(paragraphs)
            
            return {
                'title': title,
                'text': text
            }
        except Exception as e:
            logger.warning(f"BeautifulSoup extraction failed: {str(e)}")
            return {'title': '', 'text': ''}