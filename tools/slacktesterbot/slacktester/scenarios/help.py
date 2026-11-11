from tools.slacktesterbot.slacktester.scenarios.base import BaseScenario, TestCase

class HelpScenario(BaseScenario):
    name = 'help'
    description = 'Help command parsing and output'

    def get_test_cases(self) -> list[TestCase]:
        return [TestCase(name='help_general', command='help', expected={'error': False, 'text_contains': 'Commands'}, description='General help shows available commands'), TestCase(name='help_investigate', command='help investigate', expected={'error': False, 'text_contains': 'investigate'}, description='Help for investigate command'), TestCase(name='help_message', command='help message', expected={'error': False, 'text_contains': 'message'}, description='Help for message command'), TestCase(name='help_feedback', command='help feedback', expected={'error': False, 'text_contains': 'feedback'}, description='Help for feedback command'), TestCase(name='help_config', command='help config', expected={'error': False, 'text_contains': 'config'}, description='Help for config command'), TestCase(name='help_workbinder', command='help workbinder', expected={'error': False, 'text_contains': 'workbinder'}, description='Help for workbinder command')]

class VersionScenario(BaseScenario):
    name = 'version'
    description = 'Version command output'

    def get_test_cases(self) -> list[TestCase]:
        return [TestCase(name='version_display', command='version', expected={'error': False, 'text_contains': 'Log Analyzer'}, description='Version command shows bot version')]