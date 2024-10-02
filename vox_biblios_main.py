import os
import requests
import argparse
from datetime import datetime, timezone
from time import sleep
from urllib.parse import urlparse
from goose3 import Goose
import time
import sys
import itertools
import threading

from config import AWS_ACCESS_KEY, AWS_SECRET_KEY, S3_BUCKET
from audio_processing import send_polly_job
from rss_utils import create_podcast, create_episode, parse_old_rss_file, Episode, Media
from text_processing import preprocess_text, chunk_text  # Add this import
from s3_utils import upload_file, delete_file_from_s3  # Update this line
from logging_utils import logger
from cost_estimation import estimate_monthly_cost

def animate_soundwave():
    soundwave = [
        "▁▂▃▄▅▆▇█▇▆▅▄▃▂▁",
        "▂▃▄▅▆▇█▇▆▅▄▃▂▁▂",
        "▃▄▅▆▇█▇▆▅▄▃▂▁▂▃",
        "▄▅▆▇█▇▆▅▄▃▂▁▂▃▄",
        "▅▆▇█▇▆▅▄▃▂▁▂▃▄▅",
        "▆▇█▇▆▅▄▃▂▁▂▃▄▅▆",
        "▇█▇▆▅▄▃▂▁▂▃▄▅▆▇",
        "█▇▆▅▄▃▂▁▂▃▄▅▆▇█"
    ]
    
    while not animation_stop_event.is_set():
        for frame in itertools.cycle(soundwave):
            if animation_stop_event.is_set():
                break
            sys.stdout.write('\r')
            sys.stdout.write(f"Vox Biblios Processing: {frame}")
            sys.stdout.flush()
            time.sleep(0.1)
    
    sys.stdout.write('\r')
    sys.stdout.write(' ' * 30)  # Clear the animation line
    sys.stdout.write('\r')
    sys.stdout.flush()

def update_rss(update_payload):
    try:
        logger.info("Starting RSS update process")
        oldrss = grab_old_rss_file()
        df = parse_old_rss_file(oldrss)
        cost_estimate = estimate_monthly_cost()
        p = create_podcast(cost_estimate)
        
        existing_episodes = set()
        if isinstance(df, str):
            logger.warning("No existing episodes found in RSS feed")
            eplist = []
        else:
            logger.info(f"Found {len(df)} existing episodes in RSS feed")
            eplist = []
            for x in df.index:
                episode = create_episode(df, x)
                if episode:
                    eplist.append(episode)
                    existing_episodes.add(episode.media.url)
        
        # Add the missing episode
        missing_episode = Episode(
            title="Levitsky - Way 2020.txt",
            media=Media("https://s3.us-east-1.amazonaws.com/vox-biblios/key.d4e34fdf-c9b0-433b-b80f-f3295ea5cd7e.mp3"),
            summary="Levitsky - Way 2020.txt",
            publication_date=datetime(2024, 9, 25, 17, 28, 8, tzinfo=timezone.utc)
        )
        eplist.append(missing_episode)
        existing_episodes.add(missing_episode.media.url)
        
        p.episodes = eplist
        
        for y in update_payload:
            if y[0] not in existing_episodes:
                newep = Episode(title=y[1], media=Media(y[0]), summary=y[1], publication_date=y[2])
                p.episodes.append(newep)
                logger.info(f"Added new episode: {y[1]}")
            else:
                logger.info(f"Skipped duplicate episode: {y[1]}")
        
        p.rss_file('voxbiblios.rss')
        logger.info("RSS file updated successfully")
    except Exception as e:
        logger.error(f"Error updating RSS: {str(e)}", exc_info=True)

def grab_old_rss_file():
    try:
        logger.info("Fetching old RSS file")
        response = requests.get('https://vox-biblios.s3.amazonaws.com/voxbiblios.rss')
        response.raise_for_status()
        logger.info("Old RSS file fetched successfully")
        return response
    except requests.RequestException as e:
        logger.error(f"Error fetching old RSS file: {str(e)}", exc_info=True)
        return None

def read_texts_from_folder(folder):
    try:
        logger.info(f"Reading texts from folder: {folder}")
        files = os.listdir(folder)
        dict_of_texts = {}
        for f in files:
            if f.endswith('.txt'):
                logger.debug(f"Processing file: {f}")
                with open(os.path.join(folder, f), 'r') as file:
                    text = file.read()
                    preprocessed_text = preprocess_text(text)
                    dict_of_texts[f] = preprocessed_text
                logger.debug(f"File {f} processed and added to dict_of_texts")
        logger.info(f"Processed {len(dict_of_texts)} text files")
        return dict_of_texts
    except Exception as e:
        logger.error(f"Error reading texts from folder: {str(e)}", exc_info=True)
        return {}

def delete_old_texts(folder):
    try:
        logger.info(f"Deleting old text files from folder: {folder}")
        files = os.listdir(folder)
        deleted_count = 0
        for f in files:
            if f.endswith('.txt'):
                os.remove(os.path.join(folder, f))
                deleted_count += 1
                logger.debug(f"Deleted file: {f}")
        logger.info(f"Deleted {deleted_count} old text files")
    except Exception as e:
        logger.error(f"Error deleting old texts: {str(e)}", exc_info=True)

def fetch_and_process_url(url):
    try:
        logger.info(f"Fetching content from URL: {url}")
        g = Goose()
        article = g.extract(url=url)
        text = article.cleaned_text
        title = article.title
        
        preprocessed_text = preprocess_text(text)
        
        filename = f"{urlparse(url).netloc}_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
        
        logger.info(f"Processed URL content. Title: {title}")
        return filename, preprocessed_text, title
    except Exception as e:
        logger.error(f"Error fetching and processing URL: {str(e)}", exc_info=True)
        return None, None, None

def main(input_source):
    try:
        logger.info(f"Starting main processing with input source: {input_source}")
        
        update_payload = []
        
        if input_source.startswith('http://') or input_source.startswith('https://'):
            # Process URL (keep this part as is)
            filename, text, title = fetch_and_process_url(input_source)
            if filename and text:
                logger.info(f"Sending Polly job for URL: {input_source}")
                chunks = chunk_text(text)
                for i, chunk in enumerate(chunks):
                    resp = send_polly_job(chunk)
                    if resp:
                        timestamp = datetime.now(timezone.utc)
                        sleep(2)
                        chunk_title = f"{title or filename} (Part {i+1})"
                        update_payload.append((resp['SynthesisTask']['OutputUri'], chunk_title, timestamp))
                        logger.debug(f"Polly job completed for URL chunk {i+1}: {input_source}")
                    else:
                        logger.error(f"Failed to process chunk {i+1} for URL: {input_source}")
        else:
            # Process folder
            dict_of_texts = read_texts_from_folder(input_source)
            for filename, text in dict_of_texts.items():
                logger.info(f"Processing file: {filename} (length: {len(text)} characters)")
                chunks = chunk_text(text)
                logger.info(f"File {filename} split into {len(chunks)} chunks")
                for i, chunk in enumerate(chunks):
                    logger.info(f"Sending Polly job for {filename} chunk {i+1}/{len(chunks)} (length: {len(chunk)} characters)")
                    resp = send_polly_job(chunk)
                    if resp:
                        timestamp = datetime.now(timezone.utc)
                        sleep(2)
                        chunk_title = f"{filename} (Part {i+1})" if len(chunks) > 1 else filename
                        update_payload.append((resp['SynthesisTask']['OutputUri'], chunk_title, timestamp))
                        logger.info(f"Polly job completed for {filename} chunk {i+1}/{len(chunks)}")
                    else:
                        logger.error(f"Failed to process {filename} chunk {i+1}/{len(chunks)}")
        
        update_rss(update_payload)
        
        output_file = 'voxbiblios.rss'
        logger.info(f"Uploading RSS file to S3: {output_file}")
        upload_file(output_file, S3_BUCKET)
        
        if not input_source.startswith('http://') and not input_source.startswith('https://'):
            delete_old_texts(input_source)
        
        logger.info("Processing completed successfully")
    except Exception as e:
        logger.error(f"An error occurred in main processing: {str(e)}", exc_info=True)

def parse_arguments():
    parser = argparse.ArgumentParser(description="Vox Biblios: Text-to-Podcast Generator")
    parser.add_argument('input', type=str, nargs='?', default='text-q', help='Input folder containing text files or a URL')
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    input_source = args.input
    
    if not input_source:
        logger.error("Input source is required.")
        exit(1)
    
    global animation_stop_event
    animation_stop_event = threading.Event()

    if not args.verbose:
        animation_thread = threading.Thread(target=animate_soundwave)
        animation_thread.start()

    logger.info(f"Starting Vox Biblios with input source: {input_source}")
    main(input_source)

