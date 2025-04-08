"""
Advanced logging configuration for Vox Biblios.
"""
import os
import logging
from logging.handlers import RotatingFileHandler
import sys
from functools import lru_cache
from typing import Optional
from pathlib import Path

from vox_biblios.config import config


class LogFormatter(logging.Formatter):
    """Custom log formatter with color support for console output."""
    
    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    
    FORMATS = {
        logging.DEBUG: f"{grey}%(asctime)s - %(name)s - %(levelname)s - %(message)s{reset}",
        logging.INFO: "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        logging.WARNING: f"{yellow}%(asctime)s - %(name)s - %(levelname)s - %(message)s{reset}",
        logging.ERROR: f"{red}%(asctime)s - %(name)s - %(levelname)s - %(message)s{reset}",
        logging.CRITICAL: f"{bold_red}%(asctime)s - %(name)s - %(levelname)s - %(message)s{reset}"
    }
    
    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


@lru_cache(maxsize=32)
def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger instance.
    
    Args:
        name: The name of the logger (typically __name__)
        
    Returns:
        A configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Set the root logger level
    logger.setLevel(config.app.log_level)
    
    # Only configure handlers if they haven't been added yet
    if not logger.handlers:
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(LogFormatter())
        logger.addHandler(console_handler)
        
        # File handler
        log_dir = Path(config.app.log_dir)
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / config.app.log_file
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5
        )
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        logger.addHandler(file_handler)
    
    return logger


# Initialize the root logger
root_logger = get_logger("vox_biblios")


class SoundWaveAnimation:
    """Sound wave animation for the console during processing."""
    
    def __init__(self):
        self.frames = [
            "▁▂▃▄▅▆▇█▇▆▅▄▃▂▁",
            "▂▃▄▅▆▇█▇▆▅▄▃▂▁▂",
            "▃▄▅▆▇█▇▆▅▄▃▂▁▂▃",
            "▄▅▆▇█▇▆▅▄▃▂▁▂▃▄",
            "▅▆▇█▇▆▅▄▃▂▁▂▃▄▅",
            "▆▇█▇▆▅▄▃▂▁▂▃▄▅▆",
            "▇█▇▆▅▄▃▂▁▂▃▄▅▆▇",
            "█▇▆▅▄▃▂▁▂▃▄▅▆▇█"
        ]
        self._running = False
        self._thread = None
    
    def start(self):
        """Start the animation in a separate thread."""
        if not self._running and sys.stdout.isatty():
            import threading
            import itertools
            import time
            
            self._running = True
            
            def animate():
                for frame in itertools.cycle(self.frames):
                    if not self._running:
                        break
                    sys.stdout.write('\r')
                    sys.stdout.write(f"Vox Biblios Processing: {frame}")
                    sys.stdout.flush()
                    time.sleep(0.1)
                
                # Clear the animation line
                sys.stdout.write('\r')
                sys.stdout.write(' ' * 40)
                sys.stdout.write('\r')
                sys.stdout.flush()
            
            self._thread = threading.Thread(target=animate)
            self._thread.daemon = True
            self._thread.start()
    
    def stop(self):
        """Stop the animation."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.5)