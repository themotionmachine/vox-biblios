import os
import requests
import argparse
from datetime import datetime, timezone
from time import sleep

from config import AWS_ACCESS_KEY, AWS_SECRET_KEY, S3_BUCKET
from audio_processing import send_polly_job
from rss_utils import create_podcast, create_episode, parse_old_rss_file, Episode, Media
from text_processing import preprocess_text
from s3_utils import upload_file, delete_file_from_s3  # Update this line
from logging_utils import logger

def update_rss(update_payload):
    try:
        logger.info("Starting RSS update process")
        oldrss = grab_old_rss_file()
        df = parse_old_rss_file(oldrss)
        p = create_podcast()
        
        if isinstance(df, str):
            logger.warning("No existing episodes found in RSS feed")
            eplist = []
        else:
            logger.info(f"Found {len(df)} existing episodes in RSS feed")
            eplist = [create_episode(df, x) for x in df.index]
        
        p.episodes += eplist
        
        for y in update_payload:
            newep = Episode(title=y[1], media=Media(y[0]), summary=y[1], publication_date=y[2])
            p.episodes.append(newep)
            logger.info(f"Added new episode: {y[1]}")
        
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

def main(input_folder, output_file):
    try:
        logger.info(f"Starting main processing with input folder: {input_folder} and output file: {output_file}")
        
        dict_of_texts = read_texts_from_folder(input_folder)
        update_payload = []
        
        for filename, text in dict_of_texts.items():
            logger.info(f"Sending Polly job for file: {filename}")
            resp = send_polly_job(text)
            timestamp = datetime.now(timezone.utc)
            sleep(2)
            update_payload.append((resp['SynthesisTask']['OutputUri'], filename, timestamp))
            logger.debug(f"Polly job completed for file: {filename}")
        
        update_rss(update_payload)
        
        if output_file:
            logger.info(f"Uploading RSS file to S3: {output_file}")
            upload_file(output_file, S3_BUCKET)
        else:
            logger.warning("Output file not specified. Skipping S3 upload.")
        
        delete_old_texts(input_folder)
        
        logger.info("Processing completed successfully")
    except Exception as e:
        logger.error(f"An error occurred in main processing: {str(e)}", exc_info=True)

def parse_arguments():
    parser = argparse.ArgumentParser(description="Vox Biblios: Text-to-Podcast Generator")
    parser.add_argument('--input', type=str, help='Input folder containing text files')
    parser.add_argument('--output', type=str, help='Output RSS file path')
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    
    if not args.input and not args.output:
        # No arguments provided, use default values
        input_folder = 'text-q'
        output_file = 'voxbiblios.rss'
        logger.info(f"No arguments provided. Using default values: input={input_folder}, output={output_file}")
    else:
        # Arguments provided, use them
        input_folder = args.input
        output_file = args.output
        logger.info(f"Starting Vox Biblios with arguments: input={input_folder}, output={output_file}")
        
        if not input_folder or not output_file:
            logger.error("Both input and output arguments are required when providing custom values.")
            exit(1)
    
    main(input_folder, output_file)

