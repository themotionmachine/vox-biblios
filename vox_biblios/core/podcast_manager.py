"""
Core podcast manager for Vox Biblios.
"""
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

from vox_biblios.config import config
from vox_biblios.utils.logging import get_logger
from vox_biblios.utils.audio import concat_audio
from vox_biblios.core.text_processor import TextProcessor
from vox_biblios.adapters.web_scraper import WebScraper
from vox_biblios.exceptions import PodcastManagerError
from vox_biblios.tts import create_provider, TTSProvider

logger = get_logger(__name__)


@dataclass
class ProcessResult:
    """Outcome of a processing run."""
    episodes: List[Dict[str, Any]] = field(default_factory=list)
    failures: List[Dict[str, str]] = field(default_factory=list)
    rss_url: Optional[str] = None

    @property
    def exit_code(self) -> int:
        """0 = full success, 1 = nothing succeeded, 2 = partial failure."""
        if self.failures:
            return 2 if self.episodes else 1
        return 0


def _safe_filename(title: str) -> str:
    slug = re.sub(r'[^A-Za-z0-9._-]+', '-', title).strip('-')[:80] or "episode"
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    return f"{slug}-{timestamp}.mp3"


class PodcastManager:
    """Central manager for Vox Biblios podcast generator."""

    def __init__(
        self,
        provider: Optional[str] = None,
        voice: Optional[str] = None,
        output_dir: Optional[Union[str, Path]] = None,
    ):
        """Initialize the podcast manager.

        Args:
            provider: TTS provider name ('pocket-tts', 'kokoro', 'polly', 'say').
                      Default from config.
            voice: Voice to use for TTS. Default from config or provider default.
            output_dir: If set, write MP3s to this local directory and skip
                        S3 upload and RSS feed updates entirely (no AWS needed).
        """
        self.text_processor = TextProcessor()
        self.web_scraper = WebScraper()
        self.output_dir = Path(output_dir) if output_dir else None

        self._provider_name = provider or config.tts.default_provider
        self._voice = voice or config.tts.default_voice
        self._tts_provider: TTSProvider = create_provider(self._provider_name, self._voice)

        # AWS-backed services are created lazily so local mode never touches them
        self._s3_service = None
        self._rss_manager = None

        logger.debug(
            f"Initialized PodcastManager (provider={self._provider_name}, "
            f"voice={self._voice}, output_dir={self.output_dir})"
        )

    @property
    def s3_service(self):
        if self._s3_service is None:
            from vox_biblios.aws.s3 import S3Service
            self._s3_service = S3Service()
        return self._s3_service

    @property
    def rss_manager(self):
        if self._rss_manager is None:
            from vox_biblios.adapters.rss import PodcastRSSManager
            self._rss_manager = PodcastRSSManager()
        return self._rss_manager

    def _synthesize_article(self, text: str, title: str) -> Optional[Path]:
        """
        Synthesize a full article into a single MP3.

        Text is chunked to the provider's comfortable size, each chunk is
        synthesized separately, and the segments are concatenated.

        Returns:
            Path to the final MP3 (in a temp location), or None on failure
        """
        chunks = self.text_processor.chunk(text, max_size=self._tts_provider.max_chunk_chars)
        if not chunks:
            logger.warning(f"No synthesizable text for '{title}'")
            return None

        logger.info(f"Synthesizing '{title}' in {len(chunks)} chunk(s) with {self._provider_name}")

        segment_paths: List[str] = []
        try:
            for i, chunk in enumerate(chunks):
                segment_path = tempfile.mktemp(suffix='.mp3')
                logger.info(f"Synthesizing chunk {i + 1}/{len(chunks)} ({len(chunk)} chars)")
                self._tts_provider.synthesize(chunk, Path(segment_path))
                segment_paths.append(segment_path)

            final_path = tempfile.mktemp(suffix='.mp3')
            concat_audio(segment_paths, final_path)
            return Path(final_path)

        except Exception as e:
            logger.error(f"Synthesis failed for '{title}': {e}")
            return None

        finally:
            for p in segment_paths:
                if os.path.exists(p):
                    os.remove(p)

    def _make_episode(self, audio_path: Path, title: str, text: str, source: str) -> Dict[str, Any]:
        """Publish one article's audio (locally or to S3) and build episode data."""
        filename = _safe_filename(title)

        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            dest = self.output_dir / filename
            shutil.move(str(audio_path), dest)
            url = str(dest)
        else:
            try:
                url = self.s3_service.upload_file(audio_path, object_key=filename)
            finally:
                if audio_path.exists():
                    audio_path.unlink()

        preview_length = config.app.preview_length
        text_preview = (
            text[:preview_length].strip() + "..."
            if len(text) > preview_length
            else text.strip()
        )

        return {
            'title': title,
            'url': url,
            'description': f"Generated from {source}\n\nPreview: {text_preview}",
            'pubDate': datetime.now(timezone.utc),
        }

    def process_texts_from_folder(self, folder_path: Union[str, Path]) -> ProcessResult:
        """
        Process all text files in a folder, one episode per file.

        Source files are deleted only when their synthesis fully succeeded.

        Args:
            folder_path: Path to folder containing text files

        Returns:
            ProcessResult with episodes and failures

        Raises:
            PodcastManagerError: If processing fails entirely
        """
        logger.info(f"Processing texts from folder: {folder_path}")

        try:
            processed_texts = self.text_processor.process_folder(folder_path)

            if not processed_texts:
                logger.warning(f"No text files found in {folder_path}")
                return ProcessResult()

            result = ProcessResult()
            succeeded_files: List[str] = []

            for filename, text in processed_texts.items():
                title = Path(filename).stem
                audio_path = self._synthesize_article(text, title)

                if audio_path:
                    try:
                        episode = self._make_episode(audio_path, title, text, filename)
                        result.episodes.append(episode)
                        succeeded_files.append(filename)
                        logger.info(f"Successfully processed '{filename}'")
                        continue
                    except Exception as e:
                        logger.error(f"Failed to publish '{filename}': {e}")
                        result.failures.append({'source': filename, 'error': str(e)})
                else:
                    result.failures.append({'source': filename, 'error': 'synthesis failed'})

            if succeeded_files:
                self.text_processor.delete_files(folder_path, succeeded_files)

            logger.info(
                f"Processed {len(result.episodes)}/{len(processed_texts)} files successfully"
            )
            return result

        except Exception as e:
            error_msg = f"Failed to process texts from folder {folder_path}: {str(e)}"
            logger.error(error_msg)
            raise PodcastManagerError(error_msg) from e

    def process_url(self, url: str) -> ProcessResult:
        """
        Process content from a URL into a single episode.

        Args:
            url: URL to process

        Returns:
            ProcessResult with the episode or failure

        Raises:
            PodcastManagerError: If processing fails entirely
        """
        logger.info(f"Processing content from URL: {url}")

        try:
            content = self.web_scraper.extract_content(url)

            if not content or not content.get('text'):
                logger.warning(f"No content extracted from {url}")
                return ProcessResult(failures=[{'source': url, 'error': 'no content extracted'}])

            title = content.get('title', '')
            if not title:
                parsed_url = urlparse(url)
                path = parsed_url.path.strip('/')
                if path:
                    title = path.replace('-', ' ').replace('_', ' ').title()
                else:
                    title = parsed_url.netloc.replace('www.', '')

            text = self.text_processor.preprocess(content['text'])

            result = ProcessResult()
            audio_path = self._synthesize_article(text, title)

            if audio_path:
                try:
                    episode = self._make_episode(audio_path, title, text, url)
                    result.episodes.append(episode)
                    logger.info(f"Successfully processed URL '{url}'")
                    return result
                except Exception as e:
                    logger.error(f"Failed to publish episode for '{url}': {e}")
                    result.failures.append({'source': url, 'error': str(e)})
            else:
                result.failures.append({'source': url, 'error': 'synthesis failed'})

            return result

        except Exception as e:
            error_msg = f"Failed to process content from URL {url}: {str(e)}"
            logger.error(error_msg)
            raise PodcastManagerError(error_msg) from e

    def process_and_update(self, input_source: str) -> ProcessResult:
        """
        Process an input source and (unless in local mode) update the RSS feed.

        Args:
            input_source: Folder path, file path, or URL to process

        Returns:
            ProcessResult; rss_url is set when the feed was updated

        Raises:
            PodcastManagerError: If processing fails entirely
        """
        logger.info(f"Processing input source: {input_source}")

        try:
            if input_source.startswith(('http://', 'https://')):
                result = self.process_url(input_source)
            else:
                result = self.process_texts_from_folder(input_source)

            if result.episodes and not self.output_dir:
                result.rss_url = self.rss_manager.update_feed_with_episodes(result.episodes)
                logger.info(f"Podcast feed updated: {result.rss_url}")

            return result

        except PodcastManagerError:
            raise
        except Exception as e:
            error_msg = f"Failed to process input source {input_source}: {str(e)}"
            logger.error(error_msg)
            raise PodcastManagerError(error_msg) from e
