import requests
import xmltodict
from podgen import Podcast, Episode
from rss_utils import create_podcast
from s3_utils import upload_file_to_s3, delete_file_from_s3
import logging
from urllib.parse import urlparse

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fetch_old_rss():
    url = "https://s3.us-east-1.amazonaws.com/vox-biblios/voxbiblios.rss"
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    else:
        logger.error(f"Failed to fetch RSS file. Status code: {response.status_code}")
        return None

def get_s3_keys_from_rss(parsed_rss):
    s3_keys = []
    if 'rss' in parsed_rss and 'channel' in parsed_rss['rss'] and 'item' in parsed_rss['rss']['channel']:
        items = parsed_rss['rss']['channel']['item']
        if isinstance(items, list):
            for item in items:
                if 'enclosure' in item and '@url' in item['enclosure']:
                    url = item['enclosure']['@url']
                    parsed_url = urlparse(url)
                    s3_keys.append(parsed_url.path.lstrip('/'))
        elif isinstance(items, dict):  # If there's only one item
            if 'enclosure' in items and '@url' in items['enclosure']:
                url = items['enclosure']['@url']
                parsed_url = urlparse(url)
                s3_keys.append(parsed_url.path.lstrip('/'))
    return s3_keys

def clear_podcast_feed():
    logger.info("Starting to clear podcast feed")

    # Fetch the old RSS file
    old_rss = fetch_old_rss()
    if not old_rss:
        logger.error("Failed to fetch old RSS file. Aborting.")
        return

    # Parse the old RSS file
    parsed_rss = xmltodict.parse(old_rss)

    # Get S3 keys of audio files to delete
    s3_keys_to_delete = get_s3_keys_from_rss(parsed_rss)

    # Delete audio files from S3
    for key in s3_keys_to_delete:
        try:
            delete_file_from_s3('vox-biblios', key)
            logger.info(f"Deleted file from S3: {key}")
        except Exception as e:
            logger.error(f"Failed to delete file from S3: {key}. Error: {str(e)}")

    # Create a new empty podcast
    new_podcast = create_podcast()

    # Preserve the publication date of the channel
    if 'rss' in parsed_rss and 'channel' in parsed_rss['rss']:
        channel = parsed_rss['rss']['channel']
        if 'pubDate' in channel:
            new_podcast.publication_date = channel['pubDate']

    # Generate the new RSS file
    new_rss_content = new_podcast.rss_str()

    # Save the new RSS file locally
    with open('voxbiblios.rss', 'w', encoding='utf-8') as f:
        f.write(new_rss_content)

    logger.info("New empty RSS file created locally")

    # Upload the new RSS file to S3
    upload_file_to_s3('voxbiblios.rss', 'vox-biblios', 'voxbiblios.rss')

    logger.info("Podcast feed cleared successfully")

if __name__ == "__main__":
    clear_podcast_feed()