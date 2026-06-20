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
          vox-biblios process https://example.com/article  # Queue a URL to the Cloudflare control plane (default)
          vox-biblios process - < article.txt   # Queue text from stdin
          vox-biblios process --target s3 article.txt       # Legacy: synthesize + upload to S3 directly
          vox-biblios process --provider kokoro # Use Kokoro (local MLX) for TTS
          vox-biblios process --output-dir out/ # Local mode: write MP3s, no publishing
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
        '--target',
        type=str,
        choices=['cloudflare', 's3', 'local'],
        default=None,
        help=(f'Where to publish: cloudflare (control-plane queue, default), '
              f's3 (legacy direct upload + RSS), or local (write MP3s, needs '
              f'--output-dir). Default: {config.target}')
    )
    process_parser.add_argument(
        '--feed',
        type=str,
        default=None,
        metavar='SLUG',
        help='Control-plane feed slug to submit to (cloudflare target only; default feed if omitted)'
    )
    process_parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        metavar='DIR',
        help='Write MP3s to a local directory and skip publishing (implies --target local; no network/AWS needed)'
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
    init_parser.add_argument('--control-plane-url', default='https://vb.activationlayer.org')
    init_parser.add_argument('--control-plane-token', default=None)
    init_parser.add_argument('--aws-access-key', default=None)
    init_parser.add_argument('--aws-secret-key', default=None)
    init_parser.add_argument('--aws-region', default='us-east-1')
    init_parser.add_argument('--s3-bucket', default='vox-biblios')
    init_parser.add_argument('--polly-voice', default='Joanna')
    init_parser.add_argument('--podcast-name', default='Vox Biblios')
    init_parser.add_argument('--podcast-website', default='vox-biblios.example.com')
    config_subparsers.add_parser('show', help='Show configuration sources')
    config_subparsers.add_parser('edit', help='Edit configuration file')

    # Feed command (control-plane feed management)
    feed_parser = subparsers.add_parser('feed', help='Manage control-plane feeds')
    feed_subparsers = feed_parser.add_subparsers(dest='feed_command', help='Feed command')

    feed_create_parser = feed_subparsers.add_parser('create', help='Create a control-plane feed')
    feed_create_parser.add_argument('slug', type=str, help='Feed slug (must match ^[a-z0-9-]+$)')
    feed_create_parser.add_argument('--title', type=str, required=True, help='Feed title (required)')
    feed_create_parser.add_argument('--description', type=str, default=None, help='Feed description')
    feed_create_parser.add_argument('--link', type=str, default=None, help='Feed homepage link')
    feed_create_parser.add_argument('--author', type=str, default=None, help='Feed author')
    feed_create_parser.add_argument('--image-url', type=str, default=None, help='Feed cover image URL')
    feed_create_parser.add_argument('--language', type=str, default=None, help='Feed language (default: en)')
    feed_create_parser.add_argument('--explicit', action='store_true', default=None,
                                    help='Mark the feed as explicit')
    feed_create_parser.add_argument('--tts-provider', type=str, default=None,
                                    help='Default TTS provider for this feed (requires --tts-voice)')
    feed_create_parser.add_argument('--tts-voice', type=str, default=None,
                                    help='Default TTS voice for this feed (requires --tts-provider)')
    feed_create_parser.add_argument('--json', action='store_true', help='Emit machine-readable JSON on stdout')

    feed_list_parser = feed_subparsers.add_parser('list', help='List control-plane feeds')
    feed_list_parser.add_argument('--json', action='store_true', help='Emit machine-readable JSON on stdout')

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


def _gather_text_items(folder: str) -> list:
    """Read each .txt file in a folder as a control-plane submission.

    Raw (un-preprocessed) text is sent — the poller re-runs the full CLI, which
    preprocesses identically to a direct run, so sending raw keeps the two paths
    byte-equivalent. Title is the file stem, matching folder-mode S3 behavior.
    """
    from vox_biblios.core.text_processor import TextProcessor
    tp = TextProcessor()
    items = []
    for path in sorted(Path(folder).glob('*.txt')):
        try:
            text = tp._read_file_with_encoding(path)
        except Exception as e:
            logger.warning(f"Skipping {path.name}: {e}")
            continue
        if not text.strip():
            continue
        items.append({
            'kind': 'text',
            'payload': text,
            'title': path.stem,
            'source': path.name,
            'filename': path.name,
        })
    return items


def _utc_age_minutes(ts: Optional[str]) -> Optional[float]:
    """Age in minutes of a UTC timestamp string, or None if unparseable."""
    if not ts:
        return None
    from datetime import datetime, timezone
    # SQLite datetime() yields "YYYY-MM-DD HH:MM:SS" (UTC); accept ISO 'T' too.
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds() / 60.0
        except ValueError:
            continue
    return None


def _warn_if_queue_unattended(client, json_mode: bool) -> None:
    """Best-effort warning if the queue suggests the poller isn't draining it,
    so a submission doesn't silently sit unsynthesized (issue #6, open Q4)."""
    try:
        stats = client.stats()
    except Exception as e:
        logger.debug(f"poller-liveness check skipped: {e}")
        return

    reasons = []
    if stats.get('stale_synthesizing', 0) > 0:
        reasons.append(f"{stats['stale_synthesizing']} item(s) stuck mid-synthesis")
    age_min = _utc_age_minutes(stats.get('oldest_queued_at'))
    if age_min is not None and age_min >= 15:
        reasons.append(f"oldest queued item is {int(age_min)} min old")

    if reasons:
        msg = ("the control-plane poller may not be running ("
               + "; ".join(reasons) + "). Your item will queue but won't "
               "publish until the host poller drains it.")
        if json_mode:
            logger.warning(msg)  # keep JSON stdout clean
        else:
            print(Fore.YELLOW + "Warning: " + msg + Style.RESET_ALL)


def _submit_to_control_plane(input_source: str, is_url: bool,
                             args: argparse.Namespace, json_mode: bool) -> int:
    """Thin-submit the input to the Cloudflare control-plane queue.

    No synthesis happens here — the host poller claims and synthesizes later.
    Errors (rather than silently falling back to S3) when the control plane
    isn't configured, since a silent wrong-feed publish is the bug issue #6 fixes.
    """
    from vox_biblios.adapters.control_plane import ControlPlaneClient, ControlPlaneError

    cp = config.control_plane
    if not cp.token:
        if json_mode:
            print(json.dumps({'status': 'error', 'error': 'CONTROL_PLANE_TOKEN not set'}))
        else:
            print(Fore.RED + "Error: Cloudflare control plane is the default publish "
                  "target, but CONTROL_PLANE_TOKEN is not set." + Style.RESET_ALL)
            print("  • Configure it:  vox-biblios config init  "
                  "(sets CONTROL_PLANE_URL + CONTROL_PLANE_TOKEN)")
            print("  • Or publish another way:  --target s3  (legacy direct)  "
                  "or  --target local --output-dir DIR")
        return 1

    if is_url:
        submissions = [{'kind': 'url', 'payload': input_source, 'title': None,
                        'source': input_source}]
    else:
        submissions = _gather_text_items(input_source)
        if not submissions:
            msg = f"No non-empty .txt files found in {input_source}"
            if json_mode:
                print(json.dumps({'status': 'error', 'error': msg}))
            else:
                print(Fore.YELLOW + msg + Style.RESET_ALL)
            return 1

    if not json_mode:
        feed_desc = f" (feed: {args.feed})" if args.feed else ""
        print(f"Target: cloudflare control plane at {cp.url}{feed_desc}")

    client = ControlPlaneClient(cp.url, cp.token)
    _warn_if_queue_unattended(client, json_mode)

    queued, failures, submitted_files = [], [], []
    for sub in submissions:
        try:
            if sub['kind'] == 'url':
                res = client.submit_url(sub['payload'], feed=args.feed)
            else:
                res = client.submit_text(sub['payload'], title=sub['title'], feed=args.feed)
            queued.append({'id': res.get('id'), 'status': res.get('status', 'queued'),
                           'source': sub['source']})
            if sub.get('filename'):
                submitted_files.append(sub['filename'])
        except ControlPlaneError as e:
            failures.append({'source': sub['source'], 'error': str(e)})

    # Drain the folder: delete only the source files we successfully queued
    # (mirrors the S3 path's "delete on success" semantics).
    if submitted_files:
        from vox_biblios.core.text_processor import TextProcessor
        TextProcessor().delete_files(input_source, submitted_files)

    exit_code = 0 if not failures else (2 if queued else 1)

    if json_mode:
        print(json.dumps({
            'status': ['success', 'failure', 'partial'][exit_code],
            'target': 'cloudflare',
            'feed': args.feed,
            'queued': queued,
            'failures': failures,
        }, indent=2))
    else:
        for q in queued:
            print(Fore.GREEN + f"  ✓ queued {q['source']}" + Style.RESET_ALL
                  + f" -> {q['id']} ({q['status']})")
        for f in failures:
            print(Fore.RED + f"  ✗ {f['source']}: {f['error']}" + Style.RESET_ALL)
        if exit_code == 0:
            print(Fore.GREEN + f"Submitted {len(queued)} item(s) to the control plane."
                  + Style.RESET_ALL)
            print(f"The host poller will synthesize and publish to: {cp.url}")
        elif exit_code == 2:
            print(Fore.YELLOW + "Submitted with some failures." + Style.RESET_ALL)
        else:
            print(Fore.RED + "Submission failed." + Style.RESET_ALL)

    return exit_code


def _control_plane_client_or_error(json_mode: bool):
    """Build a ControlPlaneClient, or print the token-missing guidance and None.

    Mirrors the guard in _submit_to_control_plane: the control plane is the
    default surface, so a missing token is an error (not a silent fallback).
    """
    from vox_biblios.adapters.control_plane import ControlPlaneClient

    cp = config.control_plane
    if not cp.token:
        if json_mode:
            print(json.dumps({'status': 'error', 'error': 'CONTROL_PLANE_TOKEN not set'}))
        else:
            print(Fore.RED + "Error: Cloudflare control plane is the default publish "
                  "target, but CONTROL_PLANE_TOKEN is not set." + Style.RESET_ALL)
            print("  • Configure it:  vox-biblios config init  "
                  "(sets CONTROL_PLANE_URL + CONTROL_PLANE_TOKEN)")
            print("  • Or publish another way:  --target s3  (legacy direct)  "
                  "or  --target local --output-dir DIR")
        return None
    return ControlPlaneClient(cp.url, cp.token)


def feed_command(args: argparse.Namespace) -> int:
    """Execute the feed subcommands (create / list) against the control plane."""
    from vox_biblios.adapters.control_plane import ControlPlaneError

    if not getattr(args, 'feed_command', None):
        print(Fore.RED + "Error: Please specify a feed subcommand (create or list)" + Style.RESET_ALL)
        return 1

    json_mode = getattr(args, 'json', False)
    client = _control_plane_client_or_error(json_mode)
    if client is None:
        return 1

    if args.feed_command == 'list':
        try:
            body = client.list_feeds()
        except ControlPlaneError as e:
            if json_mode:
                print(json.dumps({'status': 'error', 'error': str(e)}))
            else:
                print(Fore.RED + f"Error: {e}" + Style.RESET_ALL)
            return 1

        feeds = body.get('feeds', [])
        if json_mode:
            print(json.dumps(feeds, indent=2))
        else:
            if not feeds:
                print("No feeds found.")
            else:
                for feed in feeds:
                    slug = feed.get('slug', '?')
                    title = feed.get('title', '')
                    print(Fore.GREEN + f"  {slug}" + Style.RESET_ALL + f"  {title}")
                print(f"\n{len(feeds)} feed(s).")
        return 0

    if args.feed_command == 'create':
        # Voice is provider-specific, so the two flags must come as a pair.
        if (args.tts_provider is None) != (args.tts_voice is None):
            msg = "--tts-provider and --tts-voice must be given together"
            if json_mode:
                print(json.dumps({'status': 'error', 'error': msg}))
            else:
                print(Fore.RED + f"Error: {msg}" + Style.RESET_ALL)
            return 1
        try:
            body = client.create_feed(
                args.slug,
                args.title,
                description=args.description,
                link=args.link,
                author=args.author,
                image_url=args.image_url,
                language=args.language,
                explicit=args.explicit,
                tts_provider=args.tts_provider,
                tts_voice=args.tts_voice,
            )
        except ControlPlaneError as e:
            if json_mode:
                print(json.dumps({'status': 'error', 'error': str(e)}))
            else:
                print(Fore.RED + f"Error: {e}" + Style.RESET_ALL)
            return 1

        feed = body.get('feed', body)
        if json_mode:
            print(json.dumps(feed, indent=2))
        else:
            print(Fore.GREEN + f"Created feed '{feed.get('slug', args.slug)}'" + Style.RESET_ALL
                  + f" ({feed.get('title', args.title)})")
        return 0

    print(Fore.RED + f"Error: Unknown feed subcommand: {args.feed_command}" + Style.RESET_ALL)
    return 1


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

        # Resolve the publish target. --output-dir is the local destination, so
        # its presence forces local mode regardless of --target (this is also
        # how the poller invokes us). Otherwise: explicit flag, then config.
        if args.output_dir:
            target = 'local'
        else:
            target = args.target or config.target

        # The cloudflare target doesn't synthesize here — it submits the raw
        # input to the control-plane queue and the host poller synthesizes later.
        if target == 'cloudflare':
            return _submit_to_control_plane(effective_input, is_url, args, json_mode)

        if target == 'local' and not args.output_dir:
            msg = "--target local requires --output-dir DIR (where MP3s are written)."
            if json_mode:
                print(json.dumps({'status': 'error', 'error': msg}))
            else:
                print(Fore.RED + f"Error: {msg}" + Style.RESET_ALL)
            return 1

        effective_provider = args.provider or config.tts.default_provider
        if not json_mode:
            source_desc = "URL" if is_url else "folder"
            print(f"Processing {source_desc}: {effective_input}")
            print(f"Using TTS provider: {effective_provider}")
            if args.voice:
                print(f"Using voice: {args.voice}")
            if target == 'local':
                print(f"Local mode: writing MP3s to {args.output_dir}")
            else:
                print("Target: s3 (legacy direct upload + RSS)")

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

# Default publish target for `vox-biblios process`:
#   cloudflare  submit to the control-plane queue (host poller synthesizes) [default]
#   s3          legacy direct upload + RSS (needs AWS creds below)
#   local       write MP3s locally (process --output-dir DIR)
VB_TARGET=cloudflare

# Cloudflare control plane (VB_TARGET=cloudflare). The token is the queue's
# bearer (the worker's API_TOKEN secret); the poller reads the same value.
CONTROL_PLANE_URL={values['control_plane_url']}
CONTROL_PLANE_TOKEN={values['control_plane_token']}

# AWS Credentials (required for VB_TARGET=s3 publishing and the Polly provider;
# not needed for cloudflare or local targets)
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
                    'control_plane_url': args.control_plane_url,
                    'control_plane_token': args.control_plane_token or '',
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
                print("The default target is the Cloudflare control plane; set its token below.")
                print("AWS credentials are only needed for --target s3 or the Polly provider.\n")

                values = {
                    'control_plane_url': input(f"CONTROL_PLANE_URL [{args.control_plane_url}]: ").strip() or args.control_plane_url,
                    'control_plane_token': input("CONTROL_PLANE_TOKEN (queue bearer token): ").strip(),
                    'aws_access_key': input("AWS_ACCESS_KEY (blank unless using --target s3): ").strip(),
                    'aws_secret_key': input("AWS_SECRET_KEY (blank unless using --target s3): ").strip(),
                    'aws_region': input(f"AWS_REGION [{args.aws_region}]: ").strip() or args.aws_region,
                    's3_bucket': input(f"S3_BUCKET [{args.s3_bucket}]: ").strip() or args.s3_bucket,
                    'polly_voice': input(f"POLLY_VOICE_ID [{args.polly_voice}]: ").strip() or args.polly_voice,
                    'podcast_name': input(f"PODCAST_NAME [{args.podcast_name}]: ").strip() or args.podcast_name,
                    'podcast_website': input(f"PODCAST_WEBSITE [{args.podcast_website}]: ").strip() or args.podcast_website,
                }

            _write_config_file(config_file, values)

            print(Fore.GREEN + f"\nConfiguration file created at: {config_file}" + Style.RESET_ALL)
            if not values['control_plane_token']:
                print(Fore.YELLOW + "No CONTROL_PLANE_TOKEN set: the default cloudflare target "
                      "will error until you add one (or use --target s3 / --output-dir)."
                      + Style.RESET_ALL)
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
    elif args.command == 'feed':
        return feed_command(args)
    elif args.command == 'voices':
        return voices_command(args)
    else:
        print(Fore.RED + f"Error: Unknown command: {args.command}" + Style.RESET_ALL)
        return 1


if __name__ == "__main__":
    sys.exit(main())
