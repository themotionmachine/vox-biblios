"""
macOS 'say' command TTS provider.
"""
import os
import subprocess
import tempfile
from typing import List, Optional

from vox_biblios.tts.base import TTSProvider, TTSResult
from vox_biblios.aws.s3 import S3Service
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
        self._s3_service = S3Service()

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

    def synthesize(self, text: str, title: str) -> TTSResult:
        """
        Synthesize text using macOS 'say' command.

        Args:
            text: The text to synthesize
            title: A title for this synthesis (used for temp files)

        Returns:
            TTSResult with the uploaded audio URL

        Raises:
            SynthesisError: If synthesis fails
        """
        logger.info(f"Synthesizing with 'say' (voice={self._voice})")

        # Create temp files
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp_in:
            tmp_in.write(text)
            input_file = tmp_in.name

        aiff_file = input_file.replace('.txt', '.aiff')
        m4a_file = input_file.replace('.txt', '.m4a')

        try:
            # Build say command
            cmd = ['say', '-f', input_file, '-o', aiff_file]
            if self._voice:
                cmd.extend(['-v', self._voice])

            # Run say command
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode != 0:
                raise SynthesisError(f"'say' command failed: {result.stderr.decode()}")

            # Convert AIFF to M4A
            af_cmd = ['afconvert', '-f', 'm4af', '-d', 'aac', '-o', m4a_file, aiff_file]
            af_result = subprocess.run(af_cmd, capture_output=True)
            if af_result.returncode != 0:
                raise SynthesisError(f"Audio conversion failed: {af_result.stderr.decode()}")

            # Upload to S3
            uploaded_url = self._s3_service.upload_file(m4a_file)

            return TTSResult(
                audio_url=uploaded_url,
                duration_seconds=None,  # Could calculate from audio file if needed
                format="m4a",
                provider=self.name
            )

        except Exception as e:
            if not isinstance(e, SynthesisError):
                raise SynthesisError(f"Synthesis failed: {e}") from e
            raise

        finally:
            # Cleanup temp files
            for f in [input_file, aiff_file, m4a_file]:
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
                    # Voice name is the first part before multiple spaces
                    parts = line.split()
                    if parts:
                        voice_name = parts[0]
                        voices.append(voice_name)

            return voices

        except Exception as e:
            logger.warning(f"Error getting voice list: {e}")
            return []
