"""
TTS provider factory for creating provider instances.
"""
from typing import Dict, List, Optional, Type

from vox_biblios.tts.base import TTSProvider
from vox_biblios.exceptions import ProviderNotFoundError


# Registry mapping provider names to their module paths and class names
# Using lazy imports to avoid loading unnecessary dependencies
PROVIDER_REGISTRY: Dict[str, tuple] = {
    "pocket-tts": ("vox_biblios.tts.pocket_tts_provider", "PocketTTSProvider"),
    "kokoro": ("vox_biblios.tts.kokoro_provider", "KokoroProvider"),
    "polly": ("vox_biblios.tts.polly_provider", "PollyProvider"),
    "say": ("vox_biblios.tts.say_provider", "SayProvider"),
}


def _import_provider_class(provider_name: str) -> Type[TTSProvider]:
    """
    Dynamically import a provider class.

    Args:
        provider_name: Name of the provider to import

    Returns:
        The provider class

    Raises:
        ProviderNotFoundError: If the provider is not found
    """
    if provider_name not in PROVIDER_REGISTRY:
        available = ", ".join(PROVIDER_REGISTRY.keys())
        raise ProviderNotFoundError(
            f"Unknown TTS provider: '{provider_name}'. Available providers: {available}"
        )

    module_path, class_name = PROVIDER_REGISTRY[provider_name]

    try:
        import importlib
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    except ImportError as e:
        raise ProviderNotFoundError(
            f"Failed to import provider '{provider_name}': {e}. "
            f"Make sure the required dependencies are installed."
        ) from e
    except AttributeError as e:
        raise ProviderNotFoundError(
            f"Provider class '{class_name}' not found in module '{module_path}': {e}"
        ) from e


def create_provider(provider_name: str, voice: Optional[str] = None) -> TTSProvider:
    """
    Create a TTS provider instance.

    Args:
        provider_name: Name of the provider (pocket-tts, polly, say)
        voice: Optional voice to use (provider-specific)

    Returns:
        An initialized TTSProvider instance

    Raises:
        ProviderNotFoundError: If the provider is not found
        VoiceNotFoundError: If the voice is invalid for the provider
    """
    provider_class = _import_provider_class(provider_name)

    if voice:
        return provider_class(voice=voice)
    return provider_class()


def get_available_providers() -> List[str]:
    """
    Get list of available TTS providers.

    Returns:
        List of provider names
    """
    return list(PROVIDER_REGISTRY.keys())
