"""
AWS client factory to provide consistent client instantiation across the application.
"""
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError
from functools import lru_cache

from vox_biblios.config import config
from vox_biblios.utils.logging import get_logger

logger = get_logger(__name__)

class AWSClientError(Exception):
    """Exception raised for AWS client related errors."""
    pass


class AWSClientFactory:
    """Factory for creating AWS service clients."""
    
    @staticmethod
    @lru_cache(maxsize=8)
    def get_client(service_name: str, region_name: Optional[str] = None) -> Any:
        """
        Get an AWS service client.

        Args:
            service_name: The AWS service name (e.g., 's3', 'polly')
            region_name: Optional region name override

        Returns:
            The requested AWS service client

        Raises:
            AWSClientError: If there's an error creating the client
        """
        try:
            # Validate AWS credentials before creating client
            config.aws.validate()

            region = region_name or config.aws.region

            client = boto3.client(
                service_name,
                aws_access_key_id=config.aws.access_key,
                aws_secret_access_key=config.aws.secret_key,
                region_name=region
            )

            logger.debug(f"Created AWS client for service: {service_name} in region: {region}")
            return client

        except (ClientError, ValueError) as e:
            error_msg = f"Failed to create AWS client for {service_name}: {str(e)}"
            logger.error(error_msg)
            raise AWSClientError(error_msg) from e


# Convenience methods for common services
def get_s3_client():
    """Get an S3 client (for AWS S3 only, e.g., Polly output)."""
    return AWSClientFactory.get_client("s3")


def get_storage_client():
    """
    Get a storage client for S3-compatible object storage.

    This returns a boto3 S3 client configured for the storage provider
    specified in config (S3, Cloudflare R2, or Backblaze B2).

    Returns:
        Configured boto3 S3 client for the storage provider
    """
    try:
        storage_config = config.storage
        storage_config.validate()

        client_kwargs = {
            "aws_access_key_id": storage_config.access_key,
            "aws_secret_access_key": storage_config.secret_key,
        }

        # Add endpoint URL for non-S3 providers
        if storage_config.endpoint_url:
            client_kwargs["endpoint_url"] = storage_config.endpoint_url

        # Set region (R2 uses 'auto', B2 uses specific regions)
        if storage_config.region:
            client_kwargs["region_name"] = storage_config.region

        client = boto3.client("s3", **client_kwargs)

        logger.debug(
            f"Created storage client for provider: {storage_config.provider} "
            f"(endpoint: {storage_config.endpoint_url or 'default'})"
        )
        return client

    except (ClientError, ValueError) as e:
        error_msg = f"Failed to create storage client: {str(e)}"
        logger.error(error_msg)
        raise AWSClientError(error_msg) from e


def get_polly_client():
    """Get a Polly client."""
    return AWSClientFactory.get_client("polly")


def get_cloudwatch_client():
    """Get a CloudWatch client."""
    return AWSClientFactory.get_client("cloudwatch")


def get_ce_client():
    """Get a Cost Explorer client."""
    return AWSClientFactory.get_client("ce")