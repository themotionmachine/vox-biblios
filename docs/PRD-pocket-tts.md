# PRD: Pocket TTS Integration for Vox Biblios

**Version**: 1.0
**Date**: 2026-01-16
**Author**: Engineering
**Status**: Draft

---

## 1. Executive Summary

This PRD outlines the integration of [Pocket TTS](https://github.com/kyutai-labs/pocket-tts) as the default text-to-speech provider for Vox Biblios. Pocket TTS is a lightweight, CPU-optimized TTS model that runs ~6x faster than real-time without requiring cloud services or GPU hardware. This integration will provide users with high-quality, zero-cost speech synthesis while maintaining backward compatibility with existing AWS Polly and macOS `say` providers.

### Key Outcomes
- **Default TTS provider** changes from AWS Polly to Pocket TTS
- **Zero cloud costs** for default usage (no AWS account required)
- **Formal TTS provider interface** enabling clean extensibility
- **Three provider options**: Pocket TTS (default), AWS Polly (cloud), macOS say (fallback)

---

## 2. Background & Motivation

### Current State
Vox Biblios currently supports two TTS providers:
1. **AWS Polly** (default): High-quality neural TTS requiring AWS credentials and incurring per-character costs
2. **macOS `say`** (local): Zero-cost but lower quality, macOS-only, requires `--use-local-speech` flag

### Problems with Current Approach
1. **Barrier to entry**: New users must set up AWS credentials before generating their first podcast
2. **Ongoing costs**: AWS Polly charges ~$16/million characters for neural voices
3. **Platform lock-in**: Local alternative only works on macOS
4. **Architecture limitations**: Conditional branching pattern makes adding providers difficult

### Why Pocket TTS
| Feature | Pocket TTS | AWS Polly | macOS say |
|---------|-----------|-----------|-----------|
| Cost | Free | ~$16/M chars | Free |
| Quality | High (100M params) | High (neural) | Medium |
| Platform | Cross-platform | Cross-platform | macOS only |
| Latency | ~200ms first chunk | Variable (async) | Low |
| Speed | 6x real-time (CPU) | N/A (cloud) | 1x real-time |
| Offline | Yes | No | Yes |
| Setup | `pip install` | AWS credentials | None |

---

## 3. Goals & Non-Goals

### Goals
1. Integrate Pocket TTS as the default TTS provider
2. Create a formal `TTSProvider` abstract interface for all providers
3. Implement provider selection via `--provider` CLI flag
4. Maintain full backward compatibility with existing workflows
5. Support all 8 Pocket TTS voices with `alba` as default
6. Handle model download/caching transparently

### Non-Goals
1. Streaming audio output (batch processing is sufficient for podcast generation)
2. Voice cloning capabilities (future consideration)
3. Multi-language support (Pocket TTS is English-only)
4. Real-time TTS (not needed for podcast workflow)
5. GPU acceleration (CPU performance is sufficient)

---

## 4. Technical Design

### 4.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI Layer                                │
│  vox-biblios process [--provider {pocket-tts,polly,say}] path   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      PodcastManager                              │
│  - Receives provider name from CLI                               │
│  - Creates appropriate TTSProvider instance via factory          │
│  - Delegates synthesis to provider                               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    TTSProviderFactory                            │
│  create(provider_name: str) -> TTSProvider                       │
└─────────────────────────────────────────────────────────────────┘
                                │
                ┌───────────────┼───────────────┐
                ▼               ▼               ▼
┌───────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  PocketTTSProvider│ │  PollyProvider  │ │  SayProvider    │
│  (default)        │ │  (cloud)        │ │  (macOS)        │
└───────────────────┘ └─────────────────┘ └─────────────────┘
                │               │               │
                └───────────────┴───────────────┘
                                │
                                ▼
                    ┌───────────────────┐
                    │    S3Service      │
                    │  (upload audio)   │
                    └───────────────────┘
```

### 4.2 TTSProvider Interface

```python
# vox_biblios/tts/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from pathlib import Path


@dataclass
class TTSResult:
    """Standardized result from TTS synthesis."""
    audio_url: str              # S3 URL of uploaded audio
    duration_seconds: float     # Audio duration (for RSS feed)
    format: str                 # Audio format (mp3, m4a, etc.)
    provider: str               # Provider name for logging


class TTSProvider(ABC):
    """Abstract base class for TTS providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g., 'pocket-tts', 'polly', 'say')."""
        pass

    @property
    @abstractmethod
    def supports_voices(self) -> bool:
        """Whether provider supports multiple voices."""
        pass

    @abstractmethod
    def synthesize(self, text: str, voice: Optional[str] = None) -> TTSResult:
        """
        Convert text to speech and upload to S3.

        Args:
            text: Text to synthesize (may be chunked by caller)
            voice: Optional voice override

        Returns:
            TTSResult with audio URL and metadata

        Raises:
            TTSError: On synthesis or upload failure
        """
        pass

    @abstractmethod
    def get_available_voices(self) -> list[str]:
        """Return list of available voice identifiers."""
        pass

    def validate_voice(self, voice: str) -> bool:
        """Check if voice is valid for this provider."""
        return voice in self.get_available_voices()
```

### 4.3 PocketTTSProvider Implementation

```python
# vox_biblios/tts/pocket_tts_provider.py

import tempfile
from pathlib import Path
from typing import Optional
import subprocess

from pocket_tts import TTSModel

from .base import TTSProvider, TTSResult
from ..aws.s3 import S3Service
from ..config import config
from ..utils.logging import get_logger
from ..exceptions import TTSError

logger = get_logger(__name__)


class PocketTTSProvider(TTSProvider):
    """Pocket TTS provider using local AI model."""

    VOICES = ['alba', 'marius', 'javert', 'jean', 'fantine', 'cosette', 'eponine', 'azelma']
    DEFAULT_VOICE = 'alba'

    def __init__(self, voice: Optional[str] = None):
        self._voice = voice or config.pocket_tts.voice or self.DEFAULT_VOICE
        self._model: Optional[TTSModel] = None
        self._voice_states: dict = {}
        self._s3_service = S3Service()

        if not self.validate_voice(self._voice):
            raise TTSError(f"Invalid Pocket TTS voice: {self._voice}. "
                          f"Available: {', '.join(self.VOICES)}")

    @property
    def name(self) -> str:
        return 'pocket-tts'

    @property
    def supports_voices(self) -> bool:
        return True

    @property
    def model(self) -> TTSModel:
        """Lazy-load the TTS model on first use."""
        if self._model is None:
            logger.info("Loading Pocket TTS model (first use)...")
            self._model = TTSModel.load_model()
            logger.info("Pocket TTS model loaded successfully")
        return self._model

    def _get_voice_state(self, voice: str):
        """Get or create voice state for the specified voice."""
        if voice not in self._voice_states:
            voice_url = f"hf://kyutai/tts-voices/{voice}/casual.wav"
            self._voice_states[voice] = self.model.get_state_for_audio_prompt(voice_url)
        return self._voice_states[voice]

    def synthesize(self, text: str, voice: Optional[str] = None) -> TTSResult:
        """Generate speech using Pocket TTS and upload to S3."""
        voice = voice or self._voice

        if not self.validate_voice(voice):
            raise TTSError(f"Invalid voice: {voice}")

        logger.debug(f"Synthesizing {len(text)} characters with voice '{voice}'")

        try:
            # Generate audio
            voice_state = self._get_voice_state(voice)
            audio_data = self.model.generate_audio(voice_state, text)

            # Save to temporary file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_wav:
                tmp_wav_path = Path(tmp_wav.name)
                audio_data.save(tmp_wav_path)

            # Convert WAV to MP3 for smaller file size
            tmp_mp3_path = tmp_wav_path.with_suffix('.mp3')
            self._convert_to_mp3(tmp_wav_path, tmp_mp3_path)

            # Upload to S3
            s3_key = f"{config.aws.polly_output_key_prefix}/{tmp_mp3_path.name}"
            audio_url = self._s3_service.upload_file(str(tmp_mp3_path), s3_key)

            # Calculate duration (approximate from audio data)
            duration = self._estimate_duration(audio_data)

            # Cleanup temp files
            tmp_wav_path.unlink(missing_ok=True)
            tmp_mp3_path.unlink(missing_ok=True)

            return TTSResult(
                audio_url=audio_url,
                duration_seconds=duration,
                format='mp3',
                provider=self.name
            )

        except Exception as e:
            logger.error(f"Pocket TTS synthesis failed: {e}")
            raise TTSError(f"Pocket TTS synthesis failed: {e}") from e

    def _convert_to_mp3(self, wav_path: Path, mp3_path: Path) -> None:
        """Convert WAV to MP3 using ffmpeg."""
        try:
            subprocess.run(
                ['ffmpeg', '-y', '-i', str(wav_path), '-codec:a', 'libmp3lame',
                 '-qscale:a', '2', str(mp3_path)],
                check=True,
                capture_output=True
            )
        except subprocess.CalledProcessError as e:
            raise TTSError(f"Audio conversion failed: {e.stderr.decode()}") from e
        except FileNotFoundError:
            raise TTSError("ffmpeg not found. Install with: brew install ffmpeg")

    def _estimate_duration(self, audio_data) -> float:
        """Estimate audio duration from sample data."""
        # Pocket TTS outputs at 24kHz sample rate
        sample_rate = 24000
        num_samples = len(audio_data.audio_data) if hasattr(audio_data, 'audio_data') else 0
        return num_samples / sample_rate if num_samples > 0 else 0.0

    def get_available_voices(self) -> list[str]:
        return self.VOICES.copy()
```

### 4.4 Refactored Existing Providers

```python
# vox_biblios/tts/polly_provider.py

class PollyProvider(TTSProvider):
    """AWS Polly TTS provider (cloud-based)."""

    NEURAL_VOICES = ['Joanna', 'Matthew', 'Ivy', 'Kendra', 'Kimberly', 'Salli', 'Joey', 'Justin']

    def __init__(self, voice: Optional[str] = None):
        self._voice = voice or config.aws.polly_voice_id
        self._polly_service = PollyService()  # Existing service
        self._s3_service = S3Service()

    @property
    def name(self) -> str:
        return 'polly'

    # ... implementation wrapping existing PollyService


# vox_biblios/tts/say_provider.py

class SayProvider(TTSProvider):
    """macOS say command TTS provider."""

    def __init__(self, voice: Optional[str] = None):
        self._voice = voice or 'Samantha'  # macOS default
        self._s3_service = S3Service()

        if not self._is_macos():
            raise TTSError("SayProvider is only available on macOS")

    @property
    def name(self) -> str:
        return 'say'

    # ... implementation extracting logic from PodcastManager
```

### 4.5 Provider Factory

```python
# vox_biblios/tts/factory.py

from typing import Optional
from .base import TTSProvider
from .pocket_tts_provider import PocketTTSProvider
from .polly_provider import PollyProvider
from .say_provider import SayProvider
from ..exceptions import TTSError


PROVIDER_REGISTRY = {
    'pocket-tts': PocketTTSProvider,
    'polly': PollyProvider,
    'say': SayProvider,
}

DEFAULT_PROVIDER = 'pocket-tts'


def create_provider(
    provider_name: Optional[str] = None,
    voice: Optional[str] = None
) -> TTSProvider:
    """
    Create a TTS provider instance.

    Args:
        provider_name: Provider identifier. Defaults to 'pocket-tts'.
        voice: Optional voice override for the provider.

    Returns:
        Configured TTSProvider instance.

    Raises:
        TTSError: If provider_name is invalid.
    """
    provider_name = provider_name or DEFAULT_PROVIDER

    if provider_name not in PROVIDER_REGISTRY:
        available = ', '.join(PROVIDER_REGISTRY.keys())
        raise TTSError(f"Unknown provider: {provider_name}. Available: {available}")

    provider_class = PROVIDER_REGISTRY[provider_name]
    return provider_class(voice=voice)
```

### 4.6 Configuration Updates

```python
# vox_biblios/config.py (additions)

@dataclass
class PocketTTSConfig:
    """Pocket TTS configuration."""
    voice: str = "alba"
    # Model path is handled by pocket-tts library (HuggingFace cache)


@dataclass
class TTSConfig:
    """General TTS configuration."""
    default_provider: str = "pocket-tts"  # Changed from polly


class Config:
    def __init__(self):
        # ... existing code ...
        self.pocket_tts = PocketTTSConfig(
            voice=os.getenv("POCKET_TTS_VOICE", "alba")
        )
        self.tts = TTSConfig(
            default_provider=os.getenv("TTS_PROVIDER", "pocket-tts")
        )
```

### 4.7 CLI Updates

```python
# vox_biblios/cli.py (modifications)

def create_parser():
    # ... existing code ...

    process_parser.add_argument(
        '--provider',
        choices=['pocket-tts', 'polly', 'say'],
        default=None,  # Falls back to config default
        help='TTS provider to use (default: pocket-tts)'
    )

    process_parser.add_argument(
        '--voice',
        type=str,
        default=None,
        help='Voice to use for TTS (provider-specific)'
    )

    # Deprecate --use-local-speech but keep for backward compatibility
    process_parser.add_argument(
        '--use-local-speech',
        action='store_true',
        help='[DEPRECATED] Use --provider say instead'
    )

    # Add voice listing command
    subparsers.add_parser(
        'voices',
        help='List available voices for each provider'
    )
```

### 4.8 PodcastManager Updates

```python
# vox_biblios/core/podcast_manager.py (modifications)

from ..tts.factory import create_provider, DEFAULT_PROVIDER
from ..tts.base import TTSProvider


class PodcastManager:
    def __init__(
        self,
        provider: Optional[str] = None,
        voice: Optional[str] = None,
        use_local_speech: bool = False  # Deprecated, kept for compatibility
    ):
        # Handle deprecated flag
        if use_local_speech:
            logger.warning("--use-local-speech is deprecated. Use --provider say instead.")
            provider = 'say'

        self.tts_provider: TTSProvider = create_provider(provider, voice)
        self.text_processor = TextProcessor()
        self.rss_manager = PodcastRSSManager()
        # ... rest of init

    def _process_chunk(self, chunk: str, title: str) -> dict:
        """Process a single text chunk through TTS."""
        result = self.tts_provider.synthesize(chunk)

        return {
            'title': title,
            'url': result.audio_url,
            'description': f"Preview: {chunk[:config.app.preview_length]}...",
            'pubDate': datetime.now(timezone.utc),
            'duration': result.duration_seconds,
        }
```

---

## 5. File Structure

```
vox_biblios/
├── tts/                          # NEW: TTS provider module
│   ├── __init__.py
│   ├── base.py                   # TTSProvider ABC, TTSResult
│   ├── factory.py                # Provider factory
│   ├── pocket_tts_provider.py    # Pocket TTS implementation
│   ├── polly_provider.py         # AWS Polly (refactored from aws/polly.py)
│   └── say_provider.py           # macOS say (extracted from podcast_manager.py)
├── aws/
│   ├── polly.py                  # Keep PollyService for backward compat
│   └── ...
├── core/
│   ├── podcast_manager.py        # Updated to use TTSProvider
│   └── ...
├── config.py                     # Add PocketTTSConfig, TTSConfig
├── cli.py                        # Add --provider, --voice flags
└── exceptions.py                 # Add TTSError
```

---

## 6. Dependencies

### New Dependencies

```toml
# pyproject.toml additions

[project]
dependencies = [
    # ... existing ...
    "pocket-tts>=0.1.0",    # Pocket TTS library
]

[project.optional-dependencies]
polly = [
    "boto3>=1.26.0",        # Move to optional for AWS Polly users
]
```

### System Requirements

| Requirement | Purpose | Installation |
|-------------|---------|--------------|
| ffmpeg | Convert WAV→MP3 | `brew install ffmpeg` (macOS), `apt install ffmpeg` (Linux) |
| Python 3.10+ | Pocket TTS requirement | Already required by vox-biblios |

---

## 7. Migration & Backward Compatibility

### Breaking Changes
None. All existing functionality preserved.

### Deprecations
| Feature | Replacement | Removal Version |
|---------|-------------|-----------------|
| `--use-local-speech` flag | `--provider say` | v2.0.0 |

### Migration Path for Existing Users

1. **AWS Polly users**: Add `--provider polly` to maintain current behavior
2. **Local speech users**: Replace `--use-local-speech` with `--provider say`
3. **New users**: No action needed, Pocket TTS works out of the box

### Environment Variable Changes

| Old | New | Notes |
|-----|-----|-------|
| N/A | `TTS_PROVIDER` | Default provider selection |
| N/A | `POCKET_TTS_VOICE` | Pocket TTS voice selection |

---

## 8. Error Handling

### New Exception Hierarchy

```python
class TTSError(VoxBibliosError):
    """Base exception for TTS-related errors."""
    pass

class ProviderNotFoundError(TTSError):
    """Requested provider does not exist."""
    pass

class VoiceNotFoundError(TTSError):
    """Requested voice not available for provider."""
    pass

class ModelLoadError(TTSError):
    """Failed to load TTS model."""
    pass

class SynthesisError(TTSError):
    """Failed to synthesize speech."""
    pass
```

### Error Scenarios

| Scenario | Error | User Message |
|----------|-------|--------------|
| Invalid provider | `ProviderNotFoundError` | "Unknown provider: X. Available: pocket-tts, polly, say" |
| Invalid voice | `VoiceNotFoundError` | "Voice 'X' not available for pocket-tts. Available: alba, marius, ..." |
| Model download fails | `ModelLoadError` | "Failed to download Pocket TTS model. Check internet connection." |
| ffmpeg missing | `SynthesisError` | "ffmpeg not found. Install with: brew install ffmpeg" |
| macOS say on Linux | `TTSError` | "SayProvider is only available on macOS" |

---

## 9. Testing Strategy

### Unit Tests

```python
# tests/tts/test_pocket_tts_provider.py

class TestPocketTTSProvider:
    def test_initialization_with_default_voice(self):
        provider = PocketTTSProvider()
        assert provider._voice == 'alba'

    def test_initialization_with_custom_voice(self):
        provider = PocketTTSProvider(voice='marius')
        assert provider._voice == 'marius'

    def test_invalid_voice_raises_error(self):
        with pytest.raises(TTSError):
            PocketTTSProvider(voice='invalid')

    def test_available_voices(self):
        provider = PocketTTSProvider()
        voices = provider.get_available_voices()
        assert 'alba' in voices
        assert len(voices) == 8

    @pytest.mark.slow
    def test_synthesize_produces_audio(self, mock_s3):
        provider = PocketTTSProvider()
        result = provider.synthesize("Hello world")
        assert result.audio_url.endswith('.mp3')
        assert result.duration_seconds > 0


# tests/tts/test_factory.py

class TestProviderFactory:
    def test_default_provider_is_pocket_tts(self):
        provider = create_provider()
        assert provider.name == 'pocket-tts'

    def test_create_polly_provider(self):
        provider = create_provider('polly')
        assert provider.name == 'polly'

    def test_invalid_provider_raises_error(self):
        with pytest.raises(TTSError):
            create_provider('invalid')
```

### Integration Tests

```python
# tests/integration/test_podcast_generation.py

@pytest.mark.integration
class TestPodcastGenerationWithPocketTTS:
    def test_end_to_end_podcast_creation(self, sample_text_file, mock_s3):
        manager = PodcastManager(provider='pocket-tts')
        result = manager.process_and_update(sample_text_file)
        assert 'rss' in result

    def test_chunked_text_produces_multiple_episodes(self, large_text_file, mock_s3):
        manager = PodcastManager(provider='pocket-tts')
        # ... verify multi-part episode handling
```

### Performance Tests

```python
# tests/performance/test_pocket_tts_performance.py

@pytest.mark.performance
class TestPocketTTSPerformance:
    def test_synthesis_speed(self):
        """Verify Pocket TTS achieves >3x real-time on CI hardware."""
        provider = PocketTTSProvider()
        text = "Sample text " * 100  # ~1200 characters

        start = time.time()
        result = provider.synthesize(text)
        elapsed = time.time() - start

        # Audio duration should be ~8 seconds, synthesis should be <3 seconds
        assert elapsed < result.duration_seconds / 3
```

---

## 10. Documentation Updates

### README.md Updates

```markdown
## Quick Start

# Install vox-biblios
uv tool install git+https://github.com/themotionmachine/vox-biblios.git

# Generate a podcast (uses Pocket TTS by default - no cloud account needed!)
vox-biblios process my-article.txt

## TTS Providers

Vox Biblios supports three TTS providers:

| Provider | Command | Requirements | Cost |
|----------|---------|--------------|------|
| **Pocket TTS** (default) | `--provider pocket-tts` | ffmpeg | Free |
| AWS Polly | `--provider polly` | AWS credentials | ~$16/M chars |
| macOS say | `--provider say` | macOS only | Free |

### Pocket TTS Voices

--voice alba      # Default, female
--voice marius    # Male
--voice javert    # Male
--voice jean      # Male
--voice fantine   # Female
--voice cosette   # Female
--voice eponine   # Female
--voice azelma    # Female

### Examples

# Use default (Pocket TTS with alba voice)
vox-biblios process article.txt

# Use Pocket TTS with different voice
vox-biblios process --voice marius article.txt

# Use AWS Polly for highest quality
vox-biblios process --provider polly article.txt

# Use macOS say for fastest processing
vox-biblios process --provider say article.txt
```

### CLAUDE.md Updates

Add to "Running the Application" section:

```markdown
# TTS Provider Selection
vox-biblios process path/to/folder                    # Uses Pocket TTS (default)
vox-biblios process --provider polly path/to/folder   # Uses AWS Polly
vox-biblios process --provider say path/to/folder     # Uses macOS say
vox-biblios process --voice marius path/to/folder     # Uses specific voice
```

---

## 11. Rollout Plan

### Phase 1: Foundation (Week 1)
- [ ] Create `vox_biblios/tts/` module structure
- [ ] Implement `TTSProvider` abstract base class
- [ ] Implement `TTSResult` dataclass
- [ ] Add `TTSError` exception hierarchy
- [ ] Write unit tests for base classes

### Phase 2: Pocket TTS Provider (Week 2)
- [ ] Implement `PocketTTSProvider` class
- [ ] Add ffmpeg conversion logic
- [ ] Implement voice state caching
- [ ] Write unit and integration tests
- [ ] Add `pocket-tts` to dependencies

### Phase 3: Provider Migration (Week 3)
- [ ] Implement `PollyProvider` wrapping existing `PollyService`
- [ ] Implement `SayProvider` extracting from `PodcastManager`
- [ ] Implement provider factory
- [ ] Update `PodcastManager` to use providers
- [ ] Maintain backward compatibility

### Phase 4: CLI & Config (Week 4)
- [ ] Add `--provider` and `--voice` CLI flags
- [ ] Deprecate `--use-local-speech` with warning
- [ ] Add `PocketTTSConfig` to configuration
- [ ] Update config loading for new options
- [ ] Add `vox-biblios voices` command

### Phase 5: Documentation & Release (Week 5)
- [ ] Update README.md
- [ ] Update CLAUDE.md
- [ ] Write migration guide
- [ ] Update example config files
- [ ] Release as minor version bump

---

## 12. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Default provider usage | >80% of new users | CLI analytics |
| Processing success rate | >99% | Error logging |
| Synthesis speed | >3x real-time | Performance tests |
| User setup time | <2 minutes | User feedback |
| AWS cost reduction | >90% for local users | User reports |

---

## 13. Open Questions

1. **Model caching**: Should we provide a CLI command to pre-download the Pocket TTS model, or rely on lazy loading?
   - Recommendation: Lazy loading with `vox-biblios model download` optional command

2. **Voice quality comparison**: Should we provide A/B comparison tooling for users to evaluate voices?
   - Recommendation: Out of scope for initial release

3. **Fallback behavior**: If Pocket TTS fails, should we automatically fall back to another provider?
   - Recommendation: No automatic fallback; explicit provider selection preferred

4. **Platform-specific ffmpeg alternatives**: Use `afconvert` on macOS instead of ffmpeg?
   - Recommendation: Require ffmpeg for consistency across platforms

---

## 14. Appendix

### A. Pocket TTS Voice Characteristics

| Voice | Gender | Style | Notes |
|-------|--------|-------|-------|
| alba | Female | Casual | Default, clear articulation |
| marius | Male | Casual | - |
| javert | Male | - | Named from Les Misérables |
| jean | Male | - | Named from Les Misérables |
| fantine | Female | - | Named from Les Misérables |
| cosette | Female | - | Named from Les Misérables |
| eponine | Female | - | Named from Les Misérables |
| azelma | Female | - | Named from Les Misérables |



### C. Related Resources

- [Pocket TTS GitHub](https://github.com/kyutai-labs/pocket-tts)
- [Pocket TTS HuggingFace Voices](https://huggingface.co/kyutai/tts-voices)
- [AWS Polly Documentation](https://docs.aws.amazon.com/polly/)
