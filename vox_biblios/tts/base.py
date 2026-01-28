"""
Base classes and types for TTS providers.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TTSResult:
    """Result from a TTS synthesis operation."""
    audio_url: str
    duration_seconds: Optional[float]
    format: str
    provider: str


class TTSProvider(ABC):
    """Abstract base class for TTS providers."""

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
    def synthesize(self, text: str, title: str) -> TTSResult:
        """
        Synthesize text to speech.

        Args:
            text: The text to synthesize
            title: A title/identifier for this synthesis (used for output filenames)

        Returns:
            TTSResult with the audio URL and metadata

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
