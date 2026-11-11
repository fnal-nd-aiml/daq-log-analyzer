import json
from datetime import datetime
from typing import Any
from tools.slacktesterbot.slacktester.scenarios.base import ScenarioResult

class JSONReporter:

    def report(self, results: list[ScenarioResult]) -> None:
        passed = [r for r in results if r.passed]
        failed = [r for r in results if not r.passed]
        scenarios: dict[str, dict[str, Any]] = {}
        for result in results:
            if result.scenario not in scenarios:
                scenarios[result.scenario] = {'passed': 0, 'failed': 0, 'tests': []}
            scenario = scenarios[result.scenario]
            scenario['passed'] = int(scenario['passed']) + (1 if result.passed else 0)
            scenario['failed'] = int(scenario['failed']) + (0 if result.passed else 1)
            scenario['tests'].append({'name': result.name, 'passed': result.passed, 'duration_ms': result.duration_ms, 'error': result.error})
        output = {'timestamp': datetime.now().isoformat(), 'summary': {'total': len(results), 'passed': len(passed), 'failed': len(failed), 'duration_ms': sum((r.duration_ms for r in results))}, 'scenarios': scenarios, 'failed_tests': [{'scenario': r.scenario, 'name': r.name, 'error': r.error, 'expected': _serialize(r.expected), 'actual': _serialize(r.actual)} for r in failed]}
        print(json.dumps(output, indent=2))

def _serialize(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return str(value)