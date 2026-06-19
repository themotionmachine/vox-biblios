"""
Test doubles registered into the real TTS factory.

``FakeTTSProvider`` is a hermetic stand-in for a real backend: it writes a tiny
stub MP3 to the requested path instead of calling macOS ``say``, AWS Polly, or
any neural model. It is referenced by module path from ``PROVIDER_REGISTRY`` so
the golden contract test drives the *real* ``create_provider`` / argparse path
(``--provider fake``) rather than monkeypatching the factory away.
"""
from pathlib import Path
from typing import List, Optional

from vox_biblios.tts.base import TTSProvider, TTSResult

# A minimal, non-empty payload so episode files are real files on disk (the
# poller asserts ``episodes[0]["url"]`` exists). Not valid MP3 frames — nothing
# on the test path decodes audio, since concat_audio is stubbed too.
STUB_AUDIO_BYTES = b"FAKE-MP3\x00stub-audio-for-tests\n"


class FakeTTSProvider(TTSProvider):
    """Deterministic, dependency-free TTS provider for tests."""

    def __init__(self, voice: Optional[str] = None):
        self._voice = voice

    @property
    def name(self) -> str:
        return "fake"

    @property
    def supports_voices(self) -> bool:
        return True

    def synthesize(self, text: str, output_path: Path) -> TTSResult:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(STUB_AUDIO_BYTES)
        return TTSResult(
            audio_path=output_path,
            duration_seconds=1.0,
            format="mp3",
            provider=self.name,
        )

    def get_available_voices(self) -> List[str]:
        return ["fake-voice-a", "fake-voice-b"]
