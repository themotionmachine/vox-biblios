"""
AWS S3 service integration for file storage.
"""
from typing import Optional, Union, List, Dict, Any
from pathlib import Path
import json
import io
import mimetypes
import backoff

from botocore.exceptions import ClientError

from vox_biblios.aws.aws_client import get_storage_client
from vox_biblios.config import config
from vox_biblios.utils.logging import get_logger
from vox_biblios.exceptions import S3Error

logger = get_logger(__name__)


class S3Service:
    """Service for AWS S3 storage operations."""
    
    def __init__(self, bucket_name: Optional[str] = None):
        """
        Initialize the S3 service.
        
        Args:
            bucket_name: S3 bucket name (default from config)
        """
        self.bucket_name = bucket_name or config.storage.bucket
        self.client = get_storage_client()
        
        logger.debug(f"Initialized S3Service with bucket_name={self.bucket_name}")
    
    def upload_file(self, 
                    file_path: Union[str, Path], 
                    object_key: Optional[str] = None, 
                    content_type: Optional[str] = None) -> str:
        """
        Upload a file to S3.
        
        Args:
            file_path: Path to the file to upload
            object_key: S3 object key (defaults to file name)
            content_type: Content type of the file (auto-detected if not provided)
            
        Returns:
            The S3 URL of the uploaded file
            
        Raises:
            S3Error: If the upload fails
        """
        file_path = Path(file_path)
        object_key = object_key or file_path.name
        
        # Auto-detect content type if not provided
        if not content_type:
            content_type, _ = mimetypes.guess_type(str(file_path))
            content_type = content_type or 'application/octet-stream'
        
        logger.info(f"Uploading file {file_path} to S3 bucket {self.bucket_name}/{object_key}")
        
        try:
            self._upload_file_with_retry(file_path, object_key, content_type)

            # Return the public URL for the configured storage backend
            public_url = config.storage.get_public_url(object_key)
            logger.info(f"File uploaded successfully to {public_url}")

            return public_url
            
        except Exception as e:
            error_msg = f"Failed to upload file {file_path} to S3: {str(e)}"
            logger.error(error_msg)
            raise S3Error(error_msg) from e
    
    def delete_file(self, object_key: str) -> bool:
        """
        Delete a file from S3.
        
        Args:
            object_key: S3 object key
            
        Returns:
            True if the file was deleted, False otherwise
            
        Raises:
            S3Error: If the deletion fails
        """
        logger.info(f"Deleting file from S3 bucket {self.bucket_name}/{object_key}")
        
        try:
            # Delete the file
            self.client.delete_object(Bucket=self.bucket_name, Key=object_key)
            
            logger.info(f"File deleted successfully from {object_key}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to delete file from S3: {str(e)}"
            logger.error(error_msg)
            raise S3Error(error_msg) from e
    
    @backoff.on_exception(
        backoff.expo,
        ClientError,
        max_tries=5,
        jitter=backoff.full_jitter,
        giveup=lambda e: 'ThrottlingException' not in str(e)
    )
    def _upload_file_with_retry(self, file_path: Path, object_key: str, content_type: str) -> None:
        """
        Upload a file to S3 with retry mechanism.
        
        Args:
            file_path: Path to the file to upload
            object_key: S3 object key
            content_type: Content type of the file
        """
        extra_args = {'ContentType': content_type} if content_type else {}
        self.client.upload_file(
            str(file_path),
            self.bucket_name,
            object_key,
            ExtraArgs=extra_args
        )