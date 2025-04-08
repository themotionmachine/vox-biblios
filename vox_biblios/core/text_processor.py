"""
Text processing utilities for Vox Biblios.
"""
import re
import nltk
from nltk.tokenize import sent_tokenize, PunktSentenceTokenizer
from typing import List, Dict, Optional, Union
from pathlib import Path
import os

from vox_biblios.config import config
from vox_biblios.utils.logging import get_logger
from vox_biblios.exceptions import TextProcessingError

logger = get_logger(__name__)

# Initialize NLTK punkt tokenizer
try:
    nltk.data.find('tokenizers/punkt/english.pickle')
except LookupError:
    logger.info("Downloading NLTK punkt tokenizer data")
    nltk.download('punkt', quiet=True)

# Create a tokenizer instance
_tokenizer = PunktSentenceTokenizer()

# Set the NLTK data path to ensure it's found
nltk.data.path.append('/Users/rwm/nltk_data')

# Ensure we have the correct punkt data
try:
    nltk.data.find('tokenizers/punkt/english.pickle')
except LookupError:
    logger.info("Downloading NLTK punkt English data")
    nltk.download('punkt', quiet=True)


class TextProcessor:
    """Process text for TTS conversion."""
    
    def __init__(self, max_chunk_size: Optional[int] = None):
        """
        Initialize the text processor.
        
        Args:
            max_chunk_size: Maximum size of text chunks in characters
                           (defaults to config value)
        """
        self.max_chunk_size = max_chunk_size or config.app.chunk_size
        logger.debug(f"Initialized TextProcessor with max_chunk_size={self.max_chunk_size}")
    
    def preprocess(self, text: str) -> str:
        """
        Preprocess text to prepare it for TTS.
        
        Args:
            text: Raw input text
            
        Returns:
            Preprocessed text
        """
        logger.info(f"Preprocessing text of length {len(text)} characters")
        
        # Apply preprocessing steps
        text = self._remove_urls(text)
        text = self._remove_noise(text)
        text = self._remove_long_numbers(text)
        text = self._normalize_whitespace(text)
        
        logger.info(f"Preprocessing complete, final length: {len(text)} characters")
        return text
    
    def chunk(self, text: str) -> List[str]:
        """
        Split text into chunks suitable for TTS processing.
        
        Args:
            text: Text to chunk
            
        Returns:
            List of text chunks
        """
        logger.info(f"Chunking text of length {len(text)} characters")
        
        if not text:
            logger.warning("Empty text provided for chunking")
            return []
        
        chunks = []
        current_chunk = ""
        sentences = _tokenizer.tokenize(text)
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) < self.max_chunk_size:
                current_chunk += sentence + ' '
            else:
                # If current chunk is not empty, add it to chunks
                if current_chunk:
                    chunks.append(current_chunk.strip())
                
                # Start a new chunk
                current_chunk = sentence + ' '
        
        # Add the final chunk if not empty
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        logger.info(f"Created {len(chunks)} chunks")
        for i, chunk in enumerate(chunks):
            logger.debug(f"Chunk {i+1} length: {len(chunk)} characters")
        
        return chunks
    
    def process_folder(self, folder_path: Union[str, Path]) -> Dict[str, str]:
        """
        Process all text files in a folder.
        
        Args:
            folder_path: Path to the folder containing text files
            
        Returns:
            Dictionary mapping filenames to processed text
        """
        folder_path = Path(folder_path)
        logger.info(f"Processing text files from folder: {folder_path}")
        
        if not folder_path.exists() or not folder_path.is_dir():
            error_msg = f"Folder does not exist or is not a directory: {folder_path}"
            logger.error(error_msg)
            raise TextProcessingError(error_msg)
        
        result = {}
        
        # Get all .txt files in the folder
        txt_files = list(folder_path.glob("*.txt"))
        logger.info(f"Found {len(txt_files)} text files in {folder_path}")
        
        for file_path in txt_files:
            try:
                logger.debug(f"Processing file: {file_path.name}")
                
                # Read and process the file
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
                
                processed_text = self.preprocess(text)
                result[file_path.name] = processed_text
                
                logger.debug(f"Successfully processed file: {file_path.name}")
            
            except Exception as e:
                logger.error(f"Error processing file {file_path.name}: {str(e)}", exc_info=True)
        
        return result
    
    def delete_processed_files(self, folder_path: Union[str, Path]) -> int:
        """
        Delete all text files from a folder after processing.
        
        Args:
            folder_path: Path to the folder containing text files
            
        Returns:
            Number of files deleted
        """
        folder_path = Path(folder_path)
        logger.info(f"Deleting processed text files from folder: {folder_path}")
        
        deleted_count = 0
        
        try:
            for file_path in folder_path.glob("*.txt"):
                try:
                    file_path.unlink()
                    deleted_count += 1
                    logger.debug(f"Deleted file: {file_path.name}")
                except Exception as e:
                    logger.warning(f"Failed to delete file {file_path.name}: {str(e)}")
            
            logger.info(f"Deleted {deleted_count} text files from {folder_path}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error deleting files from {folder_path}: {str(e)}", exc_info=True)
            return deleted_count
    
    # Private helper methods
    
    def _remove_urls(self, text: str) -> str:
        """Remove URLs from text."""
        logger.debug("Removing URLs from text")
        return re.sub(r'http\S+|www\S+|https\S+', '', text)
    
    def _remove_noise(self, text: str) -> str:
        """Remove repeated sentences that might be noise."""
        logger.debug("Removing noise from text")
        
        # Split text into sentences using the punkt tokenizer instance
        sentences = _tokenizer.tokenize(text)
        
        # Filter out sentences that appear too many times (likely noise)
        sentence_counts = {}
        for sentence in sentences:
            sentence_counts[sentence] = sentence_counts.get(sentence, 0) + 1
        
        filtered_sentences = [s for s in sentences if sentence_counts[s] <= 10]
        
        # Log how many sentences were removed
        removed_count = len(sentences) - len(filtered_sentences)
        if removed_count > 0:
            logger.debug(f"Removed {removed_count} noisy sentences")
        
        return ' '.join(filtered_sentences)
    
    def _remove_long_numbers(self, text: str) -> str:
        """Remove long numbers that are unlikely to be read properly."""
        logger.debug("Removing long numbers from text")
        return re.sub(r'\d{7,}', '', text)
    
    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace in text."""
        logger.debug("Normalizing whitespace")
        # Replace multiple whitespace characters with a single space
        return re.sub(r'\s+', ' ', text).strip()