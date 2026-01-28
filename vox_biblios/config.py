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

# Configuration file search strategy:
# 1. Current working directory (.env.local) - for project-based usage
# 2. XDG config directory (~/.config/vox-biblios/config.env) - standard location
# 3. Home directory (~/.vox-biblios.env) - fallback location
# 4. Environment variables already set (no .env file needed)

def load_configuration():
    """Load configuration from multiple possible locations."""
    config_sources = []

    # Location 1: Current working directory (for development/project use)
    cwd_config = Path.cwd() / '.env.local'
    if cwd_config.exists():
        load_dotenv(cwd_config)
        config_sources.append(str(cwd_config))

    # Location 2: XDG config directory (standard for Linux/Unix)
    xdg_config_home = os.getenv('XDG_CONFIG_HOME',
                                 os.path.expanduser('~/.config'))
    xdg_config = Path(xdg_config_home) / 'vox-biblios' / 'config.env'
    if xdg_config.exists():
        load_dotenv(xdg_config)
        config_sources.append(str(xdg_config))

    # Location 3: Home directory (macOS/Windows friendly)
    home_config = Path.home() / '.vox-biblios.env'
    if home_config.exists():
        load_dotenv(home_config)
        config_sources.append(str(home_config))

    # Location 4: Environment variables already set (no action needed)
    # This is checked in Config.__init__ by accessing os.environ

    return config_sources

# Load configuration from discovered locations
# Note: load_dotenv won't override already-set environment variables
_config_sources = load_configuration()

def get_config_sources():
    """Get list of configuration files that were loaded."""
    return _config_sources

@dataclass
class AWSConfig:
    """AWS configuration settings."""
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    region: str = "us-east-1"
    s3_bucket: str = "vox-biblios"
    polly_engine: str = "neural"
    polly_format: str = "mp3"
    polly_voice_id: str = "Joanna"
    polly_output_key_prefix: str = "audio"

    def validate(self):
        """Validate that required AWS credentials are set."""
        if not self.access_key or not self.secret_key:
            raise ValueError("AWS_ACCESS_KEY and AWS_SECRET_KEY environment variables must be set")


@dataclass
class PocketTTSConfig:
    """Pocket TTS configuration settings."""
    voice: str = "alba"


@dataclass
class TTSConfig:
    """TTS provider configuration settings."""
    default_provider: str = "pocket-tts"
    default_voice: Optional[str] = None  # None means use provider default


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
    tts: TTSConfig
    pocket_tts: PocketTTSConfig

    def __init__(self):
        """Initialize configuration from environment variables."""
        # Load AWS credentials (optional during init, validated when used)
        aws_access_key = os.environ.get("AWS_ACCESS_KEY")
        aws_secret_key = os.environ.get("AWS_SECRET_KEY")

        # Initialize AWS configuration (credentials are optional for non-AWS commands)
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

        # Initialize TTS configuration
        self.tts = TTSConfig(
            default_provider=os.environ.get("TTS_PROVIDER", "pocket-tts"),
            default_voice=os.environ.get("TTS_VOICE") or None
        )

        # Initialize Pocket TTS configuration
        self.pocket_tts = PocketTTSConfig(
            voice=os.environ.get("POCKET_TTS_VOICE", "alba")
        )
    
    @property
    def get_rss_url(self) -> str:
        """Get the full URL for the RSS feed."""
        return f"https://s3.{self.aws.region}.amazonaws.com/{self.aws.s3_bucket}/{self.app.rss_filename}"


# Lazy-loaded singleton configuration instance
_config_instance = None

def get_config() -> Config:
    """
    Get the singleton configuration instance.
    Lazily initializes on first access.
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance

# For backward compatibility, create a property-like object
class ConfigProxy:
    """Proxy object that lazily loads config on attribute access."""
    def __getattr__(self, name):
        return getattr(get_config(), name)

config = ConfigProxy()