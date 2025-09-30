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
from vox_biblios.config import config

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
    else:
        print(Fore.RED + f"Error: Unknown command: {args.command}" + Style.RESET_ALL)
        return 1


if __name__ == "__main__":
    sys.exit(main())