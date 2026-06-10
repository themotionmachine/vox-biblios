"""
AWS Polly TTS provider.
"""
import os
import tempfile
from pathlib import Path
from typing import List, Optional

from vox_biblios.tts.base import TTSProvider, TTSResult
from vox_biblios.aws.polly import PollyService
from vox_biblios.config import config
from vox_biblios.utils.audio import to_mp3, get_duration_seconds
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
    """TTS provider using AWS Polly's synchronous API."""

    # Sync SynthesizeSpeech allows 3000 billed chars; leave headroom
    max_chunk_chars = 2800

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

    def synthesize(self, text: str, output_path: Path) -> TTSResult:
        """
        Synthesize text using AWS Polly, writing an MP3.

        Args:
            text: The text to synthesize
            output_path: Where to write the MP3 file

        Returns:
            TTSResult with the local audio path

        Raises:
            SynthesisError: If synthesis fails
        """
        logger.info(f"Synthesizing with Polly (voice={self._voice})")

        try:
            audio_bytes = self._polly_service.synthesize_speech(text)
            if not audio_bytes:
                raise SynthesisError("Polly returned empty audio")

            if config.aws.polly_format == "mp3":
                Path(output_path).write_bytes(audio_bytes)
            else:
                # Re-encode non-mp3 formats so episodes stay uniform
                raw_file = tempfile.mktemp(suffix=f'.{config.aws.polly_format}')
                try:
                    Path(raw_file).write_bytes(audio_bytes)
                    to_mp3(raw_file, output_path)
                finally:
                    if os.path.exists(raw_file):
                        os.remove(raw_file)

            return TTSResult(
                audio_path=Path(output_path),
                duration_seconds=get_duration_seconds(output_path),
                format="mp3",
                provider=self.name
            )

        except PollyError as e:
            raise SynthesisError(f"Polly synthesis failed: {e}") from e

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
