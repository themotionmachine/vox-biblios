"""
Command line interface for Vox Biblios.
"""
import argparse
import sys
import textwrap
from typing import List, Optional
import os
from pathlib import Path

from colorama import init, Fore, Style

from vox_biblios.core.podcast_manager import PodcastManager
from vox_biblios.utils.logging import get_logger, SoundWaveAnimation
from vox_biblios.config import config, get_config_sources

# Initialize colorama for cross-platform colored terminal output
init()

logger = get_logger(__name__)


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """
    Parse command line arguments.
    
    Args:
        args: Command line arguments (defaults to sys.argv[1:])
        
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Vox Biblios: Text-to-Podcast Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          vox-biblios                           # Process all text files in the default text-q directory
          vox-biblios process texts/            # Process all text files in the texts/ directory
          vox-biblios process https://example.com/  # Process content from URL
          vox-biblios clear                     # Clear the podcast feed
          vox-biblios cost                      # Show AWS cost estimate
          vox-biblios config init               # Initialize configuration file
          vox-biblios config show               # Show configuration sources
        """)
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Process command
    process_parser = subparsers.add_parser('process', help='Process text files or URL')
    process_parser.add_argument(
        'input',
        type=str,
        nargs='?',
        default='text-q',  # Default to text-q folder if not specified
        help='Input folder containing text files or a URL (default: text-q)'
    )
    process_parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    process_parser.add_argument(
        '--use-local-speech',
        action='store_true',
        help='Use macOS "say" command instead of AWS Polly for text-to-speech'
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
    config_subparsers.add_parser('init', help='Initialize configuration file')
    config_subparsers.add_parser('show', help='Show configuration sources')
    config_subparsers.add_parser('edit', help='Edit configuration file')

    # Parse args
    return parser.parse_args(args)


def process_command(args: argparse.Namespace) -> int:
    """
    Execute process command.
    
    Args:
        args: Command line arguments
        
    Returns:
        Exit code
    """
    print(Fore.CYAN + "🎙 Vox Biblios: Processing input source" + Style.RESET_ALL)
    
    try:
        # Validate input source
        input_source = args.input
        
        if input_source.startswith(('http://', 'https://')):
            print(f"Processing content from URL: {input_source}")
        else:
            # Check if folder exists
            if not os.path.exists(input_source) or not os.path.isdir(input_source):
                # Create the folder if it doesn't exist
                try:
                    os.makedirs(input_source)
                    print(Fore.YELLOW + f"Created input folder: {input_source}" + Style.RESET_ALL)
                except Exception as e:
                    print(Fore.RED + f"Error: Could not create folder {input_source}: {str(e)}" + Style.RESET_ALL)
                    return 1
            
            print(f"Processing text files from folder: {input_source}")
        
        # Create and use podcast manager
        use_local_speech = getattr(args, 'use_local_speech', False)
        manager = PodcastManager(use_local_speech=use_local_speech)
        
        if not args.verbose:
            # Show animation during processing
            animation = SoundWaveAnimation()
            animation.start()
        
        try:
            rss_url = manager.process_and_update(input_source)
            
            if not args.verbose:
                animation.stop()
            
            print(Fore.GREEN + "✅ Processing completed successfully!" + Style.RESET_ALL)
            print(f"RSS feed available at: {rss_url}")
            return 0
            
        except Exception as e:
            if not args.verbose:
                animation.stop()
            
            print(Fore.RED + f"Error: {str(e)}" + Style.RESET_ALL)
            logger.error(f"Processing failed: {str(e)}", exc_info=True)
            return 1
            
    except Exception as e:
        print(Fore.RED + f"Error: {str(e)}" + Style.RESET_ALL)
        logger.error(f"Unexpected error in process command: {str(e)}", exc_info=True)
        return 1


def clear_command(args: argparse.Namespace) -> int:
    """
    Execute clear command.
    
    Args:
        args: Command line arguments
        
    Returns:
        Exit code
    """
    print(Fore.CYAN + "🧹 Vox Biblios: Clearing podcast feed" + Style.RESET_ALL)
    
    try:
        # Create and use podcast manager
        manager = PodcastManager(use_local_speech=False)
        
        try:
            rss_url = manager.clear_podcast_feed()
            
            print(Fore.GREEN + "✅ Podcast feed cleared successfully!" + Style.RESET_ALL)
            print(f"RSS feed available at: {rss_url}")
            return 0
            
        except Exception as e:
            print(Fore.RED + f"Error: {str(e)}" + Style.RESET_ALL)
            logger.error(f"Clearing podcast feed failed: {str(e)}", exc_info=True)
            return 1
            
    except Exception as e:
        print(Fore.RED + f"Error: {str(e)}" + Style.RESET_ALL)
        logger.error(f"Unexpected error in clear command: {str(e)}", exc_info=True)
        return 1


def cost_command(args: argparse.Namespace) -> int:
    """
    Execute cost command.
    
    Args:
        args: Command line arguments
        
    Returns:
        Exit code
    """
    print(Fore.CYAN + "💰 Vox Biblios: AWS Cost Estimation" + Style.RESET_ALL)
    
    try:
        days = args.days
        print(f"Estimating AWS costs for the last {days} days...")
        
        # Create and use cost estimation service
        from vox_biblios.aws.cost import CostEstimationService
        cost_service = CostEstimationService()
        
        try:
            # Get monthly cost
            monthly = cost_service.get_monthly_cost(days=days)
            
            # Get service breakdown
            services = cost_service.get_service_costs(days=days)
            
            # Display results
            print(Fore.GREEN + f"\nTotal cost (last {days} days): {monthly['formatted']}" + Style.RESET_ALL)
            print("\nCost breakdown by service:")
            
            # Sort services by cost
            sorted_services = sorted(services.items(), key=lambda x: x[1], reverse=True)
            
            for service, cost in sorted_services:
                if cost > 0.01:  # Only show services with meaningful costs
                    percentage = (cost / monthly['cost']) * 100
                    print(f"- {service}: ${cost:.2f} ({percentage:.1f}%)")
            
            # Display forecast
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
        print(Fore.CYAN + "📋 Vox Biblios: Configuration Sources" + Style.RESET_ALL)
        sources = get_config_sources()

        if sources:
            print("\nConfiguration loaded from:")
            for source in sources:
                print(f"  ✓ {source}")
        else:
            print("\n⚠️  No configuration files found.")
            print("Using environment variables only.")

        print("\n" + Fore.YELLOW + "Configuration file priority:" + Style.RESET_ALL)
        print("  1. ./.env.local (current directory)")
        print("  2. ~/.config/vox-biblios/config.env (XDG config)")
        print("  3. ~/.vox-biblios.env (home directory)")
        print("  4. Environment variables")

        return 0

    elif args.config_command == 'init':
        print(Fore.CYAN + "🔧 Vox Biblios: Initialize Configuration" + Style.RESET_ALL)

        # Determine config location
        xdg_config_home = os.getenv('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
        config_dir = Path(xdg_config_home) / 'vox-biblios'
        config_file = config_dir / 'config.env'

        # Check if config already exists
        if config_file.exists():
            print(f"\n⚠️  Configuration file already exists at: {config_file}")
            response = input("Overwrite? (y/N): ").strip().lower()
            if response != 'y':
                print("Cancelled.")
                return 0

        # Create config directory
        try:
            config_dir.mkdir(parents=True, exist_ok=True)

            # Interactive prompts for configuration
            print("\nEnter your configuration values (press Enter to use defaults):\n")

            aws_access_key = input("AWS_ACCESS_KEY (required): ").strip()
            aws_secret_key = input("AWS_SECRET_KEY (required): ").strip()

            if not aws_access_key or not aws_secret_key:
                print(Fore.RED + "\nError: AWS credentials are required." + Style.RESET_ALL)
                return 1

            aws_region = input("AWS_REGION [us-east-1]: ").strip() or "us-east-1"
            s3_bucket = input("S3_BUCKET [vox-biblios]: ").strip() or "vox-biblios"
            polly_voice = input("POLLY_VOICE_ID [Joanna]: ").strip() or "Joanna"
            podcast_name = input("PODCAST_NAME [Vox Biblios]: ").strip() or "Vox Biblios"
            podcast_website = input("PODCAST_WEBSITE [vox-biblios.example.com]: ").strip() or "vox-biblios.example.com"

            # Write config file
            config_content = f"""# Vox Biblios Configuration
# Generated by: vox-biblios config init

# Required AWS Credentials
AWS_ACCESS_KEY={aws_access_key}
AWS_SECRET_KEY={aws_secret_key}

# AWS Settings
AWS_REGION={aws_region}
S3_BUCKET={s3_bucket}
POLLY_VOICE_ID={polly_voice}
POLLY_ENGINE=neural
POLLY_FORMAT=mp3
POLLY_KEY_PREFIX=audio

# Podcast Settings
PODCAST_NAME={podcast_name}
PODCAST_DESCRIPTION=I speak with the voices of all the words I've seen.
PODCAST_WEBSITE={podcast_website}
PODCAST_EXPLICIT=false

# Optional Settings
# PREVIEW_LENGTH=100
# CHUNK_SIZE=90000
# LOG_LEVEL=INFO
# RSS_FILENAME=voxbiblios.rss
# PODCAST_IMAGE=https://example.com/image.jpg
"""

            config_file.write_text(config_content)
            print(Fore.GREEN + f"\n✅ Configuration file created at: {config_file}" + Style.RESET_ALL)
            print("\nYou can edit this file anytime with:")
            print(f"  vox-biblios config edit")

            return 0

        except Exception as e:
            print(Fore.RED + f"Error: Failed to create configuration file: {str(e)}" + Style.RESET_ALL)
            logger.error(f"Config init failed: {str(e)}", exc_info=True)
            return 1

    elif args.config_command == 'edit':
        print(Fore.CYAN + "📝 Vox Biblios: Edit Configuration" + Style.RESET_ALL)

        # Find existing config file or suggest creation
        sources = get_config_sources()

        if sources:
            config_file = Path(sources[0])  # Use first (highest priority) config file
            print(f"\nOpening: {config_file}")
        else:
            # No config file exists, suggest standard location
            xdg_config_home = os.getenv('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
            config_file = Path(xdg_config_home) / 'vox-biblios' / 'config.env'

            print(f"\n⚠️  No configuration file found.")
            print(f"Creating new file at: {config_file}")

            # Create directory and empty file
            try:
                config_file.parent.mkdir(parents=True, exist_ok=True)
                if not config_file.exists():
                    config_file.write_text("# Vox Biblios Configuration\n# Add your settings here\n\n")
            except Exception as e:
                print(Fore.RED + f"Error: Failed to create config file: {str(e)}" + Style.RESET_ALL)
                return 1

        # Open in editor
        editor = os.getenv('EDITOR', 'nano')
        try:
            import subprocess
            result = subprocess.run([editor, str(config_file)])
            if result.returncode == 0:
                print(Fore.GREEN + "\n✅ Configuration updated." + Style.RESET_ALL)
                return 0
            else:
                print(Fore.RED + f"\nError: Editor exited with code {result.returncode}" + Style.RESET_ALL)
                return result.returncode
        except Exception as e:
            print(Fore.RED + f"Error: Failed to open editor: {str(e)}" + Style.RESET_ALL)
            print(f"\nYou can manually edit the file at: {config_file}")
            return 1

    return 0


def main() -> int:
    """
    Main entry point.
    
    Returns:
        Exit code
    """
    # Parse command line arguments
    args = parse_args()
    
    # If no command is provided, default to 'process' with default input
    if not args.command:
        # Create args for default process command
        parser = argparse.ArgumentParser()
        parser.add_argument('input', default='text-q')
        parser.add_argument('--verbose', action='store_true', default=False)
        args = parser.parse_args(['text-q'])
        args.command = 'process'
        logger.info("No command specified, defaulting to 'process text-q'")
    
    # Execute the selected command
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
    else:
        print(Fore.RED + f"Error: Unknown command: {args.command}" + Style.RESET_ALL)
        return 1


if __name__ == "__main__":
    sys.exit(main())