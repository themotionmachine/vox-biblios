// Voice catalog for the control-plane UI and API validation.
//
// SOURCE OF TRUTH is the Python side — each provider's *_VOICES list in
// vox_biblios/tts/*_provider.py. This file mirrors those lists so the Worker
// (which can't run Python) can populate dropdowns and reject obviously-bad
// values early. The CLI remains the real validator: it raises VoiceNotFoundError
// at synthesis time, so a stale entry here fails the queue item with a clear
// error rather than producing wrong audio. Keep this in sync when voices change.
//
// `say` (macOS) is intentionally omitted: its voice list is host-dynamic
// (`say -v ?`), so it isn't a sensible persisted feed default. It stays
// reachable via the CLI's --provider/--voice flags.

export interface VoiceGroup {
  /** Provider id as understood by the CLI's --provider flag. */
  provider: string;
  /** Human label for the optgroup. */
  label: string;
  voices: string[];
}

export const VOICE_CATALOG: VoiceGroup[] = [
  {
    provider: "pocket-tts",
    label: "Pocket TTS",
    voices: ["alba", "marius", "javert", "jean", "fantine", "cosette", "eponine", "azelma"],
  },
  {
    provider: "kokoro",
    label: "Kokoro",
    voices: [
      "af_heart", "af_bella", "af_nicole", "af_nova", "af_sarah", "af_sky",
      "am_adam", "am_echo", "am_michael", "am_puck",
      "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
      "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    ],
  },
  {
    provider: "polly",
    label: "Amazon Polly",
    voices: [
      "Joanna", "Matthew", "Kendra", "Kimberly", "Salli", "Joey", "Justin",
      "Kevin", "Ivy", "Ruth", "Stephen", "Danielle", "Gregory",
    ],
  },
];

/** True if (provider, voice) is a known pair in the catalog. */
export function isKnownVoice(provider: string, voice: string): boolean {
  const group = VOICE_CATALOG.find((g) => g.provider === provider);
  return !!group && group.voices.includes(voice);
}

export interface VoiceSelection {
  provider: string | null;
  voice: string | null;
}

/**
 * Normalize a (provider, voice) pair coming off the wire into a tri-state:
 *   - { ok, provider, voice }        both present and valid
 *   - { ok, provider: null, voice: null }  both absent → "use default"
 *   - { error }                      only one present, or an unknown pair
 * Empty strings are treated as absent so a "use default" <option value=""> and
 * an omitted JSON field behave the same.
 */
export function parseVoiceSelection(
  providerRaw: unknown,
  voiceRaw: unknown,
): { ok: true; value: VoiceSelection } | { ok: false; error: string } {
  const provider = typeof providerRaw === "string" && providerRaw.trim() !== "" ? providerRaw.trim() : null;
  const voice = typeof voiceRaw === "string" && voiceRaw.trim() !== "" ? voiceRaw.trim() : null;
  if (provider === null && voice === null) return { ok: true, value: { provider: null, voice: null } };
  if (provider === null || voice === null) {
    return { ok: false, error: "tts_provider and tts_voice must be set together (or both omitted)" };
  }
  if (!isKnownVoice(provider, voice)) {
    return { ok: false, error: `unknown voice '${voice}' for provider '${provider}'` };
  }
  return { ok: true, value: { provider, voice } };
}

/** Encode a selection for a single <select> option value: "provider:voice" or "". */
export function encodeVoiceValue(provider: string | null, voice: string | null): string {
  return provider && voice ? `${provider}:${voice}` : "";
}

/** Decode a single "provider:voice" form value back into raw parts ("" → nulls). */
export function decodeVoiceValue(value: unknown): { provider: string | null; voice: string | null } {
  if (typeof value !== "string" || value.trim() === "") return { provider: null, voice: null };
  const idx = value.indexOf(":");
  if (idx === -1) return { provider: value.trim(), voice: null };
  return { provider: value.slice(0, idx).trim() || null, voice: value.slice(idx + 1).trim() || null };
}
