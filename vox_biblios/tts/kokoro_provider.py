"""
Kokoro TTS provider using mlx-audio (Apple Silicon native).
"""
import os
import tempfile
from pathlib import Path
from typing import List, Optional

from vox_biblios.tts.base import TTSProvider, TTSResult
from vox_biblios.utils.audio import to_mp3, get_duration_seconds
from vox_biblios.utils.logging import get_logger
from vox_biblios.exceptions import SynthesisError, VoiceNotFoundError, ModelLoadError

logger = get_logger(__name__)

KOKORO_MODEL = "prince-canuma/Kokoro-82M"

# Kokoro voice naming: [a]merican/[b]ritish + [f]emale/[m]ale + name
KOKORO_VOICES = [
    "af_heart",   # Default voice
    "af_bella",
    "af_nicole",
    "af_nova",
    "af_sarah",
    "af_sky",
    "am_adam",
    "am_echo",
    "am_michael",
    "am_puck",
    "bf_alice",
    "bf_emma",
    "bf_isabella",
    "bf_lily",
    "bm_daniel",
    "bm_fable",
    "bm_george",
    "bm_lewis",
]


def _patch_mlx_audio_interpolate():
    """Work around mlx-audio 0.4.4 SineGen length bug (Blaizzy/mlx-audio#784).

    interpolate() uses math.ceil on N * (1/300), and float drift makes some
    audio lengths round up an extra frame, producing a (1,N,1) vs (1,N+300,9)
    broadcast error in the Kokoro vocoder. Rounding before ceil fixes it.
    Remove once the upstream fix (PR #785) is released.
    """
    import math
    import mlx_audio.tts.models.interpolate as interp_mod
    import mlx_audio.tts.models.kokoro.istftnet as istft_mod

    if getattr(interp_mod, "_vox_biblios_patched", False):
        return

    orig = interp_mod.interpolate

    def fixed(input, size=None, scale_factor=None, **kwargs):
        if size is None and scale_factor is not None:
            sf = scale_factor if isinstance(scale_factor, (list, tuple)) \
                else [scale_factor] * (input.ndim - 2)
            size = [
                max(1, math.ceil(round(input.shape[i + 2] * float(sf[i]), 6)))
                for i in range(input.ndim - 2)
            ]
            scale_factor = None
        return orig(input, size=size, scale_factor=scale_factor, **kwargs)

    interp_mod.interpolate = fixed
    interp_mod._vox_biblios_patched = True
    # istftnet binds interpolate at import time, so patch its reference too
    istft_mod.interpolate = fixed


class KokoroProvider(TTSProvider):
    """TTS provider using Kokoro-82M via MLX."""

    # Generation is split per sentence internally (see synthesize), so
    # chunks can be large; this mainly bounds memory per concatenation
    max_chunk_chars = 4000

    def __init__(self, voice: Optional[str] = None):
        """
        Initialize the Kokoro provider.

        Args:
            voice: Voice name (default: 'af_heart')
        """
        self._voice = voice or "af_heart"
        self._model = None  # Lazy-loaded

        if not self.validate_voice(self._voice):
            raise VoiceNotFoundError(
                f"Voice '{self._voice}' not found. Available voices: {', '.join(KOKORO_VOICES)}"
            )

        logger.debug(f"Initialized KokoroProvider with voice={self._voice}")

    @property
    def name(self) -> str:
        return "kokoro"

    @property
    def supports_voices(self) -> bool:
        return True

    def _load_model(self):
        if self._model is not None:
            return

        try:
            from mlx_audio.tts.utils import load_model
        except ImportError as e:
            raise ModelLoadError(
                "mlx-audio not installed. Install with: pip install 'vox-biblios[kokoro]' "
                "or: pip install mlx-audio"
            ) from e

        try:
            _patch_mlx_audio_interpolate()
        except Exception as e:
            logger.debug(f"Skipping mlx-audio interpolate patch: {e}")

        try:
            import contextlib
            import sys

            # misaki's G2P needs spacy's en_core_web_sm; its runtime
            # auto-download installs into the wrong environment under uv,
            # so fail fast with instructions instead
            import spacy.util
            if not spacy.util.is_package("en_core_web_sm"):
                raise ModelLoadError(
                    "spacy model 'en_core_web_sm' not installed. Reinstall with the "
                    "kokoro extra: pip install 'vox-biblios[kokoro]'"
                )

            logger.info(f"Loading Kokoro model ({KOKORO_MODEL})...")
            with contextlib.redirect_stdout(sys.stderr):
                self._model = load_model(KOKORO_MODEL)
            logger.info("Kokoro model loaded successfully")
        except ModelLoadError:
            raise
        except Exception as e:
            raise ModelLoadError(f"Failed to load Kokoro model: {e}") from e

    def synthesize(self, text: str, output_path: Path) -> TTSResult:
        """
        Synthesize text using Kokoro, writing an MP3.

        Args:
            text: The text to synthesize
            output_path: Where to write the MP3 file

        Returns:
            TTSResult with the local audio path

        Raises:
            SynthesisError: If synthesis fails
        """
        logger.info(f"Synthesizing with Kokoro (voice={self._voice})")
        self._load_model()

        wav_file = tempfile.mktemp(suffix='.wav')

        try:
            import contextlib
            import sys
            import numpy as np
            import scipy.io.wavfile
            from nltk.tokenize import sent_tokenize

            segments = []
            sample_rate = 24000
            # Generate one sentence at a time: mlx_audio's Kokoro vocoder
            # crashes with a broadcast_shapes error when a single generation
            # exceeds roughly 20s of audio. Also keep stdout clean for --json
            # (mlx_audio prints status lines to stdout).
            with contextlib.redirect_stdout(sys.stderr):
                for sentence in sent_tokenize(text):
                    for result in self._model.generate(text=sentence, voice=self._voice, speed=1.0):
                        segments.append(np.asarray(result.audio, dtype=np.float32))
                        sample_rate = getattr(result, 'sample_rate', sample_rate)

            if not segments:
                raise SynthesisError("Kokoro generated no audio")

            audio = np.concatenate(segments)
            scipy.io.wavfile.write(wav_file, sample_rate, audio)

            to_mp3(wav_file, output_path)

            return TTSResult(
                audio_path=Path(output_path),
                duration_seconds=get_duration_seconds(output_path),
                format="mp3",
                provider=self.name
            )

        except Exception as e:
            if not isinstance(e, (SynthesisError, ModelLoadError)):
                raise SynthesisError(f"Kokoro synthesis failed: {e}") from e
            raise

        finally:
            if os.path.exists(wav_file):
                os.remove(wav_file)

    def get_available_voices(self) -> List[str]:
        """
        Get list of available Kokoro voices.

        Returns:
            List of voice names
        """
        return KOKORO_VOICES.copy()
