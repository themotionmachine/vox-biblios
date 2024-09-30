import re
import nltk
from nltk.tokenize import sent_tokenize
from logging_utils import logger

nltk.download('punkt', quiet=True)

def preprocess_text(text):
    logger.info("Starting text preprocessing")
    text = remove_urls(text)
    text = remove_noise(text)
    text = remove_long_numbers(text)
    logger.info("Text preprocessing completed")
    return text

def remove_urls(text):
    logger.debug("Removing URLs from text")
    return re.sub(r'http\S+|www\S+', '', text)

def remove_noise(text):
    logger.debug("Removing noise from text")
    text = re.sub(r'\s+', ' ', text)
    sentences = sent_tokenize(text)
    cleaned_text = ' '.join([s for s in sentences if sentences.count(s) <= 10])
    logger.debug(f"Removed {len(sentences) - len(cleaned_text.split('.'))} noisy sentences")
    return cleaned_text

def remove_long_numbers(text):
    logger.debug("Removing long numbers from text")
    return re.sub(r'\d{7,}', '', text)

def chunk_text(text, max_chars=99000):  # Set to 99000 to be safe
    logger.info(f"Chunking text of length {len(text)} characters")
    chunks = []
    current_chunk = ""
    sentences = sent_tokenize(text)
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) < max_chars:
            current_chunk += sentence + ' '
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence + ' '
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    logger.info(f"Created {len(chunks)} chunks")
    for i, chunk in enumerate(chunks):
        logger.debug(f"Chunk {i+1} length: {len(chunk)} characters")
    
    return chunks