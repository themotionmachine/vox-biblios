"""
Pocket TTS provider using local neural TTS.
"""
import os
import subprocess
import tempfile
from typing import List, Optional

from vox_biblios.tts.base import TTSProvider, TTSResult
from vox_biblios.aws.s3 import S3Service
from vox_biblios.utils.logging import get_logger
from vox_biblios.exceptions import SynthesisError, VoiceNotFoundError, ModelLoadError

logger = get_logger(__name__)

# Available Pocket TTS voices
POCKET_TTS_VOICES = [
    "alba",      # Default voice
    "marius",
    "javert",
    "jean",
    "fantine",
    "cosette",
    "eponine",
    "azelma",
]


class PocketTTSProvider(TTSProvider):
    """TTS provider using Pocket TTS local neural synthesis."""

    def __init__(self, voice: Optional[str] = None):
        """
        Initialize the Pocket TTS provider.

        Args:
            voice: Voice name (default: 'alba')
        """
        self._voice = voice or "alba"
        self._s3_service = S3Service()
        self._model = None  # Lazy-loaded
        self._voice_state = None  # Lazy-loaded

        if not self.validate_voice(self._voice):
            raise VoiceNotFoundError(
                f"Voice '{self._voice}' not found. Available voices: {', '.join(POCKET_TTS_VOICES)}"
            )

        logger.debug(f"Initialized PocketTTSProvider with voice={self._voice}")

    @property
    def name(self) -> str:
        return "pocket-tts"

    @property
    def supports_voices(self) -> bool:
        return True

    def _load_model(self):
        """Lazy-load the TTS model and voice state."""
        if self._model is not None:
            return

        try:
            from pocket_tts import TTSModel

            logger.info("Loading Pocket TTS model...")
            self._model = TTSModel.load_model()
            logger.info("Pocket TTS model loaded successfully")

            logger.info(f"Loading voice '{self._voice}'...")
            # Pass the voice name as a string - the model handles predefined voices internally
            self._voice_state = self._model.get_state_for_audio_prompt(self._voice)
            logger.info(f"Voice '{self._voice}' loaded successfully")

        except ImportError as e:
            raise ModelLoadError(
                "pocket-tts library not installed. Install with: pip install pocket-tts"
            ) from e
        except Exception as e:
            raise ModelLoadError(f"Failed to load Pocket TTS model: {e}") from e

    def synthesize(self, text: str, title: str) -> TTSResult:
        """
        Synthesize text using Pocket TTS.

        Args:
            text: The text to synthesize
            title: A title for this synthesis (used in filename)

        Returns:
            TTSResult with the uploaded audio URL

        Raises:
            SynthesisError: If synthesis fails
        """
        logger.info(f"Synthesizing with Pocket TTS (voice={self._voice})")

        # Lazy-load model
        self._load_model()

        # Create temp files
        wav_file = tempfile.mktemp(suffix='.wav')
        mp3_file = tempfile.mktemp(suffix='.mp3')

        try:
            import scipy.io.wavfile

            # Generate audio
            logger.debug(f"Generating audio for text of length {len(text)}")
            audio = self._model.generate_audio(self._voice_state, text)

            # Save WAV file
            scipy.io.wavfile.write(wav_file, self._model.sample_rate, audio.numpy())

            if not os.path.exists(wav_file):
                raise SynthesisError("Pocket TTS did not generate audio file")

            # Convert WAV to MP3 using ffmpeg
            ffmpeg_cmd = [
                'ffmpeg', '-y',  # Overwrite output
                '-i', wav_file,
                '-acodec', 'libmp3lame',
                '-ab', '128k',
                '-ar', '22050',
                mp3_file
            ]

            result = subprocess.run(ffmpeg_cmd, capture_output=True)
            if result.returncode != 0:
                raise SynthesisError(f"FFmpeg conversion failed: {result.stderr.decode()}")

            # Upload to S3
            uploaded_url = self._s3_service.upload_file(mp3_file)

            return TTSResult(
                audio_url=uploaded_url,
                duration_seconds=None,  # Could calculate from audio if needed
                format="mp3",
                provider=self.name
            )

        except Exception as e:
            if not isinstance(e, (SynthesisError, ModelLoadError)):
                raise SynthesisError(f"Pocket TTS synthesis failed: {e}") from e
            raise

        finally:
            # Cleanup temp files
            for f in [wav_file, mp3_file]:
                if os.path.exists(f):
                    os.remove(f)

    def get_available_voices(self) -> List[str]:
        """
        Get list of available Pocket TTS voices.

        Returns:
            List of voice names
        """
        return POCKET_TTS_VOICES.copy()
