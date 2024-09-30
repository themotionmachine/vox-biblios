# Vox Biblios 

## A Personal Text-to-Podcast Generator

Vox Biblios is a versatile personal podcast generator built using Python. It allows users to convert text files or web content into podcast episodes and publish them to an RSS feed.

### Features

1. **Text-to-Podcast Conversion**: Converts text files or web content into podcast episodes.
2. **RSS Feed Generation**: Generates and updates an RSS feed for the podcast.
3. **Amazon Polly Integration**: Utilizes Amazon Polly to convert text to speech and upload the audio to an S3 bucket.
4. **Web Content Processing**: Ability to fetch and process content from URLs.
5. **Flexible Input**: Accepts either a folder path containing text files or a URL as input.

### Usage

To use Vox Biblios, run the following command:



## Todo
implement: https://claude.ai/chat/62eaca82-ee1c-4860-b8e2-869c357bab9f

## Notes

- The `chunk_text` function is designed to split the text into chunks of 99,000 characters each.
- The `send_polly_job` function is used to send the text to Amazon Polly for conversion to speech.
- The `update_rss` function is used to update the RSS feed with the new podcast episode.
- The `upload_file` function is used to upload the RSS feed to an S3 bucket.
- The `delete_old_texts` function is used to delete old text files from the input folder.