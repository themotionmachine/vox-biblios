"""
Pocket TTS provider using local neural TTS.
"""
import os
import tempfile
from pathlib import Path
from typing import List, Optional

from vox_biblios.config import config
from vox_biblios.tts.base import TTSProvider, TTSResult
from vox_biblios.utils.audio import to_mp3, get_duration_seconds
from vox_biblios.utils.logging import get_logger
from vox_biblios.exceptions import SynthesisError, VoiceNotFoundError, ModelLoadError

logger = get_logger(__name__)

# Available Pocket TTS English voices
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

    # Pocket TTS chunks internally, but shorter passages keep memory flat
    # and limit the blast radius of a failed generation
    max_chunk_chars = 4000

    def __init__(self, voice: Optional[str] = None):
        """
        Initialize the Pocket TTS provider.

        Args:
            voice: Voice name (default from config, falls back to 'alba')
        """
        self._voice = voice or config.pocket_tts.voice
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

            model_config = config.pocket_tts.model
            logger.info(f"Loading Pocket TTS model ({model_config})...")
            self._model = TTSModel.load_model(language=model_config)
            logger.info("Pocket TTS model loaded successfully")

            logger.info(f"Loading voice '{self._voice}'...")
            self._voice_state = self._model.get_state_for_audio_prompt(self._voice)
            logger.info(f"Voice '{self._voice}' loaded successfully")

        except ImportError as e:
            raise ModelLoadError(
                "pocket-tts library not installed. Install with: pip install pocket-tts"
            ) from e
        except Exception as e:
            raise ModelLoadError(f"Failed to load Pocket TTS model: {e}") from e

    def synthesize(self, text: str, output_path: Path) -> TTSResult:
        """
        Synthesize text using Pocket TTS, writing an MP3.

        Args:
            text: The text to synthesize
            output_path: Where to write the MP3 file

        Returns:
            TTSResult with the local audio path

        Raises:
            SynthesisError: If synthesis fails
        """
        logger.info(f"Synthesizing with Pocket TTS (voice={self._voice})")

        self._load_model()

        wav_file = tempfile.mktemp(suffix='.wav')

        try:
            import scipy.io.wavfile

            logger.debug(f"Generating audio for text of length {len(text)}")
            audio = self._model.generate_audio(self._voice_state, text)

            scipy.io.wavfile.write(wav_file, self._model.sample_rate, audio.numpy())

            to_mp3(wav_file, output_path)

            return TTSResult(
                audio_path=Path(output_path),
                duration_seconds=get_duration_seconds(output_path),
                format="mp3",
                provider=self.name
            )

        except Exception as e:
            if not isinstance(e, (SynthesisError, ModelLoadError)):
                raise SynthesisError(f"Pocket TTS synthesis failed: {e}") from e
            raise

        finally:
            if os.path.exists(wav_file):
                os.remove(wav_file)

    def get_available_voices(self) -> List[str]:
        """
        Get list of available Pocket TTS voices.

        Returns:
            List of voice names
        """
        return POCKET_TTS_VOICES.copy()
