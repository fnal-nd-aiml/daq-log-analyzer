from rich.console import Console
from rich.table import Table
from rich.text import Text
from tools.slacktesterbot.slacktester.scenarios.base import ScenarioResult

class TerminalReporter:

    def __init__(self, verbose: bool=False) -> None:
        self.verbose = verbose
        self.console = Console()

    def report(self, results: list[ScenarioResult]) -> None:
        passed = [r for r in results if r.passed]
        failed = [r for r in results if not r.passed]
        self.console.print()
        self.console.print('[bold]Slack Tester Bot Results[/bold]')
        self.console.print('=' * 50)
        scenarios: dict[str, list[ScenarioResult]] = {}
        for result in results:
            if result.scenario not in scenarios:
                scenarios[result.scenario] = []
            scenarios[result.scenario].append(result)
        for scenario_name, scenario_results in scenarios.items():
            self._report_scenario(scenario_name, scenario_results)
        self.console.print()
        self._report_summary(passed, failed)

    def _report_scenario(self, scenario_name: str, results: list[ScenarioResult]) -> None:
        passed = sum((1 for r in results if r.passed))
        total = len(results)
        if passed == total:
            status = Text(f'[{scenario_name}]', style='bold green')
            status.append(f' {passed}/{total} passed')
        else:
            status = Text(f'[{scenario_name}]', style='bold red')
            status.append(f' {passed}/{total} passed')
        self.console.print(status)
        if self.verbose or any((not r.passed for r in results)):
            table = Table(show_header=True, header_style='bold', box=None, padding=(0, 1))
            table.add_column('Test', style='cyan')
            table.add_column('Status')
            table.add_column('Duration')
            if self.verbose:
                table.add_column('Details')
            for result in results:
                if result.passed:
                    status_text = Text('PASS', style='green')
                else:
                    status_text = Text('FAIL', style='red')
                duration = f'{result.duration_ms}ms'
                if self.verbose:
                    details = ''
                    if result.error:
                        details = result.error[:50]
                    elif result.actual:
                        details = str(result.actual)[:50]
                    table.add_row(result.name, status_text, duration, details)
                else:
                    table.add_row(result.name, status_text, duration)
            self.console.print(table)
        for result in results:
            if not result.passed and result.error:
                self.console.print(f'  [red]Error:[/red] {result.error}')
                if self.verbose and result.expected:
                    self.console.print(f'  [dim]Expected: {result.expected}[/dim]')
                if self.verbose and result.actual:
                    self.console.print(f'  [dim]Actual: {result.actual}[/dim]')

    def _report_summary(self, passed: list[ScenarioResult], failed: list[ScenarioResult]) -> None:
        total = len(passed) + len(failed)
        total_duration = sum((r.duration_ms for r in passed + failed))
        self.console.print('-' * 50)
        if failed:
            self.console.print(f'[bold red]FAILED[/bold red]: {len(failed)} tests failed')
            for result in failed:
                self.console.print(f'  - {result.scenario}/{result.name}')
        else:
            self.console.print('[bold green]PASSED[/bold green]: All tests passed')
        self.console.print()
        self.console.print(f'Total: {total} tests | Passed: {len(passed)} | Failed: {len(failed)} | Duration: {total_duration}ms')