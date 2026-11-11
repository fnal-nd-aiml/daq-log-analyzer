import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

def cmd_start(args: argparse.Namespace) -> int:
    from tools.slackmonitorbot.slackmonitor.config import get_default_config_path, load_config, load_output_config
    from tools.slackmonitorbot.slackmonitor.monitor import SlackMonitor
    config_path = Path(args.config) if args.config else None
    config = load_config(config_path)
    if not config:
        default_path = config_path or get_default_config_path()
        print(f'Error: Could not load Slack configuration from {default_path}', file=sys.stderr)
        return 1
    bot_token = config.get('bot_token')
    app_token = config.get('app_token')
    if not bot_token or not app_token:
        print('Error: bot_token and app_token required in config.yaml slack section', file=sys.stderr)
        return 1
    output_config = load_output_config(config_path)
    if args.stdout:
        output_file = None
    elif args.output:
        output_file = Path(args.output)
    else:
        output_file = Path(output_config['file'])
    status_file = Path(output_config['status_file'])
    monitor = SlackMonitor(bot_token=bot_token, app_token=app_token, output_file=output_file, status_file=status_file, timeout=args.timeout, use_stdout=args.stdout, channel=config.get('channel'), target_bot=config.get('target_bot'), announce_on_connect=config.get('announce_on_connect', True))
    try:
        asyncio.run(monitor.start())
    except KeyboardInterrupt:
        print('\n\nMonitor stopped by user', file=sys.stderr)
    return 0

async def send_message_async(bot_token: str, channel: str, message: str) -> bool:
    from slack_sdk.web.async_client import AsyncWebClient
    client = AsyncWebClient(token=bot_token)
    try:
        channel_id: str
        if channel.startswith('C'):
            channel_id = channel
        else:
            result = await client.conversations_list(types='public_channel,private_channel')
            channels: list[dict] = result.get('channels', [])
            found_id: str | None = None
            for ch in channels:
                if ch.get('name') == channel:
                    found_id = ch.get('id')
                    break
            if not found_id:
                print(f'Error: Could not find channel #{channel}', file=sys.stderr)
                return False
            channel_id = found_id
        await client.chat_postMessage(channel=channel_id, text=message)
        print(f'Sent to {channel}: {message}')
        return True
    except Exception as e:
        print(f'Error sending message: {e}', file=sys.stderr)
        return False

def cmd_send(args: argparse.Namespace) -> int:
    from tools.slackmonitorbot.slackmonitor.config import get_default_config_path, load_config
    config_path = Path(args.config) if args.config else None
    config = load_config(config_path)
    if not config:
        default_path = config_path or get_default_config_path()
        print(f'Error: Could not load configuration from {default_path}', file=sys.stderr)
        return 1
    bot_token = config.get('bot_token')
    channel = config.get('channel')
    if not bot_token:
        print('Error: bot_token required in config.yaml', file=sys.stderr)
        return 1
    if not channel:
        print('Error: channel required in config.yaml', file=sys.stderr)
        return 1
    message = args.message
    success = asyncio.run(send_message_async(bot_token, channel, message))
    return 0 if success else 1

def cmd_status(args: argparse.Namespace) -> int:
    from tools.slackmonitorbot.slackmonitor.config import load_output_config
    config_path = Path(args.config) if args.config else None
    output_config = load_output_config(config_path)
    status_file = Path(output_config['status_file'])
    if not status_file.exists():
        print('Slack Monitor Status')
        print('=' * 40)
        print('Status: NOT RUNNING')
        print(f'No status file found ({status_file})')
        return 0
    try:
        status = json.loads(status_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f'Error reading status file: {e}', file=sys.stderr)
        return 1
    pid = status.get('pid')
    started_at = status.get('started_at', 'unknown')
    message_count = status.get('message_count', 0)
    connected = status.get('connected', False)
    channel = status.get('channel')
    running = False
    if pid:
        try:
            import os
            os.kill(pid, 0)
            running = True
        except (OSError, ProcessLookupError):
            running = False
    print('Slack Monitor Status')
    print('=' * 40)
    if running:
        print(f'Status: RUNNING (PID {pid})')
    else:
        print(f'Status: STOPPED (last PID {pid})')
    if channel:
        print(f'Channel: #{channel}')
    if started_at and started_at != 'unknown':
        try:
            start_time = datetime.fromisoformat(started_at)
            duration = datetime.now() - start_time
            minutes = int(duration.total_seconds() // 60)
            if minutes < 1:
                duration_str = 'just now'
            elif minutes == 1:
                duration_str = '1 minute ago'
            else:
                duration_str = f'{minutes} minutes ago'
            print(f'Started: {started_at} ({duration_str})')
        except ValueError:
            print(f'Started: {started_at}')
    else:
        print(f'Started: {started_at}')
    print(f'Messages captured: {message_count}')
    print(f"Connected: {('Yes' if connected else 'No')}")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser(prog='slackmonitorbot', description='Monitor Slack messages for Claude Code debugging')
    parser.add_argument('--config', '-c', help='Path to config file (default: tools/slackmonitorbot/config.yaml)')
    subparsers = parser.add_subparsers(dest='command', required=True)
    start_parser = subparsers.add_parser('start', help='Start monitoring')
    start_parser.add_argument('--output', '-o', default=None, help='Output file path (default: from config or slack-monitor.log)')
    start_parser.add_argument('--stdout', action='store_true', help='Write to stdout instead of file')
    start_parser.add_argument('--timeout', '-t', type=int, default=None, help='Exit after N seconds (default: run indefinitely)')
    subparsers.add_parser('status', help='Check monitor status')
    send_parser = subparsers.add_parser('send', help='Send a message to the target bot')
    send_parser.add_argument('message', help='Message to send (use quotes for multi-word messages)')
    args = parser.parse_args()
    if args.command == 'start':
        return cmd_start(args)
    elif args.command == 'status':
        return cmd_status(args)
    elif args.command == 'send':
        return cmd_send(args)
    return 0
if __name__ == '__main__':
    sys.exit(main())