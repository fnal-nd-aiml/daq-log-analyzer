import argparse
import asyncio
import sys
from pathlib import Path
from typing import Union
from tools.mcptester.mcptester.config import TesterConfig, load_config
from tools.mcptester.mcptester.reporters.json_report import JSONReporter
from tools.mcptester.mcptester.reporters.terminal import TerminalReporter
from tools.mcptester.mcptester.runner import MockCommandRunner, MockTestRunner

def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='mcptester', description='Automated testing tool for MCP server tools')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    run_parser = subparsers.add_parser('run', help='Run mock test scenarios (local)')
    run_parser.add_argument('--scenario', '-s', type=str, help='Run specific scenario category (e.g., binders, commands)')
    run_parser.add_argument('--json', action='store_true', help='Output results as JSON')
    run_parser.add_argument('--verbose', '-v', action='store_true', help='Show verbose output')
    run_parser.add_argument('--config', '-c', type=Path, help='Path to config file')
    run_parser.add_argument('--no-mock', action='store_true', help='Disable mocking for command tools (requires real LLM)')
    run_parser.add_argument('--mode', choices=['mock', 'rest'], default='mock', help='Test mode: mock (direct MCP calls) or rest (ASGI HTTP)')
    live_parser = subparsers.add_parser('live', help='Run live tests against running MCP server')
    live_parser.add_argument('--scenario', '-s', type=str, help='Run specific scenario category')
    live_parser.add_argument('--url', type=str, help='MCP server URL (default from config)')
    live_parser.add_argument('--timeout', type=int, default=30, help='Timeout in seconds for server responses (default: 30)')
    live_parser.add_argument('--skip-commands', action='store_true', help='Skip commands scenario (which calls real LLM and takes long)')
    live_parser.add_argument('--json', action='store_true', help='Output results as JSON')
    live_parser.add_argument('--verbose', '-v', action='store_true', help='Show verbose output')
    live_parser.add_argument('--config', '-c', type=Path, help='Path to config file')
    list_parser = subparsers.add_parser('list', help='List available test scenarios')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    tools_parser = subparsers.add_parser('tools', help='List available MCP tools')
    tools_parser.add_argument('--json', action='store_true', help='Output as JSON')
    return parser

def list_scenarios(json_output: bool=False) -> int:
    from tools.mcptester.mcptester.scenarios import get_all_scenarios
    scenarios = get_all_scenarios()
    if json_output:
        import json
        data = {name: {'description': scenario.description, 'test_count': len(scenario.get_test_cases())} for name, scenario in scenarios.items()}
        print(json.dumps(data, indent=2))
    else:
        print('Available Test Scenarios')
        print('=' * 50)
        total_tests = 0
        for name, scenario in scenarios.items():
            test_count = len(scenario.get_test_cases())
            total_tests += test_count
            print(f'  {name:<15} - {scenario.description} ({test_count} tests)')
        print()
        print(f'Total: {len(scenarios)} scenarios, {total_tests} test cases')
    return 0

async def list_tools(json_output: bool=False) -> int:
    from tools.mcptester.mcptester.config import TesterConfig
    runner = MockTestRunner(TesterConfig())
    tools = await runner.list_available_tools()
    if json_output:
        import json
        print(json.dumps({'tools': tools, 'count': len(tools)}, indent=2))
    else:
        print('Available MCP Tools')
        print('=' * 50)
        for tool in tools:
            print(f'  - {tool}')
        print()
        print(f'Total: {len(tools)} tools')
    return 0

async def run_scenarios(config: TesterConfig, scenario_filter: str | None=None, json_output: bool=False, verbose: bool=False, use_mocks: bool=True, mode: str='mock') -> int:
    from tools.mcptester.mcptester.scenarios import get_all_scenarios
    runner = None
    rest_runner_ctx = None
    if mode == 'rest':
        from tools.mcptester.mcptester.rest_runner import RESTTestRunner
        rest_runner = RESTTestRunner(config)
        rest_runner_ctx = rest_runner
        runner = rest_runner
        if not json_output:
            print('REST mode: testing via ASGI transport with fixture DB...')
    elif use_mocks:
        runner = MockCommandRunner(config)
    else:
        runner = MockTestRunner(config)
    all_scenarios = get_all_scenarios()
    skip_commands_in_rest = mode == 'rest'
    scenarios_to_run = {}
    if scenario_filter:
        if scenario_filter in all_scenarios:
            scenarios_to_run[scenario_filter] = all_scenarios[scenario_filter]
        else:
            print(f"Error: Unknown scenario '{scenario_filter}'", file=sys.stderr)
            print(f"Available: {', '.join(all_scenarios.keys())}", file=sys.stderr)
            return 2
    else:
        for name in config.scenarios.enabled:
            if name in all_scenarios:
                if skip_commands_in_rest and name == 'commands':
                    if not json_output:
                        print('Skipping commands scenario in REST mode')
                    continue
                scenarios_to_run[name] = all_scenarios[name]
    reporter: Union[JSONReporter, TerminalReporter]
    if json_output:
        reporter = JSONReporter()
    else:
        reporter = TerminalReporter(verbose=verbose or config.output.verbose)
    all_results = []
    try:
        if rest_runner_ctx:
            async with rest_runner_ctx:
                for name, scenario in scenarios_to_run.items():
                    if not json_output and verbose:
                        print(f'Running scenario: {name}...')
                    results = await scenario.run(runner)
                    all_results.extend(results)
        else:
            for name, scenario in scenarios_to_run.items():
                if not json_output and verbose:
                    print(f'Running scenario: {name}...')
                results = await scenario.run(runner)
                all_results.extend(results)
    except KeyboardInterrupt:
        print('\n\nInterrupted by user')
    finally:
        if hasattr(runner, 'reset'):
            runner.reset()
    reporter.report(all_results)
    failed = sum((1 for r in all_results if not r.passed))
    return 0 if failed == 0 else 1

async def run_live_tests(config: TesterConfig, scenario_filter: str | None=None, server_url: str | None=None, timeout: int=30, json_output: bool=False, verbose: bool=False, skip_commands: bool=False) -> int:
    from tools.mcptester.mcptester.live_runner import LiveTestRunner
    from tools.mcptester.mcptester.scenarios import get_all_scenarios
    url = server_url or config.live.server_url
    if not url:
        print('Error: No server URL specified.', file=sys.stderr)
        print('Use --url or set live.server_url in config.yaml', file=sys.stderr)
        return 2
    if not json_output:
        print(f'Connecting to MCP server at {url}...')
    runner = LiveTestRunner(config, url, timeout)
    all_scenarios = get_all_scenarios()
    scenarios_to_run = {}
    if scenario_filter:
        if scenario_filter in all_scenarios:
            scenarios_to_run[scenario_filter] = all_scenarios[scenario_filter]
        else:
            print(f"Error: Unknown scenario '{scenario_filter}'", file=sys.stderr)
            print(f"Available: {', '.join(all_scenarios.keys())}", file=sys.stderr)
            return 2
    else:
        for name in config.scenarios.enabled:
            if name in all_scenarios:
                if skip_commands and name == 'commands':
                    if not json_output:
                        print('Skipping commands scenario (use --scenario commands to run)')
                    continue
                scenarios_to_run[name] = all_scenarios[name]
    reporter: Union[JSONReporter, TerminalReporter]
    if json_output:
        reporter = JSONReporter()
    else:
        reporter = TerminalReporter(verbose=verbose or config.output.verbose)
    all_results = []
    try:
        async with runner:
            tools = await runner.list_available_tools()
            if not json_output:
                print(f'Connected. Found {len(tools)} tools.')
                print()
            for name, scenario in scenarios_to_run.items():
                if not json_output and verbose:
                    print(f'Running scenario: {name}...')
                results = await scenario.run(runner)
                all_results.extend(results)
    except ConnectionRefusedError:
        print(f'Error: Could not connect to MCP server at {url}', file=sys.stderr)
        print('Make sure the server is running: ./run.sh mcp --sse', file=sys.stderr)
        return 2
    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('\n\nInterrupted by user')
    reporter.report(all_results)
    failed = sum((1 for r in all_results if not r.passed))
    return 0 if failed == 0 else 1

def main() -> None:
    parser = create_parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(0)
    if args.command == 'list':
        sys.exit(list_scenarios(json_output=args.json))
    if args.command == 'tools':
        exit_code = asyncio.run(list_tools(json_output=args.json))
        sys.exit(exit_code)
    if args.command == 'run':
        config = load_config(args.config)
        exit_code = asyncio.run(run_scenarios(config, scenario_filter=args.scenario, json_output=args.json, verbose=args.verbose, use_mocks=not args.no_mock, mode=args.mode))
        sys.exit(exit_code)
    if args.command == 'live':
        config = load_config(args.config)
        exit_code = asyncio.run(run_live_tests(config, scenario_filter=args.scenario, server_url=args.url, timeout=args.timeout, json_output=args.json, verbose=args.verbose, skip_commands=args.skip_commands))
        sys.exit(exit_code)
if __name__ == '__main__':
    main()