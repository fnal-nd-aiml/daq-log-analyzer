import json
from datetime import datetime, timezone
from typing import Any
from tools.mcptester.mcptester.scenarios.base import ScenarioResult

class JSONReporter:

    def report(self, results: list[ScenarioResult]) -> None:
        output = self.to_dict(results)
        print(json.dumps(output, indent=2))

    def to_dict(self, results: list[ScenarioResult]) -> dict[str, Any]:
        passed = [r for r in results if r.passed]
        failed = [r for r in results if not r.passed]
        total_duration = sum((r.duration_ms for r in results))
        scenarios: dict[str, list[ScenarioResult]] = {}
        for result in results:
            if result.scenario not in scenarios:
                scenarios[result.scenario] = []
            scenarios[result.scenario].append(result)
        return {'summary': {'total': len(results), 'passed': len(passed), 'failed': len(failed), 'duration_ms': total_duration, 'success': len(failed) == 0, 'timestamp': datetime.now(timezone.utc).isoformat()}, 'scenarios': {name: self._scenario_to_dict(name, scenario_results) for name, scenario_results in scenarios.items()}, 'failures': [{'scenario': r.scenario, 'test': r.name, 'error': r.error, 'expected': r.expected, 'actual': self._serialize_actual(r.actual)} for r in failed]}

    def _scenario_to_dict(self, name: str, results: list[ScenarioResult]) -> dict[str, Any]:
        passed = sum((1 for r in results if r.passed))
        total = len(results)
        return {'name': name, 'passed': passed, 'total': total, 'success': passed == total, 'tests': [{'name': r.name, 'passed': r.passed, 'duration_ms': r.duration_ms, 'error': r.error} for r in results]}

    def _serialize_actual(self, actual: Any) -> Any:
        if actual is None:
            return None
        if isinstance(actual, (str, int, float, bool)):
            return actual
        if isinstance(actual, (list, dict)):
            return actual
        return str(actual)[:500]