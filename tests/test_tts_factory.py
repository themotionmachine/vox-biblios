"""
Tests for ``vox_biblios.tts.factory``.

Known keys resolve, unknown keys raise ``ProviderNotFoundError``, import
failures are translated, and the advertised provider list matches the registry.
"""
import pytest

from vox_biblios.tts import factory, create_provider, get_available_providers
from vox_biblios.exceptions import ProviderNotFoundError


def test_available_providers_matches_registry():
    assert get_available_providers() == list(factory.PROVIDER_REGISTRY.keys())


def test_registry_advertises_the_documented_providers():
    assert set(factory.PROVIDER_REGISTRY) == {"pocket-tts", "kokoro", "polly", "say"}


def test_unknown_provider_raises():
    with pytest.raises(ProviderNotFoundError) as exc:
        create_provider("does-not-exist")
    assert "Available providers" in str(exc.value)


def test_import_provider_class_unknown_raises():
    with pytest.raises(ProviderNotFoundError):
        factory._import_provider_class("nope")


def test_import_failure_is_translated(monkeypatch):
    # A registered provider whose module can't be imported surfaces as
    # ProviderNotFoundError, not a raw ImportError.
    monkeypatch.setitem(
        factory.PROVIDER_REGISTRY, "broken", ("vox_biblios._no_such_module", "X")
    )
    with pytest.raises(ProviderNotFoundError) as exc:
        factory._import_provider_class("broken")
    assert "broken" in str(exc.value)


def test_missing_class_in_module_is_translated(monkeypatch):
    monkeypatch.setitem(
        factory.PROVIDER_REGISTRY, "noclass", ("vox_biblios.exceptions", "NotAClass")
    )
    with pytest.raises(ProviderNotFoundError):
        factory._import_provider_class("noclass")


def test_create_known_provider_via_fake(fake_tts):
    # fake_tts registers tests.fakes.FakeTTSProvider under "fake".
    provider = create_provider("fake")
    assert provider.name == "fake"


def test_create_provider_passes_voice(fake_tts):
    provider = create_provider("fake", voice="fake-voice-a")
    assert provider._voice == "fake-voice-a"
