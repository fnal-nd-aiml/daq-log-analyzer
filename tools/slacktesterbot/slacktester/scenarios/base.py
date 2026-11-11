from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from tools.slacktesterbot.slacktester.runner import MockTestRunner

@dataclass
class TestCase:
    name: str
    command: str
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
            cmd_result = await runner.send_command(test_case.command)
            duration_ms = int((time.time() - start) * 1000)
            passed, error, actual = self.validate_result(cmd_result, test_case.expected)
            return ScenarioResult(name=test_case.name, passed=passed, duration_ms=duration_ms, error=error, expected=test_case.expected, actual=actual)
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            return ScenarioResult(name=test_case.name, passed=False, duration_ms=duration_ms, error=str(e), expected=test_case.expected, actual=None)

    def validate_result(self, result: Any, expected: dict[str, Any]) -> tuple[bool, str | None, Any]:
        from tools.slacktesterbot.slacktester.runner import CommandResult
        if not isinstance(result, CommandResult):
            return (False, f'Expected CommandResult, got {type(result).__name__}', result)
        if 'error' in expected:
            if expected['error'] is True:
                if result.error:
                    return (True, None, {'error': result.error})
                return (False, 'Expected error but none occurred', {'error': None})
            if expected['error'] is False:
                if result.error:
                    return (False, f'Unexpected error: {result.error}', {'error': result.error})
        if 'parse_result' in expected:
            actual_parse = result.parse_result
            expected_parse = expected['parse_result']
            if expected_parse is None:
                if actual_parse is not None:
                    return (False, 'Expected parse to fail', {'parse_result': actual_parse})
                return (True, None, {'parse_result': None})
            if actual_parse is None:
                return (False, 'Parse returned None', {'parse_result': None})
            for key, expected_val in expected_parse.items():
                if key not in actual_parse:
                    return (False, f"Missing key '{key}' in parse result", {'parse_result': actual_parse})
                actual_val = actual_parse[key]
                if actual_val != expected_val:
                    return (False, f"Key '{key}': expected {expected_val!r}, got {actual_val!r}", {'parse_result': actual_parse})
        if 'text_contains' in expected:
            if result.text is None:
                return (False, 'Expected text but got None', {'text': None})
            expected_text = expected['text_contains']
            if expected_text.lower() not in result.text.lower():
                return (False, f"Text does not contain '{expected_text}'", {'text': result.text[:200]})
        if 'has_blocks' in expected:
            has_blocks = result.blocks is not None and len(result.blocks) > 0
            if expected['has_blocks'] and (not has_blocks):
                return (False, 'Expected blocks but none present', {'blocks': result.blocks})
            if not expected['has_blocks'] and has_blocks:
                return (False, 'Expected no blocks but found some', {'blocks': result.blocks})
        return (True, None, {'parse_result': result.parse_result, 'text': result.text})