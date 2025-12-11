"""
Configuration management for Vox Biblios.
Loads configuration from environment variables with sensible defaults.
"""
import os
from dataclasses import dataclass
from typing import Optional
from pathlib import Path
import logging
from dotenv import load_dotenv

# Load environment variables from .env.local file
load_dotenv('.env.local')

@dataclass
class AWSConfig:
    """AWS configuration settings."""
    access_key: str
    secret_key: str
    region: str = "us-east-1"
    s3_bucket: str = "vox-biblios"
    polly_engine: str = "neural"
    polly_format: str = "mp3"
    polly_voice_id: str = "Joanna"
    polly_output_key_prefix: str = "audio"


@dataclass
class AppConfig:
    """Application configuration settings."""
    log_level: int = logging.INFO
    log_file: str = "vox_biblios.log"
    log_dir: str = "logs"
    chunk_size: int = 90000  # Character limit for Polly (reduced from 99000 for safety)
    preview_length: int = 100  # Number of characters to include in the description preview
    rss_filename: str = "voxbiblios.rss"
    podcast_name: str = "Vox Biblios"
    podcast_description: str = "I speak with the voices of all the words I've seen."
    podcast_website: str = "example.org"
    podcast_explicit: bool = False
    podcast_image: Optional[str] = None 


class Config:
    """Main configuration class."""
    aws: AWSConfig
    app: AppConfig
    
    def __init__(self):
        """Initialize configuration from environment variables."""
        # Validate required environment variables
        aws_access_key = os.environ.get("AWS_ACCESS_KEY")
        aws_secret_key = os.environ.get("AWS_SECRET_KEY")
        
        if not aws_access_key or not aws_secret_key:
            raise ValueError("AWS_ACCESS_KEY and AWS_SECRET_KEY environment variables must be set")
        
        # Initialize AWS configuration
        self.aws = AWSConfig(
            access_key=aws_access_key,
            secret_key=aws_secret_key,
            region=os.environ.get("AWS_REGION", "us-east-1"),
            s3_bucket=os.environ.get("S3_BUCKET", "vox-biblios"),
            polly_engine=os.environ.get("POLLY_ENGINE", "neural"),
            polly_format=os.environ.get("POLLY_FORMAT", "mp3"),
            polly_voice_id=os.environ.get("POLLY_VOICE_ID", "Joanna"),
            polly_output_key_prefix=os.environ.get("POLLY_KEY_PREFIX", "audio")
        )
        
        # Initialize application configuration
        log_level_name = os.environ.get("LOG_LEVEL", "INFO")
        log_level = getattr(logging, log_level_name.upper(), logging.INFO)
        
        self.app = AppConfig(
            log_level=log_level,
            log_file=os.environ.get("LOG_FILE", "vox_biblios.log"),
            log_dir=os.environ.get("LOG_DIR", "logs"),
            chunk_size=int(os.environ.get("CHUNK_SIZE", "90000")),
            preview_length=int(os.environ.get("PREVIEW_LENGTH", "100")),
            rss_filename=os.environ.get("RSS_FILENAME", "voxbiblios.rss"),
            podcast_name=os.environ.get("PODCAST_NAME", "Vox Biblios"),
            podcast_description=os.environ.get("PODCAST_DESCRIPTION", 
                                               "I speak with the voices of all the words I've seen."),
            podcast_website=os.environ.get("PODCAST_WEBSITE", "vox-biblios.example.com"),
            podcast_explicit=os.environ.get("PODCAST_EXPLICIT", "").lower() == "true",
            podcast_image=os.environ.get("PODCAST_IMAGE")
        )
    
    @property
    def get_rss_url(self) -> str:
        """Get the full URL for the RSS feed."""
        return f"https://s3.{self.aws.region}.amazonaws.com/{self.aws.s3_bucket}/{self.app.rss_filename}"


# Create a singleton configuration instance
config = Config()