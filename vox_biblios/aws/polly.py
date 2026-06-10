"""
AWS Polly service integration for text-to-speech conversion.
"""
from typing import Optional
import backoff

from botocore.exceptions import ClientError

from vox_biblios.aws.aws_client import get_polly_client
from vox_biblios.config import config
from vox_biblios.utils.logging import get_logger
from vox_biblios.exceptions import PollyError

logger = get_logger(__name__)

# Synchronous SynthesizeSpeech is limited to 3000 billed characters
MAX_SYNC_CHARS = 3000


class PollyService:
    """Service for AWS Polly text-to-speech conversion."""

    def __init__(self,
                 voice_id: Optional[str] = None,
                 engine: Optional[str] = None,
                 output_format: Optional[str] = None):
        """
        Initialize the Polly service.

        Args:
            voice_id: Polly voice ID (default from config)
            engine: Polly engine (default from config)
            output_format: Output audio format (default from config)
        """
        self.voice_id = voice_id or config.aws.polly_voice_id
        self.engine = engine or config.aws.polly_engine
        self.output_format = output_format or config.aws.polly_format

        self.client = get_polly_client()

        logger.debug(f"Initialized PollyService with voice_id={self.voice_id}, engine={self.engine}")

    def synthesize_speech(self, text: str) -> bytes:
        """
        Convert text to speech using the synchronous Polly API.

        Args:
            text: Text to convert (max 3000 billed characters)

        Returns:
            Audio bytes in the configured output format

        Raises:
            PollyError: If synthesis fails
        """
        logger.info(f"Synthesizing {len(text)} characters with Polly (sync)")

        if len(text) > MAX_SYNC_CHARS:
            raise PollyError(
                f"Text exceeds Polly synchronous limit ({len(text)} > {MAX_SYNC_CHARS} chars)"
            )

        try:
            response = self._synthesize_with_retry(text)
            return response['AudioStream'].read()
        except ClientError as e:
            error_msg = f"Polly synthesis failed: {str(e)}"
            logger.error(error_msg)
            raise PollyError(error_msg) from e

    @backoff.on_exception(
        backoff.expo,
        ClientError,
        max_tries=5,
        jitter=backoff.full_jitter,
        giveup=lambda e: 'ThrottlingException' not in str(e)
    )
    def _synthesize_with_retry(self, text: str):
        return self.client.synthesize_speech(
            Engine=self.engine,
            LanguageCode='en-US',
            OutputFormat=self.output_format,
            Text=text,
            TextType='text',
            VoiceId=self.voice_id
        )
