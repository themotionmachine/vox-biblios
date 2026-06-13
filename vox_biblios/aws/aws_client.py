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

    @staticmethod
    @lru_cache(maxsize=2)
    def get_storage_client() -> Any:
        """
        Get an S3-compatible storage client for the configured backend.

        Supports AWS S3 and Cloudflare R2; R2 differs only by an endpoint_url
        override, so both use boto3's 's3' client.

        Raises:
            AWSClientError: If there's an error creating the client
        """
        try:
            config.storage.validate()

            client_kwargs: Dict[str, Any] = {
                "aws_access_key_id": config.storage.access_key,
                "aws_secret_access_key": config.storage.secret_key,
                "region_name": config.storage.region,
            }
            if config.storage.endpoint_url:
                client_kwargs["endpoint_url"] = config.storage.endpoint_url

            client = boto3.client("s3", **client_kwargs)

            logger.debug(
                f"Created storage client for backend: {config.storage.backend} "
                f"(endpoint={config.storage.endpoint_url or 'aws'})"
            )
            return client

        except (ClientError, ValueError) as e:
            error_msg = f"Failed to create storage client: {str(e)}"
            logger.error(error_msg)
            raise AWSClientError(error_msg) from e


# Convenience methods for common services
def get_s3_client():
    """Get an S3 client."""
    return AWSClientFactory.get_client("s3")


def get_storage_client():
    """Get an S3-compatible storage client (AWS S3 or Cloudflare R2)."""
    return AWSClientFactory.get_storage_client()


def get_polly_client():
    """Get a Polly client."""
    return AWSClientFactory.get_client("polly")


def get_cloudwatch_client():
    """Get a CloudWatch client."""
    return AWSClientFactory.get_client("cloudwatch")


def get_ce_client():
    """Get a Cost Explorer client."""
    return AWSClientFactory.get_client("ce")