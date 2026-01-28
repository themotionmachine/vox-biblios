"""
TTS (Text-to-Speech) module for Vox Biblios.

Provides a unified interface for multiple TTS backends:
- pocket-tts: Local neural TTS using Pocket TTS library (default)
- polly: AWS Polly cloud TTS service
- say: macOS built-in speech synthesis
"""
from vox_biblios.tts.base import TTSProvider, TTSResult
from vox_biblios.tts.factory import create_provider, get_available_providers

__all__ = [
    "TTSProvider",
    "TTSResult",
    "create_provider",
    "get_available_providers",
]
