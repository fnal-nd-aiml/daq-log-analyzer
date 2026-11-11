from tools.slacktesterbot.slacktester.scenarios.base import BaseScenario, TestCase

class InvestigateScenario(BaseScenario):
    name = 'investigate'
    description = 'Investigate command parsing'

    def get_test_cases(self) -> list[TestCase]:
        return [TestCase(name='investigate_basic', command='investigate', expected={'error': False, 'parse_result': {'error_line': None, 'context_lines': 60}}, description='Basic investigate command without options (default context=60)'), TestCase(name='investigate_with_error_line', command='investigate error=150', expected={'error': False, 'parse_result': {'error_line': 150, 'context_lines': 60}}, description='Investigate with specific error line'), TestCase(name='investigate_with_context', command='investigate context=50', expected={'error': False, 'parse_result': {'error_line': None, 'context_lines': 50}}, description='Investigate with context lines'), TestCase(name='investigate_with_both_options', command='investigate error=100 context=25', expected={'error': False, 'parse_result': {'error_line': 100, 'context_lines': 25}}, description='Investigate with both error line and context'), TestCase(name='investigate_with_mention', command='<@U_BOT_USER> investigate error=200', expected={'error': False, 'parse_result': {'error_line': 200, 'context_lines': 60}}, description='Investigate command with bot mention')]