# Vox Biblios

A personal text-to-podcast generator that converts text files and web content into podcast episodes.

## Features

- **Text-to-Podcast Conversion**: Process text files or web content into audio podcast episodes
- **Multiple TTS Providers**:
  - **Pocket TTS** (default): High-quality local neural TTS with multiple voices (alba, marius, javert, jean, fantine, cosette, eponine, azelma)
  - **AWS Polly**: Cloud-based neural TTS with many voice options
  - **macOS Say**: Quick local generation using built-in macOS speech synthesis
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
- **ffmpeg**: Required for Pocket TTS audio conversion (`brew install ffmpeg` on macOS)
- AWS account with S3 access (required for storing audio files)
- AWS credentials configured

### Platform-Specific Features

**All platforms:**
- Pocket TTS (default): Local neural TTS, requires ffmpeg for WAV to MP3 conversion
- AWS Polly: Cloud TTS (requires AWS account and credentials)

**macOS only:**
- `--provider say` uses macOS built-in `say` and `afconvert` commands

### Global Installation (Recommended)

Install vox-biblios as a global command that works from any directory without virtual environment activation.

#### Option 1: Using uv (Recommended)

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/themotionmachine/vox-biblios.git
cd vox-biblios

# Install vox-biblios globally from local directory
uv tool install .
```

Or install directly from GitHub without cloning:

```bash
uv tool install git+https://github.com/themotionmachine/vox-biblios.git
```

#### Option 2: Using pipx

```bash
# Install pipx if not already installed
python3 -m pip install --user pipx
pipx ensurepath

# Clone the repository
git clone https://github.com/themotionmachine/vox-biblios.git
cd vox-biblios

# Install vox-biblios globally from local directory
pipx install .
```

Or install directly from GitHub:

```bash
pipx install git+https://github.com/themotionmachine/vox-biblios.git
```

After installation, the `vox-biblios` command will be available globally:

```bash
vox-biblios config init    # Set up configuration
vox-biblios process text-q/  # Use from anywhere
```

> **Note**: Once published to PyPI, you'll be able to install with just `uv tool install vox-biblios` or `pipx install vox-biblios`.

### Development Installation

For local development or if you prefer the project-based approach:

#### Quick Setup with Scripts

```bash
# Install and set up Vox Biblios
./setup_voxbiblios.sh

# Run Vox Biblios (automatically activates venv)
./run_voxbiblios.sh [command]
```

#### Manual Setup with uv

```bash
# Create and activate a virtual environment
uv venv
source .venv/bin/activate

# Install in development mode
uv sync

# Use the command (within activated venv)
vox-biblios [command]
```

## Configuration

Vox Biblios reads configuration from environment variables and config files. Configuration files are searched in the following priority order:

1. `./.env.local` (current directory - for development)
2. `~/.config/vox-biblios/config.env` (XDG config directory - recommended for global install)
3. `~/.vox-biblios.env` (home directory - alternative location)
4. Environment variables already set in your shell

### Quick Configuration Setup

For global installation, use the interactive config initialization:

```bash
vox-biblios config init
```

This will guide you through setting up your configuration file at `~/.config/vox-biblios/config.env`.

### Manual Configuration

Create a configuration file in one of the locations above:

```bash
# For global installation (recommended)
mkdir -p ~/.config/vox-biblios
nano ~/.config/vox-biblios/config.env

# OR for development (project directory)
nano .env.local
```

Add your configuration settings:

```bash
# Required
AWS_ACCESS_KEY=your_access_key_here
AWS_SECRET_KEY=your_secret_key_here

# Optional (with defaults shown)
AWS_REGION=us-east-1
S3_BUCKET=vox-biblios
POLLY_VOICE_ID=Joanna
PODCAST_NAME=Vox Biblios
PODCAST_WEBSITE=vox-biblios.example.com
```

### Configuration Management Commands

```bash
vox-biblios config show  # Show where configuration is loaded from
vox-biblios config init  # Interactive configuration setup
vox-biblios config edit  # Edit configuration in your default editor
```

### Available Configuration Variables

Required environment variables:

- `AWS_ACCESS_KEY`: Your AWS access key
- `AWS_SECRET_KEY`: Your AWS secret key

TTS configuration:

- `TTS_PROVIDER`: Default TTS provider (default: pocket-tts). Options: pocket-tts, polly, say
- `TTS_VOICE`: Default voice for TTS (provider-specific)
- `POCKET_TTS_VOICE`: Default voice for Pocket TTS (default: alba). Options: alba, marius, javert, jean, fantine, cosette, eponine, azelma

Optional environment variables:

- `PREVIEW_LENGTH`: Number of text characters to include in episode descriptions (default: 100)
- `CHUNK_SIZE`: Maximum character size for text chunks (default: 90000)
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

### Default Behavior

When run without arguments, Vox Biblios processes all `.txt` files in the `text-q` directory (created automatically if it doesn't exist):

```bash
vox-biblios  # Processes text-q/ directory
```

### Basic Commands

Process text files in a directory (uses Pocket TTS by default):

```bash
vox-biblios process path/to/text/files/
```

Process content from a URL:

```bash
vox-biblios process https://example.com/article
```

### TTS Provider Selection

Use a specific TTS provider:

```bash
# Use Pocket TTS (default) - local neural TTS
vox-biblios process path/to/text/files/

# Use AWS Polly - cloud neural TTS
vox-biblios process --provider polly path/to/text/files/

# Use macOS say - local system TTS (macOS only)
vox-biblios process --provider say path/to/text/files/
```

Select a specific voice:

```bash
# Use a different Pocket TTS voice
vox-biblios process --voice marius path/to/text/files/

# Use a specific Polly voice
vox-biblios process --provider polly --voice Matthew path/to/text/files/
```

List available voices for all providers:

```bash
vox-biblios voices

# Or for a specific provider
vox-biblios voices --provider pocket-tts
```

### Other Commands

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
- `--provider {pocket-tts,polly,say}`: TTS provider to use (default: pocket-tts)
- `--voice VOICE`: Voice to use for TTS (provider-specific)
- `-v, --verbose`: Enable verbose output for debugging
- `--use-local-speech`: DEPRECATED - use `--provider say` instead

### Text File Format

Vox Biblios accepts any plain text files with `.txt` extension. No special formatting is required.

### RSS Feed

The generated RSS feed is uploaded to your S3 bucket and is available at:

```
https://s3.{region}.amazonaws.com/{bucket}/{rss_filename}
```

This URL can be added to podcast players to subscribe to your generated podcast.

### Scripting and Automation

Vox Biblios can be integrated into automation pipelines. When installed globally, you can use the `vox-biblios` command directly in shell scripts without any virtual environment setup.

```bash
#!/bin/bash
# nightly.sh - run from cron or other schedulers
set -e

# Process a folder of new articles
vox-biblios process /data/new-articles
```

For development installations, use the provided wrapper script:

```bash
#!/bin/bash
# nightly.sh - for development setup
set -e

cd /path/to/vox-biblios
./run_voxbiblios.sh process /data/new-articles
```

Schedule this script with `cron` or another job runner to automatically convert new text files and upload the updated RSS feed.



## Architecture

Vox Biblios follows a modular architecture:

- **Core**: Central podcast manager and text processing
- **TTS**: Unified TTS provider interface with implementations for Pocket TTS, AWS Polly, and macOS Say
- **AWS**: Integration with AWS services (Polly, S3, Cost Explorer)
- **Adapters**: External service integrations (RSS, web scraper)
- **Utils**: Shared utilities (logging, helpers)
- **CLI**: Command line interface

## License

This project is licensed under the MIT License - see the LICENSE file for details
