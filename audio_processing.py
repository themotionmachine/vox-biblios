import boto3
from botocore.exceptions import ClientError
from logging_utils import logger
from config import AWS_ACCESS_KEY, AWS_SECRET_KEY

def send_polly_job(text, voice_id='Joanna'):
    try:
        logger.info(f"Sending Polly job with voice_id: {voice_id}")
        polly_client = boto3.Session(
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY,
            region_name='us-east-1').client('polly')
        
        response = polly_client.start_speech_synthesis_task(
            VoiceId=voice_id,
            OutputS3BucketName='vox-biblios',
            OutputS3KeyPrefix='key',
            OutputFormat='mp3', 
            Text=text,
            Engine='neural'
        )
        logger.info(f"Polly job sent successfully. Task ID: {response['SynthesisTask']['TaskId']}")
        return response
    except ClientError as e:
        logger.error(f"Error sending Polly job: {str(e)}", exc_info=True)
        return None