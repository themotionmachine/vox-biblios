"""
macOS 'say' command TTS provider.
"""
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from vox_biblios.tts.base import TTSProvider, TTSResult
from vox_biblios.utils.audio import to_mp3, get_duration_seconds
from vox_biblios.utils.logging import get_logger
from vox_biblios.exceptions import SynthesisError, VoiceNotFoundError

logger = get_logger(__name__)


class SayProvider(TTSProvider):
    """TTS provider using macOS 'say' command."""

    def __init__(self, voice: Optional[str] = None):
        """
        Initialize the Say provider.

        Args:
            voice: Optional voice name (default: system default)
        """
        self._voice = voice

        if voice and not self.validate_voice(voice):
            raise VoiceNotFoundError(
                f"Voice '{voice}' not found. Available voices: {', '.join(self.get_available_voices())}"
            )

        logger.debug(f"Initialized SayProvider with voice={voice}")

    @property
    def name(self) -> str:
        return "say"

    @property
    def supports_voices(self) -> bool:
        return True

    def synthesize(self, text: str, output_path: Path) -> TTSResult:
        """
        Synthesize text using macOS 'say' command, writing an MP3.

        Args:
            text: The text to synthesize
            output_path: Where to write the MP3 file

        Returns:
            TTSResult with the local audio path

        Raises:
            SynthesisError: If synthesis fails
        """
        logger.info(f"Synthesizing with 'say' (voice={self._voice})")

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp_in:
            tmp_in.write(text)
            input_file = tmp_in.name

        aiff_file = input_file.replace('.txt', '.aiff')

        try:
            cmd = ['say', '-f', input_file, '-o', aiff_file]
            if self._voice:
                cmd.extend(['-v', self._voice])

            result = subprocess.run(cmd, capture_output=True)
            if result.returncode != 0:
                raise SynthesisError(f"'say' command failed: {result.stderr.decode()}")

            to_mp3(aiff_file, output_path)

            return TTSResult(
                audio_path=Path(output_path),
                duration_seconds=get_duration_seconds(output_path),
                format="mp3",
                provider=self.name
            )

        except Exception as e:
            if not isinstance(e, SynthesisError):
                raise SynthesisError(f"Synthesis failed: {e}") from e
            raise

        finally:
            for f in [input_file, aiff_file]:
                if os.path.exists(f):
                    os.remove(f)

    def get_available_voices(self) -> List[str]:
        """
        Get list of available voices from 'say -v ?'.

        Returns:
            List of voice names
        """
        try:
            result = subprocess.run(['say', '-v', '?'], capture_output=True, text=True)
            if result.returncode != 0:
                logger.warning("Failed to get voice list from 'say'")
                return []

            voices = []
            for line in result.stdout.strip().split('\n'):
                # Format: "Voice Name    language_code  # description"
                if line.strip():
                    parts = line.split()
                    if parts:
                        voices.append(parts[0])

            return voices

        except Exception as e:
            logger.warning(f"Error getting voice list: {e}")
            return []
