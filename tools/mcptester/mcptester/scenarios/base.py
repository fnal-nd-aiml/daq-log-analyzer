from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from tools.mcptester.mcptester.runner import MockTestRunner

@dataclass
class TestCase:
    name: str
    tool: str
    params: dict[str, Any] = field(default_factory=dict)
    expected: dict[str, Any] = field(default_factory=dict)
    description: str = ''

@dataclass
class ScenarioResult:
    name: str
    passed: bool
    duration_ms: int = 0
    error: str | None = None
    expected: Any = None
    actual: Any = None
    scenario: str = ''

class BaseScenario(ABC):
    name: str = 'base'
    description: str = 'Base scenario'

    @abstractmethod
    def get_test_cases(self) -> list[TestCase]:
        pass

    async def run(self, runner: 'MockTestRunner') -> list[ScenarioResult]:
        results = []
        test_cases = self.get_test_cases()
        for test_case in test_cases:
            result = await self.run_test_case(runner, test_case)
            result.scenario = self.name
            results.append(result)
        return results

    async def run_test_case(self, runner: 'MockTestRunner', test_case: TestCase) -> ScenarioResult:
        import time
        start = time.time()
        try:
            tool_result = await runner.call_tool(test_case.tool, test_case.params)
            duration_ms = int((time.time() - start) * 1000)
            if tool_result == '__SKIPPED__':
                return ScenarioResult(name=test_case.name, passed=True, duration_ms=0, error=None, expected=test_case.expected, actual='SKIPPED')
            passed, error, actual = self.validate_result(tool_result, test_case.expected)
            return ScenarioResult(name=test_case.name, passed=passed, duration_ms=duration_ms, error=error, expected=test_case.expected, actual=actual)
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            return ScenarioResult(name=test_case.name, passed=False, duration_ms=duration_ms, error=str(e), expected=test_case.expected, actual=None)

    def validate_result(self, result: Any, expected: dict[str, Any]) -> tuple[bool, str | None, Any]:
        import json
        from tools.mcptester.mcptester.validators import all_items_have_keys, all_items_match, array_length_between, exact_value, nested_value, value_in
        parsed = None
        if isinstance(result, str):
            try:
                parsed = json.loads(result)
            except json.JSONDecodeError:
                if expected.get('json_valid', True):
                    return (False, 'Result is not valid JSON', result[:200])
                parsed = None
        if 'error' in expected:
            if expected['error'] is True:
                if parsed and 'error' in parsed:
                    return (True, None, {'error': parsed['error']})
                return (False, 'Expected error but none found', parsed)
            if expected['error'] is False:
                if parsed and 'error' in parsed:
                    return (False, f"Unexpected error: {parsed['error']}", {'error': parsed['error']})
        if 'contains_keys' in expected:
            required_keys = expected['contains_keys']
            if not parsed:
                return (False, 'Cannot check keys: result is not JSON', result[:200])
            check_obj = parsed
            if isinstance(parsed, list):
                if len(parsed) == 0:
                    pass
                else:
                    check_obj = parsed[0]
            if isinstance(check_obj, dict):
                missing = [k for k in required_keys if k not in check_obj]
                if missing:
                    return (False, f'Missing required keys: {missing}', {'keys': list(check_obj.keys()) if isinstance(check_obj, dict) else None})
        if expected.get('is_array'):
            if not isinstance(parsed, list):
                return (False, 'Expected array but got different type', type(parsed).__name__)
        if 'min_length' in expected:
            min_len = expected['min_length']
            if parsed is None:
                actual_len = len(result) if result else 0
            elif isinstance(parsed, (list, dict, str)):
                actual_len = len(parsed)
            else:
                actual_len = 0
            if actual_len < min_len:
                return (False, f'Length {actual_len} less than minimum {min_len}', {'length': actual_len})
        if 'contains_text' in expected:
            search_text = expected['contains_text']
            if isinstance(result, str) and search_text.lower() not in result.lower():
                return (False, f"Result does not contain '{search_text}'", result[:200])
        if 'exact_values' in expected and parsed and isinstance(parsed, dict):
            for field, exp_val in expected['exact_values'].items():
                ok, err = exact_value(parsed, field, exp_val)
                if not ok:
                    return (False, err, parsed)
        if 'array_length_range' in expected and isinstance(parsed, list):
            min_l, max_l = expected['array_length_range']
            ok, err = array_length_between(parsed, min_l, max_l)
            if not ok:
                return (False, err, {'length': len(parsed)})
        if 'all_items_keys' in expected and isinstance(parsed, list):
            ok, err = all_items_have_keys(parsed, expected['all_items_keys'])
            if not ok:
                return (False, err, parsed)
        if 'all_items_field_equals' in expected and isinstance(parsed, list):
            for field, exp_val in expected['all_items_field_equals'].items():
                ok, err = all_items_match(parsed, field, exp_val)
                if not ok:
                    return (False, err, parsed)
        if 'value_in' in expected and parsed and isinstance(parsed, dict):
            for field, allowed in expected['value_in'].items():
                ok, err = value_in(parsed, field, allowed)
                if not ok:
                    return (False, err, parsed)
        if 'nested_values' in expected and parsed and isinstance(parsed, dict):
            for path, exp_val in expected['nested_values'].items():
                ok, err = nested_value(parsed, path, exp_val)
                if not ok:
                    return (False, err, parsed)
        return (True, None, parsed if parsed else result)