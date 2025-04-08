# Vox Biblios

A personal text-to-podcast generator that converts text files and web content into podcast episodes.

## Features

- **Text-to-Podcast Conversion**: Process text files or web content into audio podcast episodes
- **AWS Polly Integration**: High-quality text-to-speech using AWS Polly neural voices
- **RSS Feed Generation**: Automatically generate and update an RSS feed for podcast distribution
- **Cost Monitoring**: Built-in AWS cost estimation and monitoring
- **Web Scraping**: Extract content from URLs for processing
- **Flexible Input**: Accept local text files or web URLs
- **Command Line Interface**: Easy-to-use CLI for all operations

## Installation

### Prerequisites

- Python 3.8 or higher
- AWS account with Polly and S3 access
- AWS credentials configured

### Installation from PyPI

```bash
pip install vox-biblios
```

### Installation from Source

```bash
git clone https://github.com/username/vox-biblios.git
cd vox-biblios
pip install -e .
```

## Configuration

Vox Biblios uses environment variables for configuration. Copy the `.env.example` file to `.env` and customize:

```bash
cp .env.example .env
nano .env  # Edit with your settings
```

Required environment variables:

- `AWS_ACCESS_KEY`: Your AWS access key
- `AWS_SECRET_KEY`: Your AWS secret key

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

### Text File Format

Vox Biblios accepts any plain text files with `.txt` extension. No special formatting is required.

### RSS Feed

The generated RSS feed is uploaded to your S3 bucket and is available at:

```
https://s3.{region}.amazonaws.com/{bucket}/{rss_filename}
```

This URL can be added to podcast players to subscribe to your generated podcast.

## Development

### Setting Up Development Environment

```bash
# Clone the repository
git clone https://github.com/username/vox-biblios.git
cd vox-biblios

# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

### Code Quality

Maintain code quality with:

```bash
# Format code
black vox_biblios tests

# Sort imports
isort vox_biblios tests

# Type checking
mypy vox_biblios

# Linting
flake8 vox_biblios tests
```

## Architecture

Vox Biblios follows a modular architecture:

- **Core**: Central podcast manager and text processing
- **AWS**: Integration with AWS services (Polly, S3, Cost Explorer)
- **Adapters**: External service integrations (RSS, web scraper)
- **Utils**: Shared utilities (logging, helpers)
- **CLI**: Command line interface

## License

This project is licensed under the MIT License - see the LICENSE file for details.