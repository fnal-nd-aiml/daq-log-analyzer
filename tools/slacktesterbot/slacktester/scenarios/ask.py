from tools.slacktesterbot.slacktester.scenarios.base import BaseScenario, TestCase

class AskScenario(BaseScenario):
    name = 'ask'
    description = 'Ask command parsing'

    def get_test_cases(self) -> list[TestCase]:
        return [TestCase(name='ask_quoted', command='ask "What causes timeout errors in artdaq?"', expected={'error': False, 'parse_result': {'question': 'What causes timeout errors in artdaq?'}}, description='Ask command with quoted question'), TestCase(name='ask_unquoted', command='ask How do I configure the event builder', expected={'error': False, 'parse_result': {'question': 'How do I configure the event builder'}}, description='Ask command with unquoted question'), TestCase(name='ask_empty', command='ask', expected={'error': False, 'parse_result': None}, description='Ask command without question returns None'), TestCase(name='ask_with_special_chars', command='ask "What is the difference between BoardReader and FragmentGenerator?"', expected={'error': False, 'parse_result': {'question': 'What is the difference between BoardReader and FragmentGenerator?'}}, description='Ask command with special characters in question')]