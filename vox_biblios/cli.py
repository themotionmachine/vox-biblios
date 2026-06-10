"""
Command line interface for Vox Biblios.
"""
import argparse
import json
import sys
import textwrap
from typing import List, Optional
import os
from pathlib import Path

from colorama import init, Fore, Style

from vox_biblios.utils.logging import get_logger, SoundWaveAnimation
from vox_biblios.config import config, get_config_sources
from vox_biblios.tts import create_provider, get_available_providers
from vox_biblios.exceptions import ProviderNotFoundError

# Initialize colorama for cross-platform colored terminal output;
# strip color codes when stdout is not a terminal (pipes, agents, cron)
init(strip=not sys.stdout.isatty())

logger = get_logger(__name__)


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """
    Parse command line arguments.

    Args:
        args: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Parsed arguments
    """
    providers = get_available_providers()

    parser = argparse.ArgumentParser(
        description="Vox Biblios: Text-to-Podcast Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          vox-biblios                           # Process text files with default provider (pocket-tts)
          vox-biblios process texts/            # Process all text files in the texts/ directory
          vox-biblios process article.txt       # Process a single text file
          vox-biblios process https://example.com/article  # Process a URL
          vox-biblios process - < article.txt   # Process text from stdin
          vox-biblios process --provider kokoro # Use Kokoro (local MLX) for TTS
          vox-biblios process --output-dir out/ # Local mode: write MP3s, skip AWS/RSS
          vox-biblios process --dry-run texts/  # Show cleaned text without synthesizing
          vox-biblios process --json texts/     # Machine-readable output
          vox-biblios voices                    # List available voices for each provider
          vox-biblios clear                     # Clear the podcast feed
          vox-biblios cost                      # Show AWS cost estimate
          vox-biblios config init               # Initialize configuration file

        Exit codes for 'process': 0 = success, 1 = failure, 2 = partial failure
        """)
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Process command
    process_parser = subparsers.add_parser('process', help='Process text files, a single file, a URL, or stdin')
    process_parser.add_argument(
        'input',
        type=str,
        nargs='?',
        default='text-q',
        help="Input folder, .txt file, URL, or '-' for stdin (default: text-q)"
    )
    process_parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    process_parser.add_argument(
        '--provider',
        type=str,
        choices=providers,
        default=None,
        help=f'TTS provider to use (default: {config.tts.default_provider})'
    )
    process_parser.add_argument(
        '--voice',
        type=str,
        default=None,
        help='Voice to use for TTS (provider-specific)'
    )
    process_parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        metavar='DIR',
        help='Write MP3s to a local directory and skip S3 upload / RSS update (no AWS needed)'
    )
    process_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print the cleaned text that would be synthesized, then exit'
    )
    process_parser.add_argument(
        '--json',
        action='store_true',
        help='Emit machine-readable JSON on stdout'
    )

    # Clear command
    clear_parser = subparsers.add_parser('clear', help='Clear podcast feed')
    clear_parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    # Cost command
    cost_parser = subparsers.add_parser('cost', help='Show AWS cost estimate')
    cost_parser.add_argument(
        '-d', '--days',
        type=int,
        default=30,
        help='Number of days to include in estimate (default: 30)'
    )

    # Version command
    subparsers.add_parser('version', help='Show version information')

    # Config command
    config_parser = subparsers.add_parser('config', help='Manage configuration')
    config_subparsers = config_parser.add_subparsers(dest='config_command', help='Configuration command')
    init_parser = config_subparsers.add_parser('init', help='Initialize configuration file')
    init_parser.add_argument('--non-interactive', action='store_true',
                             help='Write the config from flags without prompting')
    init_parser.add_argument('--force', action='store_true',
                             help='Overwrite an existing config file without asking')
    init_parser.add_argument('--aws-access-key', default=None)
    init_parser.add_argument('--aws-secret-key', default=None)
    init_parser.add_argument('--aws-region', default='us-east-1')
    init_parser.add_argument('--s3-bucket', default='vox-biblios')
    init_parser.add_argument('--polly-voice', default='Joanna')
    init_parser.add_argument('--podcast-name', default='Vox Biblios')
    init_parser.add_argument('--podcast-website', default='vox-biblios.example.com')
    config_subparsers.add_parser('show', help='Show configuration sources')
    config_subparsers.add_parser('edit', help='Edit configuration file')

    # Voices command
    voices_parser = subparsers.add_parser('voices', help='List available TTS voices')
    voices_parser.add_argument(
        '--provider',
        type=str,
        choices=providers,
        default=None,
        help='Show voices for a specific provider only'
    )

    return parser.parse_args(args)


def _resolve_input(input_source: str, json_mode: bool):
    """Normalize the process input: stdin and single files become a temp folder.

    Returns:
        (effective_input, is_url) or raises SystemExit-style error via ValueError
    """
    import tempfile

    if input_source.startswith(('http://', 'https://')):
        return input_source, True

    if input_source == '-':
        text = sys.stdin.read()
        if not text.strip():
            raise ValueError("No text received on stdin")
        temp_dir = tempfile.mkdtemp(prefix='vox-biblios-')
        (Path(temp_dir) / 'stdin.txt').write_text(text, encoding='utf-8')
        return temp_dir, False

    path = Path(input_source)
    if path.is_file():
        if path.suffix.lower() != '.txt':
            raise ValueError(f"Only .txt files are supported, got: {path.name}")
        import shutil
        temp_dir = tempfile.mkdtemp(prefix='vox-biblios-')
        shutil.copy(path, Path(temp_dir) / path.name)
        return temp_dir, False

    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        if not json_mode:
            print(Fore.YELLOW + f"Created input folder: {path}" + Style.RESET_ALL)

    if not path.is_dir():
        raise ValueError(f"Input is neither a folder, a .txt file, nor a URL: {input_source}")

    return str(path), False


def _dry_run(input_source: str, is_url: bool, json_mode: bool) -> int:
    """Print the cleaned text that would be synthesized."""
    from vox_biblios.core.text_processor import TextProcessor
    processor = TextProcessor()

    if is_url:
        from vox_biblios.adapters.web_scraper import WebScraper
        content = WebScraper().extract_content(input_source)
        texts = {content.get('title') or input_source: processor.preprocess(content.get('text', ''))}
    else:
        texts = processor.process_folder(input_source)

    if json_mode:
        payload = {
            'dry_run': True,
            'files': [
                {'name': name, 'cleaned_text': text, 'chars': len(text)}
                for name, text in texts.items()
            ]
        }
        print(json.dumps(payload, indent=2))
    else:
        for name, text in texts.items():
            print(Fore.CYAN + f"--- {name} ({len(text)} chars after cleanup) ---" + Style.RESET_ALL)
            print(text)
            print()

    return 0


def process_command(args: argparse.Namespace) -> int:
    """
    Execute process command.

    Args:
        args: Command line arguments

    Returns:
        Exit code (0 = success, 1 = failure, 2 = partial failure)
    """
    from vox_biblios.core.podcast_manager import PodcastManager

    json_mode = args.json

    if not json_mode:
        print(Fore.CYAN + "Vox Biblios: Processing input source" + Style.RESET_ALL)

    try:
        effective_input, is_url = _resolve_input(args.input, json_mode)
    except ValueError as e:
        if json_mode:
            print(json.dumps({'status': 'error', 'error': str(e)}))
        else:
            print(Fore.RED + f"Error: {e}" + Style.RESET_ALL)
        return 1

    try:
        if args.dry_run:
            return _dry_run(effective_input, is_url, json_mode)

        effective_provider = args.provider or config.tts.default_provider
        if not json_mode:
            source_desc = "URL" if is_url else "folder"
            print(f"Processing {source_desc}: {effective_input}")
            print(f"Using TTS provider: {effective_provider}")
            if args.voice:
                print(f"Using voice: {args.voice}")
            if args.output_dir:
                print(f"Local mode: writing MP3s to {args.output_dir}")

        manager = PodcastManager(
            provider=args.provider,
            voice=args.voice,
            output_dir=args.output_dir,
        )

        animation = None
        if not args.verbose and not json_mode:
            animation = SoundWaveAnimation()
            animation.start()

        try:
            result = manager.process_and_update(effective_input)
        finally:
            if animation:
                animation.stop()

        if json_mode:
            payload = {
                'status': ['success', 'failure', 'partial'][result.exit_code],
                'episodes': [
                    {
                        'title': ep['title'],
                        'url': ep['url'],
                        'description': ep['description'],
                    }
                    for ep in result.episodes
                ],
                'failures': result.failures,
                'rss_url': result.rss_url,
            }
            print(json.dumps(payload, indent=2))
        else:
            for ep in result.episodes:
                print(Fore.GREEN + f"  ✓ {ep['title']}" + Style.RESET_ALL + f" -> {ep['url']}")
            for failure in result.failures:
                print(Fore.RED + f"  ✗ {failure['source']}: {failure['error']}" + Style.RESET_ALL)

            if result.exit_code == 0:
                print(Fore.GREEN + "Processing completed successfully!" + Style.RESET_ALL)
            elif result.exit_code == 2:
                print(Fore.YELLOW + "Processing completed with failures." + Style.RESET_ALL)
            else:
                print(Fore.RED + "Processing failed." + Style.RESET_ALL)

            if result.rss_url:
                print(f"RSS feed available at: {result.rss_url}")

        return result.exit_code

    except Exception as e:
        if json_mode:
            print(json.dumps({'status': 'error', 'error': str(e)}))
        else:
            print(Fore.RED + f"Error: {str(e)}" + Style.RESET_ALL)
        logger.error(f"Processing failed: {str(e)}", exc_info=True)
        return 1


def clear_command(args: argparse.Namespace) -> int:
    """
    Execute clear command.

    Args:
        args: Command line arguments

    Returns:
        Exit code
    """
    print(Fore.CYAN + "Vox Biblios: Clearing podcast feed" + Style.RESET_ALL)

    try:
        from vox_biblios.adapters.rss import PodcastRSSManager
        rss_url = PodcastRSSManager().clear_podcast_feed()

        print(Fore.GREEN + "Podcast feed cleared successfully!" + Style.RESET_ALL)
        print(f"RSS feed available at: {rss_url}")
        return 0

    except Exception as e:
        print(Fore.RED + f"Error: {str(e)}" + Style.RESET_ALL)
        logger.error(f"Clearing podcast feed failed: {str(e)}", exc_info=True)
        return 1


def cost_command(args: argparse.Namespace) -> int:
    """
    Execute cost command.

    Args:
        args: Command line arguments

    Returns:
        Exit code
    """
    print(Fore.CYAN + "Vox Biblios: AWS Cost Estimation" + Style.RESET_ALL)

    try:
        days = args.days
        print(f"Estimating AWS costs for the last {days} days...")

        from vox_biblios.aws.cost import CostEstimationService
        cost_service = CostEstimationService()

        try:
            monthly = cost_service.get_monthly_cost(days=days)
            services = cost_service.get_service_costs(days=days)

            print(Fore.GREEN + f"\nTotal cost (last {days} days): {monthly['formatted']}" + Style.RESET_ALL)
            print("\nCost breakdown by service:")

            sorted_services = sorted(services.items(), key=lambda x: x[1], reverse=True)

            for service, cost in sorted_services:
                if cost > 0.01:  # Only show services with meaningful costs
                    percentage = (cost / monthly['cost']) * 100
                    print(f"- {service}: ${cost:.2f} ({percentage:.1f}%)")

            try:
                forecast = cost_service.get_cost_forecast()
                print(Fore.YELLOW + f"\nForecast for next 30 days: {forecast['formatted']}" + Style.RESET_ALL)
            except Exception as e:
                logger.warning(f"Failed to get cost forecast: {str(e)}")

            return 0

        except Exception as e:
            print(Fore.RED + f"Error: {str(e)}" + Style.RESET_ALL)
            logger.error(f"Cost estimation failed: {str(e)}", exc_info=True)
            return 1

    except Exception as e:
        print(Fore.RED + f"Error: {str(e)}" + Style.RESET_ALL)
        logger.error(f"Unexpected error in cost command: {str(e)}", exc_info=True)
        return 1


def version_command(_: argparse.Namespace) -> int:
    """
    Execute version command.

    Args:
        _: Command line arguments (unused)

    Returns:
        Exit code
    """
    from vox_biblios import __version__
    print(Fore.CYAN + "Vox Biblios: Text-to-Podcast Generator" + Style.RESET_ALL)
    print(f"Version: {__version__}")
    print("Author: Ryan Williams")
    return 0


def _write_config_file(config_file: Path, values: dict) -> None:
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_content = f"""# Vox Biblios Configuration
# Generated by: vox-biblios config init

# AWS Credentials (required for S3/RSS publishing and Polly; not needed
# for local mode: vox-biblios process --output-dir DIR)
AWS_ACCESS_KEY={values['aws_access_key']}
AWS_SECRET_KEY={values['aws_secret_key']}

# AWS Settings
AWS_REGION={values['aws_region']}
S3_BUCKET={values['s3_bucket']}
POLLY_VOICE_ID={values['polly_voice']}
POLLY_ENGINE=neural
POLLY_FORMAT=mp3
POLLY_KEY_PREFIX=audio

# Podcast Settings
PODCAST_NAME={values['podcast_name']}
PODCAST_DESCRIPTION=I speak with the voices of all the words I've seen.
PODCAST_WEBSITE={values['podcast_website']}
PODCAST_EXPLICIT=false

# Optional Settings
# TTS_PROVIDER=pocket-tts
# TTS_VOICE=
# POCKET_TTS_VOICE=alba
# POCKET_TTS_MODEL=english_2026-04
# PREVIEW_LENGTH=100
# CHUNK_SIZE=90000
# LOG_LEVEL=INFO
# RSS_FILENAME=voxbiblios.rss
# PODCAST_IMAGE=https://example.com/image.jpg
"""
    config_file.write_text(config_content)


def config_command(args: argparse.Namespace) -> int:
    """
    Execute config command.

    Args:
        args: Command line arguments

    Returns:
        Exit code
    """
    if not args.config_command:
        print(Fore.RED + "Error: Please specify a config subcommand (init, show, or edit)" + Style.RESET_ALL)
        return 1

    if args.config_command == 'show':
        print(Fore.CYAN + "Vox Biblios: Configuration Sources" + Style.RESET_ALL)
        sources = get_config_sources()

        if sources:
            print("\nConfiguration loaded from:")
            for source in sources:
                print(f"  - {source}")
        else:
            print("\nNo configuration files found.")
            print("Using environment variables only.")

        print("\n" + Fore.YELLOW + "Configuration file priority:" + Style.RESET_ALL)
        print("  1. ./.env.local (current directory)")
        print("  2. ~/.config/vox-biblios/config.env (XDG config)")
        print("  3. ~/.vox-biblios.env (home directory)")
        print("  4. Environment variables")

        return 0

    elif args.config_command == 'init':
        print(Fore.CYAN + "Vox Biblios: Initialize Configuration" + Style.RESET_ALL)

        xdg_config_home = os.getenv('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
        config_dir = Path(xdg_config_home) / 'vox-biblios'
        config_file = config_dir / 'config.env'

        if config_file.exists() and not args.force:
            if args.non_interactive:
                print(Fore.RED + f"Error: {config_file} already exists. Use --force to overwrite." + Style.RESET_ALL)
                return 1
            print(f"\nConfiguration file already exists at: {config_file}")
            response = input("Overwrite? (y/N): ").strip().lower()
            if response != 'y':
                print("Cancelled.")
                return 0

        try:
            if args.non_interactive:
                values = {
                    'aws_access_key': args.aws_access_key or '',
                    'aws_secret_key': args.aws_secret_key or '',
                    'aws_region': args.aws_region,
                    's3_bucket': args.s3_bucket,
                    'polly_voice': args.polly_voice,
                    'podcast_name': args.podcast_name,
                    'podcast_website': args.podcast_website,
                }
            else:
                print("\nEnter your configuration values (press Enter to use defaults).")
                print("AWS credentials are optional if you only use local mode (--output-dir).\n")

                values = {
                    'aws_access_key': input("AWS_ACCESS_KEY (blank for local-only): ").strip(),
                    'aws_secret_key': input("AWS_SECRET_KEY (blank for local-only): ").strip(),
                    'aws_region': input(f"AWS_REGION [{args.aws_region}]: ").strip() or args.aws_region,
                    's3_bucket': input(f"S3_BUCKET [{args.s3_bucket}]: ").strip() or args.s3_bucket,
                    'polly_voice': input(f"POLLY_VOICE_ID [{args.polly_voice}]: ").strip() or args.polly_voice,
                    'podcast_name': input(f"PODCAST_NAME [{args.podcast_name}]: ").strip() or args.podcast_name,
                    'podcast_website': input(f"PODCAST_WEBSITE [{args.podcast_website}]: ").strip() or args.podcast_website,
                }

            _write_config_file(config_file, values)

            print(Fore.GREEN + f"\nConfiguration file created at: {config_file}" + Style.RESET_ALL)
            if not values['aws_access_key']:
                print(Fore.YELLOW + "No AWS credentials set: use --output-dir for local processing." + Style.RESET_ALL)
            print("\nYou can edit this file anytime with:")
            print("  vox-biblios config edit")

            return 0

        except Exception as e:
            print(Fore.RED + f"Error: Failed to create configuration file: {str(e)}" + Style.RESET_ALL)
            logger.error(f"Config init failed: {str(e)}", exc_info=True)
            return 1

    elif args.config_command == 'edit':
        print(Fore.CYAN + "Vox Biblios: Edit Configuration" + Style.RESET_ALL)

        sources = get_config_sources()

        if sources:
            config_file = Path(sources[0])  # Use first (highest priority) config file
            print(f"\nOpening: {config_file}")
        else:
            xdg_config_home = os.getenv('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
            config_file = Path(xdg_config_home) / 'vox-biblios' / 'config.env'

            print("\nNo configuration file found.")
            print(f"Creating new file at: {config_file}")

            try:
                config_file.parent.mkdir(parents=True, exist_ok=True)
                if not config_file.exists():
                    config_file.write_text("# Vox Biblios Configuration\n# Add your settings here\n\n")
            except Exception as e:
                print(Fore.RED + f"Error: Failed to create config file: {str(e)}" + Style.RESET_ALL)
                return 1

        editor = os.getenv('EDITOR', 'nano')
        try:
            import subprocess
            result = subprocess.run([editor, str(config_file)])
            if result.returncode == 0:
                print(Fore.GREEN + "\nConfiguration updated." + Style.RESET_ALL)
                return 0
            else:
                print(Fore.RED + f"\nError: Editor exited with code {result.returncode}" + Style.RESET_ALL)
                return result.returncode
        except Exception as e:
            print(Fore.RED + f"Error: Failed to open editor: {str(e)}" + Style.RESET_ALL)
            print(f"\nYou can manually edit the file at: {config_file}")
            return 1

    return 0


def voices_command(args: argparse.Namespace) -> int:
    """
    Execute voices command - list available TTS voices.

    Args:
        args: Command line arguments

    Returns:
        Exit code
    """
    print(Fore.CYAN + "Vox Biblios: Available TTS Voices" + Style.RESET_ALL)

    providers_to_show = [args.provider] if args.provider else get_available_providers()

    for provider_name in providers_to_show:
        print(f"\n{Fore.GREEN}{provider_name}{Style.RESET_ALL}:")
        try:
            provider = create_provider(provider_name)
            voices = provider.get_available_voices()
            if voices:
                for voice in voices:
                    print(f"  - {voice}")
            else:
                print("  (no voices available or unable to retrieve)")
        except ProviderNotFoundError as e:
            print(f"  {Fore.RED}Error: {e}{Style.RESET_ALL}")
        except Exception as e:
            print(f"  {Fore.YELLOW}Unable to load provider: {e}{Style.RESET_ALL}")

    print(f"\n{Fore.YELLOW}Note:{Style.RESET_ALL} Default provider is '{config.tts.default_provider}'")
    print("Use --provider and --voice flags with the 'process' command to select.")

    return 0


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code
    """
    args = parse_args()

    # If no command is provided, default to 'process text-q'
    if not args.command:
        logger.info("No command specified, defaulting to 'process text-q'")
        args = parse_args(['process', 'text-q'])

    if args.command == 'process':
        return process_command(args)
    elif args.command == 'clear':
        return clear_command(args)
    elif args.command == 'cost':
        return cost_command(args)
    elif args.command == 'version':
        return version_command(args)
    elif args.command == 'config':
        return config_command(args)
    elif args.command == 'voices':
        return voices_command(args)
    else:
        print(Fore.RED + f"Error: Unknown command: {args.command}" + Style.RESET_ALL)
        return 1


if __name__ == "__main__":
    sys.exit(main())
