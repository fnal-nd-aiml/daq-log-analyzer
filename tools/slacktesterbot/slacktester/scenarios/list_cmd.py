from tools.slacktesterbot.slacktester.scenarios.base import BaseScenario, TestCase

class ListScenario(BaseScenario):
    name = 'list'
    description = 'List command parsing'

    def get_test_cases(self) -> list[TestCase]:
        return [TestCase(name='list_default', command='list', expected={'error': False, 'parse_result': {'limit': 10}}, description='List command with default limit'), TestCase(name='list_custom_limit', command='list limit=5', expected={'error': False, 'parse_result': {'limit': 5}}, description='List command with custom limit'), TestCase(name='list_large_limit', command='list limit=50', expected={'error': False, 'parse_result': {'limit': 50}}, description='List command with large limit'), TestCase(name='list_limit_one', command='list limit=1', expected={'error': False, 'parse_result': {'limit': 1}}, description='List command with limit of 1')]