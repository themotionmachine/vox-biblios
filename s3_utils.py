import boto3
from botocore.exceptions import ClientError
from logging_utils import logger

def upload_file(file_name, bucket, object_name=None):
    if object_name is None:
        object_name = file_name

    s3_client = boto3.client('s3')
    try:
        logger.info(f"Uploading file {file_name} to S3 bucket {bucket}")
        s3_client.upload_file(file_name, bucket, object_name)
        logger.info(f"File {file_name} uploaded successfully to {bucket}/{object_name}")
        return True
    except ClientError as e:
        logger.error(f"Error uploading file to S3: {str(e)}", exc_info=True)
        return False

def delete_file_from_s3(bucket, key):
    s3_client = boto3.client('s3')
    try:
        s3_client.delete_object(Bucket=bucket, Key=key)
        logger.info(f"File deleted from S3: {key}")
    except ClientError as e:
        logger.error(f"Error deleting file from S3: {key}. {e}")
        raise