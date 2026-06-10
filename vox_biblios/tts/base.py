"""
Base classes and types for TTS providers.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class TTSResult:
    """Result from a TTS synthesis operation."""
    audio_path: Path
    duration_seconds: Optional[float]
    format: str
    provider: str


class TTSProvider(ABC):
    """Abstract base class for TTS providers.

    Providers synthesize text to a local audio file. Uploading, RSS
    management, and chunk concatenation are the caller's responsibility.
    """

    # Largest text a single synthesize() call handles well. The manager
    # chunks longer texts and concatenates the resulting audio.
    max_chunk_chars: int = 90000

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider name."""
        pass

    @property
    @abstractmethod
    def supports_voices(self) -> bool:
        """Return whether this provider supports multiple voices."""
        pass

    @abstractmethod
    def synthesize(self, text: str, output_path: Path) -> TTSResult:
        """
        Synthesize text to speech, writing an MP3 to output_path.

        Args:
            text: The text to synthesize
            output_path: Where to write the MP3 file

        Returns:
            TTSResult with the local audio path and metadata

        Raises:
            SynthesisError: If synthesis fails
        """
        pass

    @abstractmethod
    def get_available_voices(self) -> List[str]:
        """
        Get list of available voices for this provider.

        Returns:
            List of voice names/identifiers
        """
        pass

    def validate_voice(self, voice: str) -> bool:
        """
        Validate that a voice is available for this provider.

        Args:
            voice: The voice name to validate

        Returns:
            True if the voice is valid, False otherwise
        """
        return voice in self.get_available_voices()
