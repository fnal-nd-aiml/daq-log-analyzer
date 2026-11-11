import argparse
import asyncio
import glob
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Union
if TYPE_CHECKING:
    from slack_sdk.web.async_client import AsyncWebClient
from tools.slacktesterbot.slacktester.config import TesterConfig, load_config
from tools.slacktesterbot.slacktester.reporters.json_report import JSONReporter
from tools.slacktesterbot.slacktester.reporters.terminal import TerminalReporter
from tools.slacktesterbot.slacktester.runner import MockTestRunner

def get_last_investigation_from_db() -> tuple[str | None, str | None]:
    import sqlite3
    db_path = Path('data/knowledge.db')
    if not db_path.exists():
        return (None, None)
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('''
            SELECT wb.investigation_id, wb.id as binder_id
            FROM work_binders wb
            ORDER BY wb.created_at DESC
            LIMIT 1
        ''')
        row = cursor.fetchone()
        conn.close()
        if row:
            return (row['investigation_id'], row['binder_id'])
    except Exception as e:
        print(f'Warning: Could not read database: {e}', file=sys.stderr)
    return (None, None)

def get_artifacts_for_investigation(investigation_id: str) -> list[dict]:
    import sqlite3
    db_path = Path('data/knowledge.db')
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('''
            SELECT id FROM work_binders WHERE investigation_id LIKE ?
        ''', (f'%{investigation_id}%',))
        binder = cursor.fetchone()
        if not binder:
            conn.close()
            return []
        cursor = conn.execute('''
            SELECT id, artifact_type, phase
            FROM binder_artifacts
            WHERE binder_id = ?
            ORDER BY created_at
        ''', (binder['id'],))
        artifacts = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return artifacts
    except Exception as e:
        print(f'Warning: Could not read artifacts: {e}', file=sys.stderr)
    return []

async def get_channel_id(config: TesterConfig) -> tuple[str | None, 'AsyncWebClient | None']:
    from slack_sdk.web.async_client import AsyncWebClient
    if not config.slack.bot_token or not config.slack.channel:
        return (None, None)
    client = AsyncWebClient(token=config.slack.bot_token)
    channel = config.slack.channel
    if channel.startswith('C'):
        return (channel, client)
    try:
        result = await client.conversations_list(types='public_channel,private_channel')
        channels: list[dict] = result.get('channels', [])
        for ch in channels:
            if ch.get('name') == channel:
                return (ch.get('id'), client)
    except Exception as e:
        print(f'Error looking up channel: {e}', file=sys.stderr)
    return (None, client)

async def join_and_announce(config: TesterConfig) -> tuple[str | None, 'AsyncWebClient | None']:
    if not config.slack.bot_token:
        print('Error: bot_token required in config', file=sys.stderr)
        return (None, None)
    if not config.slack.channel:
        print('Error: channel required in config', file=sys.stderr)
        return (None, None)
    channel_id, client = await get_channel_id(config)
    if not channel_id or not client:
        print(f'Error: Could not find channel #{config.slack.channel}', file=sys.stderr)
        return (None, client)
    try:
        await client.conversations_join(channel=channel_id)
        print(f'Joined channel {config.slack.channel}')
    except Exception as e:
        print(f'Note: Could not join channel (may already be member): {e}', file=sys.stderr)
    try:
        target = config.slack.target_bot or 'the Slack bot'
        message = f':test_tube: *Slack Tester Bot* has joined!\nReady to test `{target}` commands.\n_This bot runs functional tests against the command parser._'
        await client.chat_postMessage(channel=channel_id, text=message)
        print(f'Announced in channel {config.slack.channel}')
    except Exception as e:
        print(f'Error sending announcement: {e}', file=sys.stderr)
    return (channel_id, client)

async def leave_and_announce(channel_id: str | None, client: 'AsyncWebClient | None', passed: int, failed: int) -> None:
    if not channel_id or not client:
        return
    try:
        status = ':white_check_mark:' if failed == 0 else ':x:'
        message = f':wave: *Slack Tester Bot* disconnecting.\n{status} Tests complete: {passed} passed, {failed} failed.'
        await client.chat_postMessage(channel=channel_id, text=message)
        print('Announced disconnect')
    except Exception as e:
        print(f'Warning: Could not announce disconnect: {e}', file=sys.stderr)

def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='slacktesterbot', description='Functional testing tool for the Slack bot')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    run_parser = subparsers.add_parser('run', help='Run mock test scenarios (local)')
    run_parser.add_argument('--scenario', '-s', type=str, help='Run specific scenario category')
    run_parser.add_argument('--json', action='store_true', help='Output results as JSON')
    run_parser.add_argument('--verbose', '-v', action='store_true', help='Show verbose output')
    run_parser.add_argument('--config', '-c', type=Path, help='Path to config file')
    live_parser = subparsers.add_parser('live', help='Run live tests against the real bot in Slack')
    live_parser.add_argument('--test', '-t', type=str, help='Run specific test (help, version, message, config)')
    live_parser.add_argument('--timeout', type=int, default=120, help='Timeout in seconds for bot response (default: 120)')
    live_parser.add_argument('--config', '-c', type=Path, help='Path to config file')
    live_parser.add_argument('--last-investigation', '-l', action='store_true', help='Use the most recent investigation for binder/artifact tests')
    list_parser = subparsers.add_parser('list', help='List available scenarios')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    send_parser = subparsers.add_parser('send', help='Send a custom message to the bot')
    send_parser.add_argument('message', type=str, help="Message to send to the bot (e.g., 'help' or 'message <error text>')")
    send_parser.add_argument('--timeout', type=int, default=120, help='Timeout in seconds for bot response (default: 120)')
    send_parser.add_argument('--config', '-c', type=Path, help='Path to config file')
    send_parser.add_argument('--files', '-f', nargs='+', type=str, help='File paths to attach (supports glob patterns)')
    return parser

def list_scenarios(json_output: bool=False) -> int:
    from tools.slacktesterbot.slacktester.scenarios import get_all_scenarios
    scenarios = get_all_scenarios()
    if json_output:
        import json
        data = {name: {'description': scenario.description, 'test_count': len(scenario.get_test_cases())} for name, scenario in scenarios.items()}
        print(json.dumps(data, indent=2))
    else:
        print('Available Test Scenarios')
        print('=' * 50)
        for name, scenario in scenarios.items():
            test_count = len(scenario.get_test_cases())
            print(f'  {name:<15} - {scenario.description} ({test_count} tests)')
        print()
        print(f'Total: {len(scenarios)} scenario categories')
    return 0

async def run_live_tests(config: TesterConfig, test_filter: str | None=None, timeout: int=30, last_investigation: bool=False) -> int:
    from tools.slacktesterbot.slacktester.live_runner import LiveTestRunner
    if not config.slack.bot_token:
        print('Error: bot_token required in config for live tests', file=sys.stderr)
        return 1
    if not config.slack.channel:
        print('Error: channel required in config for live tests', file=sys.stderr)
        return 1
    if not config.slack.target_bot_id:
        print('Error: target_bot_id required in config for live tests', file=sys.stderr)
        return 1
    last_inv_id: str | None = None
    last_artifacts: list[dict] = []
    if last_investigation:
        last_inv_id, _ = get_last_investigation_from_db()
        if last_inv_id:
            print(f'Using last investigation from database: {last_inv_id[:8]}')
            last_artifacts = get_artifacts_for_investigation(last_inv_id[:8])
            print(f'Found {len(last_artifacts)} artifacts')
            type_counts: dict[str, int] = {}
            for a in last_artifacts:
                t = a['artifact_type']
                type_counts[t] = type_counts.get(t, 0) + 1
            for t, count in sorted(type_counts.items()):
                print(f'  - {t}: {count}')
        else:
            print('Warning: No investigation found in database', file=sys.stderr)
    channel_id, client = await join_and_announce(config)
    if not channel_id or not client:
        return 1
    runner = LiveTestRunner(config, client, channel_id)
    runner.response_timeout = timeout
    live_tests = {'help': {'command': 'help', 'expected_contains': ['investigate', 'message', 'help'], 'description': 'Test help command'}, 'version': {'command': 'version', 'expected_contains': ['version', 'v'], 'description': 'Test version command'}, 'config': {'command': 'config', 'expected_contains': ['verbose', 'config'], 'description': 'Test config show command'}, 'list': {'command': 'list', 'expected_contains': [], 'description': 'Test list command'}, 'wb_list': {'command': 'workbinder list', 'expected_contains': [], 'description': 'Test workbinder list'}, 'wb_show': {'command': None, 'expected_contains': [], 'description': 'Test workbinder show with random binder ID', 'dynamic': 'binder'}, 'wb_artifacts': {'command': None, 'expected_contains': [], 'description': 'Test workbinder artifacts with random binder ID', 'dynamic': 'binder'}, 'wb_artifact': {'command': None, 'expected_contains': [], 'description': 'Test workbinder artifact with random artifact ID', 'dynamic': 'artifact'}, 'wb_artifact_all': {'command': None, 'expected_contains': ['All Artifacts', 'Total'], 'description': 'Test workbinder artifact all (export all artifacts)', 'dynamic': 'binder'}, 'wb_search': {'command': None, 'expected_contains': [], 'description': 'Test workbinder search with random binder ID', 'dynamic': 'binder'}, 'wb_history': {'command': None, 'expected_contains': [], 'description': 'Test workbinder history with random binder ID', 'dynamic': 'binder'}, 'wb_audit': {'command': None, 'expected_contains': [], 'description': 'Test workbinder audit with random binder ID', 'dynamic': 'binder'}}
    tests_to_run = {}
    if test_filter:
        if test_filter in live_tests:
            tests_to_run[test_filter] = live_tests[test_filter]
        else:
            print(f"Error: Unknown test '{test_filter}'", file=sys.stderr)
            print(f"Available: {', '.join(live_tests.keys())}", file=sys.stderr)
            await leave_and_announce(channel_id, client, 0, 0)
            return 2
    else:
        tests_to_run = live_tests
    print(f'\nRunning {len(tests_to_run)} live tests against {config.slack.target_bot}...')
    print(f'Timeout: {timeout}s per test\n')
    print('=' * 60)
    passed = 0
    failed = 0
    results = []
    cached_investigation_ids: list[str] = [last_inv_id[:8]] if last_inv_id else []
    cached_artifact_ids: list[str] = [a['id'][:8] for a in last_artifacts]

    async def fetch_artifact_ids(inv_id: str) -> None:
        nonlocal cached_artifact_ids
        if cached_artifact_ids:
            return
        print(f'  Fetching artifacts for investigation {inv_id}...')
        art_result = await runner.send_command(f'workbinder artifacts inv={inv_id}', response_timeout=timeout)
        if art_result.bot_responses:
            import re
            all_text = runner.get_all_text(art_result.bot_responses)
            ids = re.findall('•\\s*`([a-f0-9]{8})`', all_text)
            cached_artifact_ids.extend(ids)
            if ids:
                print(f'  Found {len(ids)} artifact IDs: {ids[:3]}...')
    try:
        for name, test_config in tests_to_run.items():
            command = test_config['command']
            dynamic_type = test_config.get('dynamic')
            if dynamic_type == 'binder':
                print(f"\n[{name}] {test_config['description']}")
                if not cached_investigation_ids:
                    print('  Fetching investigation list...')
                    list_result = await runner.send_command('list', response_timeout=timeout)
                    if list_result.bot_responses:
                        import re
                        all_text = runner.get_all_text(list_result.bot_responses)
                        ids = re.findall('`([a-f0-9]{8})`', all_text)
                        cached_investigation_ids.extend(ids)
                if not cached_investigation_ids:
                    print('  Status: SKIP (no investigation IDs found)')
                    continue
                import random
                inv_id = random.choice(cached_investigation_ids)
                if name == 'wb_show':
                    command = f'workbinder show inv={inv_id}'
                elif name == 'wb_artifacts':
                    command = f'workbinder artifacts inv={inv_id}'
                elif name == 'wb_artifact_all':
                    command = f'workbinder artifact all inv={inv_id}'
                elif name == 'wb_search':
                    command = f'workbinder search inv={inv_id} "error"'
                elif name == 'wb_history':
                    command = f'workbinder history inv={inv_id}'
                elif name == 'wb_audit':
                    command = f'workbinder audit inv={inv_id}'
                print(f'  Selected investigation: {inv_id}')
                print(f'  Command: {command}')
            elif dynamic_type == 'artifact':
                print(f"\n[{name}] {test_config['description']}")
                if not cached_investigation_ids:
                    print('  Fetching investigation list...')
                    list_result = await runner.send_command('list', response_timeout=timeout)
                    if list_result.bot_responses:
                        import re
                        all_text = runner.get_all_text(list_result.bot_responses)
                        ids = re.findall('`([a-f0-9]{8})`', all_text)
                        cached_investigation_ids.extend(ids)
                if not cached_investigation_ids:
                    print('  Status: SKIP (no investigation IDs found)')
                    continue
                import random
                inv_id = random.choice(cached_investigation_ids)
                await fetch_artifact_ids(inv_id)
                if not cached_artifact_ids:
                    print('  Status: SKIP (no artifact IDs found)')
                    continue
                artifact_id = random.choice(cached_artifact_ids)
                command = f'workbinder artifact {artifact_id}'
                print(f'  Selected artifact: {artifact_id}')
                print(f'  Command: {command}')
            else:
                print(f"\n[{name}] {test_config['description']}")
                print(f'  Command: {command}')
            result = await runner.run_test(name=name, command=command, expected_contains=test_config.get('expected_contains'), timeout=timeout)
            results.append(result)
            if result['passed']:
                import re
                all_text = runner.get_all_text(result.get('responses', []))
                if name == 'list':
                    ids = re.findall('`([a-f0-9]{8})`', all_text)
                    cached_investigation_ids.extend(ids)
                elif name == 'wb_artifacts':
                    ids = re.findall('•\\s*`([a-f0-9]{8})`', all_text)
                    cached_artifact_ids.extend(ids)
            if result['passed']:
                passed += 1
                print(f"  Status: PASS ({result['duration_ms']}ms)")
                print(f"  Responses: {result['response_count']}")
                if result['responses']:
                    first_resp = result['responses'][0].get('text', '')[:100]
                    print(f'  First response: {first_resp}...')
            else:
                failed += 1
                print(f"  Status: FAIL ({result['duration_ms']}ms)")
                print(f"  Error: {result.get('error', 'Unknown error')}")
                if result.get('timed_out'):
                    print('  (Bot did not respond in time)')
    except KeyboardInterrupt:
        print('\n\nInterrupted by user')
    finally:
        await leave_and_announce(channel_id, client, passed, failed)
    print('\n' + '=' * 60)
    print(f'\nResults: {passed} passed, {failed} failed')
    return 0 if failed == 0 else 1

async def send_custom_message(config: TesterConfig, message: str, timeout: int=120, file_paths: list[str] | None=None) -> int:
    from tools.slacktesterbot.slacktester.live_runner import LiveTestRunner
    if not config.slack.bot_token:
        print('Error: bot_token required in config for sending messages', file=sys.stderr)
        return 1
    if not config.slack.channel:
        print('Error: channel required in config for sending messages', file=sys.stderr)
        return 1
    if not config.slack.target_bot_id:
        print('Error: target_bot_id required in config for sending messages', file=sys.stderr)
        return 1
    resolved_files: list[Path] = []
    if file_paths:
        for pattern in file_paths:
            matches = glob.glob(pattern)
            if not matches:
                print(f'Error: No files matched pattern: {pattern}', file=sys.stderr)
                return 1
            for match in sorted(matches):
                p = Path(match)
                if not p.is_file():
                    print(f'Error: Not a file: {p}', file=sys.stderr)
                    return 1
                if p.stat().st_size == 0:
                    print(f'Error: File is empty: {p}', file=sys.stderr)
                    return 1
                resolved_files.append(p)
        print(f'\nFiles to upload ({len(resolved_files)}):')
        for f in resolved_files:
            size_kb = f.stat().st_size / 1024
            print(f'  {f.name} ({size_kb:.1f} KB)')
    channel_id, client = await join_and_announce(config)
    if not channel_id or not client:
        return 1
    runner = LiveTestRunner(config, client, channel_id)
    runner.response_timeout = timeout
    print(f'\nSending message to {config.slack.target_bot}...')
    print(f'Message: {message}')
    if resolved_files:
        print(f'Files: {len(resolved_files)}')
    print(f'Timeout: {timeout}s')
    print('=' * 60)
    try:
        if resolved_files:
            result = await runner.send_command_with_files(command=message, file_paths=resolved_files, response_timeout=timeout)
        else:
            result = await runner.send_command(message, response_timeout=timeout)
        if result.error:
            print(f'\nError: {result.error}')
            await leave_and_announce(channel_id, client, 0, 1)
            return 1
        if result.timed_out:
            print(f'\nTimeout: Bot did not respond within {timeout}s')
            await leave_and_announce(channel_id, client, 0, 1)
            return 1
        print(f'\nReceived {len(result.bot_responses)} response(s) in {result.duration_ms}ms')
        print('=' * 60)
        for i, response in enumerate(result.bot_responses, 1):
            print(f'\n--- Response {i} ---')
            text = response.get('text', '')
            if text:
                print(text)
            else:
                blocks = response.get('blocks', [])
                if blocks:
                    block_text = runner._extract_text_from_blocks(blocks)
                    print(block_text if block_text else '(No text in blocks)')
                else:
                    print('(No text content)')
        await leave_and_announce(channel_id, client, 1, 0)
        return 0
    except KeyboardInterrupt:
        print('\n\nInterrupted by user')
        await leave_and_announce(channel_id, client, 0, 0)
        return 1
    except Exception as e:
        print(f'\nUnexpected error: {e}')
        await leave_and_announce(channel_id, client, 0, 1)
        return 1

async def run_scenarios(config: TesterConfig, scenario_filter: str | None=None, json_output: bool=False, verbose: bool=False) -> int:
    from tools.slacktesterbot.slacktester.scenarios import get_all_scenarios
    channel_id: str | None = None
    client = None
    if config.slack.bot_token and config.slack.channel:
        channel_id, client = await join_and_announce(config)
    runner = MockTestRunner(config)
    all_scenarios = get_all_scenarios()
    scenarios_to_run = {}
    if scenario_filter:
        if scenario_filter in all_scenarios:
            scenarios_to_run[scenario_filter] = all_scenarios[scenario_filter]
        else:
            print(f"Error: Unknown scenario '{scenario_filter}'", file=sys.stderr)
            print(f"Available: {', '.join(all_scenarios.keys())}", file=sys.stderr)
            await leave_and_announce(channel_id, client, 0, 0)
            return 2
    else:
        for name in config.scenarios.enabled:
            if name in all_scenarios:
                scenarios_to_run[name] = all_scenarios[name]
    reporter: Union[JSONReporter, TerminalReporter]
    if json_output:
        reporter = JSONReporter()
    else:
        reporter = TerminalReporter(verbose=verbose or config.output.verbose)
    all_results = []
    try:
        for name, scenario in scenarios_to_run.items():
            results = await scenario.run(runner)
            all_results.extend(results)
    except KeyboardInterrupt:
        print('\n\nInterrupted by user')
    finally:
        passed = sum((1 for r in all_results if r.passed))
        failed = len(all_results) - passed
        await leave_and_announce(channel_id, client, passed, failed)
    reporter.report(all_results)
    return 0 if failed == 0 else 1

def main() -> None:
    parser = create_parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(0)
    if args.command == 'list':
        sys.exit(list_scenarios(json_output=args.json))
    if args.command == 'run':
        config = load_config(args.config)
        exit_code = asyncio.run(run_scenarios(config, scenario_filter=args.scenario, json_output=args.json, verbose=args.verbose))
        sys.exit(exit_code)
    if args.command == 'live':
        config = load_config(args.config)
        exit_code = asyncio.run(run_live_tests(config, test_filter=args.test, timeout=args.timeout, last_investigation=args.last_investigation))
        sys.exit(exit_code)
    if args.command == 'send':
        config = load_config(args.config)
        exit_code = asyncio.run(send_custom_message(config, message=args.message, timeout=args.timeout, file_paths=args.files))
        sys.exit(exit_code)