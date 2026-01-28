"""
Custom exceptions for Vox Biblios.
"""

class VoxBibliosError(Exception):
    """Base exception for all Vox Biblios errors."""
    pass


class ConfigError(VoxBibliosError):
    """Exception raised for configuration errors."""
    pass


class AWSError(VoxBibliosError):
    """Base exception for AWS-related errors."""
    pass


class S3Error(AWSError):
    """Exception raised for S3-related errors."""
    pass


class PollyError(AWSError):
    """Exception raised for Polly-related errors."""
    pass


class CostEstimationError(AWSError):
    """Exception raised for Cost Explorer-related errors."""
    pass


class RSSError(VoxBibliosError):
    """Exception raised for RSS-related errors."""
    pass


class TextProcessingError(VoxBibliosError):
    """Exception raised for text processing errors."""
    pass


class WebScraperError(VoxBibliosError):
    """Exception raised for web scraping errors."""
    pass


class PodcastManagerError(VoxBibliosError):
    """Exception raised for podcast manager errors."""
    pass


class TTSError(VoxBibliosError):
    """Base exception for TTS-related errors."""
    pass


class ProviderNotFoundError(TTSError):
    """Exception raised when a TTS provider is not found."""
    pass


class VoiceNotFoundError(TTSError):
    """Exception raised when a voice is not found for a provider."""
    pass


class ModelLoadError(TTSError):
    """Exception raised when a TTS model fails to load."""
    pass


class SynthesisError(TTSError):
    """Exception raised when speech synthesis fails."""
    pass