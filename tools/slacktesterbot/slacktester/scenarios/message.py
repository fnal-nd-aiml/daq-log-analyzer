from tools.slacktesterbot.slacktester.scenarios.base import BaseScenario, TestCase

class MessageScenario(BaseScenario):
    name = 'message'
    description = 'Message command parsing'

    def get_test_cases(self) -> list[TestCase]:
        return [TestCase(name='message_quoted', command='message "Error: Connection refused to localhost:5000"', expected={'error': False, 'parse_result': {'message': 'Error: Connection refused to localhost:5000'}}, description='Message command with quoted text'), TestCase(name='message_unquoted', command='message Connection timeout after 30 seconds', expected={'error': False, 'parse_result': {'message': 'Connection timeout after 30 seconds'}}, description='Message command with unquoted text'), TestCase(name='message_with_special_chars', command='message "Error [500]: Internal server error"', expected={'error': False, 'parse_result': {'message': 'Error [500]: Internal server error'}}, description='Message command with special characters'), TestCase(name='message_empty', command='message', expected={'error': False, 'parse_result': None}, description='Message command without text returns None'), TestCase(name='message_multiword', command='message Failed to initialize subsystem due to timeout', expected={'error': False, 'parse_result': {'message': 'Failed to initialize subsystem due to timeout'}}, description='Message command with multiple words')]