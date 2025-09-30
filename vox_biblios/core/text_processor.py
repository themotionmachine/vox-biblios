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
        text = self._remove_bibliography(text)
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
            
        The method uses a multi-level approach:
        1. First tries to split by sentences
        2. If sentences are too long, splits by paragraphs
        3. If paragraphs are too long, splits by words
        4. If words are too long, splits by characters (last resort)
        """
        logger.info(f"Chunking text of length {len(text)} characters")
        
        if not text:
            logger.warning("Empty text provided for chunking")
            return []
        
        chunks = []
        current_chunk = ""
        
        # First try to split by sentences
        sentences = _tokenizer.tokenize(text)
        
        for sentence in sentences:
            # If adding this sentence would exceed the chunk size
            if len(current_chunk) + len(sentence) + 1 > self.max_chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                
                # If a single sentence is too long, try splitting by paragraphs
                if len(sentence) > self.max_chunk_size:
                    logger.warning(f"Sentence exceeds max chunk size ({len(sentence)} > {self.max_chunk_size}), trying paragraph split")
                    paragraphs = sentence.split('\n\n')
                    
                    for paragraph in paragraphs:
                        if len(paragraph) > self.max_chunk_size:
                            # If paragraph is too long, split by words
                            logger.warning(f"Paragraph exceeds max chunk size ({len(paragraph)} > {self.max_chunk_size}), splitting by words")
                            words = paragraph.split()
                            current_part = ""
                            
                            for word in words:
                                if len(current_part) + len(word) + 1 > self.max_chunk_size:
                                    if current_part:
                                        chunks.append(current_part.strip())
                                        current_part = ""
                                
                                # If a single word is too long, split by characters (last resort)
                                if len(word) > self.max_chunk_size:
                                    logger.warning(f"Word exceeds max chunk size ({len(word)} > {self.max_chunk_size}), splitting by characters")
                                    for i in range(0, len(word), self.max_chunk_size):
                                        chunks.append(word[i:i + self.max_chunk_size])
                                else:
                                    current_part += word + " "
                            
                            if current_part:
                                chunks.append(current_part.strip())
                        else:
                            current_chunk = paragraph + "\n\n"
                else:
                    current_chunk = sentence + " "
            else:
                current_chunk += sentence + " "
        
        # Add the final chunk if not empty
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        # Final validation
        for i, chunk in enumerate(chunks):
            chunk_length = len(chunk)
            logger.debug(f"Chunk {i+1} length: {chunk_length} characters")
            if chunk_length > self.max_chunk_size:
                logger.error(f"Chunk {i+1} still exceeds max chunk size ({chunk_length} > {self.max_chunk_size})")
                # If we still have oversized chunks, force split them
                if chunk_length > self.max_chunk_size:
                    chunks[i:i+1] = [chunk[j:j + self.max_chunk_size] 
                                   for j in range(0, len(chunk), self.max_chunk_size)]
        
        logger.info(f"Created {len(chunks)} chunks")
        return chunks
    
    def _read_file_with_encoding(self, file_path: Path) -> str:
        """
        Try to read a file with different encodings.
        
        Args:
            file_path: Path to the file to read
            
        Returns:
            The file contents as a string
            
        Raises:
            TextProcessingError if no encoding works
        """
        encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                logger.debug(f"Failed to read {file_path} with {encoding} encoding")
                continue
        
        error_msg = f"Could not read {file_path} with any of the attempted encodings: {encodings}"
        logger.error(error_msg)
        raise TextProcessingError(error_msg)
    
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
                text = self._read_file_with_encoding(file_path)
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
        # Replace multiple spaces with single space
        text = re.sub(r'\s+', ' ', text)
        # Remove leading/trailing whitespace
        return text.strip()

    def _remove_bibliography(self, text: str) -> str:
        """
        Remove bibliography section from text.
        
        Args:
            text: Input text
            
        Returns:
            Text with bibliography section removed
        """
        logger.info("Removing bibliography section")
        
        original_length = len(text)
        processed_text = self._remove_bibliography_helper(text)
        removed_length = original_length - len(processed_text)
        
        if removed_length > 0:
            percentage = (removed_length / original_length) * 100
            logger.info(f"Removed bibliography: {removed_length} characters ({percentage:.1f}% of document)")
        else:
            logger.info("No bibliography section detected")
        
        return processed_text

    def _remove_bibliography_helper(self, text: str) -> str:
        """
        Helper function to remove bibliography section from text.
        
        Args:
            text: Input text
            
        Returns:
            Text with bibliography section removed
        """
        # Split text into lines for better context analysis
        lines = text.split('\n')
        
        # Common bibliography section header patterns
        patterns = [
            r'^(?:\s*|\d+\.\s*)References\s*$',
            r'^(?:\s*|\d+\.\s*)Bibliography\s*$',
            r'^(?:\s*|\d+\.\s*)Works\s+Cited\s*$',
            r'^(?:\s*|\d+\.\s*)Literature\s+Cited\s*$',
            r'^(?:\s*|\d+\.\s*)Cited\s+Literature\s*$',
            r'^(?:\s*|\d+\.\s*)Sources\s*$',
            r'^(?:\s*|\d+\.\s*)References\s+and\s+Notes\s*$',
            r'^(?:\s*|\d+\.\s*)Works\s+Consulted\s*$'
        ]
        
        # Only consider matches in the last 30% of the document
        cutoff_index = int(len(lines) * 0.7)
        
        # Find potential bibliography header lines
        for i in range(cutoff_index, len(lines)):
            line = lines[i]
            
            # Check against each pattern
            if any(re.match(pattern, line, re.IGNORECASE) for pattern in patterns):
                # Verify it's a standalone header
                # (empty line before or after, or at document start/end)
                is_standalone = (i == 0 or not lines[i-1].strip() or 
                                i == len(lines)-1 or not lines[i+1].strip())
                
                if is_standalone:
                    # Return text up to this point
                    return '\n'.join(lines[:i])
        
        # No bibliography section found
        return text