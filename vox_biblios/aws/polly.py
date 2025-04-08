"""
AWS Polly service integration for text-to-speech conversion.
"""
from typing import Dict, Any, List, Optional
import time
import backoff

from botocore.exceptions import ClientError

from vox_biblios.aws.aws_client import get_polly_client
from vox_biblios.config import config
from vox_biblios.utils.logging import get_logger
from vox_biblios.exceptions import PollyError

logger = get_logger(__name__)


class PollyService:
    """Service for AWS Polly text-to-speech conversion."""
    
    def __init__(self, 
                 voice_id: Optional[str] = None,
                 engine: Optional[str] = None,
                 output_format: Optional[str] = None,
                 bucket_name: Optional[str] = None,
                 key_prefix: Optional[str] = None):
        """
        Initialize the Polly service.
        
        Args:
            voice_id: Polly voice ID (default from config)
            engine: Polly engine (default from config)
            output_format: Output audio format (default from config)
            bucket_name: S3 bucket for output (default from config)
            key_prefix: S3 key prefix for output (default from config)
        """
        self.voice_id = voice_id or config.aws.polly_voice_id
        self.engine = engine or config.aws.polly_engine
        self.output_format = output_format or config.aws.polly_format
        self.bucket_name = bucket_name or config.aws.s3_bucket
        self.key_prefix = key_prefix or config.aws.polly_output_key_prefix
        
        self.client = get_polly_client()
        
        logger.debug(f"Initialized PollyService with voice_id={self.voice_id}, engine={self.engine}")
    
    def synthesize_speech(self, text: str) -> Dict[str, Any]:
        """
        Convert text to speech using AWS Polly.
        
        Args:
            text: Text to convert to speech
            
        Returns:
            AWS Polly synthesis task response
            
        Raises:
            PollyError: If the synthesis task fails
        """
        logger.info(f"Starting speech synthesis task for text of length {len(text)} characters")
        
        try:
            response = self._start_synthesis_task(text)
            
            task_id = response['SynthesisTask']['TaskId']
            logger.info(f"Synthesis task started successfully. Task ID: {task_id}")
            
            return response
            
        except ClientError as e:
            error_msg = f"Error starting speech synthesis task: {str(e)}"
            logger.error(error_msg)
            raise PollyError(error_msg) from e
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get the status of a speech synthesis task.
        
        Args:
            task_id: Polly task ID
            
        Returns:
            The task status response
        """
        try:
            response = self.client.get_speech_synthesis_task(TaskId=task_id)
            return response['SynthesisTask']
        except ClientError as e:
            logger.error(f"Error getting task status: {str(e)}")
            raise PollyError(f"Failed to get status for task {task_id}: {str(e)}") from e
    
    def process_text_chunks(self, chunks: List[str]) -> List[Dict[str, Any]]:
        """
        Process multiple text chunks with Polly.
        
        Args:
            chunks: List of text chunks to process
            
        Returns:
            List of successful task responses
        """
        logger.info(f"Processing {len(chunks)} text chunks with Polly")
        
        results = []
        for i, chunk in enumerate(chunks):
            try:
                logger.info(f"Processing chunk {i+1}/{len(chunks)} (length: {len(chunk)} characters)")
                response = self.synthesize_speech(chunk)
                results.append(response)
                
                # Add a small delay between requests to avoid throttling
                if i < len(chunks) - 1:
                    time.sleep(1)
                    
            except PollyError as e:
                logger.error(f"Failed to process chunk {i+1}: {str(e)}")
                # Continue with the next chunk
        
        logger.info(f"Completed processing {len(results)}/{len(chunks)} chunks")
        return results
    
    def wait_for_completion(self, task_id: str, timeout: int = 600) -> Dict[str, Any]:
        """
        Wait for a Polly task to complete.
        
        Args:
            task_id: The task ID to wait for
            timeout: Maximum time to wait in seconds
            
        Returns:
            The completed task status
            
        Raises:
            PollyError: If the task fails or times out
        """
        logger.info(f"Waiting for Polly task {task_id} to complete (timeout: {timeout}s)")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            task = self.get_task_status(task_id)
            status = task['TaskStatus']
            
            if status == 'completed':
                logger.info(f"Task {task_id} completed successfully")
                return task
            elif status == 'failed':
                error_msg = f"Task {task_id} failed: {task.get('TaskStatusReason', 'Unknown error')}"
                logger.error(error_msg)
                raise PollyError(error_msg)
            
            # Sleep before checking again
            time.sleep(5)
        
        # If we get here, the task timed out
        error_msg = f"Task {task_id} timed out after {timeout} seconds"
        logger.error(error_msg)
        raise PollyError(error_msg)
    
    @backoff.on_exception(
        backoff.expo,
        ClientError,
        max_tries=5,
        jitter=backoff.full_jitter,
        giveup=lambda e: 'ThrottlingException' not in str(e)
    )
    def _start_synthesis_task(self, text: str) -> Dict[str, Any]:
        """
        Start a speech synthesis task with retry mechanism.
        
        Args:
            text: Text to synthesize
            
        Returns:
            AWS Polly response
        """
        return self.client.start_speech_synthesis_task(
            Engine=self.engine,
            LanguageCode='en-US',
            OutputFormat=self.output_format,
            OutputS3BucketName=self.bucket_name,
            OutputS3KeyPrefix=self.key_prefix,
            Text=text,
            TextType='text',
            VoiceId=self.voice_id
        )