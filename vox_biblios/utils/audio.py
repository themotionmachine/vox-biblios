"""
Audio file utilities built on ffmpeg.
"""
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Union

from vox_biblios.utils.logging import get_logger
from vox_biblios.exceptions import SynthesisError

logger = get_logger(__name__)

MP3_BITRATE = "128k"
MP3_SAMPLE_RATE = "44100"


def _run_ffmpeg(args: List[str]) -> None:
    cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error'] + args
    try:
        result = subprocess.run(cmd, capture_output=True)
    except FileNotFoundError as e:
        raise SynthesisError(
            "ffmpeg not found. Install it with: brew install ffmpeg"
        ) from e
    if result.returncode != 0:
        raise SynthesisError(f"ffmpeg failed: {result.stderr.decode().strip()}")


def to_mp3(input_path: Union[str, Path], output_path: Union[str, Path]) -> Path:
    """Convert any audio file (wav, aiff, ...) to MP3 with standard settings."""
    output_path = Path(output_path)
    _run_ffmpeg([
        '-i', str(input_path),
        '-acodec', 'libmp3lame',
        '-ab', MP3_BITRATE,
        '-ar', MP3_SAMPLE_RATE,
        str(output_path),
    ])
    return output_path


def concat_audio(segment_paths: List[Union[str, Path]],
                 output_path: Union[str, Path]) -> Path:
    """Concatenate audio segments into a single MP3.

    Re-encodes via the concat demuxer so segments with differing sample
    rates (e.g. Polly's 24kHz vs local 44.1kHz) still join cleanly.
    """
    output_path = Path(output_path)

    if len(segment_paths) == 1:
        to_mp3(segment_paths[0], output_path)
        return output_path

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        for seg in segment_paths:
            escaped = str(Path(seg).resolve()).replace("'", r"'\''")
            f.write(f"file '{escaped}'\n")
        list_file = f.name

    try:
        _run_ffmpeg([
            '-f', 'concat', '-safe', '0',
            '-i', list_file,
            '-acodec', 'libmp3lame',
            '-ab', MP3_BITRATE,
            '-ar', MP3_SAMPLE_RATE,
            str(output_path),
        ])
    finally:
        Path(list_file).unlink(missing_ok=True)

    return output_path


def get_duration_seconds(audio_path: Union[str, Path]) -> Optional[float]:
    """Get audio duration via ffprobe; returns None if unavailable."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', str(audio_path)],
            capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (FileNotFoundError, ValueError):
        pass
    return None
