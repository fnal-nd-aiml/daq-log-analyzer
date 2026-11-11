from rich.console import Console
from rich.table import Table
from rich.text import Text
from tools.mcptester.mcptester.scenarios.base import ScenarioResult

class TerminalReporter:

    def __init__(self, verbose: bool=False) -> None:
        self.verbose = verbose
        self.console = Console()

    def report(self, results: list[ScenarioResult]) -> None:
        passed = [r for r in results if r.passed]
        failed = [r for r in results if not r.passed]
        self.console.print()
        self.console.print('[bold]MCP Tester Results[/bold]')
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
            table.add_column('Tool', style='dim')
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
                tool_name = self._extract_tool_name(result)
                if self.verbose:
                    details = ''
                    if result.error:
                        details = result.error[:50]
                    elif result.actual:
                        details = str(result.actual)[:50]
                    table.add_row(result.name, tool_name, status_text, duration, details)
                else:
                    table.add_row(result.name, tool_name, status_text, duration)
            self.console.print(table)
        for result in results:
            if not result.passed and result.error:
                self.console.print(f'  [red]Error:[/red] {result.error}')
                if self.verbose and result.expected:
                    self.console.print(f'  [dim]Expected: {result.expected}[/dim]')
                if self.verbose and result.actual:
                    actual_str = str(result.actual)[:200]
                    self.console.print(f'  [dim]Actual: {actual_str}[/dim]')

    def _extract_tool_name(self, result: ScenarioResult) -> str:
        name = result.name
        for tool in ['list_binders', 'get_binder', 'get_binder_summary', 'search_artifacts', 'get_artifact', 'get_artifact_history', 'search_artifact_content', 'search_audit_log', 'get_artifact_audit_trail', 'get_audit_summary', 'list_patterns', 'get_pattern', 'get_pattern_statistics', 'list_calibrations', 'get_calibration', 'get_hypotheses', 'get_evidence', 'get_causal_chains', 'get_challenges', 'get_llm_requests', 'get_llm_responses', 'get_llm_exchanges', 'get_llm_statistics', 'get_investigation_state', 'get_phase_states', 'list_investigations_with_state', 'find_similar_investigations', 'investigate_error', 'analyze_message', 'submit_feedback', 'ask_experts']:
            if name.startswith(tool.replace('_', '_')):
                return tool
            simplified = tool.replace('_', '')
            if simplified in name.replace('_', ''):
                return tool
        return ''

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