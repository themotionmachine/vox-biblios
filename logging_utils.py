import logging
from logging.handlers import RotatingFileHandler
import os

def setup_logging(log_file='vox_biblios.log', console_level=logging.INFO, file_level=logging.DEBUG):
    # Create logs directory if it doesn't exist
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_file_path = os.path.join(log_dir, log_file)

    # Create a logger
    logger = logging.getLogger('vox_biblios')
    logger.setLevel(logging.DEBUG)

    # Create handlers
    console_handler = logging.StreamHandler()
    file_handler = RotatingFileHandler(log_file_path, maxBytes=10485760, backupCount=5)  # 10MB per file, max 5 files

    # Set logging levels for handlers
    console_handler.setLevel(console_level)
    file_handler.setLevel(file_level)

    # Create formatters and add it to handlers
    format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    console_format = logging.Formatter(format_string)
    file_format = logging.Formatter(format_string)
    console_handler.setFormatter(console_format)
    file_handler.setFormatter(file_format)

    # Add handlers to the logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger

# Create a global logger instance
logger = setup_logging()