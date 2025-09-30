# Vox Biblios

A personal text-to-podcast generator that converts text files and web content into podcast episodes.

## Features

- **Text-to-Podcast Conversion**: Process text files or web content into audio podcast episodes
- **Local and AWS TTS**: Uses macOS `say` for quick, offline generation with automatic AIFF to M4A conversion, and falls back to AWS Polly neural voices when needed
- **RSS Feed Generation**: Automatically generate and update an RSS feed for podcast distribution
- **Text Previews**: Includes text previews in episode descriptions for better context
- **Cost Monitoring**: Built-in AWS cost estimation and monitoring
- **Web Scraping**: Extract content from URLs for processing
- **Automatic Text Cleanup**: Removes URLs, noise, long numbers and bibliography sections before conversion
- **Flexible Input**: Accept local text files or web URLs
- **Command Line Interface**: Easy-to-use CLI for all operations

## Installation

### Prerequisites

- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) package manager 
- AWS account with Polly and S3 access (in order to use AWS Polly)
- AWS credentials configured

### Quick Installation

The simplest way to install and run Vox Biblios is using the provided scripts:

```bash
# Install and set up Vox Biblios
./setup_voxbiblios.sh

# Run Vox Biblios
./run_voxbiblios.sh [command]
```

### Manual Installation with uv

If you prefer a manual installation:

```bash
# Create and activate a virtual environment
uv venv
source .venv/bin/activate

# Install in development mode
uv sync
```

## Configuration

Vox Biblios reads configuration from environment variables. Create a `.env.local` file in the project root and add your settings:

```bash
touch .env.local
nano .env.local  # Edit with your configuration
```

Required environment variables:

- `AWS_ACCESS_KEY`: Your AWS access key
- `AWS_SECRET_KEY`: Your AWS secret key

Optional environment variables:

- `PREVIEW_LENGTH`: Number of text characters to include in episode descriptions (default: 100)
- `CHUNK_SIZE`: Maximum character size for Polly text chunks (default: 90000)
- `AWS_REGION`: AWS region to use (default: us-east-1)
- `S3_BUCKET`: S3 bucket for storing audio files (default: vox-biblios)
- `POLLY_VOICE_ID`: AWS Polly voice to use (default: Joanna)
- `POLLY_ENGINE`: Polly engine to use (default: neural)
- `POLLY_FORMAT`: Output audio format (default: mp3)
- `POLLY_KEY_PREFIX`: S3 key prefix for audio files (default: audio)
- `RSS_FILENAME`: Name of the RSS feed file (default: voxbiblios.rss)
- `PODCAST_NAME`: Podcast title (default: Vox Biblios)
- `PODCAST_DESCRIPTION`: Podcast description
- `PODCAST_WEBSITE`: Website URL for the podcast
- `PODCAST_IMAGE`: URL to podcast artwork
- `LOG_LEVEL`: Logging level (default: INFO)

All other settings have sensible defaults, but you can customize them as needed.

## Usage

### Basic Commands

Process text files in a directory:

```bash
vox-biblios process path/to/text/files/
```

Process content from a URL:

```bash
vox-biblios process https://example.com/article
```

Process using macOS "say" command instead of AWS Polly:

```bash
vox-biblios process --use-local-speech path/to/text/files/
```

Clear the podcast feed:

```bash
vox-biblios clear
```

Check AWS cost estimates:

```bash
vox-biblios cost
```

Show version information:

```bash
vox-biblios version
```

### Command Options

**Process Command Options:**
- `--use-local-speech`: Use macOS "say" command instead of AWS Polly for text-to-speech generation. This option allows you to generate audio locally without AWS costs, though the audio quality may differ from AWS Polly's neural voices.
- `-v, --verbose`: Enable verbose output for debugging

### Text File Format

Vox Biblios accepts any plain text files with `.txt` extension. No special formatting is required.

### RSS Feed

The generated RSS feed is uploaded to your S3 bucket and is available at:

```
https://s3.{region}.amazonaws.com/{bucket}/{rss_filename}
```

This URL can be added to podcast players to subscribe to your generated podcast.

### Scripting and Automation

Vox Biblios can be integrated into automation pipelines. Use the `vox-biblios` CLI in shell scripts to process new text and update your feed.

```bash
#!/bin/bash
# nightly.sh - run from cron or other schedulers
set -e

# Navigate to the Vox Biblios project
cd /path/to/vox-biblios

# Activate the environment and process a folder of new articles
./run_voxbiblios.sh process /data/new-articles
```

Schedule this script with `cron` or another job runner to automatically convert new text files and upload the updated RSS feed.



## Architecture

Vox Biblios follows a modular architecture:

- **Core**: Central podcast manager and text processing
- **AWS**: Integration with AWS services (Polly, S3, Cost Explorer)
- **Adapters**: External service integrations (RSS, web scraper)
- **Utils**: Shared utilities (logging, helpers)
- **CLI**: Command line interface

## License

This project is licensed under the MIT License - see the LICENSE file for details
