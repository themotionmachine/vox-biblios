"""
AWS Polly TTS provider.
"""
from typing import List, Optional

from vox_biblios.tts.base import TTSProvider, TTSResult
from vox_biblios.aws.polly import PollyService
from vox_biblios.config import config
from vox_biblios.utils.logging import get_logger
from vox_biblios.exceptions import SynthesisError, PollyError

logger = get_logger(__name__)

# Common English Polly neural voices
POLLY_VOICES = [
    "Joanna",
    "Matthew",
    "Kendra",
    "Kimberly",
    "Salli",
    "Joey",
    "Justin",
    "Kevin",
    "Ivy",
    "Ruth",
    "Stephen",
    "Danielle",
    "Gregory",
]


class PollyProvider(TTSProvider):
    """TTS provider using AWS Polly."""

    def __init__(self, voice: Optional[str] = None):
        """
        Initialize the Polly provider.

        Args:
            voice: Optional voice ID (default from config)
        """
        self._voice = voice or config.aws.polly_voice_id
        self._polly_service = PollyService(voice_id=self._voice)

        logger.debug(f"Initialized PollyProvider with voice={self._voice}")

    @property
    def name(self) -> str:
        return "polly"

    @property
    def supports_voices(self) -> bool:
        return True

    def synthesize(self, text: str, title: str) -> TTSResult:
        """
        Synthesize text using AWS Polly.

        Args:
            text: The text to synthesize
            title: A title for this synthesis (unused, Polly auto-generates)

        Returns:
            TTSResult with the S3 audio URL

        Raises:
            SynthesisError: If synthesis fails
        """
        logger.info(f"Synthesizing with Polly (voice={self._voice})")

        try:
            response = self._polly_service.synthesize_speech(text)

            if not response:
                raise SynthesisError("Polly returned empty response")

            # Extract URL from Polly response format
            output_uri = response['SynthesisTask']['OutputUri']

            return TTSResult(
                audio_url=output_uri,
                duration_seconds=None,
                format=config.aws.polly_format,
                provider=self.name
            )

        except PollyError as e:
            raise SynthesisError(f"Polly synthesis failed: {e}") from e
        except KeyError as e:
            raise SynthesisError(f"Unexpected Polly response format: {e}") from e

    def get_available_voices(self) -> List[str]:
        """
        Get list of common Polly neural voices.

        Returns:
            List of voice IDs
        """
        return POLLY_VOICES

    def validate_voice(self, voice: str) -> bool:
        """
        Validate a Polly voice.

        Note: This is a loose validation - Polly has many voices.
        Invalid voices will fail at synthesis time.

        Args:
            voice: The voice ID to validate

        Returns:
            True (we allow any voice, Polly will validate)
        """
        return True
